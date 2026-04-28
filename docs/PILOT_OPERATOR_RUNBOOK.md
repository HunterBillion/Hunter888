# Operator runbook — TZ-4 пилот (15 тестеров)

> Этот документ для оператора (admin / dev-on-call) который запускает + сопровождает пилот.

## 0. Готовность к старту

### 0.1 Прод состояние перед onboarding

Проверить:
```bash
ssh root@72.56.38.62 "cd /opt/hunter888 && git log --oneline -3"
# Должно быть: B1 + C1 + C3 в трёх последних коммитах

ssh root@72.56.38.62 "cd /opt/hunter888 && docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres bash -c 'psql -U \$POSTGRES_USER -d \$POSTGRES_DB -c \"SELECT version_num FROM alembic_version;\"'"
# Должно быть: 20260427_004
```

### 0.2 Provisioning пилотных аккаунтов

Скрипт нужен — текущий `scripts/seed_*` не покрывает массовое создание manager аккаунтов с нужными ролями. Выполнить вручную через Django shell или admin/users API:

```python
# В контейнере api: docker compose exec api python
from app.database import async_session
from app.models.user import User, UserRole
from app.core.security import hash_password
import asyncio, uuid

async def make_pilot():
    async with async_session() as db:
        # 15 manager + 1 рop + 1 admin
        for i in range(1, 16):
            db.add(User(
                id=uuid.uuid4(),
                email=f"manager{i}@hunter-pilot.test",
                full_name=f"Pilot Manager {i}",
                hashed_password=hash_password("PilotPass2026!"),
                role=UserRole.manager,
                is_active=True,
            ))
        db.add(User(email="rop@hunter-pilot.test", ..., role=UserRole.rop))
        db.add(User(email="admin@hunter-pilot.test", ..., role=UserRole.admin))
        await db.commit()

asyncio.run(make_pilot())
```

После чего раздать креды + URL https://x-hunter.expert.

### 0.3 Smoke-tests checklist (перед раздачей кред)

| Роль | Путь | Ожидаемый результат |
|---|---|---|
| manager | `/training` → выбрать сценарий → "Начать чат" | Сессия открывается, AI отвечает |
| manager | `/center` → выбрать сценарий → "Начать звонок" | Сессия открывается **без 400** (C1 fix) |
| manager | `/clients` → создать клиента → загрузить PDF | Attachment появляется с chip "OCR ожидает" + "Получен" |
| manager | `/home` → "Принять" превью | Имя в превью = имя в pre-call screen |
| rop | `/dashboard?tab=methodology&sub=knowledge_review` | Очередь видна (может быть пуста — это ок) |
| rop | `/dashboard?tab=methodology&sub=ai_quality` | Сводка видна с empty-state "За окно нарушений нет" |
| rop | `/dashboard?tab=activity` → filter "Документы" | Audit log с upload_attachment events если были |
| admin | `/dashboard?tab=system` | Client domain panel + Runtime metrics видны |

Если что-то из smoke checklist падает — **НЕ раздавайте кред**, фиксируйте сначала.

## 1. Daily monitoring (7 дней warn-only window)

### 1.1 Что смотреть каждое утро

```sql
-- Сводка за прошлый день
SELECT
  event_type,
  COUNT(*) AS count,
  COUNT(DISTINCT actor_id) AS unique_actors,
  COUNT(DISTINCT session_id) AS unique_sessions
FROM domain_events
WHERE event_type IN (
    'conversation.policy_violation_detected',
    'persona.conflict_detected',
    'persona.slot_locked',
    'attachment.uploaded',
    'attachment.linked',
    'attachment.duplicate_detected'
)
  AND occurred_at > NOW() - INTERVAL '24 hours'
GROUP BY 1
ORDER BY 2 DESC;
```

```sql
-- Distribution по severity для policy events
SELECT
  payload_json->>'code' AS code,
  payload_json->>'severity' AS severity,
  COUNT(*) AS count
FROM domain_events
WHERE event_type = 'conversation.policy_violation_detected'
  AND occurred_at > NOW() - INTERVAL '24 hours'
GROUP BY 1, 2
ORDER BY 3 DESC;
```

```sql
-- Snapshot mutation_blocked_count > 0 — это bug-сигналы
SELECT
  session_id,
  full_name,
  captured_from,
  captured_at,
  mutation_blocked_count
FROM session_persona_snapshots
WHERE mutation_blocked_count > 0
ORDER BY captured_at DESC;
```

