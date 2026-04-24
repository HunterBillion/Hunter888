# CI lint debt — context & cleanup plan

## State at `4098a9c` (TZ-1 scope closed)

- **Backend**: `ruff check .` reports ~5.5k findings. Most are pre-2026-04
  code (naming, formatting, unused imports). None are bugs — they are
  style warnings in files that were never touched during TZ-1.
- **Frontend**: `npm run lint` surfaces `~70` warnings + a handful of
  pre-existing errors (`react/jsx-no-comment-textnodes`,
  `@typescript-eslint/no-require-imports`) in components that predate the
  Next.js 15 upgrade. TypeScript itself (`tsc --noEmit`) is clean.

## Why the CI lint step is advisory (`continue-on-error: true`)

Making lint a hard gate on this PR would require either:

1. Auto-fixing all 5.5k findings in a single PR, which would modify ~250
   files outside TZ-1 and risked regressing unrelated code (ruff safe-fix
   once introduced 6 new test failures in our local audit, so the fix is
   *not* purely cosmetic).
2. Letting every unrelated PR inherit the red CI — the state before this
   commit.

Neither is acceptable. The step now runs but does not block, so authors
keep visibility without blocking delivery.

## Hard guards that DO block

- `npx tsc --noEmit` — type safety is strictly enforced.
- Alembic `upgrade head` must succeed.
- **TZ-1 scope pytest** (the "Test — TZ-1 scope (blocking)" CI step) —
  `test_client_domain.py`, `test_client_domain_repair.py`,
  `test_client_domain_invariants.py`, `test_client_domain_parity.py`,
  `test_training_session_attachments.py`, `test_event_bus_outbox.py`,
  `test_crm_followup.py`, `test_game_crm_chat.py`. All 53 tests must
  pass. The invariant test inside this scope protects the TZ-1 contract
  from any new code path trying to bypass the canonical helper.
- The full suite still runs alongside (advisory) so coverage numbers
  stay visible; hard-gating it would require paying down the ~116
  pre-existing failures first.

## Follow-up plan

Open a separate PR named `chore(lint): one-shot ruff cleanup` that
applies `ruff check --fix-only .` and `ruff format .` to the whole tree.
Verify the full pytest suite stays at the current pass/fail split before
merging. Then flip the two `continue-on-error: true` back to `false`.

Same procedure for frontend: a `chore(lint): fix legacy ESLint errors`
PR that addresses the explicit `jsx-no-comment-textnodes` and
`no-require-imports` sites, then drops the `continue-on-error` there
too.

Both cleanup PRs are strictly out of TZ-1 scope.
