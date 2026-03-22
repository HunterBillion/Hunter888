"""CRUD endpoints for custom character presets."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.custom_character import CustomCharacter
from app.models.user import User

router = APIRouter()


class CustomCharacterCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    archetype: str = Field(..., min_length=1, max_length=50)
    profession: str = Field(..., min_length=1, max_length=50)
    lead_source: str = Field(..., min_length=1, max_length=50)
    difficulty: int = Field(5, ge=1, le=10)
    description: str | None = None


class CustomCharacterResponse(BaseModel):
    id: str
    name: str
    archetype: str
    profession: str
    lead_source: str
    difficulty: int
    description: str | None
    created_at: str

    model_config = {"from_attributes": True}


@router.get("/characters/custom")
async def list_custom_characters(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CustomCharacterResponse]:
    """List all custom characters for the current user."""
    result = await db.execute(
        select(CustomCharacter)
        .where(CustomCharacter.user_id == user.id)
        .order_by(CustomCharacter.created_at.desc())
    )
    chars = result.scalars().all()
    return [
        CustomCharacterResponse(
            id=str(c.id),
            name=c.name,
            archetype=c.archetype,
            profession=c.profession,
            lead_source=c.lead_source,
            difficulty=c.difficulty,
            description=c.description,
            created_at=c.created_at.isoformat(),
        )
        for c in chars
    ]


@router.post("/characters/custom", status_code=201)
async def create_custom_character(
    data: CustomCharacterCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CustomCharacterResponse:
    """Save a custom character preset."""
    # Limit: max 20 custom characters per user
    count_result = await db.execute(
        select(CustomCharacter).where(CustomCharacter.user_id == user.id)
    )
    if len(count_result.scalars().all()) >= 20:
        raise HTTPException(status_code=400, detail="Максимум 20 сохранённых персонажей")

    char = CustomCharacter(
        user_id=user.id,
        name=data.name,
        archetype=data.archetype,
        profession=data.profession,
        lead_source=data.lead_source,
        difficulty=data.difficulty,
        description=data.description,
    )
    db.add(char)
    await db.commit()
    await db.refresh(char)

    return CustomCharacterResponse(
        id=str(char.id),
        name=char.name,
        archetype=char.archetype,
        profession=char.profession,
        lead_source=char.lead_source,
        difficulty=char.difficulty,
        description=char.description,
        created_at=char.created_at.isoformat(),
    )


@router.delete("/characters/custom/{character_id}", status_code=204)
async def delete_custom_character(
    character_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a custom character preset."""
    result = await db.execute(
        select(CustomCharacter).where(
            CustomCharacter.id == character_id,
            CustomCharacter.user_id == user.id,
        )
    )
    char = result.scalar_one_or_none()
    if not char:
        raise HTTPException(status_code=404, detail="Персонаж не найден")

    await db.execute(
        delete(CustomCharacter).where(CustomCharacter.id == character_id)
    )
    await db.commit()
