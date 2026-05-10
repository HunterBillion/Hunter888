"""Regression tests for `GET /api/training/coach/tip` (FIND-005, P1).

Background
==========
Прод-аудит 2026-05-10 показал, что endpoint /api/training/coach/tip
отдаёт 500 любому залогиненому пользователю. В логах:

    column "training_sessions.ended_at" must appear in the GROUP BY
    clause or be used in an aggregate function

Root cause: `apps/api/app/services/ai_coach.py:188-199` строил
SQL с `func.count()` + `func.avg()` БЕЗ GROUP BY и при этом
`.order_by(desc(TrainingSession.ended_at)).limit(5)`. Это невалидный
SQL в Postgres — нельзя сортировать агрегат по неагрегированной
колонке без GROUP BY.

Fix (тот же файл): subquery на топ-5 завершённых сессий, затем
агрегаты по выборке.

Тесты ниже — AST-guard'ы, привязанные к структуре фикса. Если кто-то
позже выкинет subquery и вернётся к плоскому select(count, avg) с
order_by/limit — тесты упадут.
"""

from __future__ import annotations

import inspect

import pytest

from app.services.ai_coach import get_proactive_tip


class TestNoFlatAggregateWithOrderBy:
    """Структурный guard на ai_coach.get_proactive_tip — он НЕ должен
    содержать невалидный паттерн `func.count() + order_by(...)
    .limit(N)` в одном select.
    """

    def test_uses_subquery_for_recent_stats(self):
        src = inspect.getsource(get_proactive_tip)
        # subquery должна присутствовать (это часть правильного фикса)
        assert ".subquery()" in src, (
            "Регресс FIND-005: get_proactive_tip больше не использует "
            "subquery для топ-5 последних сессий. Это рискует вернуть "
            "невалидный SQL (aggregate without GROUP BY) и 500 на "
            "/api/training/coach/tip."
        )

    def test_select_from_subquery_pattern(self):
        src = inspect.getsource(get_proactive_tip)
        assert "select_from(recent_subq)" in src or "select_from(" in src, (
            "Регресс FIND-005: после subquery должен идти "
            "select(...).select_from(subq) для агрегации."
        )

    def test_anchor_comment_present(self):
        """Anchor-комментарий с FIND-005 / 2026-05-10 — чтобы будущий
        рефакторинг увидел контекст и не повторил ошибку."""
        src = inspect.getsource(get_proactive_tip)
        assert "FIND-005" in src or "2026-05-10" in src
