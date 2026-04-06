"""Expand scenarios from 15 to 60 (DOC_05).

Revision ID: 20260404_008
Revises: 20260404_007
Create Date: 2026-04-04

Adds 45 new ScenarioCode enum values.
Renames couple_call → special_couple for consistency.
"""

from alembic import op


revision = "20260404_008"
down_revision = "20260404_007"
branch_labels = None
depends_on = None

NEW_CODES = [
    "cold_social", "cold_database", "cold_premium", "cold_event", "cold_expired", "cold_insurance",
    "warm_repeat", "warm_webinar", "warm_vip", "warm_ghosted", "warm_complaint", "warm_competitor",
    "in_chatbot", "in_partner", "in_complaint", "in_urgent", "in_corporate",
    "special_ghosted", "special_urgent", "special_guarantor", "special_couple",
    "special_inheritance", "special_psychologist", "special_vip", "special_medical", "special_boss",
    "follow_up_first", "follow_up_second", "follow_up_third", "follow_up_rescue", "follow_up_memory",
    "crisis_collector", "crisis_pre_court", "crisis_business", "crisis_criminal", "crisis_full",
    "compliance_basic", "compliance_docs", "compliance_legal", "compliance_advanced", "compliance_full",
    "multi_party_basic", "multi_party_lawyer", "multi_party_creditors", "multi_party_family", "multi_party_full",
]


def upgrade() -> None:
    # Add new enum values to scenariocode type
    for code in NEW_CODES:
        op.execute(f"ALTER TYPE scenariocode ADD VALUE IF NOT EXISTS '{code}'")

    # Rename couple_call → special_couple in existing data
    op.execute("""
        UPDATE scenario_templates SET code = 'special_couple' WHERE code = 'couple_call'
    """)
    op.execute("""
        UPDATE scenarios SET scenario_type = 'special_couple' WHERE scenario_type = 'couple_call'
    """)


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values
    # Revert data rename
    op.execute("""
        UPDATE scenario_templates SET code = 'couple_call' WHERE code = 'special_couple'
    """)
    op.execute("""
        UPDATE scenarios SET scenario_type = 'couple_call' WHERE scenario_type = 'special_couple'
    """)
