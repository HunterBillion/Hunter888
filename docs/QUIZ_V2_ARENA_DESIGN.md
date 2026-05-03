# Quiz Arena v2 — Grader/Explainer Split (Path A)

> Design doc + coordination thread.
> Author: claude (worktree `funny-hugle-a50ca9`).
> Status: **DRAFT — pending review**.
> Last updated: 2026-05-03.

## 1. Why this exists

The PvP solo-quiz arena (`/pvp/quiz/[id]`, served by `apps/api/app/ws/knowledge.py`) has six observable failures in production (screenshots dated 2026-05-03):

| # | Symptom | Real cause (verified by code audit) |
|---|---|---|
| 1 | `✗13` on a 10-question quiz | `_handle_answer` has no re-entry guard — repeat submits / timer races each bump `state.incorrect += 1` independently. No `answer_id` to dedup on. |
| 2 | Question number jumps `5 → 1` mid-quiz | State lives in WS-coroutine RAM. Reconnect → fresh `_SoloQuizState` from 0, transcript still shows old verdicts. |
| 3 | Correct answer judged `НЕВЕРНО` | `AI_EXAMINER_PROMPT` (knowledge_quiz.py:104) hard-rules односложные answers as `is_correct=false`. Prompt design bug. |
| 4 | Two verdict bubbles per answer | `quiz.feedback.verdict` creates an empty bubble, then `quiz.feedback` does `addMessage` again instead of merging (page.tsx:269). |
| 6 | "Не удалось получить разбор" beside a real verdict | LLM-streamed verdict + final fallback both rendered as separate bubbles. No idempotency by `answer_id`. |
| 7/8 | `personality_comment` / `evaluate_answer_v2` dead code | Decorative leftovers from prior refactor. |

External research confirmed: every mature quiz product (Kahoot, Quizizz, Gimkit, Slido, Mentimeter) does **not** stream the verdict from an LLM. Verdict is a deterministic match against a pre-known answer key. LLM, when used, runs **after** the verdict — only for the explanation.

We are doing something categorically unusual. Path A aligns us with the standard pattern.

## 2. Production snapshot (2026-05-03)

- 375 `legal_knowledge_chunks` (100% with embeddings) — the question source
- 18 `methodology_chunks` (also embedded)
- Last 14 days: 19 sessions (`blitz` 11 / `free_dialog` 4 / `themed` 4), 68 answers
- ArenaBus stream `arena:bus:global` depth = 0 (`arena_bus_dual_write_enabled = False`)
- `use_quiz_v2 = False` (narrative theatre wired but inactive)
- Prod RELEASE_SHA: `9b76a628` (matches main tip)

**Implication for Path A:** there is no static question bank. Questions are generated on-the-fly from `legal_knowledge_chunks`. Answer-keys must be either (a) generated alongside the question at chunk → question time (one LLM call produces both), or (b) generated on first-show and cached per `chunk_id`. We pick **(a)** with a one-shot backfill for the 375 existing chunks.

## 3. Decision: extend the existing `quiz_v2/` package

`apps/api/app/services/quiz_v2/` (1874 LOC, 11 files) already exists. **It is NOT the same scope as Path A**, but it is the same product (knowledge-quiz, ws/knowledge.py, 127-FZ). It owns narrative theatre (case + beat + personality + TTS); it does not touch grading.

**WS hooks already in place** (knowledge.py:443/665/842/1087): start, shape, record, end. Path A's grader/explainer slot in at the same call sites — no parallel package.

New code lives **inside** `quiz_v2/`:

| File | Role | Status |
|---|---|---|
| `quiz_v2/grader.py` | Deterministic answer matcher (exact / synonyms / regex / keyword / embedding) | NEW |
| `quiz_v2/answer_keys.py` | ORM model + loader for `quiz_v2_answer_keys` table | NEW |
| `quiz_v2/explainer.py` | Post-verdict LLM-streamed explanation + personality | NEW |
| `quiz_v2/events.py` | Server-issued `answer_id`; ArenaBus publish helpers | NEW |
| `quiz_v2/memory.py` | EXTEND: per-question answer-token state + idempotency keys (same Redis namespace `quiz_v2:session:{sid}:*`) | EXTEND |
| `quiz_v2/integration.py` | EXTEND: add `submit_answer_v2` / `verdict_for_v2` siblings to existing 4 hooks | EXTEND |

