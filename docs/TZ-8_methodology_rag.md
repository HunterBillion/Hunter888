# ТЗ-8 — Per-team methodology RAG (`MethodologyChunk`)

> **Статус:** `implementation-ready spec` (rev 1, 2026-05-01).
> **Приоритет:** `P1 / trust layer + onboarding velocity`.
> **Связь с программой:** опирается на [TZ-1](TZ-1_unified_client_domain_events.md)
> (canonical events), [TZ-3](TZ-3_constructor_scenario_version_contracts.md)
> (publish flow patterns), [TZ-4](TZ-4_attachments_knowledge_persona_policy.md)
> (governance модель `actual / disputed / outdated / needs_review`),
> [TZ-5](TZ-5_input_funnel_parser.md) (wizard import) и **PR #153 / PR-X**
> (foundation для wiki RAG: embedding live-backfill, prompt-injection
> wrapping, team-scoped writes, AST-инвариант).
>
> **Рабочее имя в переписке:** «TZ-6 methodology». Номер `TZ-6` уже
> принадлежит [pre-pilot performance](TZ-6_pre_pilot_performance.md),
> `TZ-7` — [UX polish sweep](TZ-7_ux_polish_sweep.md). Поэтому ТЗ
> получил номер **TZ-8** при сохранении смыслового содержания, на
> которое договорились РАГ-агент + ТЗ-5-агент + product-owner
> (2026-04-30 .. 2026-05-01).

---

## §0. TL;DR

ROП'ы пилотных команд хотят добавлять **командные playbook'и**
(скрипт открытия, обработка возражений, таблица «контр-аргумент → факт»,
тон под персону клиента) и видеть, что AI-коуч и AI-судья реально
их учитывают в следующей же сессии. Сейчас этого пути не существует:

* **`legal_knowledge_chunks`** через wizard ТЗ-5 = факты о законе,
  глобально, через review queue. Не подходит для team-specific
  процедур (один стандарт скрипта на всю платформу — это уничтожит
  специфику бизнеса).
* **`WikiPage`** через ingest_service = автогенерация по сессиям
  конкретного менеджера (per-manager). Не подходит для общего
  командного знания (его пишет ROП, а не extractor сессии).
* **`PersonalityChunk`** = lorebook персонажей-клиентов, не
  методология.

ТЗ-8 закрывает этот пробел: новая таблица **`methodology_chunks`**
(per-team), новый CRUD UI на странице «Команда → Методология»,
4-я ветка в `rag_unified.retrieve_all_context` (`retrieve_methodology_context`),
re-use существующей governance-модели TZ-4 (см. §6 — общая для
`WikiPage` и `MethodologyChunk`, **не две схемы**), wrapping
prompt-injection через тот же контракт `[DATA_START] / [DATA_END]`,
что заведён в PR-X.

Без review queue (см. §7 за обоснованием — methodology≠arena_knowledge).

---

## §1. Граница знаний (НЕ удалять — TZ-5 fixed point)

> Эта секция — **контракт между ТЗ-5 и ТЗ-8**. Любое предложение
> объединить таблицы / расширить `arena_knowledge` на playbook'и /
> сделать `methodology` глобальной по умолчанию — должно начинаться
> с цитирования этой секции и явного TZ §13 ревью. Иначе через
> 3 месяца кто-то «упростит» — и спецификация бизнеса утечёт в
> чужие команды.

