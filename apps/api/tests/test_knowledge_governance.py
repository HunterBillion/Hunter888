import uuid

from app.services.knowledge_governance import (
    can_use_for_recommendation,
    needs_source_warning,
    normalize_knowledge_status,
)
from app.services.rag_legal import RAGContext, RAGResult


def _rag(status: str) -> RAGResult:
    return RAGResult(
        chunk_id=uuid.uuid4(),
        category="procedure",
        fact_text=f"Факт со статусом {status}",
        law_article="127-ФЗ",
        relevance_score=0.9,
        knowledge_status=status,
    )


def test_knowledge_status_normalization():
    assert normalize_knowledge_status("OUTDATED") == "outdated"
    assert normalize_knowledge_status("unknown") == "actual"


def test_outdated_source_is_not_recommendable():
    assert can_use_for_recommendation("actual")
    assert not can_use_for_recommendation("outdated")
    assert needs_source_warning("disputed")
    assert needs_source_warning("needs_review")


def test_rag_prompt_context_excludes_outdated_and_marks_disputed():
    context = RAGContext(query="банкротство", results=[
        _rag("outdated"),
        _rag("disputed"),
    ])
    prompt = context.to_prompt_context()
    assert "outdated" not in prompt
    assert "disputed" in prompt
    assert "использовать осторожно" in prompt


def test_rag_prompt_context_empty_when_only_outdated():
    context = RAGContext(query="банкротство", results=[_rag("outdated")])
    assert context.to_prompt_context() == ""
