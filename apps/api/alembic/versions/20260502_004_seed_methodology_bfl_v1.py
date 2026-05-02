"""Seed methodology_chunks v1 — БФЛ playbook (18 chunks).

Revision ID: 20260502_004
Revises: 20260502_003
Create Date: 2026-05-02

Why this exists
---------------

The 2026-05-02 prod audit (FIND-004) found ``methodology_chunks`` empty —
the entire TZ-8 RAG infrastructure (PR #155-#163, #172, #173) was shipped
but never populated. AI coach + AI client roleplay paths fan out to a
zero-row corpus and the methodology branch silently contributes
"" to every prompt. The fix is data, not code.

This migration seeds 18 hand-authored chunks for the БФЛ (банкротство
физических лиц) playbook, attached to the team that has active managers
in the pilot (``Отдел продаж`` — UUID hard-coded below for predictability;
the team itself is created elsewhere). All chunks use ``author_id=NULL``
to mark them as system-seeded; ROPs editing them later will set their own
author_id via the REST PATCH endpoint.

Content basis
-------------

Authored from a 4-source research sweep on 2026-05-02 (RU 127-FZ legal
substance + RU consultative-sales playbooks + EN frameworks Sandler/SPIN/
Challenger/Gap + Gong/Chorus call-analytics) with web-search verification
of legal facts current as of May 2026 (НК ст. 333.21 — должник освобождён
от пошлины с 2024; ФЗ-218 ст. 7 — БКИ хранение 7 лет; ФЗ-474 от 04.08.2023
действует с 03.11.2024 — МФЦ 25к-1млн ₽ + новые категории доступа).

Cross-references with adjacent corpora are deliberately one-directional:

  • ``law_article`` references in body cite specific article numbers
    (``ст. 213.4``, ``ст. 446 ГПК``) but never quote the article TEXT —
    that lives in ``legal_knowledge_chunks`` (375 rows) and is retrieved
    in parallel via ``rag_unified``. Duplicating costs the 1700-token
    RAG budget for nothing.

  • Archetype keywords use exact ``ArchetypeCode`` enum values
    (``desperate``, ``misinformed``, ``skeptic``, ``salary_arrest``,
    ``pre_court``) so the methodology reranker (+0.04 per keyword hit
    in ``rag_methodology.py:163``) fires when a coach query mentions
    those archetypes.

  • Emotion keywords use exact ``EmotionState`` enum values
    (``cold``, ``hostile``, ``guarded``).

Idempotent
----------

UNIQUE(team_id, title) collision on rerun → SKIP. The migration uses
``ON CONFLICT DO NOTHING`` so re-applying on a partially-seeded DB is
a no-op.

Embeddings
----------

Inserted with ``embedding=NULL``. Two paths populate them:

  1. ``embedding_live_backfill`` queue — but this migration runs OUTSIDE
     the API process, so the live worker is not invoked (no Redis push).
  2. ``embedding_backfill.populate_methodology_chunk_embeddings`` cold
     sweep — added in the same PR as this migration. Runs on next API
     lifespan startup and picks up the 18 NULL rows.

Until the cold sweep completes (seconds after deploy), the 18 chunks
are invisible to RAG (``rag_methodology.py:139`` filters
``embedding IS NOT NULL``). This is acceptable: they were invisible
before the migration too.
"""
from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260502_004"
down_revision: Union[str, Sequence[str], None] = "20260502_003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Target team — `Отдел продаж` on prod. The team has admin/rop/manager users
# attached (per audit 2026-05-02), so retrieval-time chunk_usage_logs FK
# constraints will hold. If this UUID does not exist (fresh dev DB), the
# migration logs a warning and inserts nothing — the seed is a no-op
# rather than an error, mirroring the legal-seed early-return pattern.
TARGET_TEAM_ID = "ebe86f55-2d13-43f3-9fa7-837e509e47b2"


