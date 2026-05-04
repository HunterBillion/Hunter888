---
name: hunter888-prod-deploy-guard
description: |
  Hunter888 production-server safety guard. Auto-triggers when the agent is about to SSH into 72.56.38.62, or when the agent is about to run any deploy / docker compose / git pull on a remote server, or when the prompt mentions "prod", "deploy", "production", "x-hunter.expert", or "/opt/hunter888". Encodes §2 of /CLAUDE.md including the 2026-05-03 wrong-VM trap (72.56.38.62 resolves to TWO different VMs and only msk-1-vm-cqax is Hunter888) and the FIND-007 RELEASE_SHA=unknown trap.
---

# Hunter888 Prod-Deploy Guard — §2 of /CLAUDE.md

You are about to touch the production server for Hunter888. There are two well-known traps. Run the safety checks before any mutation.

## Trap 1 — wrong VM (the 2026-05-03 near-miss)

`72.56.38.62` resolves to TWO different VMs. SSH may land on either depending on routing/IPv6/timing. ONLY ONE is Hunter888.

| hostname | Hunter888? | layout |
|---|---|---|
| `msk-1-vm-cqax` | ✅ yes | `/opt/hunter888`, 6× containers `hunter888-{api,web,whisper,redis,postgres,nginx}-1` |
| `msk-1-vm-ofzn` | ❌ NO | hunter-club + techforum + manyasha. The `python3` on `:8000` is hunter-club, NOT Hunter888. |

**Mandatory first command after every SSH session:**

```bash
hostname
```

Then:
- `msk-1-vm-cqax` → proceed with `cd /opt/hunter888`.
- `msk-1-vm-ofzn` → **disconnect immediately**. Do not `cd`, do not `git pull`, do not touch `/proc/<pid>/cwd`, do not edit any `hunter-*` file, do not poke at `/opt/hunter-club*`. Mutating ofzn breaks a different team's production.

If repeat SSH attempts keep landing on ofzn, the user has out-of-band access to cqax. Ask them to run the deploy themselves rather than improvising on ofzn.

## Trap 2 — RELEASE_SHA=unknown (FIND-007)

The compose default is `${RELEASE_SHA:-unknown}`. If you forget `export RELEASE_SHA=...` before `docker compose build`, the image ships with `release_sha=unknown` and you cannot tell which sha is running.

The official wrapper `scripts/deploy-prod.sh` captures `RELEASE_SHA = git rev-parse HEAD` and `BUILD_TIME` (UTC) and verifies via `/api/version`. **As of 2026-05-03 the script may not be present on either VM** — verified absent. Until it lands, use the manual flow below.

## Allowed on the server

```
git fetch origin main
git pull origin main           # only after a PR has been merged on GitHub
git log --oneline -N
git status
docker compose -f docker-compose.yml -f docker-compose.prod.yml build|up -d|logs|exec|ps
```

## Forbidden on the server

```
git push, git push --force      (any variant — auth is disabled, but if it ever works, it pushes unreviewed)
git reset --hard, git rebase, git commit, git merge
git checkout <branch>           (anything other than main)
editing files in the working copy directly  (overwritten on next pull)
```

## Manual deploy flow (canonical when wrapper is absent)

```bash
ssh root@72.56.38.62
hostname                                      # MUST be msk-1-vm-cqax
cd /opt/hunter888

git fetch origin main
git pull --ff-only origin main

export RELEASE_SHA=$(git rev-parse HEAD)
export BUILD_TIME=$(date -u +%FT%TZ)

docker compose -f docker-compose.yml -f docker-compose.prod.yml build api web
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d api web

# Verification — NOT optional
curl -s https://x-hunter.expert/api/version
# must report release_sha == $RELEASE_SHA
```

If `/api/version` reports `release_sha=unknown` or a different sha — the deploy did not bake your code in. Re-do with `export RELEASE_SHA=...` set BEFORE `build`.

Other domain-level verification:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api \
  python -m scripts.client_domain_ops parity
```

## Rollback

Do not `git reset` on the server. Open a revert PR on GitHub, merge it, then pull on the server as usual. For urgent targeted rollback, override `image: ghcr.io/.../api:<sha>` in a compose file using GHCR tags `:latest` and `:<sha>`.

## Output format

Before any prod mutation, your turn must include:

```
### §2 prod-deploy-guard
hostname:                        msk-1-vm-cqax  ✅
                                 msk-1-vm-ofzn  → DISCONNECT, ABORT
cwd:                             /opt/hunter888
git pull --ff-only:              ok / fast-forward of N commits
RELEASE_SHA exported:            <sha>  ✅
BUILD_TIME exported:             <UTC>
docker compose build:            ok
docker compose up -d:            ok
/api/version reports:            <sha>  ✅ matches local
                                          ❌ mismatch → re-do with export
user-facing scenario verified:   <command>  (tied to the change motivation)
```

After deploy, the §4 verification skill (hunter888-verification) is in effect — the user-facing scenario must be exercised, not just `/health`.

## Non-negotiable

This is enforceable per §7. Multiple agents running deploys without these checks broke things in 2026-04 and 2026-05.
