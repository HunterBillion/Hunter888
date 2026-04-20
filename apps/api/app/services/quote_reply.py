"""Resolve ``quoted_message_id`` from the client into a prompt fragment.

Problem: the manager clicks "Ответить" on an older AI line in the chat, types
their new message, and sends. Without context, the client LLM just sees the
new text and has no idea which of its past lines the manager is returning to.

Solution (Phase 2.5, 2026-04-18):

1. The frontend shipping the user turn includes ``quoted_message_id`` in the
   WS payload (see ``ws/training.py`` ``text.message`` handler).
2. Before we build the LLM prompt, we look up that message in ``messages``.
3. We emit a one-shot ``## ЦИТАТА МЕНЕДЖЕРА`` section that teaches the LLM
   exactly which of its own lines is being addressed, and makes it answer
   in context rather than starting fresh.

The section is transient — it is NOT persisted to EpisodicMemory, because
a quote is a per-turn hint, not a long-lived fact.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedQuote:
    """Data needed to render the quote section in the system prompt."""

    message_id: str
    role: str  # "assistant" | "user"
    content: str
    sequence_number: int

    def to_prompt_section(self, *, max_chars: int = 400) -> str:
        """Render the ``## ЦИТАТА МЕНЕДЖЕРА`` fragment for the system prompt.

        ``max_chars`` clips very long quotes so a careless paste doesn't
        blow the prompt budget. Character-aware newline handling keeps the
        quoted block readable (trailing ellipsis when cut).
        """

        quoted = self.content.strip().replace("\r", "")
        if len(quoted) > max_chars:
            quoted = quoted[: max_chars - 3].rstrip() + "…"
        # Prefix each line with '> ' markdown-style so the LLM can visually
        # separate quote from its own thought process.
        quoted_block = "\n".join(f"> {line}" for line in quoted.splitlines())

        if self.role == "assistant":
            actor = "твою собственную реплику"
        else:
            actor = "свою прошлую реплику"

        return (
            "## ЦИТАТА МЕНЕДЖЕРА\n"
            f"Менеджер отвечает именно на {actor}:\n"
            f"{quoted_block}\n"
            "Ответь, учитывая, что он возвращается к этой мысли. "
            "Не делай вид, что этой фразы не было.\n"
        )


async def resolve_quote(
    *,
    session_id: str | uuid.UUID,
    quoted_message_id: str | uuid.UUID,
    db: AsyncSession,
) -> Optional[ResolvedQuote]:
    """Look up one ``messages`` row for a session-id-scoped quote.

    Safety invariants:
      - We enforce ``quoted.session_id == session_id`` — clients cannot
        quote messages from other sessions (would leak across tenants).
      - Missing / wrong-session / corrupt UUID → returns ``None``, caller
        silently skips the injection.
    """

    from app.models.training import Message

    try:
        qid = uuid.UUID(str(quoted_message_id))
        sid = uuid.UUID(str(session_id))
    except (ValueError, TypeError) as exc:
        logger.debug("quote_reply: bad UUID quote=%r session=%r: %s",
                     quoted_message_id, session_id, exc)
        return None

    try:
        result = await db.execute(
            select(Message).where(Message.id == qid).where(Message.session_id == sid)
        )
        msg = result.scalar_one_or_none()
    except Exception as exc:  # noqa: BLE001
        logger.warning("quote_reply: select failed: %s", exc)
        return None

    if not msg:
        logger.debug(
            "quote_reply: message %s not found in session %s", qid, sid,
        )
        return None

    return ResolvedQuote(
        message_id=str(msg.id),
        role=str(getattr(msg.role, "value", msg.role)),
        content=msg.content or "",
        sequence_number=int(msg.sequence_number or 0),
    )


async def build_quote_section(
    *,
    session_id: str | uuid.UUID,
    quoted_message_id: str | uuid.UUID | None,
    db: AsyncSession,
) -> str:
    """Convenience wrapper — returns ``""`` when nothing to inject."""

    if not quoted_message_id:
        return ""
    resolved = await resolve_quote(
        session_id=session_id, quoted_message_id=quoted_message_id, db=db,
    )
    if resolved is None:
        return ""
    return resolved.to_prompt_section()
