import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user
from app.database import get_db
from app.models.character import Character
from app.models.scenario import Scenario
from app.models.script import Script
from app.models.user import User
from app.schemas.training import ScenarioResponse

router = APIRouter()


# Recommended difficulty range per experience level (used for sorting, NOT filtering)
_DIFFICULTY_SWEET_SPOT = {
    "beginner": 3,
    "intermediate": 5,
    "advanced": 7,
}


@router.get("/", response_model=list[ScenarioResponse])
async def list_scenarios(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all active scenarios.

    Sorted by closeness to user's experience level sweet spot (if set),
    so recommended scenarios appear first. All scenarios are always returned.
    """
    query = (
        select(Scenario, Character.name.label("character_name"))
        .outerjoin(Character, Scenario.character_id == Character.id)
        .where(Scenario.is_active.is_(True))
    )

    # Sort by relevance to experience level (closer to sweet spot = first)
    prefs = user.preferences or {}
    exp_level = prefs.get("experience_level")
    sweet = _DIFFICULTY_SWEET_SPOT.get(exp_level, 5) if exp_level else 5  # type: ignore[arg-type]

    result = await db.execute(query)
    rows = result.all()

    # Sort: closest to sweet spot first, then by difficulty ascending
    sorted_rows = sorted(rows, key=lambda r: (abs(r.Scenario.difficulty - sweet), r.Scenario.difficulty))

    return [
        ScenarioResponse(
            id=row.Scenario.id,
            title=row.Scenario.title,
            description=row.Scenario.description,
            scenario_type=row.Scenario.scenario_type.value,
            difficulty=row.Scenario.difficulty,
            estimated_duration_minutes=row.Scenario.estimated_duration_minutes,
            character_name=row.character_name,
        )
        for row in sorted_rows
    ]


@router.get("/{scenario_id}")
async def get_scenario(
    scenario_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get scenario with character and script details."""
    result = await db.execute(
        select(Scenario).where(Scenario.id == scenario_id, Scenario.is_active.is_(True))
    )
    scenario = result.scalar_one_or_none()
    if not scenario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scenario not found")

    # Get character
    char_result = await db.execute(select(Character).where(Character.id == scenario.character_id))
    character = char_result.scalar_one_or_none()

    # Get script with checkpoints
    script_data = None
    if scenario.script_id:
        script_result = await db.execute(
            select(Script).options(selectinload(Script.checkpoints)).where(Script.id == scenario.script_id)
        )
        script = script_result.scalar_one_or_none()
        if script:
            script_data = {
                "id": str(script.id),
                "title": script.title,
                "checkpoints": [
                    {
                        "title": cp.title,
                        "description": cp.description,
                        "order_index": cp.order_index,
                        "weight": cp.weight,
                    }
                    for cp in sorted(script.checkpoints, key=lambda c: c.order_index)
                ],
            }

    return {
        "id": str(scenario.id),
        "title": scenario.title,
        "description": scenario.description,
        "scenario_type": scenario.scenario_type.value,
        "difficulty": scenario.difficulty,
        "estimated_duration_minutes": scenario.estimated_duration_minutes,
        "character": {
            "id": str(character.id),
            "name": character.name,
            "slug": character.slug,
            "description": character.description,
            "difficulty": character.difficulty,
            "initial_emotion": character.initial_emotion.value,
        } if character else None,
        "script": script_data,
    }
