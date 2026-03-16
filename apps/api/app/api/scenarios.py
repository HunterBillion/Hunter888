from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models.scenario import Scenario
from app.models.user import User
from app.schemas.training import ScenarioResponse

router = APIRouter()


@router.get("/", response_model=list[ScenarioResponse])
async def list_scenarios(
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Scenario).where(Scenario.is_active.is_(True)))
    return result.scalars().all()
