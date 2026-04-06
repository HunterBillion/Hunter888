"""Expand scenarios from 15 to 60 (DOC_05).

Revision ID: 20260404_008
Revises: 20260404_007
Create Date: 2026-04-04

NOTE: scenario_templates.code is VARCHAR(50), NOT an enum.
New scenario codes are stored as plain strings — no ALTER TYPE needed.
The legacy 'scenarios' table uses 'scenariotype' enum (cold_call/warm_call/etc.)
which is a different concept and remains unchanged.
"""

from alembic import op


revision = "20260404_008"
down_revision = "20260404_007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # scenario_templates.code is VARCHAR(50) — new codes are just data, no schema change.
    # Rename couple_call → special_couple in scenario_templates for consistency
    op.execute("""
        UPDATE scenario_templates SET code = 'special_couple' WHERE code = 'couple_call'
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE scenario_templates SET code = 'couple_call' WHERE code = 'special_couple'
    """)