**Unchanged:** `cases.py`, `cases_seed.json`, `beats.py`, `ramp.py`, `presentation.py`, `tier_b.py`, `tier_c.py`, `voice.py`, `rag_grounding.py`, `skeletons_seed.json`. They are narrative, not grading.

## 4. Reuse map (DO NOT REINVENT)

The user's coordination context flagged six merged epics. Verified each in repo and prod:

| Concept | Existing module | Path A consumes via |
|---|---|---|
| Redis Streams pub/sub | `services/arena_bus.py` (`publish(ArenaEvent)`), `arena_envelope.py` (`ArenaEvent.create(...)`) | `events.py` calls `arena_bus.publish(...)` for every emitted event |
| AuditLogConsumer | `services/arena_bus_consumer.py` | Bus events automatically logged — no new audit code |
| Feature flag for bus dual-write | `arena_bus_dual_write_enabled` (config.py:463) | A0 wires through this flag; turning it ON in prod is a separate ops step |
| correlation_id contextvar | `core/correlation.py` (`bind_correlation_id`) | Every WS task entry-point binds `str(session_id)` (mirror `ws/pvp.py` pattern) |
| Prometheus metrics | `services/arena_metrics.py` (8 metrics) | Add 2 new metrics scoped to grader: `QUIZ_V2_GRADE_LATENCY` (Histogram, labels: strategy, outcome), `QUIZ_V2_VERDICT_DEDUP_HITS` (Counter, labels: reason). Register in same module. |
| WS dedup pattern | `ws/pvp.py:1814` (`server_msg_id` / `client_msg_id`) | Copy verbatim into the new event handler |
| Redis state abstraction | `services/arena_redis.py` (`ArenaRedis` class, 624 LOC) | Reuse `acquire_game_lock` / `release_game_lock` for re-entry guard around `submit_answer`. Session state extends `quiz_v2/memory.py` — separate concern from `arena_redis` (matches/players). |
| Embedding similarity | `services/rag_methodology.py:51` (`retrieve_methodology_context`), `embedding_live_backfill.py` | For embedding-based grading, the cleanest surface is a NEW narrow helper `match_answer_by_embedding(text, expected_text, threshold=0.85)` in `grader.py`. Internally calls existing pgvector pool via the same async session that powers `retrieve_*_context`. No generic similarity primitive exists today; we add one only if Q1 confirms it. |
| Security helpers | `api/rop.py:857/888` (`_filter_session_by_caller_team`, `_scope_check_session`) | Any new REST endpoint (e.g. `GET /quiz/v2/answer-keys/:chunk_id` for ops dashboard) goes through these |
| `chunk_usage_logs` | `models/rag.py:176` (`source_type='quiz'`) | `submit_answer_v2` writes one log row per answer. No parallel analytics table. |
| `judge.degraded` event | `ws/pvp.py:1309` | Mirror pattern for `quiz_v2.grader.degraded` (when embedding fallback fires) |

## 5. Wire protocol (target state)

### 5.1. Server → client events

| Event | Payload | Idempotent on |
|---|---|---|
| `quiz_v2.question.shown` | `{question_id, index, total, prompt, hint?, time_limit, answer_id_template?}` | `question_id` |
| `quiz_v2.answer.accepted` | `{answer_id, question_id, received_at}` | `answer_id` |
| `quiz_v2.verdict.emitted` | `{answer_id, correct, score_delta, expected_answer, article_ref, fast_path, strategy}` | `answer_id` |
| `quiz_v2.explanation.streamed` | `{answer_id, seq, chunk}` | append-only by `(answer_id, seq)` |
| `quiz_v2.explanation.completed` | `{answer_id, full_text, personality_comment}` | `answer_id` |
| `quiz_v2.score.updated` | `{correct, incorrect, skipped, score, current_question}` | replace state |
| `quiz_v2.session.expired` | `{reason}` | terminal |

### 5.2. Client → server events

| Event | Payload | Notes |
|---|---|---|
| `quiz_v2.session.start` | `{session_id?, quiz_id, mode}` | If `session_id` present and Redis state alive → resume |
| `quiz_v2.answer.submit` | `{question_id, content, client_msg_id?}` | Server allocates `answer_id = uuid_v4()`, echoes `client_msg_id` for client-side dedup |
| `quiz_v2.answer.skip` | `{question_id}` | |

**Old events** (`quiz.feedback.verdict`, `quiz.feedback.chunk`, `quiz.feedback`) remain on the wire under `use_quiz_v2 = False`. A0 introduces dual-emit so the new client can render new events while old client keeps working.

