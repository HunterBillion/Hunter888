"""Sprint 1 task #9 — unit tests for session_start new logic.

Covers:
  - `SessionStartRequest` schema exposes `real_client_id`, `source`,
    `clone_from_session_id` (Zone 1 + Zone 4).
  - `LEAD_SOURCE_TRUST_MODIFIER` table has the expected shape.
  - `build_profile_from_real_client` maps identity (name/debt/creditors/
    notes) from `RealClient` onto a generated psychological base, and
    shifts `trust_level` by the lead-source modifier.

Integration tests of the full HTTP `POST /api/training/sessions` flow
(including ownership-404 and clone-copy semantics) live in
`test_api_endpoints.py` as smoke coverage; the deep checks are here at
the unit level where we can pin behaviour without a running DB.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.training import SessionStartRequest
from app.services.client_generator import LEAD_SOURCE_TRUST_MODIFIER


# ═══════════════════════════════════════════════════════════════════════════
# 1. Schema surface — confirm the new fields exist and are UUID-typed
# ═══════════════════════════════════════════════════════════════════════════

class TestSessionStartSchema:

    def test_real_client_id_field_exists_and_optional(self):
        req = SessionStartRequest()
        assert req.real_client_id is None
        req2 = SessionStartRequest(real_client_id=uuid.uuid4())
        assert req2.real_client_id is not None

    def test_source_field_accepts_free_form_string(self):
        req = SessionStartRequest(source="crm_chat")
        assert req.source == "crm_chat"

    def test_clone_from_session_id_field_exists(self):
        req = SessionStartRequest()
        assert req.clone_from_session_id is None
        src = uuid.uuid4()
        req2 = SessionStartRequest(clone_from_session_id=src)
        assert req2.clone_from_session_id == src

    def test_invalid_uuid_rejected(self):
        with pytest.raises(Exception):
            SessionStartRequest(real_client_id="not-a-uuid")


# ═══════════════════════════════════════════════════════════════════════════
# 2. LEAD_SOURCE_TRUST_MODIFIER — static table invariants
# ═══════════════════════════════════════════════════════════════════════════

class TestLeadSourceTrustModifier:

    def test_cold_base_is_negative(self):
        # Cold contact → low baseline trust.
        assert LEAD_SOURCE_TRUST_MODIFIER["cold_base"] == -2

    def test_referral_is_positive(self):
        # Friend referral → trust bonus.
        assert LEAD_SOURCE_TRUST_MODIFIER["referral"] == 2

    def test_in_referral_direct_is_strongest(self):
        # Direct referral from existing client is the strongest positive.
        assert LEAD_SOURCE_TRUST_MODIFIER["in_referral_direct"] == 3

    def test_modifiers_bounded(self):
        # Sanity guard: nothing above ±3 (else the clamp in build_profile
        # becomes a lie).
        for key, val in LEAD_SOURCE_TRUST_MODIFIER.items():
            assert -3 <= val <= 3, f"{key}={val} outside expected range"


# ═══════════════════════════════════════════════════════════════════════════
# 3. build_profile_from_real_client — identity overrides + trust shift
# ═══════════════════════════════════════════════════════════════════════════

def _make_real_client(
    *,
    full_name: str = "Иванов Сергей Петрович",
    debt_amount: Decimal | None = Decimal("1200000.00"),
    source: str | None = "referral",
    creditors: list | None = None,
    notes: str | None = "Есть ипотека",
):
    rc = SimpleNamespace()
    rc.full_name = full_name
    rc.debt_amount = debt_amount
    rc.source = source
    rc.debt_details = (
        {"creditors": creditors} if creditors is not None else None
    )
    rc.notes = notes
    return rc


def _make_fake_gen(
    *,
    age: int = 42,
    gender: str = "male",
    city: str = "Москва",
    trust_level: int = 3,
    total_debt: int = 500_000,
    creditors: list | None = None,
):
    return SimpleNamespace(
        age=age,
        gender=gender,
        city=city,
        archetype_code="skeptic",
        education="высшее",
        total_debt=total_debt,
        creditors=creditors or [],
        income=60_000,
        income_type="official",
        fears=["потеря жилья"],
        soft_spot="семья",
        breaking_point="угроза детям",
        trust_level=trust_level,
        resistance_level=6,
    )


class TestBuildProfileFromRealClient:

    @pytest.mark.asyncio
    async def test_name_always_from_crm(self):
        """The whole point of Zone 1: the call must feel like it's with
        the same Иванов the user just opened, not a random generated name."""
        from app.services import client_generator as cg

        real = _make_real_client()
        fake_gen = _make_fake_gen()

        db = MagicMock()
        db.flush = AsyncMock()
        db.add = MagicMock()

        with patch.object(cg, "generate_client", new=AsyncMock(return_value=fake_gen)):
            profile = await cg.build_profile_from_real_client(
                real_client=real,
                session_id=uuid.uuid4(),
                db=db,
            )
        assert profile.full_name == "Иванов Сергей Петрович"
        db.add.assert_called_once()
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_debt_overrides_generator_when_known(self):
        from app.services import client_generator as cg

        real = _make_real_client(debt_amount=Decimal("1200000.00"))
        fake_gen = _make_fake_gen(total_debt=500_000)

        db = MagicMock()
        db.flush = AsyncMock()
        db.add = MagicMock()

        with patch.object(cg, "generate_client", new=AsyncMock(return_value=fake_gen)):
            profile = await cg.build_profile_from_real_client(
                real_client=real,
                session_id=uuid.uuid4(),
                db=db,
            )
        assert profile.total_debt == 1_200_000

    @pytest.mark.asyncio
    async def test_debt_falls_back_to_generator_if_crm_missing(self):
        from app.services import client_generator as cg

        real = _make_real_client(debt_amount=None)
        fake_gen = _make_fake_gen(total_debt=500_000)

        db = MagicMock()
        db.flush = AsyncMock()
        db.add = MagicMock()

        with patch.object(cg, "generate_client", new=AsyncMock(return_value=fake_gen)):
            profile = await cg.build_profile_from_real_client(
                real_client=real,
                session_id=uuid.uuid4(),
                db=db,
            )
        assert profile.total_debt == 500_000

    @pytest.mark.asyncio
    async def test_creditors_copied_from_debt_details(self):
        from app.services import client_generator as cg

        explicit = [
            {"name": "Сбербанк", "amount": 500000},
            {"name": "Тинькофф", "amount": 300000},
        ]
        real = _make_real_client(creditors=explicit)
        fake_gen = _make_fake_gen(creditors=[])

        db = MagicMock()
        db.flush = AsyncMock()
        db.add = MagicMock()

        with patch.object(cg, "generate_client", new=AsyncMock(return_value=fake_gen)):
            profile = await cg.build_profile_from_real_client(
                real_client=real,
                session_id=uuid.uuid4(),
                db=db,
            )
        assert profile.creditors == explicit

    @pytest.mark.asyncio
    async def test_trust_shifted_by_lead_source(self):
        """Referral adds +2 to the generator's trust baseline (clamped 1-10)."""
        from app.services import client_generator as cg

        real = _make_real_client(source="referral")
        fake_gen = _make_fake_gen(trust_level=3)

        db = MagicMock()
        db.flush = AsyncMock()
        db.add = MagicMock()

        with patch.object(cg, "generate_client", new=AsyncMock(return_value=fake_gen)):
            profile = await cg.build_profile_from_real_client(
                real_client=real,
                session_id=uuid.uuid4(),
                db=db,
            )
        # referral modifier = +2, base = 3 → 5.
        assert profile.trust_level == 5
        assert profile.lead_source == "referral"

    @pytest.mark.asyncio
    async def test_trust_clamped_to_range(self):
        """Absurd baseline + modifier shouldn't push trust outside [1, 10]."""
        from app.services import client_generator as cg

        real = _make_real_client(source="in_referral_direct")  # +3
        fake_gen = _make_fake_gen(trust_level=10)

        db = MagicMock()
        db.flush = AsyncMock()
        db.add = MagicMock()

        with patch.object(cg, "generate_client", new=AsyncMock(return_value=fake_gen)):
            profile = await cg.build_profile_from_real_client(
                real_client=real,
                session_id=uuid.uuid4(),
                db=db,
            )
        assert profile.trust_level == 10  # clamped

    @pytest.mark.asyncio
    async def test_unknown_crm_source_falls_back_to_cold_base(self):
        from app.services import client_generator as cg

        real = _make_real_client(source="мамкина_база")
        fake_gen = _make_fake_gen(trust_level=3)

        db = MagicMock()
        db.flush = AsyncMock()
        db.add = MagicMock()

        with patch.object(cg, "generate_client", new=AsyncMock(return_value=fake_gen)):
            profile = await cg.build_profile_from_real_client(
                real_client=real,
                session_id=uuid.uuid4(),
                db=db,
            )
        assert profile.lead_source == "cold_base"
        # cold_base modifier = -2 → trust 3 - 2 = 1.
        assert profile.trust_level == 1

    @pytest.mark.asyncio
    async def test_crm_notes_preserved(self):
        from app.services import client_generator as cg

        real = _make_real_client(notes="Звонил в прошлый раз — был в панике")
        fake_gen = _make_fake_gen()

        db = MagicMock()
        db.flush = AsyncMock()
        db.add = MagicMock()

        with patch.object(cg, "generate_client", new=AsyncMock(return_value=fake_gen)):
            profile = await cg.build_profile_from_real_client(
                real_client=real,
                session_id=uuid.uuid4(),
                db=db,
            )
        assert profile.crm_notes == "Звонил в прошлый раз — был в панике"

    @pytest.mark.asyncio
    async def test_custom_archetype_forwarded_to_generator(self):
        from app.services import client_generator as cg

        real = _make_real_client()
        fake_gen = _make_fake_gen()
        mock_gen = AsyncMock(return_value=fake_gen)

        db = MagicMock()
        db.flush = AsyncMock()
        db.add = MagicMock()

        with patch.object(cg, "generate_client", new=mock_gen):
            await cg.build_profile_from_real_client(
                real_client=real,
                session_id=uuid.uuid4(),
                db=db,
                custom_archetype="anxious",
                custom_profession="retail",
            )
        # The generator call should have received the forwarded archetype.
        call_kwargs = mock_gen.await_args.kwargs
        assert call_kwargs["archetype_code"] == "anxious"
        assert call_kwargs["profession_category"] == "retail"
