# TZ-4 architecture audit + improvements — 2026-04-28

> Snapshot of the codebase ~24h after D7.3 landed. Audit ran read-only
> via Opus subagent across the 18 PRs of the TZ-4 series; this PR
> closes 9 of the surfaced items in one shipment.

## What the audit found (8 ranked items)

The full audit report is preserved in PR #75 description. Summary:

| # | Item | Status |
|---|---|---|
| 1 | NBA decision-boundary outdated filter (§11.2.1 layer 2) | ✅ closed in this PR (I1) |
| 2 | `asyncio.gather` real-DB concurrency test for `ingest_upload` | ⚠️ partial — concurrent test added at the service-mock level (I6a); real-DB is deferred (needs a Postgres test fixture which doesn't exist yet) |
| 3 | D7.3 migration `RuntimeError` UX | 📝 documented; will be opt-in via env flag in a future PR |
| 4 | `ai_quality.py` `dict[str, object]` + 9 `# type: ignore` | ✅ closed in this PR (I2) — typed `_ManagerBucket` dataclass, **0 `# type: ignore`** |
| 5 | FE re-render risk via `usePolicyStore` selector | ✅ closed in this PR (I4) — `useShallow` + `React.memo` |
| 6 | `get_for_lead` lookup duplication (3 callsites) | ✅ closed in this PR (I5) — audit hook + persona view both delegate |
| 7 | Test coverage holes: `record_conflict_attempt` race + `mark_classified` validation + audit hook home_preview path | ✅ closed in this PR (I6a/b/c) |
| 8 | AST guard gaps (attachment status columns + persona slots + knowledge audit columns) | ✅ closed in this PR (I3) |

## Honourable mentions also closed

- I7 — `triggers` dict in `conversation_policy_engine._check_asked_known_slot` had a missing-trailing-comma footgun for single-string entries (worked because of an `isinstance(str)` promotion, but typo-prone). Replaced tuple-of-strings with `frozenset[str]` literals; the promotion shim is gone.

## What's still tracked but not in this PR

- **Audit#3** — D7.3 migration error-message UX. Deferred because operator hands-on doesn't happen until pilot incidents arise.
- **Audit#2 real-DB** — actual Postgres `asyncio.gather` against `uq_attachments_client_sha256_orig` partial UNIQUE index. Needs a real-DB pytest fixture (the project's existing `conftest.py` is in-memory SQLite which doesn't enforce partial indexes per spec).
- **Honourable: `KNOWLEDGE_GLOBAL_ANCHOR` magic UUID** — adds a CHECK or seed row to enforce the synthetic anchor. Low risk, deferred.
- **Honourable: `mark-outdated` endpoint name drift** — spec §8.3.1 line 640 says `POST /admin/knowledge/{id}/mark-outdated`, code ships `POST /admin/knowledge/{id}/review`. Either rename the endpoint with back-compat alias OR update the spec text. Deferred — spec wording change is cheaper.
- **Honourable: `AutoOutdatedForbidden` exception unused** — module-level class with zero raise sites. Removed from `__all__` and inlined as a sanity raise inside `expire_overdue` is on the backlog.

## Spec drift summary (from audit)

### Spec promised, code doesn't deliver

* **§11.2.1 NBA layer 2**: now provided via `filter_safe_knowledge_refs` helper (I1). The actual NBA call sites still don't consume legal knowledge; the helper is the single import target for when they do.
* **§15.3.7 / §15.3.8 real-DB E2E tests**: only mock-level coverage today.
* **§8.3 endpoint wording**: `mark-outdated` vs implemented `review`.
* **§7.2.6 metadata fields**: `duplicate_of_event_id`, `duplicate_count_at_upload`, `uploaded_via` — only `duplicate_of` + `domain_event_id` are written today.
* **§6.3.1 `MemoryPersona.last_confirmed_at`** is documented to update on slot lock; current `lock_slot` does not refresh this column.

### Code does, spec doesn't describe

* **`attachment.linked` event** — emitted alongside legacy `session.attachment_linked` for transition compatibility. The dual-emit isn't called out in §7.3 — should be added before D7.5 (legacy removal).
* **`KNOWLEDGE_GLOBAL_ANCHOR` synthetic UUID** — invented to satisfy `correlation_id NOT NULL` for knowledge events. Spec §8.4 doesn't address how knowledge events anchor to the lead-event log.
* **`enforceActive` carry-forward** in `usePolicyStore` — once any violation reports `enforce_active=true`, the per-session bucket keeps that flag forever. Not described in spec — pragmatic UX (don't flicker), but worth documenting.

## Test count delta after this PR

Before: **268** in TZ-1 blocking + TZ-4 scope.

After this PR: 268 + 4 (NBA filter) + 1 (concurrent record_conflict) + 1 (mark_classified validation) + 2 (audit hook home_preview + drift failure) + 1 (memory persona AST guard) = **277 / 277** target.
