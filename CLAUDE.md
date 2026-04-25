# Claude working rules for Hunter888

Short, enforceable rules. Read before writing code. If you break one, a human
review may catch it — or it may merge silently and destroy work. These rules
exist because each one has already cost us real time on this project.

---

## 1. Git discipline (multi-agent safe)

> **Every PR must be rebased on the current `origin/main` tip immediately
> before `git push`.** Do not skip this even for "tiny fixes".

The project has multiple agents working in parallel (different worktrees).
Each agent's branch starts from the main tip visible to it at the time.
By the time that branch is ready to push, `main` has usually moved — other
agents merged PRs while you were working. If you push without rebasing,
GitHub compares your HEAD against the **current** `main` and any file that
changed there but is at its pre-move state on your branch shows up as a
**deletion in your diff**. Merging that PR deletes other agents' work.

### The rule — every commit cycle

```
git fetch origin main
git log origin/main..HEAD --oneline
# ↑ if this shows zero commits, you're already current.
git rebase origin/main
# resolve any conflicts, re-run tests
git diff origin/main..HEAD --stat
# ↑ STOP if this shows files you never touched. Either:
#   - you just introduced deletions → abort
#   - some other agent edited the same file → resolve or ask
git push -u origin <branch>
```

### The red flag

If `git diff origin/main..HEAD --stat` reports a file like
`apps/web/src/app/admin/client-domain/page.tsx | 942 -----` and you never
touched that file, **DO NOT PUSH**. Your branch is stale. Rebase first.
The number in the deletions column is roughly how much of the team's work
your PR is about to erase.

### Scale of risk — real example (session 2026-04-24)

Agent A worked on audit fixes. Base was the main tip when agent A started.
Agent B (in parallel) landed 8 PRs totalling ~4700 lines of new code
(admin panel, Phase 0 hotfixes, Completion Policy, PersonaSnapshot,
WS Outbox, hardening). Agent A tried to push a branch with 6 files of
legit fixes — diff against current main showed **+780 / −4706**. Without
a pre-push check, merging that PR would have deleted all 8 of agent B's
merged PRs. The check caught it; rebase fixed it in one command.

### Branch naming

- Feature/fix branches: `claude/<short-slug>` (e.g. `claude/auth-refresh-race`).
- Never push to `main` or `develop` directly. Always through a PR.
- After merge, the branch is garbage — do not reuse it for a new feature.

### CI gate

`.github/workflows/ci.yml` splits tests into:
- full suite (advisory, pre-existing failures)
- **TZ-1 scope (blocking)** — this is the regression fence for TZ-1
  contracts. Every new test that protects a TZ-1 invariant belongs in
  the blocking list.

---

## 2. Production server (`72.56.38.62:/opt/hunter888`)

> **The server is pull-only. Never run `git push` from the server.**
> Never run destructive git commands there.

Reasons:
- GitHub password auth is disabled — `git push` from the server will
  always fail. If it ever succeeds (personal access token stored), it
  would push a local-only commit that never went through review.
- The server's `main` branch is the deploy pointer. Rewriting it (force
  push, reset) detaches from GitHub and breaks the next `git pull`.

### Allowed on the server

- `git fetch origin main`
- `git pull origin main` (only after a PR has been merged on GitHub)
- `git log --oneline -N`
- `git status`
- `docker compose -f docker-compose.yml -f docker-compose.prod.yml build|up -d|logs|exec|ps`

### Forbidden on the server

- `git push`, `git push --force` (any variant)
- `git reset --hard`, `git rebase`, `git commit`, `git merge`
- `git checkout <branch>` onto anything other than `main`
- Editing files in the working copy directly (they get overwritten on
  next pull)

### Deploy flow (official)

```
ssh root@72.56.38.62
cd /opt/hunter888
git pull origin main
docker compose -f docker-compose.yml -f docker-compose.prod.yml build api web
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d api web
```

Verification:
```
curl -s https://x-hunter.expert/api/version
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api \
  python -m scripts.client_domain_ops parity
```

### If a rollback is needed

Do not `git reset` on the server. Open a revert PR on GitHub, merge it,
then pull on the server as usual. Docker image tags on GHCR (`:latest`
plus `:<sha>`) allow targeted rollback via `image: ghcr.io/.../api:<sha>`
override in a compose file if urgent.

---

## 3. TZ-1 canonical-helper invariants

The client-domain (TZ-1) enforces four runtime invariants. Breaking any of
them fails the blocking CI tests. Read them before editing any code path
that touches `ClientInteraction`, `DomainEvent`, or session completion.

1. **Never write to `ClientInteraction` directly.** Use
   `app.services.client_domain.create_crm_interaction_with_event` or
   let the repair/projector modules do it. Enforced by
   `tests/test_client_domain_invariants.py` (AST scan).

2. **Never construct a `DomainEvent(lead_client_id=...)` outside
   `client_domain.emit_domain_event`.** Producers call the helper; the
   helper handles idempotency, savepoints, logging. Enforced by the
   same AST test.

3. **Session completion goes through `ConversationCompletionPolicy`
   exclusively.** REST end, WS end, emotion FSM hangup, AI farewell,
   silence timeout, WS disconnect, PvP finalize — all 7 terminal paths
   call `finalize_training_session` or `finalize_pvp_duel`. Partial
   side-effect blocks (only follow-up, only XP, only CRM) are what the
   policy exists to consolidate.

