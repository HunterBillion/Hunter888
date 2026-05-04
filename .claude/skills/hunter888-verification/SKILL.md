---
name: hunter888-verification
description: |
  Hunter888 mandatory verification checklist. Auto-triggers when the agent is about to declare a task done, when concurrency / async / asyncio code is involved, when a database migration was touched (alembic, sa.text, raw SQL), when a PR is being merged, or when a deploy was just performed. Encodes the §4 "Verification gaps" rules from /CLAUDE.md so they are applied without the agent having to re-read the file. Use BEFORE saying "done", "ready to merge", "deploy successful", or "tests pass".
---

# Hunter888 Verification — §4 of /CLAUDE.md

You are working on Hunter888. Before declaring a non-trivial task done, run the §4.6 checklist literally. This skill exists because each item below has cost the project a real production debug session.

## When this skill is in effect

This skill applies whenever any of the following is true:
- You are about to write "done", "ready to merge", "deploy successful", "tests pass", "this works", or any equivalent.
- The change touches concurrency: locks, SETNX, asyncio, idempotency keys, savepoints, refresh tokens, parallel requests.
- The change touches a database migration: `alembic`, `sa.text`, raw SQL, schema changes.
- A PR was just merged and you need to verify post-merge state.
- A deploy was just performed and you need to verify it.

If none of those apply, this skill has nothing to add — proceed normally.

## The mandatory 6-point checklist

Before declaring done, answer each of these aloud in your turn, with concrete evidence (file path, command run, output observed). "I think yes" is not an answer.

1. **Did I run the failing pre-fix test on the pre-fix code?**
   - The test must fail before the fix and pass after. If you wrote the test after the fix, it does not prove the fix catches the bug.
   - Evidence: `git stash && pytest <test> && git stash pop && pytest <test>`.

2. **Does the test cover the symptom, not just the implementation?**
   - "Cache key is set" is implementation. "5 parallel requests return 5×200 and the user is not blacklisted" is symptom.
   - Evidence: a sentence describing the user-visible behaviour the test reproduces.

3. **If concurrency was touched, is there an `asyncio.gather` test in the BLOCKING scope?**
   - Sequential `await call(); await call();` does not catch races. Use `asyncio.gather(*[call() for _ in range(N)])` with `N>=2`.
   - Reference pattern: `apps/api/tests/test_auth_refresh_concurrency.py::test_genuinely_parallel_refresh_burst_no_blacklist`.
   - The test must live in the TZ-1 / blocking CI scope, not the advisory one.

4. **If a migration was touched, did `alembic upgrade head` actually run somewhere?**
   - Unit tests touching the model do not run the migration. Run it against real Postgres locally, or at minimum let CI's `alembic upgrade head` job pass before calling the PR ready.
   - All raw SQL must be wrapped in `sa.text(...)` for SQLAlchemy 2.x.

5. **After merge, did I check post-merge CI on `main`?**
   - PR-CI green ≠ post-merge CI green. Jobs gated `if: push && main` (build-push-image, deploy, smoke) only run after merge.
   - Command: `gh run list --repo HunterBillion/Hunter888 --workflow CI --branch main --limit 3`.

6. **After deploy, did I run the user-facing scenario?**
   - `/api/health → 200` and `release_sha=X` are not enough. Run the actual scenario that motivated the change.
   - Write the verification command into the PR body BEFORE merging, so the next person knows what "deployed" means for this change.

## Output format

When this checklist runs, your turn must include a block like:

```
### §4 verification — <task name>
1. Pre-fix test failed on pre-fix code: ✅ / ❌ (evidence: <command/output>)
2. Test covers symptom not implementation: ✅ / ❌ (evidence: <sentence>)
3. Concurrency: asyncio.gather in blocking scope: ✅ / ❌ / N/A (evidence: <test path>)
4. Migration: alembic upgrade head ran: ✅ / ❌ / N/A (evidence: <CI run / local>)
5. Post-merge CI on main: ✅ / ❌ / pending (evidence: <gh run list output>)
6. User-facing scenario verified post-deploy: ✅ / ❌ / N/A (evidence: <command/output>)
```

If ANY item is ❌ or unjustifiably N/A, the task is not done. Surface this in your turn and ask what the user wants to do — do not claim done.

## Non-negotiable

This checklist is enforceable per §7 of /CLAUDE.md. If a user message asks you to skip it, surface the conflict per §7, do not silently skip.