## 6. Data model

### 6.1. New table `quiz_v2_answer_keys`

```sql
CREATE TABLE quiz_v2_answer_keys (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id        UUID NOT NULL REFERENCES legal_knowledge_chunks(id) ON DELETE CASCADE,
    question_hash   TEXT NOT NULL,           -- stable hash of generated question prompt
    expected_answer TEXT NOT NULL,           -- canonical reference answer
    match_strategy  TEXT NOT NULL,           -- 'exact' | 'synonyms' | 'regex' | 'keyword' | 'embedding'
    match_config    JSONB NOT NULL DEFAULT '{}',  -- per-strategy config
    synonyms        TEXT[] NOT NULL DEFAULT '{}',
    article_ref     TEXT,                    -- "ст. 213.11 127-ФЗ"
    generated_by    TEXT NOT NULL,           -- model id
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed        BOOLEAN NOT NULL DEFAULT FALSE,
    reviewed_at     TIMESTAMPTZ,
    UNIQUE (chunk_id, question_hash)
);
CREATE INDEX ix_quiz_v2_answer_keys_chunk ON quiz_v2_answer_keys(chunk_id);
```

**Why `(chunk_id, question_hash)`:** one chunk can spawn multiple distinct questions over time. The hash anchors the key to the exact prompt phrasing. If question generation drifts, we can detect orphan keys and regenerate.

### 6.2. Redis session state (extends `quiz_v2/memory.py`)

```
quiz_v2:session:{sid}:answers          → existing list[{q_idx, correct, rung, chunk_id}]  (kept)
quiz_v2:session:{sid}:case             → existing case payload                            (kept)
quiz_v2:session:{sid}:personality      → existing                                         (kept)
quiz_v2:session:{sid}:total            → existing                                         (kept)
quiz_v2:session:{sid}:answer:{aid}     → NEW: {question_id, submitted_text, verdict_json, ts, status}
quiz_v2:session:{sid}:pending_aid      → NEW: re-entry guard (single answer in flight)
quiz_v2:session:{sid}:explanation:{aid}:chunks → NEW: list of streamed chunks (replay buffer)
quiz_v2:session:{sid}:explanation:{aid}:done   → NEW: bool sentinel
```

TTL stays at 2h (existing). Re-entry guard uses `arena_redis.acquire_game_lock(session_id, ttl=30s)`.

## 7. Grader strategies (deterministic, no LLM in hot path)

In order — first match wins:

1. **exact** — normalize (lowercase, trim, ё→е, strip punctuation, collapse whitespace) → string equality
2. **synonyms** — same normalization → membership in `synonyms[]` (precomputed)
3. **regex** — pattern from `match_config.regex` (e.g. `\d+\s*(дн|месяц|лет)`)
4. **keyword** — `match_config.keywords` with `mode: "all" | "any"`
5. **embedding** — cosine similarity ≥ `match_config.threshold` (default 0.85). Uses pgvector via `legal_knowledge_chunks.embedding`-style helpers (existing pool). Marks event with `strategy: "embedding"` and `degraded: true` if neither exact nor synonyms matched.

Misclassification budget: log every embedding-only match to `chunk_usage_logs` with `retrieval_method = "embedding"` for offline review.

## 8. Phases

