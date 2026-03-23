import uuid

from app.services.game_crm_service import GameCRMService
from app.services.rag_legal import RAGContext, RAGResult


def test_rag_context_includes_correct_response_hint():
    context = RAGContext(
        query="что будет с имуществом",
        results=[
            RAGResult(
                chunk_id=uuid.uuid4(),
                category="property",
                fact_text="Единственное жилье защищено в ряде случаев.",
                law_article="127-ФЗ ст. 213.25",
                relevance_score=0.82,
                common_errors=["заберут любую квартиру"],
                correct_response_hint="Уточните статус жилья и исключения по иммунитету.",
            )
        ],
    )

    prompt = context.to_prompt_context()

    assert "127-ФЗ" in prompt
    assert "Подсказка" in prompt
    assert "исключения по иммунитету" in prompt


def test_game_crm_story_emotion_tracks_tension_curve():
    service = GameCRMService(None)  # type: ignore[arg-type]

    class Story:
        director_state = {"tension_curve": [0.15, 0.52, 0.87]}

    assert service._resolve_story_emotion(Story()) == "hostile"
