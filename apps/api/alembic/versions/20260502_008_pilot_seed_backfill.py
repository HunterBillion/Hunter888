"""Pilot seed backfill: preferences + onboarding + level + method team_id.

Revision ID: 20260502_008
Revises: 20260502_007
Create Date: 2026-05-02

Why this exists
---------------

Audit B5 found three orthogonal pilot-blocking issues for users
seeded via ``apps/api/scripts/seed_db.py`` with email pattern
``%@trainer.local``:

**B5-04 — arena modes locked.** Seed users land at level 1; rapid
fire requires level 9, gauntlet 10, mirror 15. Pilot testers
literally cannot exercise the arena.

**B5-05 — POST /api/training/sessions returns 409 profile_incomplete.**
Required preference fields (``gender``, ``role_title``, ``lead_source``,
``primary_contact``, ``specialization``, ``experience_level``,
``training_mode``) are unset on seed users; the runtime-guard engine
blocks training.

**B5-06 — methodologist Anna gets 400 on GET /api/methodology/chunks.**
The seed already attaches ``method@trainer.local`` to the B2B team
(post-2026-04-26 methodologist-role retirement), but a prod row
landed before the seed change with ``team_id=NULL``. The methodology
endpoint requires ``team_id`` for non-admin callers — Anna logs in
to a 400 with no path forward.

All three are data drift, not code bugs. One migration fixes all
three; deploys idempotently.

Operations
----------

1. **Backfill ``users.preferences``** for ``%@trainer.local`` rows.
   Uses ``COALESCE(preferences->>'key', default)`` so any pre-existing
   value is preserved — only NULL/empty keys get the seed default.
   Per-name presets:
     * "Иван Петров", "Дмитрий Козлов" → male, "Менеджер по продажам"
     * "Мария Сидорова", "Ксения Морозова" → female, "Менеджер по продажам"
     * Else (rop, admin, method) → role-appropriate title, neutral defaults

2. **Set ``users.onboarding_completed=TRUE``** on all
   ``@trainer.local`` rows so the FE skips the onboarding wizard.

3. **Insert ``manager_progress``** at level 15 for any
   ``@trainer.local`` user without one. Level 15 unlocks every gate
   (max gate is mirror=15). XP set to ``121_700`` to match the
   ``LEVELS`` table threshold for level 15 — keeps XP/level invariants
   consistent for any future bonus calculations.

4. **Pre-existing ``manager_progress`` rows** below level 15 get
   ``current_level = GREATEST(current_level, 15)`` and
   ``total_xp = GREATEST(total_xp, 121700)``. A user already past
   level 15 keeps their state.

5. **B5-06** ``method@trainer.local team_id``. Bind to the B2B team
   if the user exists with NULL team_id. Idempotent — explicit value
   preserved.

Idempotent — every UPDATE/INSERT is guarded so a re-run is a no-op.
``downgrade()`` is intentionally a no-op: this is data backfill,
the rows would land in this state anyway via the seed script. Reverting
the migration shouldn't roll back the team's accumulated state.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260502_008"
down_revision: Union[str, Sequence[str], None] = "20260502_007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Level 15 unlocks every gate (mirror=15 is the highest seed_levels
# threshold we care about). XP value matches the LEVELS table entry
# for level 15 — keeps the level/total_xp invariant consistent so
# any future XP-bonus accounting doesn't trip on a fabricated state.
PILOT_TARGET_LEVEL = 15
PILOT_TARGET_XP = 121_700


def upgrade() -> None:
    bind = op.get_bind()

    # ── Step 1: backfill users.preferences (B5-05) ─────────────────────
    # Per-name presets first; everything else gets the role-neutral
    # fallback. Each statement is conservative: COALESCE preserves any
    # existing value the user already entered through the FE wizard.

    # Иван Петров — male, junior sales manager.
    bind.execute(sa.text("""
        UPDATE users SET
            preferences = jsonb_build_object(
                'gender',           COALESCE(preferences->>'gender',           'male'),
                'role_title',       COALESCE(preferences->>'role_title',       'Менеджер по продажам'),
                'lead_source',      COALESCE(preferences->>'lead_source',      'warm'),
                'primary_contact',  COALESCE(preferences->>'primary_contact',  'phone'),
                'specialization',   COALESCE(preferences->>'specialization',   'bankruptcy_127fz'),
                'experience_level', COALESCE(preferences->>'experience_level', 'junior'),
                'training_mode',    COALESCE(preferences->>'training_mode',    'balanced')
            ),
            onboarding_completed = TRUE
        WHERE email = 'manager1@trainer.local'
    """))

    # Дмитрий Козлов — male, middle B2B manager.
    bind.execute(sa.text("""
        UPDATE users SET
            preferences = jsonb_build_object(
                'gender',           COALESCE(preferences->>'gender',           'male'),
                'role_title',       COALESCE(preferences->>'role_title',       'Менеджер по продажам B2B'),
                'lead_source',      COALESCE(preferences->>'lead_source',      'inbound'),
                'primary_contact',  COALESCE(preferences->>'primary_contact',  'mixed'),
                'specialization',   COALESCE(preferences->>'specialization',   'bankruptcy_127fz'),
                'experience_level', COALESCE(preferences->>'experience_level', 'middle'),
                'training_mode',    COALESCE(preferences->>'training_mode',    'balanced')
            ),
            onboarding_completed = TRUE
        WHERE email = 'manager3@trainer.local'
    """))

    # Мария Сидорова — female, middle sales.
    bind.execute(sa.text("""
        UPDATE users SET
            preferences = jsonb_build_object(
                'gender',           COALESCE(preferences->>'gender',           'female'),
                'role_title',       COALESCE(preferences->>'role_title',       'Старший менеджер по продажам'),
                'lead_source',      COALESCE(preferences->>'lead_source',      'warm'),
                'primary_contact',  COALESCE(preferences->>'primary_contact',  'phone'),
                'specialization',   COALESCE(preferences->>'specialization',   'bankruptcy_127fz'),
                'experience_level', COALESCE(preferences->>'experience_level', 'middle'),
                'training_mode',    COALESCE(preferences->>'training_mode',    'intensive')
            ),
            onboarding_completed = TRUE
        WHERE email = 'manager2@trainer.local'
    """))

    # Ксения Морозова — female, junior B2B.
    bind.execute(sa.text("""
        UPDATE users SET
            preferences = jsonb_build_object(
                'gender',           COALESCE(preferences->>'gender',           'female'),
                'role_title',       COALESCE(preferences->>'role_title',       'Менеджер по продажам B2B'),
                'lead_source',      COALESCE(preferences->>'lead_source',      'inbound'),
                'primary_contact',  COALESCE(preferences->>'primary_contact',  'mixed'),
                'specialization',   COALESCE(preferences->>'specialization',   'bankruptcy_127fz'),
                'experience_level', COALESCE(preferences->>'experience_level', 'junior'),
                'training_mode',    COALESCE(preferences->>'training_mode',    'balanced')
            ),
            onboarding_completed = TRUE
        WHERE email = 'manager4@trainer.local'
    """))

    # ROPs + admin — role-appropriate titles, senior experience.
    bind.execute(sa.text("""
        UPDATE users SET
            preferences = jsonb_build_object(
                'gender',           COALESCE(preferences->>'gender',           'male'),
                'role_title',       COALESCE(preferences->>'role_title',       'РОП Sales'),
                'lead_source',      COALESCE(preferences->>'lead_source',      'mixed'),
                'primary_contact',  COALESCE(preferences->>'primary_contact',  'mixed'),
                'specialization',   COALESCE(preferences->>'specialization',   'bankruptcy_127fz'),
                'experience_level', COALESCE(preferences->>'experience_level', 'senior'),
                'training_mode',    COALESCE(preferences->>'training_mode',    'balanced')
            ),
            onboarding_completed = TRUE
        WHERE email = 'rop1@trainer.local'
    """))
    bind.execute(sa.text("""
        UPDATE users SET
            preferences = jsonb_build_object(
                'gender',           COALESCE(preferences->>'gender',           'male'),
                'role_title',       COALESCE(preferences->>'role_title',       'РОП B2B'),
                'lead_source',      COALESCE(preferences->>'lead_source',      'inbound'),
                'primary_contact',  COALESCE(preferences->>'primary_contact',  'mixed'),
                'specialization',   COALESCE(preferences->>'specialization',   'bankruptcy_127fz'),
                'experience_level', COALESCE(preferences->>'experience_level', 'senior'),
                'training_mode',    COALESCE(preferences->>'training_mode',    'balanced')
            ),
            onboarding_completed = TRUE
        WHERE email = 'rop2@trainer.local'
    """))
    bind.execute(sa.text("""
        UPDATE users SET
            preferences = jsonb_build_object(
                'gender',           COALESCE(preferences->>'gender',           'female'),
                'role_title',       COALESCE(preferences->>'role_title',       'Методолог'),
                'lead_source',      COALESCE(preferences->>'lead_source',      'mixed'),
                'primary_contact',  COALESCE(preferences->>'primary_contact',  'mixed'),
                'specialization',   COALESCE(preferences->>'specialization',   'bankruptcy_127fz'),
                'experience_level', COALESCE(preferences->>'experience_level', 'senior'),
                'training_mode',    COALESCE(preferences->>'training_mode',    'balanced')
            ),
            onboarding_completed = TRUE
        WHERE email = 'method@trainer.local'
    """))
    bind.execute(sa.text("""
        UPDATE users SET
            preferences = jsonb_build_object(
                'gender',           COALESCE(preferences->>'gender',           'male'),
                'role_title',       COALESCE(preferences->>'role_title',       'Администратор'),
                'lead_source',      COALESCE(preferences->>'lead_source',      'mixed'),
                'primary_contact',  COALESCE(preferences->>'primary_contact',  'mixed'),
                'specialization',   COALESCE(preferences->>'specialization',   'platform'),
                'experience_level', COALESCE(preferences->>'experience_level', 'senior'),
                'training_mode',    COALESCE(preferences->>'training_mode',    'balanced')
            ),
            onboarding_completed = TRUE
        WHERE email = 'admin@trainer.local'
    """))

    # ── Step 2: insert manager_progress at level 15 (B5-04) ────────────
    bind.execute(sa.text(f"""
        INSERT INTO manager_progress (
            id, user_id, current_level, current_xp, total_xp,
            calibration_complete, skill_confidence,
            created_at, updated_at
        )
        SELECT
            gen_random_uuid(), u.id,
            {PILOT_TARGET_LEVEL}, 0, {PILOT_TARGET_XP},
            TRUE, 'medium',
            NOW(), NOW()
        FROM users u
        WHERE u.email LIKE '%@trainer.local'
          AND NOT EXISTS (
              SELECT 1 FROM manager_progress mp WHERE mp.user_id = u.id
          )
    """))

    # ── Step 3: bump existing manager_progress to ≥ level 15 ───────────
    bind.execute(sa.text(f"""
        UPDATE manager_progress mp
        SET current_level = GREATEST(mp.current_level, {PILOT_TARGET_LEVEL}),
            total_xp      = GREATEST(mp.total_xp, {PILOT_TARGET_XP}),
            updated_at    = NOW()
        FROM users u
        WHERE mp.user_id = u.id
          AND u.email LIKE '%@trainer.local'
          AND mp.current_level < {PILOT_TARGET_LEVEL}
    """))

    # ── Step 4: B5-06 — bind method@trainer.local to B2B team ──────────
    # The seed sets team_id=teams["b2b"].id, but a prod row landed before
    # the methodologist retirement seed change with team_id=NULL. Repair
    # idempotently — only updates if currently NULL.
    bind.execute(sa.text("""
        UPDATE users
        SET team_id = (
            SELECT id FROM teams
            WHERE LOWER(name) IN ('b2b', 'отдел b2b', 'b2b sales')
            ORDER BY created_at DESC LIMIT 1
        )
        WHERE email = 'method@trainer.local'
          AND team_id IS NULL
          AND EXISTS (
              SELECT 1 FROM teams
              WHERE LOWER(name) IN ('b2b', 'отдел b2b', 'b2b sales')
          )
    """))


def downgrade() -> None:
    # No-op by design. The data backfilled here represents the state
    # the seed script intends — reverting would push the platform back
    # into the broken pilot UX (level 1, profile_incomplete 409, Anna
    # 400). If a future migration needs to remove pilot users entirely,
    # write a separate purge migration.
    pass