# 18 chunks — schema mirrors ``MethodologyChunkCreate`` Pydantic model.
# Body length 350-500 chars to fit inside the rag_unified BUDGET window
# (training=350 tokens, coach=600, with body[:500] truncation in
# rag_methodology.py:154).
SEED_CHUNKS: list[dict] = [
    {
        "title": "Тёплый входящий: подтверждение заявки + бридж к боли",
        "kind": "opener",
        "body": (
            "ТРИГГЕР: клиент оставил заявку с сайта/рекламы, перезваниваем в "
            "первые 30 минут. ПРИНЦИП: Specificity disarms — конкретика из "
            "заявки доказывает что менеджер не робот; ложный выбор по времени "
            "снимает «я занят». СКРИПТ: «Иван, добрый день, [Имя], юрист по "
            "банкротству. Вы оставили заявку — у вас [N] кредитов на [Y] "
            "тысяч. Я перезвонил задать 5-7 уточняющих, понять подходит ли "
            "вам процедура. 7-10 минут. Удобно сейчас или перезвонить через "
            "час?»"
        ),
        "tags": ["funnel:lead", "must-know", "methodology-v1"],
        "keywords": ["opener", "incoming", "warm-lead", "specificity", "заявка", "перезвон"],
    },
    {
        "title": "Возврат после «я подумаю»",
        "kind": "opener",
        "body": (
            "ТРИГГЕР: 2-3 день после первого звонка, клиент сказал «подумаю»; "
            "нужно вернуться без давления. ПРИНЦИП: Loop-closing + обещание "
            "ценности, а не продажи. Снимает оборону «опять продают». СКРИПТ: "
            "«Иван, [Имя] из [Компания], обещал перезвонить по вашей ситуации. "
            "Я не для давления — к нашему прошлому разговору добавилась одна "
            "вещь, которую вам полезно знать перед решением. Минута есть?»"
        ),
        "tags": ["funnel:lead", "must-know", "methodology-v1"],
        "keywords": ["opener", "followup", "return-call", "value-frame", "подумаю"],
    },
    {
        "title": "Pain Funnel Sandler: 5-шаговый спуск к боли",
        "kind": "discovery",
        "body": (
            "ТРИГГЕР: после opener, на минутах 2-7 разговора. Нельзя продавать "
            "пока клиент сам не назвал боль 3 раза разными словами. ПРИНЦИП: "
            "Sandler Pain Funnel — клиент в долговом стрессе купит, только "
            "если боль им же verbalised. Сухие цифры долга не работают. "
            "СКРИПТ: 1) «Расскажите подробнее» → 2) «Когда последний раз "
            "приставы списали — пример» → 3) «Как давно длится» → 4) «Что уже "
            "пробовали» → 5) «Как это ощущается дома при детях/жене»."
        ),
        "tags": ["funnel:qualification", "must-know", "methodology-v1"],
        "keywords": ["discovery", "pain", "sandler", "funnel", "пристав", "семья", "эмоция"],
    },
    {
        "title": "SPIN Implication: цена бездействия",
        "kind": "discovery",
        "body": (
            "ТРИГГЕР: клиент признал боль, но колеблется или говорит «само "
            "рассосётся». ПРИНЦИП: SPIN Implication (Rackham) — пусть клиент "
            "сам спроектирует свою катастрофу, не менеджер. Self-stated "
            "сильнее рассказанного менеджером. СКРИПТ: «Если ничего не менять "
            "— что через 6 месяцев? Когда банки подадут в суд и приставы "
            "начнут списывать 50% с зарплаты, как рассчитываетесь по аренде/"
            "ипотеке? Что произойдёт с семьёй?»"
        ),
        "tags": ["funnel:qualification", "must-know", "methodology-v1"],
        "keywords": ["discovery", "implication", "spin", "цена-бездействия", "magical_thinker", "procrastinator"],
    },
    {
        "title": "Clio Triage: есть ли уже суд / арест / приставы",
        "kind": "discovery",
        "body": (
            "ТРИГГЕР: первые 3 минуты разговора. Меняет приоритет: emergency "
            "vs advisory. Не задал — клиент может потерять квартиру между "
            "консультацией и подачей. ПРИНЦИП: Clio 4-stage intake — triage "
            "первый, продажа последняя. Подача заявления вводит мораторий "
            "(127-ФЗ ст. 213.11) — стоп всем взысканиям. СКРИПТ: «Иван, до "
            "того как продолжим — есть ли уже: повестка в суд, арест счетов, "
            "удержания с зарплаты, исп.производство? Это меняет срочность "
            "подачи.»"
        ),
        "tags": ["funnel:qualification", "must-know", "crisis-flow", "methodology-v1"],
        "keywords": ["discovery", "triage", "salary_arrest", "pre_court", "court_notice", "приставы", "срочность"],
    },
    {
        "title": "Quick legal qualification: подходит ли клиент под судебное БФЛ",
        "kind": "discovery",
        "body": (
            "ТРИГГЕР: после первичной боли, до озвучивания цены. 5 фактов за "
            "3 минуты — отсекают «не наш клиент» от «работаем». ПРИНЦИП: "
            "чек-лист по 127-ФЗ ст. 213.4: общая сумма, длительность "
            "просрочки, имущество, сделки за 3 года, поручительство. Без "
            "этого любое предложение ошибочно. СКРИПТ: 1) общая сумма; "
            "2) месяцев просрочки; 3) единственное жильё/ипотека/вторая "
            "недвижимость; 4) дарили/продавали имущество за 3 года; "
            "5) поручитель по чужим долгам?"
        ),
        "tags": ["funnel:qualification", "must-know", "methodology-v1"],
        "keywords": ["discovery", "qualification", "127-фз", "213.4", "checklist", "просрочка", "имущество"],
    },
    {
        "title": "Подходит ли клиент под МФЦ-внесудебное (ФЗ-474)",
        "kind": "discovery",
        "body": (
            "ТРИГГЕР: клиент намекает на «бесплатный» вариант или сам спросил "
            "про МФЦ. ПРИНЦИП: ФЗ-474 от 04.08.2023, поправки в силе с "
            "03.11.2024. 3 пути допуска: (1) долг 25к-1млн ₽ + оконченное ИП "
            "«нет имущества»; (2) пенсионер/получатель пособий с ИП ≥ 1 года; "
            "(3) ИП ≥ 7 лет. СКРИПТ: «Сумма долга в диапазоне 25к-1млн? "
            "Окончено ИП по статье «нет имущества»? Если нет — вы пенсионер "
            "или ИП ≥ года/семи лет? Если попадает — МФЦ. Если нет — суд.»"
        ),
        "tags": ["funnel:qualification", "must-know", "mfc-path", "methodology-v1"],
        "keywords": ["discovery", "mfc", "внесудебное", "фз-474", "пенсионер", "пособие"],
    },
    {
        "title": "«Дорого, у меня нет денег»",
        "kind": "objection",
        "body": (
            "ТРИГГЕР: клиент назвал «дорого» в первые 30 секунд после "
            "озвучивания цены договора. Самое частое и логичное возражение в "
            "БФЛ. ПРИНЦИП: reframe из суммы в денежный поток + аргумент "
            "моратория: рассрочка юристу защищена от приставов, в отличие от "
            "платежей банку. Sandler negative reverse — согласись что денег "
            "нет, переведи в рассрочку. СКРИПТ: «Понимаю — если бы у вас были "
            "свободные 150 тысяч, вы бы не звонили. Рассрочка: первый платёж "
            "X, дальше Y/мес, защищены мораторием. Какая сумма реальна?»"
        ),
        "tags": ["funnel:meeting", "must-know", "methodology-v1"],
        "keywords": ["objection", "price", "дорого", "рассрочка", "мораторий", "negotiator", "shopper"],
    },
    {
        "title": "«Подумаю / посоветуюсь с супругой»",
        "kind": "objection",
        "body": (
            "ТРИГГЕР: клиент уходит «обсудить дома» — классический вежливый "
            "отказ после Pain Funnel. ПРИНЦИП: «Не убирай, а вооружай» — не "
            "борись с уходом, дай инструмент решения. Превращает отсрочку в "
            "follow-up с конкретным артефактом, к которому можно вернуться. "
            "СКРИПТ: «Конечно, такие решения принимаются вдвоём. Чтобы вам "
            "было что обсудить — пришлю расчёт по ситуации: какие долги "
            "списываются, что с квартирой, сколько по времени. На какую почту "
            "удобно?»"
        ),
        "tags": ["funnel:meeting", "must-know", "methodology-v1"],
        "keywords": ["objection", "podumayu", "wife", "supruga", "decision-maker", "couple", "deflector"],
    },
    {
        "title": "«Сам справлюсь / есть знакомый юрист»",
        "kind": "objection",
        "body": (
            "ТРИГГЕР: клиент пытается отделаться low-commitment-альтернативой. "
            "ПРИНЦИП: Pain Funnel + квалификация знакомого без атаки на него; "
            "FUD на риск ошибки в заявлении (отказ в списании за "
            "недобросовестность — 127-ФЗ ст. 213.28 п.4). СКРИПТ: «Знакомый "
            "юрист сколько дел по банкротству вёл? Банкротство у них основная "
            "специализация или среди прочего? Спросите его про сделки за 3 "
            "года и поручительство — два места где новички теряют дело и "
            "клиент остаётся с долгами.»"
        ),
        "tags": ["funnel:qualification", "methodology-v1"],
        "keywords": ["objection", "self-help", "сам", "знакомый", "shopper", "selfhelp", "213.28"],
    },
    {
        "title": "«Боюсь потерять единственное жильё»",
        "kind": "objection",
        "body": (
            "ТРИГГЕР: первый страх клиента после слова «банкротство». Для "
            "misinformed архетипа — ключевой триггер. ПРИНЦИП: ст. 446 ГПК + "
            "Постановление Пленума ВС РФ № 48 от 25.12.2018: единственное "
            "неипотечное жильё — иммунитет. Сначала факт, потом эмпатия — не "
            "наоборот. СКРИПТ: «Это самый частый страх. По закону единственное "
            "жильё не забирают — ст. 446 ГПК и Пленум ВС № 48. Исключение "
            "одно: квартира в ипотеке. У вас ипотека на эту квартиру?»"
        ),
        "tags": ["funnel:qualification", "must-know", "fear-bust", "methodology-v1"],
        "keywords": ["objection", "fear", "жильё", "квартира", "ипотека", "ст446", "пленум-48", "misinformed"],
    },
    {
        "title": "«Лучше пойду в МФЦ, там бесплатно»",
        "kind": "objection",
        "body": (
            "ТРИГГЕР: клиент сравнивает с альтернативой и пытается уйти из "
            "судебной воронки. ПРИНЦИП: признать → отсечь по фактам → "
            "перевести в свою плоскость. Не критиковать МФЦ (давление = уход), "
            "показать что путь не подходит лично ему. СКРИПТ: «МФЦ — рабочий "
            "вариант если долг 25к-1млн и оконченное ИП. По вашему долгу "
            "[сумма] МФЦ откажет, и вы потеряете 6 месяцев пока получите "
            "отказ. У вас, по фактам которые озвучили, путь только судебный "
            "— давайте по нему.»"
        ),
        "tags": ["funnel:qualification", "mfc-path", "methodology-v1"],
        "keywords": ["objection", "mfc", "альтернатива", "negotiator", "shopper", "competitor", "сравнение"],
    },
    {
        "title": "«У конкурентов под ключ 80к»",
        "kind": "objection",
        "body": (
            "ТРИГГЕР: ценовая война, клиент сравнивает на стадии решения. "
            "ПРИНЦИП: «Сравни честно» — приглашение к детальному сравнению "
            "ломает ценовое возражение, потому что у дешёвого конкурента нет "
            "того что включено у вас. Не атаковать конкурента — атаковать "
            "неполноту его пакета. СКРИПТ: «80к — это либо подача без "
            "сопровождения каждого заседания, либо демпинг новичков. Спросите "
            "у них: депозит ФУ 25к включён? публикации в ЕФРСБ и Коммерсанте? "
            "Готов сравнить договоры пункт-в-пункт.»"
        ),
        "tags": ["funnel:meeting", "methodology-v1"],
        "keywords": ["objection", "competitor", "price", "shopper", "negotiator", "80", "сравнение"],
    },
    {
        "title": "«А вы гарантируете списание долгов?»",
        "kind": "objection",
        "body": (
            "ТРИГГЕР: клиент в страхе провала, требует гарантии. Дать "
            "гарантию = ст. 779 ГК + риск ст. 14.7 КоАП («введение в "
            "заблуждение»). ПРИНЦИП: честность как продающий аргумент + "
            "down-sell на бесплатный анализ дела (микро-обязательство по "
            "Чалдини). Гарантировать судебное решение — никто не вправе. "
            "СКРИПТ: «Гарантию суда не даёт ни один юрист — это введение в "
            "заблуждение. Перед договором делаем бесплатный анализ: долги, "
            "сделки за 3 года, имущество. Видим риск отказа — говорим прямо "
            "и не берёмся. Запишемся?»"
        ),
        "tags": ["funnel:qualification", "compliance:no-guarantee", "methodology-v1"],
        "keywords": ["objection", "guarantee", "гарантия", "trust", "risk", "skeptic", "litigious"],
    },
    {
        "title": "Миф: «банкротство = клеймо на всю жизнь»",
        "kind": "counter_fact",
        "body": (
            "ТРИГГЕР: клиент произнёс «я буду банкротом», «потом везде "
            "откажут», «это пятно навсегда». ПРИНЦИП: 127-ФЗ ст. 213.30 + "
            "ФЗ-218 ст. 7. Конкретные ограничения с понятными сроками — не "
            "«пожизненно». Запись в БКИ хранится 7 лет от последнего "
            "изменения (с 2022, ранее 10). СКРИПТ: «Это миф. Ограничения по "
            "ст. 213.30: 5 лет — раскрывать факт банкротства при кредите, "
            "5 лет — запрет на собственное банкротство, 3 года — нельзя "
            "руководить ООО, 10 лет — для банка. БКИ хранит 7 лет.»"
        ),
        "tags": ["myth-bust", "must-know", "methodology-v1"],
        "keywords": ["counter_fact", "миф", "клеймо", "последствия", "213.30", "фз-218", "бки", "ashamed"],
    },
    {
        "title": "Миф: «спишут абсолютно все долги»",
        "kind": "counter_fact",
        "body": (
            "ТРИГГЕР: менеджер обещает 100% списание ИЛИ клиент сам ожидает "
            "обнулить всё. Опасно для compliance. ПРИНЦИП: 127-ФЗ ст. 213.28 "
            "п. 5-6 — закрытый перечень исключений. Не списываются: алименты, "
            "вред жизни/здоровью, моральный вред, текущие, субсидиарка, долги "
            "от мошенничества. Завышенное ожидание = жалоба после процедуры. "
            "СКРИПТ: «Списываются необеспеченные потребительские. Не "
            "списываются: алименты, вред здоровью, моральный вред, "
            "субсидиарка по ООО, долги от обмана. Что-то из исключений у "
            "вас есть?»"
        ),
        "tags": ["myth-bust", "must-know", "compliance:no-guarantee", "methodology-v1"],
        "keywords": ["counter_fact", "миф", "100", "все-долги", "исключения", "213.28", "алименты", "compliance"],
    },
    {
        "title": "Summary close + альтернативный выбор",
        "kind": "closing",
        "body": (
            "ТРИГГЕР: после обработки 2-3 возражений, клиент сигналит "
            "готовность (вопросы по срокам/первому шагу). НЕ давить, дать "
            "выбор «как именно двигаемся». ПРИНЦИП: Summary первая → "
            "assumptive close через слот → loss aversion сноской. Жёсткий "
            "клоуз убивает trauma sale. Альтернативный выбор снимает порог "
            "решения. СКРИПТ: «Подытожу: долг X, списывается Y, единственное "
            "неипотечное жильё сохраняется, рассрочка Z, срок 8-10 мес. "
            "Договор пришлю сегодня. Удобнее вторник или четверг?»"
        ),
        "tags": ["funnel:close", "must-know", "methodology-v1"],
        "keywords": ["closing", "summary", "assumptive", "alternative-choice", "loss-aversion"],
    },
    {
        "title": "Тон с desperate / overwhelmed / ashamed: якорь покоя",
        "kind": "persona_tone",
        "body": (
            "ТРИГГЕР: клиент в панике, плачет, путается в словах, говорит «не "
            "знаю что делать» — большинство звонков в БФЛ. ПРИНЦИП: эмпатия "
            "без жалости. Темп ↓15%, паузы 2-3 сек после ключевых вопросов. "
            "3F (Feel-Felt-Found). Никогда «легко», «быстро», «без проблем» "
            "— обесценивание тревоги. Никогда «должник», «банкрот» в первые "
            "минуты — стигмы. СКРИПТ: «Понимаю как вы себя сейчас чувствуете "
            "(feel) — наши клиенты тоже не знали что делать (felt) — и "
            "обнаруживали что путь понятен (found).»"
        ),
        "tags": ["tone", "must-know", "methodology-v1"],
        "keywords": ["persona_tone", "desperate", "overwhelmed", "ashamed", "anxious", "crying", "frozen", "3f", "темп"],
    },
]


