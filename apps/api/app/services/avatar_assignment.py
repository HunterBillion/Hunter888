"""Avatar Model Assignment — maps archetypes to VRM models.

Phase 2: Each ClientStory gets a persistent VRM model based on archetype.
Similar pattern to voice_assignment in tts.py.
"""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ── VRM Model Pool ─────────────────────────────────────────────────────────────
# Keys match ClientStory.vrm_model_id
# URLs are relative to /public/models/ on frontend

VRM_MODEL_POOL = {
    "young_male":    "/models/young_male.vrm",
    "mature_male":   "/models/mature_male.vrm",
    "elderly_male":  "/models/elderly_male.vrm",
    "young_female":  "/models/young_female.vrm",
    "mature_female": "/models/mature_female.vrm",
}

# Default fallback
DEFAULT_MODEL = "young_male"

# ── Archetype → Model Mapping ──────────────────────────────────────────────────
# Maps archetype_code to {gender, age} for model selection

ARCHETYPE_MODEL_MAP: dict[str, dict[str, str]] = {
    # Resistance group
    "skeptic": {"gender": "male", "age": "young"},
    "blamer": {"gender": "male", "age": "mature"},
    "sarcastic": {"gender": "male", "age": "young"},
    "aggressive": {"gender": "male", "age": "mature"},
    "hostile": {"gender": "male", "age": "mature"},
    "stubborn": {"gender": "male", "age": "elderly"},
    "conspiracy": {"gender": "male", "age": "elderly"},
    "righteous": {"gender": "male", "age": "mature"},
    "litigious": {"gender": "female", "age": "mature"},
    "scorched_earth": {"gender": "male", "age": "mature"},
    # Emotional group
    "grateful": {"gender": "female", "age": "young"},
    "anxious": {"gender": "female", "age": "young"},
    "ashamed": {"gender": "male", "age": "young"},
    "overwhelmed": {"gender": "female", "age": "young"},
    "desperate": {"gender": "female", "age": "young"},
    "crying": {"gender": "female", "age": "young"},
    "guilty": {"gender": "male", "age": "young"},
    "mood_swinger": {"gender": "female", "age": "young"},
    "frozen": {"gender": "female", "age": "young"},
    "hysteric": {"gender": "female", "age": "young"},
    # Control group
    "pragmatic": {"gender": "male", "age": "mature"},
    "shopper": {"gender": "female", "age": "mature"},
    "negotiator": {"gender": "male", "age": "mature"},
    "know_it_all": {"gender": "male", "age": "mature"},
    "manipulator": {"gender": "male", "age": "mature"},
    "lawyer_client": {"gender": "female", "age": "mature"},
    "auditor": {"gender": "male", "age": "mature"},
    "strategist": {"gender": "male", "age": "mature"},
    "power_player": {"gender": "male", "age": "mature"},
    "puppet_master": {"gender": "male", "age": "mature"},
    # Special group
    "elderly": {"gender": "male", "age": "elderly"},
    "young_debtor": {"gender": "male", "age": "young"},
    "couple": {"gender": "female", "age": "young"},
    "rushed": {"gender": "male", "age": "young"},
    "referred": {"gender": "female", "age": "young"},
    "returner": {"gender": "male", "age": "mature"},
    # Cognitive group
    "overthinker": {"gender": "male", "age": "young"},
    "concrete": {"gender": "male", "age": "mature"},
    "storyteller": {"gender": "female", "age": "elderly"},
    "misinformed": {"gender": "male", "age": "young"},
    # Professional group
    "teacher": {"gender": "female", "age": "mature"},
    "doctor": {"gender": "male", "age": "mature"},
    "military": {"gender": "male", "age": "mature"},
    "accountant": {"gender": "female", "age": "mature"},
    "salesperson": {"gender": "male", "age": "young"},
    "psychologist": {"gender": "female", "age": "mature"},
}


def resolve_model_key(archetype_code: str | None = None, gender: str | None = None) -> str:
    """Resolve VRM model key from archetype code or gender hint."""
    if archetype_code and archetype_code in ARCHETYPE_MODEL_MAP:
        mapping = ARCHETYPE_MODEL_MAP[archetype_code]
        return f"{mapping['age']}_{mapping['gender']}"

    # Fallback by gender
    if gender and gender.lower() in ("f", "female"):
        return "young_female"
    return DEFAULT_MODEL


def get_model_url(model_key: str) -> str:
    """Get frontend URL for a VRM model."""
    return VRM_MODEL_POOL.get(model_key, VRM_MODEL_POOL[DEFAULT_MODEL])


async def assign_model(
    client_story_id: str,
    archetype_code: str | None,
    gender: str | None,
    db: AsyncSession,
) -> str:
    """Assign VRM model to a ClientStory. Returns model URL."""
    from app.models.roleplay import ClientStory

    model_key = resolve_model_key(archetype_code, gender)
    model_url = get_model_url(model_key)

    try:
        story = await db.get(ClientStory, uuid.UUID(client_story_id))
        if story:
            story.vrm_model_id = model_key
            await db.flush()
    except Exception:
        logger.debug("Failed to persist vrm_model_id for story %s", client_story_id)

    return model_url
