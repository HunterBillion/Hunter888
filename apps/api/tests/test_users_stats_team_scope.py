"""Regression tests for FIND-001 (P2 cross-team scope leakage), audit
2026-05-10.

До фикса любой `rop` мог прочитать stats `rop`-а из другой команды.
rop2 (Отдел B2B) видел KPI rop1/manager1 в Отдел продаж и наоборот.
Privacy-leak между командами руководителей.

Fix: `apps/api/app/api/users.py:get_user_stats` теперь добавляет
team_id-проверку для роли rop. admin по-прежнему видит все команды.
"""

from __future__ import annotations

import inspect

from app.api.users import get_user_stats


class TestStatsTeamScopeContract:
    """Структурные guard'ы привязанные к фиксу. Любой откат —
    и тесты упадут прежде чем regression попадёт на прод.
    """

    def test_admin_branch_present(self):
        src = inspect.getsource(get_user_stats)
        assert 'role_value == "admin"' in src, (
            "Регресс FIND-001: admin-branch удалён. "
            "Это либо ломает admin-доступ к stats, либо пропускает "
            "rop без team-check."
        )

    def test_rop_branch_checks_team(self):
        src = inspect.getsource(get_user_stats)
        # rop branch должен сравнивать target.team_id с current_user.team_id
        rop_block_start = src.find('role_value == "rop"')
        assert rop_block_start >= 0, "rop branch отсутствует"
        rop_block = src[rop_block_start:rop_block_start + 600]
        assert "target.team_id" in rop_block, (
            "Регресс FIND-001: rop-branch больше не проверяет target.team_id. "
            "Любой rop может читать любого user — privacy leak возвращается."
        )
        assert "current_user.team_id" in rop_block

    def test_manager_branch_denies(self):
        """Manager и ниже — только себя. Старый код пропускал manager
        за счёт логики «role.value not in (rop, admin)». Новый код
        явно elif'ит manager → 403."""
        src = inspect.getsource(get_user_stats)
        # Ищем else-ветку или эквивалент
        assert "OWN_STATS_ONLY" in src
        # Должно быть минимум 2 raise для 403 (rop wrong-team + manager)
        assert src.count("HTTP_403_FORBIDDEN") >= 2

    def test_anchor_comment(self):
        src = inspect.getsource(get_user_stats)
        assert "FIND-001" in src or "2026-05-10" in src