| Тип знания | Таблица | Scope | Кто пишет | Через что | Review queue? |
|---|---|---|---|---|---|
| **Факт о законе / процедуре банкротства** (127-ФЗ, цифры, статьи, ВС РФ) | `legal_knowledge_chunks` | global | ROП через wizard ТЗ-5 → confidence ≥ 0.85 → auto-publish (PR #139); иначе — review queue (admin аппрувит) | wizard `POST /rop/imports`, ветка `arena_knowledge` ([scenario_extractor.py](../apps/api/app/services/scenario_extractor.py)) | **Да** — `is_active=False` по умолчанию для confidence < 0.85 |
| **Командный playbook** (скрипт, обработка возражений, тон с клиентом, таблица «контр-аргумент → факт») | **`methodology_chunks`** (NEW) | **per-team** (FK `team_id`) | ROП своей команды через ручную форму на `/dashboard → Методология` | новый router `POST /methodology/chunks` (см. §4) | **Нет** — ROП пишет → сразу `actual` (см. §7 обоснование) |
| **Личная wiki менеджера** (паттерны его сессий, его инсайты) | `wiki_pages` | per-manager | автогенерация (ingest_service / synthesis) + ручной edit ROП'а через PR-X | `PUT /wiki/{id}/pages/{path}` | Нет (autogen)/да (см. §6 governance — `actual` по умолчанию, можно перевести в `disputed`) |
| **Лоребук персонажа клиента** (OCEAN-черты, fallback фразы) | `personality_chunks` | global (per-archetype) | пока admin'ом через seed; миграция в DB-driven отложена в Эпик 4 Арена | seeds / future archetype editor | N/A |

### §1.1. Anti-pattern: «давайте всё в один `LegalKnowledgeChunk`»

Соблазн: «зачем плодить таблицы, у нас же уже есть `legal_knowledge_chunks`,
ROП напишет playbook туда, поставим `category="methodology"` и тег
`team_id` — готово».

Проблемы:

1. **Семантика scope разная.** `legal_knowledge_chunks` = факт, общий
   для всех 15 testers. `methodology_chunks` = playbook одной команды,
   другая команда даже не должна видеть его в коуче, иначе советы
   переплетаются.
2. **Семантика review queue разная.** Юр. факт нельзя ошибиться —
   потому review queue + auto-publish gating. Playbook ROП'а — это
   его экспертиза о собственной команде, ROП *компетентнее* admin'а
   тут, review queue только тормозит итерации.
3. **Семантика governance частично разная.** `actual / disputed /
   outdated` применима к обоим, но `needs_review` для playbook'а
   почти всегда "нет надобности" (см. §6.3) — таблица оптимизирована
   под другой жизненный цикл.
4. **Объём.** До 5000 чанков на команду через год × 50 команд через
   2 года = 250к строк, отдельная таблица помогает индексам и
   планировщику запросов.

Контракт: **legal = факт, methodology = процедура.** Если строка
описывает что-то, что в принципе верно/неверно объективно — это
legal. Если строка описывает «как мы тут делаем» — methodology.

### §1.2. Расширение wizard ТЗ-5 веткой `route_type="methodology"`

В первой версии ТЗ-8 `methodology_chunks` создаются **только** через
ручную форму. Отложено в TZ-8.5:

* добавить ветку `methodology` в classifier `scenario_extractor`;
* при `route_type="methodology"` → `MethodologyChunk` per-team
  (а не `LegalKnowledgeChunk` global);
* при сомнениях classifier ловит на `arena_knowledge` (как сейчас);
* единый bulk import для ROП'а: положить .docx → wizard сам решит
  «факт» vs «процедура».

Этот мост откладываем, потому что (а) classifier'у нужны новые
training labels, (б) нужна явная UX-граница в wizard'е, (в) PR-X
+ TZ-8 v1 закрывают MVP без него.

---

## §2. Цели и не-цели

### §2.1. Цели

* **C1.** ROП пишет playbook → коуч/судья видят его в **следующей
  сессии своей команды** (≤30 секунд P95 от save до search hit).
* **C2.** Изменение чужой команды невозможно (ROП team A ≠ ROП team B
  в одном API endpoint).
* **C3.** Контент не может выполнить prompt-injection — wrapping +
  filter одинаковые с wiki/legal путями (контракт PR-X).
* **C4.** Чанк, который морально устарел («скрипт от позапрошлого
  квартала») можно пометить `outdated` без удаления — он уйдёт из
  RAG, но останется в истории команды.
* **C5.** Методолог / admin видит **эффективность** чанков (которые
  реально fired в дуэлях / сессиях) — переиспользую `ChunkUsageLog`
  через `source_type="methodology"` (новое значение enum'а).
* **C6.** Контракт расширяемости — добавить новый row type в
  RAG-pipeline стоит ≤ 1 файла + 1 dispatch entry (см. §3.5).

### §2.2. Не-цели (отложены)

* `route_type="methodology"` в wizard ТЗ-5 → **TZ-8.5**.
* A/B-тестирование версий playbook'а с измерением win-rate →
  **TZ-9** (потребует версионирование на уровне `MethodologyChunk`,
  как у `ScenarioVersion`).
* Cross-team sharing «admin может промоутнуть playbook команды A
  как best practice для team B» → отдельный flow, **TZ-9**.
* Bot/personality-уровень: «персона клиента сильнее реагирует на X
  при playbook Y» → семантика persona-policy из TZ-4, не наша зона.

---

## §3. Архитектура

### §3.1. Поток данных (happy path)

```
ROП  →  POST /methodology/chunks  →  validate (filter + length)
                ↓
        INSERT INTO methodology_chunks  (status=actual)
                ↓
        commit  →  enqueue_methodology_chunk(id)
                          ↓
                Redis list  arena:embedding:backfill:methodology_chunks
                          ↓
                LiveEmbeddingBackfillWorker (PR-X, расширен на 3-ю очередь)
                          ↓
                UPDATE methodology_chunks SET embedding = ...

→ next coach/training session ──────────────┐
                                            ↓
                              retrieve_all_context
                                            ↓
        ┌───────────────────────────────────┼───────────┬──────────────┐
   retrieve_legal              retrieve_methodology   retrieve_wiki   retrieve_personality
        ↓                              ↓                  ↓                  ↓
  legal_chunks                  methodology_chunks    wiki_pages        personality_*
                              (filter by team_id =
                               session.user.team_id)
        ↓                              ↓                  ↓                  ↓
       [DATA_START]                [DATA_START]       [DATA_START]       (lorebook,
        legal data                methodology data    wiki data         отдельный путь)
       [DATA_END]                  [DATA_END]         [DATA_END]
        └───────────────────────────────┬─────────────┘
                                        ↓
                              UnifiedRAGResult.to_prompt()
                                        ↓
                              system prompt → LLM
```

### §3.2. Модули

Новые:

* **`apps/api/app/models/methodology.py`** — модель `MethodologyChunk`
  (см. §3.3).
* **`apps/api/app/services/rag_methodology.py`** — `retrieve_methodology_context`
  (по аналогии с `rag_wiki.retrieve_wiki_context`, но team-scoped).
* **`apps/api/app/api/methodology.py`** — REST router CRUD + status
  transitions.
* **`apps/api/app/schemas/methodology.py`** — Pydantic схемы.
* **`apps/web/src/components/dashboard/methodology/`** — UI таб
  «Методология».
* **`apps/web/src/lib/api/methodology.ts`** — typed FE-клиент
  (по аналогии с `team_kpi.ts` ТЗ-5).
* **`apps/api/alembic/versions/20260502_001_methodology_chunks.py`** —
  миграция (см. §3.4).
* **`apps/api/tests/test_methodology_*.py`** — функциональные +
  AST-инварианты (см. §10).

Расширяемые (минимально):

* **`apps/api/app/services/rag_unified.py`** — добавить 4-ю задачу
  в `retrieve_all_context`, поле `methodology_context` в
  `UnifiedRAGResult`, блок в `to_prompt()` с `[DATA_START] /
  [DATA_END]` (см. §3.6).
* **`apps/api/app/services/content_filter.py`** — `filter_methodology_context`
  (точная копия `filter_wiki_context` PR-X с семантикой полей).
* **`apps/api/app/services/embedding_live_backfill.py`** — добавить
  `enqueue_methodology_chunk` + `populate_single_methodology_chunk_embedding`,
  третий ключ в `_QUEUE_KEYS` и третья запись в `_DISPATCH`. Контракт
  «один воркер, N очередей» из PR-X **не меняется**.
* **`apps/api/app/models/manager_wiki.py`** — добавить `knowledge_status`
  enum-колонку в `WikiPage` (см. §6.2 — единая governance с `MethodologyChunk`).
  Это закрывает out-of-scope item из PR-X.

### §3.3. Модель `MethodologyChunk`

```python
# apps/api/app/models/methodology.py

class MethodologyKind(str, enum.Enum):
    """Семантическая категория playbook'а — для UI-фильтра + reranker bonus."""
    opener        = "opener"           # скрипт открытия звонка
    objection     = "objection"        # обработка возражений
    closing       = "closing"          # закрытие сделки / next-step
    discovery     = "discovery"        # quals/discovery-вопросы
    persona_tone  = "persona_tone"     # тон под архетип клиента
    counter_fact  = "counter_fact"     # «контр-аргумент → факт»
    process       = "process"          # процедура (handoff, эскалация)
    other         = "other"


class KnowledgeStatus(str, enum.Enum):
    """Унифицированный enum для WikiPage + MethodologyChunk (TZ-4 §8)."""
    actual       = "actual"        # действует, RAG показывает
    disputed     = "disputed"      # помечено сомнительным, RAG показывает с пометкой
    outdated     = "outdated"      # устарело, RAG НЕ показывает
    needs_review = "needs_review"  # auto-flip по TTL (см. §6.3); RAG НЕ показывает


class MethodologyChunk(Base):
    __tablename__ = "methodology_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Ownership / scope
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Content
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body:  Mapped[str] = mapped_column(Text, nullable=False)
    kind:  Mapped[MethodologyKind] = mapped_column(
        Enum(MethodologyKind), nullable=False, index=True,
    )
    tags:  Mapped[list[str]] = mapped_column(JSONB, server_default="[]", default=list)

    # Reranker hints (см. §3.6 — overlap с queryterms даёт boost)
    keywords: Mapped[list[str]] = mapped_column(
        JSONB, server_default="[]", default=list,
    )

    # Governance
    knowledge_status: Mapped[KnowledgeStatus] = mapped_column(
        Enum(KnowledgeStatus), nullable=False,
        default=KnowledgeStatus.actual, server_default="actual", index=True,
    )
    last_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    last_reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # TTL: NULL = бессрочно, иначе after this we auto-flip к
    # needs_review (Lazy auto-flip, см. §6.3 — НЕ к outdated).
    review_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True,
    )

    # Embedding (PR-X-compatible: pgvector(768), Gemini-/local-emb)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(768), nullable=True,
    )
    embedding_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    embedding_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # Audit
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )

    __table_args__ = (
        # ivfflat (TZ-5 fixed point): hnsw откладываем до 5к+ чанков на команду.
        Index(
            "ix_methodology_chunks_emb_ivf",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_methodology_chunks_team_status", "team_id", "knowledge_status"),
        Index("ix_methodology_chunks_team_kind", "team_id", "kind"),
        # Soft uniqueness — нельзя продублировать title в одной команде
        # (это будут конфликтующие playbook'и, неоднозначные для RAG).
        UniqueConstraint("team_id", "title", name="uq_methodology_team_title"),
    )
```

#### §3.3.1. Объяснения по полям

* **`team_id` NOT NULL** — нет понятия «бесхозного» methodology
  чанка. Если ROП без команды (`User.team_id IS NULL`) пытается
  создать — 403 `"ROP is not assigned to a team"` (тот же текст,
  что в `check_wiki_team_access` PR-X для консистентности).
* **`author_id` ON DELETE SET NULL** — увольнение ROП'а не должно
  стирать его playbook'и команды.
* **`title` UNIQUE per `team_id`** — иначе ROП накопит «Скрипт
  открытия (старый)» / «Скрипт открытия (новый)» / «Скрипт
  открытия (правда новый)» — RAG будет тянуть конфликт.
  UNIQUE заставляет ROП'а явно работать со статусом `outdated`.
* **`kind`** — обязателен. Без типа методология превращается в
  свалку «всё в один большой чанк». Reranker (см. §3.6) использует
  `kind` для boost'а под query-intent.
* **`tags` + `keywords`** — `tags` для UI-фильтра (free-form, ROП
  пишет какие хочет), `keywords` для reranker'а (по аналогии с
  `LegalKnowledgeChunk.match_keywords`, см. §3.6).
* **`embedding_model` + `embedding_updated_at`** — провенанс
  эмбеддинга. Когда мигрируем на новую модель (как rev2 для
  legal), сразу видно что не-обновлённое.
* **`review_due_at`** — TZ-4 §8.3.1: auto-flip ТОЛЬКО `actual →
  needs_review`. Переход в `outdated` всегда manual. Без этого
  правила TTL day-of-cutover выкосит всю methodology базу
  команды.

### §3.4. Миграция

```python
# apps/api/alembic/versions/20260502_001_methodology_chunks.py

revision = "20260502_001_methodology_chunks"
# down_revision подставить актуальный head на момент создания PR;
# гарантированно > 20260501_002 (KPI targets от ТЗ-5) — это
# fixed point из TZ-5 review.
down_revision = "<current head as of PR-A>"
```

* Создаёт таблицу `methodology_chunks` с явным `Vector(768)`.
* Создаёт `ivfflat` индекс с `lists=100` (стартовое значение для
  ≤200 строк на команду; tune'нем когда команда перевалит за 5к).
* Создаёт `knowledge_status` enum **в общей схеме** (не специфичной
  для methodology), чтобы тот же тип переиспользовать в WikiPage —
  см. §6.2.
* `wiki_pages.knowledge_status` колонка добавляется тем же
  миграционным файлом (`actual` default). NULL до бэкфилла, после
  бэкфилла NOT NULL — двух-фазная миграция по образцу
  TZ-1 client_domain backfill.

#### §3.4.1. Backfill для wiki_pages

```sql
UPDATE wiki_pages SET knowledge_status = 'actual' WHERE knowledge_status IS NULL;
```

Все существующие страницы → `actual`. Это безопасно: до сих пор
поля не было, эффективно все страницы и так считались актуальными.
Гипотетический ROП-аппрувер может прогнать сессию рецензирования
позднее.

### §3.5. Расширяемость embedding live-backfill

Контракт PR-X: добавление row type = 1 populator + 1 dispatch entry.
Демонстрация:

```python
# apps/api/app/services/embedding_live_backfill.py

_QUEUE_KEY_METHODOLOGY = "arena:embedding:backfill:methodology_chunks"
_QUEUE_KEYS = (_QUEUE_KEY_METHODOLOGY, _QUEUE_KEY_WIKI, _QUEUE_KEY)

async def populate_single_methodology_chunk_embedding(chunk_id: uuid.UUID) -> bool:
    # ...same shape as populate_single_wiki_page_embedding...

_DISPATCH = {
    _QUEUE_KEY: populate_single_legal_chunk_embedding,
    _QUEUE_KEY_WIKI: populate_single_wiki_page_embedding,
    _QUEUE_KEY_METHODOLOGY: populate_single_methodology_chunk_embedding,  # NEW
}
```

Воркер сам подхватит новую очередь без других изменений. Это
прямое подтверждение, что shape «один BLPOP, N очередей» из PR-X
не нужно менять под TZ-8.

### §3.6. RAG retrieval (`retrieve_methodology_context`)

```python
# apps/api/app/services/rag_methodology.py

async def retrieve_methodology_context(
    query: str,
    team_id: uuid.UUID,           # ← обязательный, не optional
    db: AsyncSession,
    top_k: int = 4,
    min_similarity: float | None = None,
    kind_filter: list[MethodologyKind] | None = None,
) -> list[dict]:
    """Per-team RAG over methodology_chunks.

    * Embedding pgvector cosine, как rag_wiki.
    * SQL filter: team_id == :team AND knowledge_status IN ('actual','disputed').
      ('outdated', 'needs_review') исключаются на уровне SELECT.
    * Adaptive threshold по образцу rag_wiki:
        <5 чанков на команду  → 0.15
        5-20                  → 0.25
        21-100                → 0.32
        >100                  → 0.40
    * Reranker по образцу wiki §3 PR-X:
        + 0.04 за каждое keyword overlap с query
        + 0.06 если kind ∈ {opener, objection, closing} (high-value)
        − 0.04 если status == 'disputed' (показываем, но даун-весом)
    * Возвращает list[dict] с полями: title, body[:500], kind, tags,
      knowledge_status, similarity, rerank_score.
    """
```

Бюджет токенов в `rag_unified.BUDGET`:

```python
BUDGET = {
    "training": {"legal": 700, "personality": 500, "wiki": 250, "methodology": 350},
    "coach":    {"legal": 500, "personality": 250, "wiki": 350, "methodology": 600},
    "quiz":     {"legal": 1000, "personality": 0, "wiki": 200, "methodology": 0},
}
```

* Coach получает наибольший methodology-бюджет — это его ключевая
  ценность («скажи как правильно по нашей методике»).
* Quiz=0 — викторина проверяет знание факта, не методики.
* Total ≤ 1700 токенов остаётся (8к-context safe).

#### §3.6.1. Wrapping в `to_prompt()`

```python
def to_prompt(self) -> str:
    parts = []
    if self.legal_context:
        parts.append("ПРАВОВАЯ БАЗА (127-ФЗ):\n" + self.legal_context)
    if self.methodology_context:
        parts.append(
            "МЕТОДОЛОГИЯ КОМАНДЫ:\n"
            "[DATA_START]\n" + self.methodology_context + "\n[DATA_END]"
        )
    if self.wiki_context:
        parts.append(
            "ПЕРСОНАЛЬНАЯ WIKI МЕНЕДЖЕРА:\n"
            "[DATA_START]\n" + self.wiki_context + "\n[DATA_END]"
        )
    return "\n\n".join(parts) if parts else ""
```

Тот же контракт, что в PR-X. AST-инвариант (см. §10.2) расширяется
на `methodology_context` — читается только в `to_prompt`.

### §3.7. Контекст вызова — где взять `team_id`

* **Training session** (`ws/training.py`): `session.user.team_id` —
  у тренировки есть юзер, у юзера — команда.
* **AI Coach** (`services/ai_coach.py`): юзер коуча из request scope.
* **PvP duel / arena** (`services/pvp_judge.py`): дуэль =
  два юзера. Используем **team_id игрока, чью реплику оцениваем**
  (когда оценивается реплика A — RAG показывает methodology team A).
  Если игроки из разных команд — каждый получает свой playbook
  при оценке своей реплики. Это симметрично с logic'ой ChunkUsageLog,
  где source_user_id уже фиксируется.
* **Quiz** (`services/knowledge_quiz.py`): `methodology=0` в budget
  → не вызываем retriever.

### §3.8. Edge cases

* **ROП без команды** (`team_id IS NULL`): retriever возвращает
  `[]`. UI показывает «методология недоступна — обратись к admin'у».
  Это симметрично логике PR-X для `check_wiki_team_access`.
* **Команда удалена** (`teams.id` row deleted): `ON DELETE CASCADE`
  на `methodology_chunks.team_id` → чанки команды улетают вместе.
  Это намеренно: бесхозная methodology не имеет смысла.
* **Embedding ещё NULL** (свежий чанк, воркер не отработал):
  retriever пропускает строку (`WHERE embedding IS NOT NULL`),
  это согласовано с rag_wiki/rag_legal. UX: «новый playbook
  появится в коуче через несколько секунд».

---

## §4. REST API

### §4.1. Endpoints

```
GET    /methodology/chunks
GET    /methodology/chunks/{chunk_id}
POST   /methodology/chunks
PUT    /methodology/chunks/{chunk_id}
DELETE /methodology/chunks/{chunk_id}
PATCH  /methodology/chunks/{chunk_id}/status   {status: actual|disputed|outdated|needs_review}
GET    /methodology/chunks/{chunk_id}/usage    (телеметрия — топ-сессий где fired)
```

### §4.2. Authn / authz матрица

| Endpoint | admin | rop (same team) | rop (other team) | manager (same team) | manager (other) |
|---|---|---|---|---|---|
| `GET /chunks` (list, ?team_id=X) | ✅ any team | ✅ свою | ❌ 403 | ✅ свою (read-only) | ❌ 403 |
| `GET /chunks/{id}` | ✅ | ✅ если same team | ❌ 403 | ✅ если same team (read-only) | ❌ 403 |
| `POST /chunks` | ✅ за любую team_id | ✅ только свою team_id | ❌ 403 | ❌ 403 | ❌ 403 |
| `PUT /chunks/{id}` | ✅ | ✅ если same team | ❌ 403 | ❌ 403 | ❌ 403 |
| `DELETE /chunks/{id}` | ✅ | ✅ если same team | ❌ 403 | ❌ 403 | ❌ 403 |
| `PATCH /status` | ✅ | ✅ если same team | ❌ 403 | ❌ 403 | ❌ 403 |
| `GET /usage` | ✅ | ✅ если same team | ❌ 403 | ✅ если same team (read-only) | ❌ 403 |

Реализуется через новую FastAPI dependency `require_methodology_access(chunk_id_or_team_id, mode='read'|'write')`,
по аналогии с `check_wiki_team_access` PR-X. Формат ошибок —
тот же текст «Cannot modify a wiki outside your team» → «Cannot
modify methodology outside your team» для консистентности UX.

### §4.3. POST request shape

```json
POST /methodology/chunks
{
  "title": "Открытие звонка после скан-кода",
  "body":  "1. Здороваешься, представляешься.\n2. ...\n",
  "kind":  "opener",
  "tags":  ["скан-код", "тёплый лид"],
  "keywords": ["скан", "QR", "лид", "первый звонок"]
}

→ 201 Created
{
  "id": "9f...",
  "title": "Открытие звонка после скан-кода",
  "knowledge_status": "actual",
  "version": 1,
  "team_id": "...",
  "created_at": "...",
  "embedding_pending": true   ← live-backfill ещё не отработал
}
```

### §4.4. Validation

* `title` 1..200 chars, после strip(); UNIQUE per team_id.
* `body` 10..10000 chars (10к = два экрана текста, потом разбиваем на чанки).
* `kind` ∈ enum.
* `tags`, `keywords` ≤ 20 элементов, каждый ≤ 60 chars.
* **На write — НЕ применяем jailbreak-фильтр** (см. §5 — wrapping
  на read как в PR-X). На write только PII-strip и length cap.

---

## §5. Безопасность: prompt-injection

### §5.1. Контракт

Тот же, что в PR-X для wiki: **wrapping на read**, не sanitize на write.

* `filter_methodology_context(chunks: list[dict])` в
  `content_filter.py` — копия `filter_wiki_context` с переименованием
  field-меток (`methodology_title`, `methodology_body`, `methodology_tags`).
* Применение в `rag_unified` ДО формирования `methodology_context`.
* Wrapping `[DATA_START] / [DATA_END]` в `to_prompt`.
* Системная инструкция в `llm.py:2354` (canonical consumer маркеров)
  уже умеет понимать обёртку, расширений не требует.

### §5.2. AST-инвариант

См. §10.2 — расширяем `test_wiki_invariants.py` (или клонируем как
`test_methodology_invariants.py`, см. §10.2 за обоснованием выбора).

---

## §6. Governance — единая модель для WikiPage + MethodologyChunk

> **Это TZ-5 fixed point #4.** Не делать две схемы. Один enum,
> одно правило TTL, одна логика SQL-фильтра.

### §6.1. `KnowledgeStatus` enum (общий)

Объявляется в **`apps/api/app/models/knowledge_status.py`** (новый
маленький файл) и импортируется обеими таблицами:

```python
class KnowledgeStatus(str, enum.Enum):
    actual       = "actual"
    disputed     = "disputed"
    outdated     = "outdated"
    needs_review = "needs_review"
```

Это **тот же** enum, который [TZ-4 §8](TZ-4_attachments_knowledge_persona_policy.md)
ввёл для `legal_knowledge_chunks` — но физически TZ-4 enum жил в
service-модуле `knowledge_governance.py` и до WikiPage не дошёл.
TZ-8 переезжает enum в `models/`, импортируется всеми тремя
таблицами (`legal_knowledge_chunks`, `wiki_pages`, `methodology_chunks`).

### §6.2. WikiPage добавляет `knowledge_status`

```python
# apps/api/app/models/manager_wiki.py — diff:
class WikiPage(Base):
    ...
    knowledge_status: Mapped[KnowledgeStatus] = mapped_column(
        Enum(KnowledgeStatus), nullable=False,
        default=KnowledgeStatus.actual, server_default="actual", index=True,
    )
    last_reviewed_at: Mapped[datetime | None] = ...
    last_reviewed_by: Mapped[uuid.UUID | None] = ...
    review_due_at:    Mapped[datetime | None] = ...
```

`rag_wiki.retrieve_wiki_context` фильтрует `WHERE knowledge_status
IN ('actual','disputed')` — так же как methodology в §3.6. Это
закрывает out-of-scope item PR-X (#4 governance) **без двух схем**.

### §6.3. TTL auto-flip (TZ-4 §8.3.1 carry-over)

* Auto-flip ТОЛЬКО `actual → needs_review`, через scheduled task
  `services/knowledge_review_policy.py` (новый). Запускается раз
  в час, выбирает строки `WHERE review_due_at < now() AND
  knowledge_status='actual'`, делает batch UPDATE.
* `needs_review` строки **не** показываются в RAG (фильтр §3.6).
* Переход `needs_review → actual` (пере-аппрув) или `→ outdated`
  (списать) — **только manual через PATCH /status** с заполнением
  `last_reviewed_by`.
* Это буквально copy-paste правила TZ-4 §8.3.1 — мы не изобретаем
  новое.

### §6.4. UI surface для статуса

* На карточке чанка / страницы wiki — chip со статусом (color-coded:
  зелёный `actual`, жёлтый `disputed`, серый `outdated`, оранжевый
  `needs_review`).
* «3 точки» меню → действия: «Пометить устаревшим» / «Оспорить» /
  «Подтвердить актуальность».
* PATCH `/status` принимает `{status, note?}`; при `disputed` /
  `outdated` `note` обязателен (контекст для будущих ревьюеров).

### §6.5. События (`DomainEvent`)

По образцу TZ-4 §8.4:

* `methodology.chunk.created` (aggregate=team)
* `methodology.chunk.updated`
* `methodology.chunk.status_changed`  (payload: from, to, by, note)
* `methodology.chunk.deleted`
* `wiki.page.status_changed`  (новое — раньше только manual_edit писался)

Эмиттер: `app/services/event_bus.emit_domain_event` — канонический
helper TZ-1 §3 (через который должны идти все события). AST-инвариант
TZ-1 проверяет это; не нарушаем.

---

## §7. Почему **нет review queue** — обоснование (TZ-5 fixed point #2)

> **Не удалять.** Через 2-3 итерации кто-нибудь предложит «да зачем,
> давайте как arena_knowledge через review queue». Это попытка
> унифицировать без понимания почему различие осмысленно.

### §7.1. Семантика arena_knowledge ≠ methodology

| Аспект | `arena_knowledge` (legal) | `methodology` (playbook) |
|---|---|---|
| Природа | Объективный факт | Командная договорённость |
| Кто прав в споре | Закон / суд (можно проверить) | ROП своей команды (он эксперт) |
| Цена ошибки | Высокая (юр. ошибка → штраф клиенту, репутация платформы) | Низкая (плохой скрипт → ROП через неделю поправит) |
| Скорость итерации | Раз в год (закон не меняется ежемесячно) | Раз в неделю (скрипт под новый сегмент клиентов) |
| Кто аппрувит | Admin платформы (юр. экспертиза) | ROП своей команды (бизнес-контекст) |

### §7.2. Что review queue ломает в methodology

1. **Темп.** ROП хочет потестить новый скрипт за 30 минут после
   утренней планёрки. Review queue добавляет лаг ≥ часа (admin
   разбирает раз в день). За это время менеджер уже успел провести
   3 звонка по старому скрипту.
2. **Кто аппрувит?** Admin платформы Hunter888 не знает специфику
   бизнеса команды. Если admin аппрувит «всегда yes» — review
   queue декоративная (защита нулевая, лаг реальный). Если admin
   правда вникает — он бутылочное горлышко на N команд.
3. **Цена ошибки низкая.** Плохой playbook не сжигает данные, не
   нарушает закон, не ломает RAG. Хуже = коуч даёт бесполезный
   совет в одной сессии. ROП увидит, поправит, статус `outdated`.
   Это нормальный цикл, а не аварийный.

### §7.3. Что заменяет review queue

* **`team_id` ownership** (§4.2) — структурно невозможно навредить
  чужой команде.
* **`disputed` статус** (§6) — soft signal от другого ROП'а той же
  команды или admin'а. RAG продолжает показывать (понижая ранг),
  но видно что есть несогласие.
* **`outdated` статус** — soft delete без потери истории.
* **`ChunkUsageLog`** (§8.1) — telemetry: какие чанки реально
  используются и помогают; «пустые» чанки видны методологу за
  неделю.
* **Admin override** — `admin` может PATCH-нуть статус любого
  чанка (включая «устарелое» команды), но в норме не должен
  лезть.

### §7.4. Что делать если поведение ROП'а злоупотребляет

В пилоте 15 testers — никаких злоупотреблений не ожидается, ROП'ы
сами заинтересованы в качественной методологии. Если на проде
выяснится что **конкретный** ROП дёргает чанки в боевые, не для
команды, а для эксперимента — фикс не review queue, а **soft rate
limit** (≤ N изменений/час на одного ROП'а) или явный **«draft»
флажок** (см. open question §13.1). Не ставим до факта.

---

## §8. Telemetry / эффективность

### §8.1. ChunkUsageLog — расширение

`ChunkUsageLog.source_type` сейчас — enum-string с значениями
`training_session, pvp_duel, quiz, between_call`. Добавляем
`methodology_retrieval` (логируется при retrieve), и используем
существующий `record_chunk_outcome` для post-judge оценки
(answer_correct boolean) — точно как PR #143 для legal.

`ChunkUsageLog.chunk_id` остаётся UUID; добавляем колонку
`chunk_kind` (`'legal'|'wiki'|'methodology'`) чтобы JOIN в правильную
таблицу не зависел от ORM-наследования. Миграция в той же ревизии.

### §8.2. Дашборд для методолога / ROП'а

UI на странице «Методология» → таб «Эффективность»:

* **Топ-чанков за 7д / 30д** (retrieval_count DESC)
* **% правильных ответов** на каждый чанк (`answer_correct=true rate`)
* **Не использовался ≥ 7 дней** (зомби-чанк, подсказка пометить outdated)
* **Disputed без ответа > 14 дней** — задача для ROП'а команды

Фронт пере-использует API из PR #143 (та же модель `ChunkUsageLog`).

### §8.3. Метрики

```
methodology_retrieval_total{team_id, kind, status}    counter
methodology_retrieval_returned{team_id}              histogram (returned chunks per query)
methodology_chunk_usage_total{team_id, kind, source} counter
methodology_status_changes_total{team_id, from, to}  counter
methodology_review_overdue                            gauge (rows past review_due_at)
```

По образцу метрик Эпик 1 Арены — формат и naming совместимый.

---

## §9. UI

### §9.1. Навигация

* На `/dashboard` (Команда) — добавить таб **«Методология»** рядом
  с существующим **Wiki**.
* Доступ: `admin`, `rop`, `manager` (read-only).

### §9.2. Сцены

| Сцена | Описание | Компонент |
|---|---|---|
| **Список чанков** | Карточки с title, kind, status-chip, фильтры (team / kind / status / search) | `MethodologyList.tsx` |
| **Создание / правка** | Форма с полями (§4.3) + preview сразу как будет выглядеть в коуче | `MethodologyEditor.tsx` |
| **Эффективность** | Таблица с retrieval_count / answer_correct / last_used_at | `MethodologyEffectiveness.tsx` |
| **История чанка** | Версии + кто менял статус и когда | `MethodologyHistory.tsx` |

Layout — единая страница с табами «Список / Эффективность»
(как в `WikiDashboard.tsx`).

### §9.3. Empty state

Первый чанк команды: онбординг-карточка с 3 примерами
(opener / objection / closing). ROП может «применить шаблон» →
prefill формы с realistic-текстом, потом редактировать.

### §9.4. Permissions UI

Если ROП без команды — показываем баннер:
> «Тебе не назначена команда. Methodology — командная фича.
> Обратись к admin'у.»
> [Запросить назначение в команду] (mailto / встроенная форма)

---

## §10. Тесты

### §10.1. Функциональные (`tests/test_methodology_*.py`)

* `test_methodology_crud.py` — POST/PUT/DELETE/PATCH через async client.
* `test_methodology_authz.py` — матрица §4.2 (8 кейсов rop-cross-team
  variations + admin + manager).
* `test_methodology_rag.py` — `retrieve_methodology_context` filter
  by team / status / kind.
* `test_methodology_filter.py` — `filter_methodology_context` jailbreak
  / PII / length (по образцу test_wiki_foundation.py).
* `test_methodology_status_transitions.py` — TTL auto-flip (`actual
  → needs_review` only), manual `disputed`/`outdated`.
* `test_methodology_concurrency.py` — `asyncio.gather` параллельные
  POST одного title (UNIQUE collision), параллельные PATCH status —
  по [§4.1 CLAUDE.md](../apps/api/CLAUDE.md) обязательный паттерн.

### §10.2. AST-инвариант

Расширяем `test_wiki_invariants.py` → переименовываем в
`test_rag_invariants.py` (общий guard для всех 3-х путей), либо
клонируем `test_methodology_invariants.py`. Решение: **расширяем**.
Один файл проще читается и помнится; allow-list растёт линейно
(2-3 имени), не разрастается до неуправляемого.

```python
# test_rag_invariants.py — после переименования

ALLOWED_RAG_CONTEXT_READERS = {
    "app/services/rag_unified.py",
}

# Single test that walks for both wiki_context and methodology_context.
def test_rag_context_strings_only_read_inside_to_prompt():
    for attr in ("wiki_context", "methodology_context"):
        ...
```

Файл ходит по `app/` и проверяет, что `UnifiedRAGResult.wiki_context`
**и** `UnifiedRAGResult.methodology_context` не читаются нигде кроме
allow-list. Маркеры `[DATA_START]/[DATA_END]` — тот же allow-list
с расширением `app/services/rag_methodology.py` если ему понадобится
рендерить (по проекту — нет, форматирует `to_prompt`, но добавляем
`rag_methodology.py` в allow-list если внутренний debug-render
понадобится).

### §10.3. Blocking CI scope

Добавить в `.github/workflows/ci.yml` после существующих:

```
            tests/test_methodology_crud.py \
            tests/test_methodology_authz.py \
            tests/test_methodology_rag.py \
            tests/test_methodology_filter.py \
            tests/test_methodology_status_transitions.py \
            tests/test_methodology_concurrency.py \
            tests/test_rag_invariants.py
```

(`test_wiki_invariants.py` уже в blocking scope из PR-X — после
переименования меняем строку в ci.yml в ту же ревизию.)

---

## §11. План PR'ов (incremental)

> Каждый PR должен пройти `git diff origin/main..HEAD --stat`
> red-flag check ([§1 CLAUDE.md](../apps/api/CLAUDE.md)) перед
> push. Каждый PR — green CI (PR-CI + post-merge на main).

### PR-A — Foundation: enum, миграция, governance carry-over для WikiPage

* `models/knowledge_status.py` — общий enum.
* `models/methodology.py` — модель `MethodologyChunk` (только
  декларация, без endpoints).
* `models/manager_wiki.py` — добавить `knowledge_status` в WikiPage.
* Migration `20260502_001_methodology_chunks_and_wiki_status` —
  таблица + ivfflat + WikiPage governance columns + backfill
  `actual`.
* Updates `rag_wiki.retrieve_wiki_context` — фильтр
  `WHERE knowledge_status IN ('actual','disputed')`.
* `tests/test_methodology_model.py` (smoke), регресс
  `test_wiki_foundation.py`.

**Риск:** PR-A меняет SELECT в `rag_wiki` — миграция должна быть
атомарной (alter + backfill + NOT NULL — в той же ревизии),
иначе на момент после миграции, до бэкфила, retriever возвращает 0
строк (NULL не матчит ни actual ни disputed).

### PR-B — REST API + RAG retrieval

* `services/rag_methodology.py` — `retrieve_methodology_context`.
* `services/content_filter.py` — `filter_methodology_context`.
* `services/embedding_live_backfill.py` — третья очередь.
* `services/rag_unified.py` — четвёртая ветка + budget + wrapping
  в `to_prompt`.
* `api/methodology.py` — CRUD endpoints.
* `schemas/methodology.py` — Pydantic.
* `core/deps.py` — `require_methodology_access` helper.
* AST-инвариант: переименование `test_wiki_invariants.py` →
  `test_rag_invariants.py` + расширение на `methodology_context`.
* Functional + concurrency тесты (см. §10).
* Update CI blocking scope (§10.3).

### PR-C — UI

* `MethodologyList.tsx`, `MethodologyEditor.tsx`,
  `MethodologyEffectiveness.tsx`, `MethodologyHistory.tsx`.
* Tab integration в `WikiDashboard.tsx` (или клон `MethodologyDashboard.tsx` —
  decision point §13.2).
* Typed FE-клиент `lib/api/methodology.ts`.

### PR-D — Telemetry + dashboard

* `ChunkUsageLog.chunk_kind` колонка + миграция.
* `methodology_retrieval` source_type в logger.
* Эффективность UI tab (§8.2).
* Prometheus метрики (§8.3).

### PR-E — Status transitions + TTL policy

* `services/knowledge_review_policy.py` — scheduled task для TTL
  auto-flip.
* PATCH `/status` endpoint.
* UI кнопки disputed / outdated / acknowledged.
* `wiki.page.status_changed` events (closes legacy gap).

### PR-F (опц., после пилотной обратной связи) — wizard ветка

* `route_type="methodology"` в `scenario_extractor`.
* UI: при загрузке файла в wizard ТЗ-5 → опция «это методология
  моей команды».
* Соответствующий extractor-prompt (отличный от arena_knowledge —
  выделяет процедуры, не факты).

---

## §12. Совместимость / миграция

* **Existing WikiPage rows** → `knowledge_status='actual'` (§3.4.1).
  Никаких разрушительных изменений.
* **PR-X (#153) compatibility**: TZ-8 расширяет, не ломает контракты:
  `to_prompt` добавляет блок methodology поверх legal+wiki, AST-
  инвариант расширяется, embedding_live_backfill принимает 3-ю
  очередь без изменений сигнатур.
* **TZ-4 governance**: enum переезжает из service в models, но
  значения остаются. Существующий код, импортирующий
  `knowledge_governance.KnowledgeStatus`, должен быть обновлён в
  PR-A: один импорт-rewrite, тесты ловят.
* **Wizard ТЗ-5**: НЕ ТРОГАЕМ в v1. `arena_knowledge` ветка
  остаётся как есть. Расширение → PR-F.

---

## §13. Open questions (нужны ответы перед PR-A)

### §13.1. «Draft» флажок?

Стоит ли иметь промежуточный статус `draft` (видим только автору,
не попадает в RAG, ROП может полировать перед actual)?

* **За:** ROП хочет накидать черновик «между делом», не выкладывая
  команде сырое.
* **Против:** добавляет 5-й статус, расширяет state-machine, без
  явного запроса от пилотных testers.

**Рекомендация:** **не делаем сейчас.** Если ROП хочет драфт — пишет
в `body` пометку «WIP» и сразу `outdated`-ит когда готов уйти в
прод. Если на пилоте всплывёт реальный запрос — добавим в TZ-9.

### §13.2. UI: отдельный `MethodologyDashboard.tsx` или таб в `WikiDashboard.tsx`?

* **Отдельный** проще для будущих расширений (analytics, эффективность,
  history) — много экранов, не вмещаются под одной табкой.
* **Таб в Wiki** меньше дублирует scaffold (header, breadcrumbs).

**Рекомендация:** **отдельный `MethodologyDashboard.tsx`**, навигация
через таб в общей шапке `/dashboard`. Wiki и Methodology — два
параллельных пути с разной семантикой, разделение карты помогает
ROП'у не путать «моя личная wiki» и «командная методология».

### §13.3. UNIQUE per-team title — правильное ограничение?

Альтернатива — UNIQUE по `(team_id, kind, title)`: можно иметь
одинаковое имя для opener и для closing. Но это редкий валид-кейс,
и UI должен помогать с уникальным именем (пресет-шаблоны §9.3).

**Рекомендация:** UNIQUE `(team_id, title)` — проще, тренирует
гигиену именования.

### §13.4. Reranker bonus за `kind` — как pin'ить под query intent?

В §3.6 я сделал «boost для opener/objection/closing». Это эвристика.
Лучше было бы: classifier над query, который определяет intent
(«user spоросил про возражение цены» → boost objection).

**Рекомендация:** сейчас — **простая эвристика по kind** (5 строк
кода). Если retrieval quality на пилоте окажется низкой, добавляем
intent-classifier (LLM → enum) в TZ-9 как separate enrichment.

---

## §14. Out of scope (deferred)

* **TZ-8.5** — `route_type="methodology"` в wizard ТЗ-5 (PR-F).
* **TZ-9** — версионирование чанков с A/B-тестированием
  (как `ScenarioVersion`); cross-team sharing «admin промоут как
  best practice»; intent-classifier для reranker'а; «draft» флажок
  если запросят.
* **HNSW migration** — оставляем `ivfflat lists=100` пока команда
  не превысит 5к чанков; тогда параметризируем `lists` или
  переходим на HNSW.
* **Persona-aware methodology** («для archetype `aggressive_boss`
  показывай methodology counter_fact`») — TZ-4.5 (persona memory)
  смежная зона; решим после стабилизации обоих.
* **Bulk import / export** методологии (CSV/.docx) — пока через
  ручную форму; bulk откладываем до запроса от пилотных команд.

---

## §15. Acceptance criteria

PR-A до PR-E считаются готовы когда:

1. ROП команды A создаёт чанк → следующая training-сессия менеджера
   команды A видит его в RAG (P95 ≤ 30с).
2. ROП команды B → НЕ видит чанков команды A в своём UI и в своём
   coach-RAG (проверяется и UI, и сессией; обе зоны).
3. Чанк со статусом `outdated` → НЕ surfaces в RAG (SELECT filter).
4. Чанк со статусом `disputed` → surfaces в RAG с пониженным
   рангом, видно что disputed (UI chip).
5. AST-инвариант падает на тестовом PR'е, который читает
   `methodology_context` вне `to_prompt` или эмитит DATA_START
   маркер вне allow-list.
6. `filter_methodology_context` блокирует injection / PII / overlong
   как `filter_wiki_context` PR-X (test_methodology_filter.py).
7. `asyncio.gather` 5 параллельных POST одинакового title в одну
   команду → ровно 1 успешен, 4 получают 409 Conflict (UNIQUE).
8. PR-CI зелёный, post-merge CI на `main` зелёный, full pre-existing
   blocking scope (≥255 cases) не упал.
9. Smoke на стейдже / проде после деплоя — ROП реально создаёт
   чанк через UI и видит его эффект в коуче.

---

## §16. История правок

* **rev 1, 2026-05-01** — РАГ-агент: первичная версия после
  scope-confirmation от ТЗ-5 (4 fixed points). Параллельно с PR
  #153 (PR-X foundation), не зависит от его merge.

---

## §17. Ссылки

* PR-X / PR #153 — foundation: https://github.com/HunterBillion/Hunter888/pull/153
* TZ-1 §3 — canonical event helper: [TZ-1](TZ-1_unified_client_domain_events.md)
* TZ-3 §7.3.1 — auto-publish-on-update footgun: [TZ-3](TZ-3_constructor_scenario_version_contracts.md)
* TZ-4 §8 — knowledge governance: [TZ-4](TZ-4_attachments_knowledge_persona_policy.md)
* TZ-5 — input funnel parser (wizard): [TZ-5](TZ-5_input_funnel_parser.md)
* PR #139 / #143 / #146 — Arena Content→Arena эпик (auto-publish,
  chunk-usage telemetry, live embedding backfill — переиспользуем
  все три инфраструктуры).