### 1.2 Что считать аномалией

| Метрика | Норма | Алерт |
|---|---|---|
| `near_repeat` violations | 5-15% от total | >40% — too aggressive threshold, тюнить |
| `unjustified_identity_change` | 0-2 в день на 15 manager'ов | >10 — runtime bug |
| `persona.conflict_detected` | 0-2 в день | >5 — runtime path drift, расследовать |
| `attachment.duplicate_detected` | стабильно растёт | sudden spike — multi-tab race |

## 2. Incident playbook

### 2.1 Manager жалуется "AI знает не то имя"

Запустить в shell:
```sql
SELECT
  s.id AS session_id,
  s.user_id,
  s.real_client_id,
  s.created_at,
  sps.full_name AS snapshot_name,
  sps.captured_from,
  sps.mutation_blocked_count,
  mp.full_name AS memory_persona_name,
  mp.version
FROM training_sessions s
LEFT JOIN session_persona_snapshots sps ON sps.session_id = s.id
LEFT JOIN lead_clients lc ON lc.id = s.lead_client_id
LEFT JOIN memory_personas mp ON mp.lead_client_id = lc.id
WHERE s.id = '<session_id>';
```

Diagnosis:
- `snapshot.full_name` ≠ AI говорит → snapshot drift, проверить `mutation_blocked_count`
- `mp.full_name` ≠ `snapshot.full_name` → version mismatch
- `snapshot IS NULL` → D3 capture не сработал, проверить `persona.snapshot_captured` event

### 2.2 Center button даёт 400

Сейчас не должно — закрыто C1 fix. Если воспроизводится:
- Проверить deploy: `ssh root@72.56.38.62 "cd /opt/hunter888 && git log --oneline -1"` должно показать B1 head или новее
- Проверить web container restart: `docker compose ps web` Up < 1 hour после последнего деплоя

### 2.3 Document upload "висит"

```sql
SELECT id, status, ocr_status, classification_status, verification_status, created_at
FROM attachments
WHERE id = '<attachment_id>';
```

Status `received` + `ocr_pending` + `classification_pending` — это default initial state, всё ок. Status `received` + `ocr_pending` через 2 часа — OCR worker не работает (D2 spec оставил это для D6 background workers; их пока нет в проде).

## 3. Day 7 review meeting agenda

После 7 полных дней warn-only:

1. **FP rate per code** — для каждого из 6 кодов:
   - сколько срабатываний всего
   - сколько manual-проверенных оказались ложными
   - if FP < 5% → flip enforce
   - if FP > 5% → тюнить threshold/heuristic, продлить window
2. **Persona drift count** — `mutation_blocked_count > 0` rows. Если 0 — отлично. Если > 0 — runtime bug, фиксить ДО enforce.
3. **Knowledge review queue** — сколько items оператор перевёл в `outdated`. Если 0 — TTL не назначен, knowledge не стареет (норма для пилота). Если > 5 — review SLA процесс работает.
4. **Attachment volume** — сколько upload events. Если 0 — менеджеры не загружают документы (фича не используется или unclear для них).

## 4. Flip enforce mode (после approval)

```bash
ssh root@72.56.38.62
cd /opt/hunter888

# Add env var
echo "CONVERSATION_POLICY_ENFORCE_ENABLED=true" >> .env.prod

# Restart api so settings reload (не нужен rebuild — это runtime read)
docker compose -f docker-compose.yml -f docker-compose.prod.yml restart api
```

Verify:
```bash
docker compose exec api python -c \
  "from app.services.conversation_policy_engine import enforce_enabled; print(enforce_enabled())"
# Должно вывести: True
```

После этого `critical`-severity violations начнут блокировать reply. Менеджеры увидят красный badge на call-screen вместо обычного.

## 5. Backup восстановление (drill для прода)

Делать ДО старта пилота на staging:
```bash
# Backup
docker compose exec postgres pg_dump -U $POSTGRES_USER -d $POSTGRES_DB > /backup/pre-pilot-$(date +%Y%m%d).sql

# Restore drill (на отдельной DB)
createdb hunter_drill
psql hunter_drill < /backup/pre-pilot-20260427.sql

# Verify alembic_version
psql hunter_drill -c "SELECT version_num FROM alembic_version;"
```
