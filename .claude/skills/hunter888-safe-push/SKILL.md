---
name: hunter888-safe-push
description: |
  Hunter888 pre-push safety check. Auto-triggers BEFORE any `git push`, `gh pr create`, `gh pr merge`, or any sequence that ends in pushing a branch. Multiple Claude agents work in parallel on this repository; pushing without rebasing on current `origin/main` will silently delete other agents' merged PRs because GitHub diffs your stale HEAD against the moved main. The 2026-04-24 incident nearly deleted 4700 lines of merged work — this skill encodes the §1 of /CLAUDE.md to prevent recurrence.
---

# Hunter888 Safe-Push — §1 of /CLAUDE.md

You are working on Hunter888 in a multi-agent worktree workflow. Other Claude agents merge PRs while you work. **Every** push must be rebased on the current `origin/main` tip — no exceptions, not even "tiny fixes".

## When this skill is in effect

This skill triggers before any of:
- `git push`, `git push -f`, `git push --force-with-lease`
- `gh pr create`, `gh pr ready`, `gh pr merge`
- Any wrapper or alias that ultimately calls one of the above

If you are not pushing, this skill has nothing to add.

## The mandatory pre-push sequence

Run these four commands in order. Pasting them blindly is fine — that is the point.

```bash
# 1. Get current main
git fetch origin main

# 2. See if you have new local commits (sanity check)
git log origin/main..HEAD --oneline
#    if zero output → you have no commits, abort the push

# 3. Rebase. Resolve conflicts, re-run the affected tests.
git rebase origin/main

# 4. THE CHECK — diff your branch against current main
git diff origin/main..HEAD --stat
```

## The red-flag rule (THIS is what saves the team's work)

Look at the output of step 4. Every file there should be one you actually edited.

If you see a file you never touched showing **deletions** — like:

```
apps/web/src/app/admin/client-domain/page.tsx | 942 ------
```

**STOP. Do not push.** Your branch is stale. The 942 in the deletions column is roughly the number of lines of other agents' work your PR is about to erase.

What to do:
- Re-run `git fetch origin main` and `git rebase origin/main` — if step 3 was clean but the diff still shows untouched-file deletions, something else is wrong (wrong base branch, missed `git fetch`, force-pushed history). Surface this to the user before continuing.
- If you cannot get the diff to show only the files you actually changed, do not push. Ask the user.

## Branch naming rule (§1)

- Feature/fix branches: `claude/<short-slug>` (e.g. `claude/auth-refresh-race`).
- Never push to `main` or `develop` directly. Always through a PR.
- After a branch is merged, it is garbage. Do not reuse it for a new feature — start a new branch from the new `origin/main`.

## Audit-before-push rule (§1)

Before opening a NEW feature PR (not a fixup of an existing one), audit the last ~5 merged PRs that touch the same files or surface as your work:

```bash
git log --oneline -20
git show <sha> --stat
```

Look for:
- new infrastructure you can reuse (helpers / workers / regex sets) instead of duplicating;
- new invariants other agents introduced (a column you must not bypass, a markers contract);
- pattern templates (existing AST guards, allow-list shapes) you should copy verbatim for codebase coherence.

This habit caught two bugs in this project: PR #139 `original_confidence` reuse, PR #146 `LiveEmbeddingBackfillWorker` extension. Five minutes of reading is cheaper than a duplicate-helpers rebase a month later.

## Output format

Before any push, your turn must include:

```
### §1 safe-push — <branch>
git fetch origin main:        ok
local commits ahead of main:  N (<one-line summary>)
git rebase origin/main:       ok / had conflicts (resolved: <files>)
git diff origin/main..HEAD --stat:
  <paste output>
red-flag check:               ✅ all files in diff are ones I edited
                              ❌ saw <file> with -<N> lines I didn't touch — NOT pushing
```

If the red-flag check is ❌, do not push. Surface the situation, do not "try again with --force".

## Non-negotiable

This is enforceable per §7. The server is also pull-only — see hunter888-prod-deploy-guard skill for that.