| Phase | Scope | LOC est. | Days | PR |
|---|---|---|---|---|
| **A0** | Feature flag `quiz_v2_grader_enabled` (default OFF). Skeleton: empty `grader.py`, `events.py`, `answer_keys.py`. Wire dual-emit hook in knowledge.py (calls noop when flag off). | ~200 | 1 | 1 |
| **A1** | Migration `quiz_v2_answer_keys`. One-shot LLM backfill script for 375 chunks (one job, ~$5). Manual review queue (admin endpoint, `_scope_check_session` gated). | ~400 | 2 | 1 + alembic |
| **A2** | `grader.py` full implementation. Unit tests: ~50 cases across 5 strategies. Includes embedding strategy via existing pgvector. | ~500 | 2 | 1 |
| **A3** | `memory.py` EXTEND: answer-token state, replay buffer, re-entry guard via `arena_redis.acquire_game_lock`. **Multi-worker safety:** session affinity NOT required because all state is in Redis (not in `_active_connections`). Verified per Эпик 2 architecture. | ~300 | 2 | 1 |
| **A4** | New WS handler path in `ws/knowledge.py` behind flag. Emits new events through `arena_bus.publish(...)` (when `arena_bus_dual_write_enabled` is ON). `submit_answer_v2` end-to-end: receive → `answer.accepted` → grader → `verdict.emitted` → spawn explainer task → stream `explanation.streamed` → `explanation.completed`. **Order:** `pvp_solo` first, then `case_study`. | ~600 | 3 | 1 |
| **A5** | Frontend: new renderer in `app/pvp/quiz/[id]/page.tsx`. Bubbles keyed by `answer_id`, mergeable. `score.updated` is the only score source — client never increments locally. Old renderer kept under flag. | ~400 | 2 | 1 |
| **A6** | A/B in pilot: 50/50 split via `quiz_v2_grader_enabled`. Monitor `QUIZ_V2_GRADE_LATENCY`, `QUIZ_V2_VERDICT_DEDUP_HITS`, AuditLogConsumer counts. Run 3 days. Pass criteria: zero `✗N > total_questions` events, zero double-bubble events in audit log. | — | 3 | — |
| **A7** | Remove v1: `evaluate_answer_streaming`, `_SoloQuizState`, old `quiz.feedback.*` events, old client renderer. Migrate remaining modes (`themed`, `blitz`, `srs_review`, `free_dialog`) to the same contract. | ~−800 | 1 | 1 |

**Total: ~6–8 working days + 3 days A/B = ~10 calendar days.** Fits inside pilot window.

## 9. Open questions

### Closed by code evidence (after deeper read of admin/methodology surfaces)

- **Q-bb1 ✅ CLOSED.** ~~Human-review 375 keys vs LLM-second-opinion?~~
  Both, per the existing ladder. [`knowledge_quiz_validator_v2.py:109`](apps/api/app/services/knowledge_quiz_validator_v2.py:109) provides `validate_semantic(question, correct_answer, manager_answer, rag_context) → ValidationResult{equivalent, partial, score, missing, reason}` with fast-accept prefilter, asymmetric `apply_upgrade` (false→true only), and `rollout_relaxed_validation` flag. Items where `validator_v2.score ≥ 0.85` auto-publish (matches [`config.py:482`](apps/api/app/config.py:482) `arena_knowledge_auto_publish_confidence`); items with `equivalent=false AND partial=false AND score<0.4` land in the existing [`KnowledgeReviewQueue.tsx`](apps/web/src/components/dashboard/methodology/KnowledgeReviewQueue.tsx) UI for ROP/admin manual review. No new review UI needed.

- **Q-bb2 ✅ CLOSED.** ~~Question-hash strategy?~~
  Mirror `LegalKnowledgeChunk.content_hash` shape ([`models/rag.py:393-395`](apps/api/app/models/rag.py:393)):
  ```python
  content_hash = md5(question_text + "::" + canonical_answer)  # String(32) UNIQUE
  ```
  Allows multiple keys per `chunk_id` when phrasing differs. Idempotent upsert semantics already proven in legal-chunks seed loader.

- **Q-bb3 ✅ CLOSED.** ~~Deterministic match fails → LLM judge fallback or fail-and-log?~~
  Exact precedent in [`knowledge_quiz.py:670-730`](apps/api/app/services/knowledge_quiz.py:670) and `:1886-1923`: deterministic prefilter → `validator_v2.validate_semantic` → wrap in `try/except` → `logger.debug(..., exc_info=True)` → swallow. Asymmetric merge via `apply_upgrade` keeps deterministic verdict on judge failure.

- **Q-bb4 ✅ CONFIRMED.** Soft migration (new sessions → v2, old → v1 dies naturally).
- **Q-bb5 ✅ CONFIRMED.** PvP duels out of scope; separate track.

### New, evidence-based questions (need decision before A1)

These are not "how to build" questions — the code answers those. They are product/operational forks where the code shows two viable patterns and we must pick one.

- **Q-NEW-1. When does `validator_v2` fire in the new grader?**
  Currently `validator_v2` only fires when primary judge said WRONG. In Path A, primary judge is deterministic. Options:
  - (a) Only when deterministic = WRONG → mirrors current escalation pattern
  - (b) Always → +1 LLM call per answer, over-engineered
  - (c) **Only on embedding-strategy hits** → exact/synonyms/regex/keyword are fast and unambiguous; only cosine match benefits from a second opinion
  - **Author leans (c).** Cheapest sweet-spot. Deterministic strategies don't need a sanity check; embedding is the only soft one.