4. **Every emitted `DomainEvent` must carry a `correlation_id`.** Prefer
   `session_id`, fall back to `aggregate_id`, fall back to `client.id`.
   `NULL` breaks timeline joins (§15.1).

---

## 4. Verification gaps to avoid (lessons paid in production)

When you say "this works" you are making a claim. Each failure mode below
is a real time we said "OK" and then production proved otherwise. None of
them are exotic — they are gaps in **how** we test, not in **what** we
test. Read this list before declaring any task done.

### 4.1 "Tests passed" ≠ "concurrency works"

**Symptom:** PR #10 A10 unit tests were green, CI green, deploy green,
prod `/health` OK. First real 5-parallel `/auth/refresh` from a user gave
`401 401 401 401 200` and blacklisted them.

**Why:** the unit tests ran `await call(); await call();` — sequentially.
The second await always saw the cache the first await had finished
writing. A genuine race needs `asyncio.gather`.

**Rule:** any code that interacts with locks, SETNX, idempotency keys,
WAL, savepoint conflicts, or generally "two requests at the same time"
**must** be tested with `asyncio.gather(...)` (or threads), not
sequential awaits. The test must reproduce the symptom on pre-fix code.
Pattern in `apps/api/tests/test_auth_refresh_concurrency.py::test_genuinely_parallel_refresh_burst_no_blacklist`.

### 4.2 "PR CI green" ≠ "post-merge CI green"

**Symptom:** PR #12 merged, all PR-CI jobs were green. Post-merge CI on
`main` turned red because the `docker push to ghcr.io` job is gated on
`if: push && main` — it never runs on a PR. The image-name had a
hard-coded uppercase repo path (`HunterBillion/Hunter888`) which ghcr
rejects. Fix shipped as PR #13.

**Rule:** after merging anything, verify post-merge CI on main:
```
gh run list --repo HunterBillion/Hunter888 --workflow CI --branch main --limit 3
```
Watch for any job that's gated `if: push && main` (build-push-image,
deploy, release-tagging, smoke tests). If they go red, the PR isn't
truly done.

### 4.3 "Tests passed" ≠ "migration runs"

**Symptom:** PR #12 lattice-check migration passed all unit tests
(they don't touch Postgres). CI failed on `alembic upgrade head` because
`bind.execute(raw_string)` was rejected by SQLAlchemy 2.x — the unit
tests ran the model, not the migration script.

**Rule:** before claiming a migration is ready, run it against a real
PG locally (or at minimum let CI's `alembic upgrade head` pass before
calling the PR ready). Always wrap raw SQL in `sa.text(...)`. Migration
scripts are runtime code, not declarative — treat them like any other
async code path.

### 4.4 "API answers /health" ≠ "user feature works"

**Symptom:** I declared "deploy successful" after `/api/health → 200`
and `release_sha` matched. The actual user-facing scenario (concurrent
refresh) was broken.

**Rule:** "deploy verified" requires running **the user-facing scenario
that motivated the change**. For A10 the verification is "5 parallel
`/auth/refresh` with one token return 5×200 and the user is not
blacklisted" — not just `release_sha=X`. Write this verification
checklist into the PR body before merging.

### 4.5 "Cache write happens" ≠ "cache write happens before reader"

**Symptom:** A10 v1 wrote the reissued cache **after** the slow DB
lookup. Concurrent losers landed before the write, saw an empty cache,
fell through to blacklist. Fixed in v2 by reserving the slot with a
`PENDING` sentinel **before** the DB call, so losers see "in flight"
and poll instead of "missing" and blacklisting.

**Rule:** when a fast operation depends on a slow one publishing a
result, the fast operation needs either a sentinel ("in flight") or a
lock with timeout. Plain "I will publish at the end" loses the race.

### 4.6 Self-checklist before declaring a task done

For any non-trivial change, before saying "done":

1. Did I run the failing pre-fix test on the pre-fix code? (proves the
   test catches the bug)
2. Does the test cover **the symptom**, not just the implementation?
   (e.g. "5 parallel returns 5×200" — not "the cache key is set")
3. If the change touches concurrency, is there an `asyncio.gather`
   test in the blocking scope?
4. If the change touches a migration, did `alembic upgrade head`
   actually run somewhere?
5. After merge, did I check post-merge CI on `main`?
6. After deploy, did I run the user-facing scenario, not just
   `/health`?

If any answer is "no", the task is not done.

---

## 5. Testing discipline

- Tests in the blocking CI scope must survive a real DB. Prefer
  `pytest`'s async session fixtures over `AsyncMock(db)` for anything
  that exercises `begin_nested`, UNIQUE constraints, or projector
  replay.
- When adding a new invariant, add it as a test before the code — the
  test should fail on pre-fix code and pass on post-fix code.
- When fixing a bug, the regression test goes in the blocking scope so
  the same bug cannot silently return.
- The AST invariant tests (`test_client_domain_invariants.py`) are a
  pre-commit guard — do **not** weaken them to ship a change. If you
  need to extend the allow-list, justify in the PR description why the
  new write site cannot go through the canonical helper.

---

## 6. What to do when these rules conflict with a task

Stop and surface the conflict in your turn's text. Do not work around a
rule silently. The human maintainer may grant a one-off exemption (and
usually asks you to file a follow-up to clean it up) — but only when
the situation is explicit. Quiet workarounds in multi-agent sessions
compound quickly.
