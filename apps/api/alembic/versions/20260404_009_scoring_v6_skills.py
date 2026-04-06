"""Add 4 new skill columns for 10-skill radar (DOC_06).

Revision ID: 20260404_009
Revises: 20260404_008
Create Date: 2026-04-04

Expands skill radar from 6 to 10:
+ time_management, adaptation, legal_knowledge, rapport_building
"""

from alembic import op
import sqlalchemy as sa


revision = "20260404_009"
down_revision = "20260404_008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("manager_progress", sa.Column(
        "skill_time_management", sa.Integer(), nullable=False, server_default="50",
    ))
    op.add_column("manager_progress", sa.Column(
        "skill_adaptation", sa.Integer(), nullable=False, server_default="50",
    ))
    op.add_column("manager_progress", sa.Column(
        "skill_legal_knowledge", sa.Integer(), nullable=False, server_default="50",
    ))
    op.add_column("manager_progress", sa.Column(
        "skill_rapport_building", sa.Integer(), nullable=False, server_default="50",
    ))

    op.create_check_constraint("ck_skill_time_mgmt", "manager_progress",
        "skill_time_management BETWEEN 0 AND 100")
    op.create_check_constraint("ck_skill_adaptation", "manager_progress",
        "skill_adaptation BETWEEN 0 AND 100")
    op.create_check_constraint("ck_skill_legal", "manager_progress",
        "skill_legal_knowledge BETWEEN 0 AND 100")
    op.create_check_constraint("ck_skill_rapport", "manager_progress",
        "skill_rapport_building BETWEEN 0 AND 100")


def downgrade() -> None:
    op.drop_constraint("ck_skill_rapport", "manager_progress")
    op.drop_constraint("ck_skill_legal", "manager_progress")
    op.drop_constraint("ck_skill_adaptation", "manager_progress")
    op.drop_constraint("ck_skill_time_mgmt", "manager_progress")
    op.drop_column("manager_progress", "skill_rapport_building")
    op.drop_column("manager_progress", "skill_legal_knowledge")
    op.drop_column("manager_progress", "skill_adaptation")
    op.drop_column("manager_progress", "skill_time_management")
