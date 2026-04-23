"""Governance rules for legal/news knowledge sources."""

from __future__ import annotations


KNOWLEDGE_STATUS_ACTUAL = "actual"
KNOWLEDGE_STATUS_DISPUTED = "disputed"
KNOWLEDGE_STATUS_OUTDATED = "outdated"
KNOWLEDGE_STATUS_NEEDS_REVIEW = "needs_review"

KNOWLEDGE_STATUSES = {
    KNOWLEDGE_STATUS_ACTUAL,
    KNOWLEDGE_STATUS_DISPUTED,
    KNOWLEDGE_STATUS_OUTDATED,
    KNOWLEDGE_STATUS_NEEDS_REVIEW,
}


def normalize_knowledge_status(status: object) -> str:
    value = str(status or "").strip().lower()
    return value if value in KNOWLEDGE_STATUSES else KNOWLEDGE_STATUS_ACTUAL


def can_use_for_recommendation(status: object) -> bool:
    return normalize_knowledge_status(status) != KNOWLEDGE_STATUS_OUTDATED


def needs_source_warning(status: object) -> bool:
    return normalize_knowledge_status(status) in {
        KNOWLEDGE_STATUS_DISPUTED,
        KNOWLEDGE_STATUS_NEEDS_REVIEW,
    }
