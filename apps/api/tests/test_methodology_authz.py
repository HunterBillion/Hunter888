"""TZ-8 PR-B — :func:`check_methodology_team_access` authorisation matrix.

Mirrors §4.2 of ``docs/TZ-8_methodology_rag.md``. Every cell of the
matrix has a test; missing a test for a role × mode pair lets a
future PR weaken the gate silently.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


def _user(role: str, *, user_id=None, team_id=None):
    """User-shaped mock with the attributes the gate reads."""
    u = MagicMock()
    u.id = user_id or uuid.uuid4()
    u.role = MagicMock()
    u.role.value = role
    u.team_id = team_id
    return u


# ── Calls without a chunk_id (list / create paths) ──────────────────────


class TestTeamScopeAccess:
    @pytest.mark.asyncio
    async def test_admin_any_team_read(self):
        from app.core.deps import check_methodology_team_access

        admin = _user("admin")
        await check_methodology_team_access(
            admin, team_id=uuid.uuid4(), mode="read"
        )

    @pytest.mark.asyncio
    async def test_admin_any_team_write(self):
        from app.core.deps import check_methodology_team_access

        admin = _user("admin")
        await check_methodology_team_access(
            admin, team_id=uuid.uuid4(), mode="write"
        )

    @pytest.mark.asyncio
    async def test_rop_same_team_write(self):
        from app.core.deps import check_methodology_team_access

        team_id = uuid.uuid4()
        rop = _user("rop", team_id=team_id)
        await check_methodology_team_access(rop, team_id=team_id, mode="write")

    @pytest.mark.asyncio
    async def test_rop_different_team_rejected(self):
        from fastapi import HTTPException

        from app.core.deps import check_methodology_team_access

        rop = _user("rop", team_id=uuid.uuid4())
        with pytest.raises(HTTPException) as exc:
            await check_methodology_team_access(
                rop, team_id=uuid.uuid4(), mode="write"
            )
        assert exc.value.status_code == 403
        assert "outside your team" in str(exc.value.detail).lower()

    @pytest.mark.asyncio
    async def test_rop_no_team_rejected(self):
        from fastapi import HTTPException

        from app.core.deps import check_methodology_team_access

        rop = _user("rop", team_id=None)
        with pytest.raises(HTTPException) as exc:
            await check_methodology_team_access(
                rop, team_id=uuid.uuid4(), mode="write"
            )
        assert exc.value.status_code == 403
        assert "not assigned" in str(exc.value.detail).lower()

    @pytest.mark.asyncio
    async def test_manager_same_team_read(self):
        from app.core.deps import check_methodology_team_access

        team_id = uuid.uuid4()
        manager = _user("manager", team_id=team_id)
        await check_methodology_team_access(
            manager, team_id=team_id, mode="read"
        )

    @pytest.mark.asyncio
    async def test_manager_same_team_write_rejected(self):
        from fastapi import HTTPException

        from app.core.deps import check_methodology_team_access

        team_id = uuid.uuid4()
        manager = _user("manager", team_id=team_id)
        with pytest.raises(HTTPException) as exc:
            await check_methodology_team_access(
                manager, team_id=team_id, mode="write"
            )
        assert exc.value.status_code == 403
        assert "cannot author" in str(exc.value.detail).lower()

    @pytest.mark.asyncio
    async def test_manager_different_team_rejected(self):
        from fastapi import HTTPException

        from app.core.deps import check_methodology_team_access

        manager = _user("manager", team_id=uuid.uuid4())
        with pytest.raises(HTTPException) as exc:
            await check_methodology_team_access(
                manager, team_id=uuid.uuid4(), mode="read"
            )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_methodologist_role_default_denied(self):
        """methodologist is in UserRole enum but not in the allow-list:
        the gate must default-deny rather than fall through to admin."""
        from fastapi import HTTPException

        from app.core.deps import check_methodology_team_access

        m = _user("methodologist", team_id=uuid.uuid4())
        with pytest.raises(HTTPException) as exc:
            await check_methodology_team_access(
                m, team_id=uuid.uuid4(), mode="write"
            )
        assert exc.value.status_code == 403


# ── Calls with chunk_id (read / update / delete / status paths) ─────────


class TestChunkIdScopeAccess:
    """When a chunk_id is supplied, the gate must:
      1. Load the row.
      2. Reject when role/team don't match against the row's team_id.
      3. Return the loaded row so the endpoint avoids a second SELECT.
    """

    def _mock_db_with_chunk(self, team_id):
        chunk = MagicMock()
        chunk.id = uuid.uuid4()
        chunk.team_id = team_id

        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=chunk)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result)
        return db, chunk

    @pytest.mark.asyncio
    async def test_admin_returns_loaded_chunk(self):
        from app.core.deps import check_methodology_team_access

        admin = _user("admin")
        team_id = uuid.uuid4()
        db, chunk = self._mock_db_with_chunk(team_id)
        out = await check_methodology_team_access(
            admin, chunk_id=chunk.id, db=db, mode="write"
        )
        assert out is chunk

    @pytest.mark.asyncio
    async def test_rop_same_team_returns_chunk(self):
        from app.core.deps import check_methodology_team_access

        team_id = uuid.uuid4()
        rop = _user("rop", team_id=team_id)
        db, chunk = self._mock_db_with_chunk(team_id)
        out = await check_methodology_team_access(
            rop, chunk_id=chunk.id, db=db, mode="write"
        )
        assert out is chunk

    @pytest.mark.asyncio
    async def test_rop_other_team_rejected(self):
        from fastapi import HTTPException

        from app.core.deps import check_methodology_team_access

        rop = _user("rop", team_id=uuid.uuid4())
        db, chunk = self._mock_db_with_chunk(uuid.uuid4())  # different team
        with pytest.raises(HTTPException) as exc:
            await check_methodology_team_access(
                rop, chunk_id=chunk.id, db=db, mode="write"
            )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_chunk_not_found_returns_404(self):
        from fastapi import HTTPException

        from app.core.deps import check_methodology_team_access

        admin = _user("admin")
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=None)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result)
        with pytest.raises(HTTPException) as exc:
            await check_methodology_team_access(
                admin, chunk_id=uuid.uuid4(), db=db, mode="read"
            )
        assert exc.value.status_code == 404


# ── Argument validation ─────────────────────────────────────────────────


class TestGateArgumentValidation:
    @pytest.mark.asyncio
    async def test_both_team_id_and_chunk_id_rejected(self):
        from app.core.deps import check_methodology_team_access

        admin = _user("admin")
        with pytest.raises(ValueError, match="exactly one"):
            await check_methodology_team_access(
                admin, team_id=uuid.uuid4(), chunk_id=uuid.uuid4(), mode="read"
            )

    @pytest.mark.asyncio
    async def test_neither_team_id_nor_chunk_id_rejected(self):
        from app.core.deps import check_methodology_team_access

        admin = _user("admin")
        with pytest.raises(ValueError, match="exactly one"):
            await check_methodology_team_access(admin, mode="read")

    @pytest.mark.asyncio
    async def test_unknown_mode_rejected(self):
        from app.core.deps import check_methodology_team_access

        admin = _user("admin")
        with pytest.raises(ValueError, match="mode must be"):
            await check_methodology_team_access(
                admin, team_id=uuid.uuid4(), mode="execute"
            )

    @pytest.mark.asyncio
    async def test_chunk_id_without_db_rejected(self):
        from app.core.deps import check_methodology_team_access

        admin = _user("admin")
        with pytest.raises(ValueError, match="db is required"):
            await check_methodology_team_access(
                admin, chunk_id=uuid.uuid4(), mode="read"
            )