def _team_exists(team_id: str) -> bool:
    """Verify the target team is present before inserting chunks."""
    conn = op.get_bind()
    return bool(
        conn.execute(
            sa.text("SELECT 1 FROM teams WHERE id = CAST(:tid AS uuid)"),
            {"tid": team_id},
        ).fetchone()
    )


def upgrade() -> None:
    if not _team_exists(TARGET_TEAM_ID):
        # Local dev / fresh DB: target team not seeded yet. Skip silently —
        # an empty methodology corpus is the same state we started in,
        # and rerunning later (after the team is created) is a no-op via
        # ON CONFLICT DO NOTHING.
        op.execute(
            sa.text(
                "SELECT 'methodology seed skipped: target team "
                + TARGET_TEAM_ID + " not present'"
            )
        )
        return

    # Note: every parameter that maps to a non-VARCHAR column needs an
    # explicit ``CAST(... AS <type>)`` in the SQL — ``op.execute`` plus
    # ``text(...).bindparams(...)`` strips type info, so asyncpg sees
    # VARCHAR for every bind, and Postgres refuses to coerce VARCHAR
    # → uuid / jsonb implicitly. The original 20260502_004 PR shipped
    # without the ``team_id::uuid`` cast and crashed the API container
    # on startup (alembic migration loop) — see hotfix in this revision.
    insert_sql = sa.text(
        """
        INSERT INTO methodology_chunks (
            id, team_id, author_id, title, body, kind,
            tags, keywords, knowledge_status, version,
            created_at, updated_at
        ) VALUES (
            gen_random_uuid(),
            CAST(:team_id AS uuid),
            NULL,
            :title, :body, :kind,
            CAST(:tags AS jsonb),
            CAST(:keywords AS jsonb),
            'actual', 1, now(), now()
        )
        ON CONFLICT (team_id, title) DO NOTHING
        """
    )

    for chunk in SEED_CHUNKS:
        op.execute(
            insert_sql.bindparams(
                team_id=TARGET_TEAM_ID,
                title=chunk["title"],
                body=chunk["body"],
                kind=chunk["kind"],
                tags=json.dumps(chunk["tags"], ensure_ascii=False),
                keywords=json.dumps(chunk["keywords"], ensure_ascii=False),
            )
        )


def downgrade() -> None:
    # Targeted DELETE by (team_id, title) — leaves any user-authored
    # chunks for the team intact. Cascading chunk_usage_logs FK was
    # dropped in 20260502_002, so logs become orphan-but-findable rows;
    # they're filtered by ``is_deleted`` at read time.
    delete_sql = sa.text(
        "DELETE FROM methodology_chunks "
        "WHERE team_id = CAST(:team_id AS uuid) AND title = :title"
    )
    for chunk in SEED_CHUNKS:
        op.execute(
            delete_sql.bindparams(
                team_id=TARGET_TEAM_ID,
                title=chunk["title"],
            )
        )
