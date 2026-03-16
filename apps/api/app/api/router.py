from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.consent import router as consent_router
from app.api.health import router as health_router
from app.api.scenarios import router as scenarios_router
from app.api.training import router as training_router
from app.api.users import router as users_router

api_router = APIRouter()

api_router.include_router(health_router, tags=["monitoring"])
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(users_router, prefix="/users", tags=["users"])
api_router.include_router(consent_router, prefix="/consent", tags=["consent"])
api_router.include_router(scenarios_router, prefix="/scenarios", tags=["scenarios"])
api_router.include_router(training_router, prefix="/training", tags=["training"])