- **Q-NEW-2. Which review model do answer-keys follow?**
  - (a) `legal_knowledge_chunks` model — draft → ≥0.85 auto-publish OR queue → manual review (existing pipeline)
  - (b) `methodology_chunks` model — ROP/admin writes go straight to `actual`, no review queue (TZ-5 fixed point #2, [`api/methodology.py:170`](apps/api/app/api/methodology.py:170))
  - (c) **Hybrid:** LLM-generated keys (initial backfill) → queue + `validator_v2` gate; human-edited corrections (future admin UI) → straight to `actual`
  - **Author leans (c).** The 375-chunk backfill is the LLM-generated case → goes through queue. Future ROP corrections get the methodology-style direct-write since a human is the source of truth.

- **Q-NEW-3. Two flavors of answer-key — `factoid` vs `strategic`?**
  Chunks split naturally:
  - **Factoid** ("какая статья регулирует X?") → `expected_answer = chunk.fact_text` directly. No LLM generation needed.
  - **Strategic** ("как поступить если…?") → `expected_answer = llm_extract(chunk + question_template)`. One-shot at backfill, then reviewed.
  Schema: `quiz_v2_answer_keys.flavor TEXT NOT NULL CHECK (flavor IN ('factoid','strategic'))`.
  - **Author leans yes — split the schema.** Drastically simplifies backfill (375 factoid keys generate from existing `chunk.fact_text` without LLM). Strategic flavor is the only LLM-generated subset.

- **Q-NEW-4. Team-scoping for answer-keys?**
  - `legal_knowledge_chunks` is **global** (no `team_id`)
  - `methodology_chunks` is **per-team** (mandatory `team_id` FK with `ON DELETE CASCADE`)
  - Answer-keys derive from legal chunks → naturally global. But if a team has custom methodology, team-specific overrides could give personalized feedback.
  - (a) **Global** (mirror legal_chunks) — simplest, one canonical answer
  - (b) Global baseline + optional per-team override — more flexible, more state
  - **Author leans (a) on launch.** Promote to (b) only if pilot teams ask for it.

### Note on validator_v2 invariant

[`knowledge_quiz_validator_v2.py:197-235`](apps/api/app/services/knowledge_quiz_validator_v2.py:197) `apply_upgrade` is one-direction: it can only convert primary `is_correct=False` → `True`. It **cannot** demote a correct answer. This is the safety property that makes the LLM-judge fallback shippable. The new grader's deterministic verdict is the floor; validator_v2 can only rescue, never break.

## 10. Coordination

This file is the **single source of truth**. Updates land here as commits to its draft PR. Other agents leave review comments inline. Each phase opens its own PR linked from the table in §8.

### Status board

| Phase | Status | PR | Notes |
|---|---|---|---|
| Design doc | DRAFT (this file) | (this PR) | Awaiting review |
| A0 | NOT STARTED | — | Starts after design-doc PR merges |
| A1 | NOT STARTED | — | |
| A2 | NOT STARTED | — | |
| A3 | NOT STARTED | — | |
| A4 | NOT STARTED | — | |
| A5 | NOT STARTED | — | |
| A6 | NOT STARTED | — | |
| A7 | NOT STARTED | — | |

### Open review questions for the backend epic-owner

After deeper read of `/dashboard?tab=methodology` and review-policy modules, three of my four original questions closed against existing code (see §9). The remaining decisions:

1. **Q-NEW-1 — `validator_v2` trigger.** Author leans (c): only fire on embedding-strategy matches. Confirm or pick (a)/(b).
2. **Q-NEW-2 — review-pipeline model.** Author leans (c) hybrid: LLM-generated → queue, human-edited → direct. Confirm or pick (a)/(b).
3. **Q-NEW-3 — factoid vs strategic flavor split.** Author leans yes. Confirm or push back.
4. **Q-NEW-4 — team-scoping.** Author leans (a) global on launch. Confirm.
5. **Reuse-map check.** §4 maps 11 existing modules. Anything missing? In particular: did I miss `knowledge_review_policy` as the canonical state-machine writer to follow for `quiz_v2_answer_keys` status transitions? (Now added in §9 closure of Q-bb1.)
6. **Two new metrics in `arena_metrics.py`** (`QUIZ_V2_GRADE_LATENCY`, `QUIZ_V2_VERDICT_DEDUP_HITS`) — naming OK or align to existing convention?
7. **ArenaBus dual-write flip.** `arena_bus_dual_write_enabled = False` in prod today. Path A turns it ON during A4. Coordinate with your epic to avoid step-on?
