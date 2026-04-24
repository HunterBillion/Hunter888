"""Canonical CRM-timeline read path (TZ-1 Фаза 5 cutover).

Before cutover the CRM UI reads ``ClientInteraction`` rows directly —
same as the system has always done. When
``settings.client_domain_cutover_read_enabled`` flips to ``True``, this
module becomes the single read path: only rows carrying a
``metadata.domain_event_id`` are returned, guaranteeing the timeline is
sourced from the canonical event log. Any row without that marker is
treated as pre-cutover legacy drift and hidden from the UI.

The helper keeps the read contract identical (list of ``ClientInteraction``
ORM objects) so the existing endpoints can call it without changing their
response shape.
"""

from __future__ import annotations

import uuid

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.client import ClientInteraction


def _cutover_enabled() -> bool:
    return bool(getattr(settings, "client_domain_cutover_read_enabled", False))


async def read_client_interactions(
    db: AsyncSession,
    *,
    client_id: uuid.UUID,
    limit: int | None = None,
    offset: int = 0,
) -> list[ClientInteraction]:
    """Return interactions for ``client_id``, respecting the cutover flag.

    After cutover only canonical rows (``metadata.domain_event_id NOT
    NULL``) are surfaced. Before cutover the legacy "all rows" behaviour
    is preserved so no UI regressions happen mid-migration.
    """
    stmt = (
        select(ClientInteraction)
        .where(ClientInteraction.client_id == client_id)
        .order_by(ClientInteraction.created_at.desc())
    )
    if _cutover_enabled():
        stmt = stmt.where(
            and_(
                ClientInteraction.metadata_.is_not(None),
                ClientInteraction.metadata_["domain_event_id"].astext.is_not(None),
            )
        )
    if offset:
        stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)

    result = await db.execute(stmt)
    return list(result.scalars().all())
