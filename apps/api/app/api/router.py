from fastapi import APIRouter

from app.api.analytics import router as analytics_router
from app.api.auth import router as auth_router
from app.api.consent import router as consent_router
from app.api.dashboard import router as dashboard_router
from app.api.gamification import router as gamification_router
from app.api.health import router as health_router
from app.api.scenarios import router as scenarios_router
from app.api.tournament import router as tournament_router
from app.api.training import router as training_router
from app.api.users import router as users_router
from app.api.routes.emotion_traps import router as emotion_traps_router
from app.api.routes.progress import router as progress_router

api_router = APIRouter()

api_router.include_router(health_router, tags=["monitoring"])
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(users_router, prefix="/users", tags=["users"])
api_router.include_router(consent_router, prefix="/consent", tags=["consent"])
api_router.include_router(scenarios_router, prefix="/scenarios", tags=["scenarios"])
api_router.include_router(training_router, prefix="/training", tags=["training"])
api_router.include_router(gamification_router, prefix="/gamification", tags=["gamification"])
api_router.include_router(analytics_router, prefix="/analytics", tags=["analytics"])
api_router.include_router(tournament_router, prefix="/tournament", tags=["tournament"])
api_router.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(emotion_traps_router, tags=["emotion", "traps", "chains"])
api_router.include_router(progress_router, tags=["progress"])

# Custom Characters (CharacterBuilder save)
from app.api.custom_characters import router as custom_characters_router

api_router.include_router(custom_characters_router, tags=["characters"])

# Agent 7 — Unified Client Domain: CRM Core
from app.api.clients import router as clients_router
from app.api.clients import notifications_router, reminders_router

api_router.include_router(clients_router, prefix="/clients", tags=["clients"])
api_router.include_router(notifications_router, prefix="/notifications", tags=["notifications"])
api_router.include_router(reminders_router, prefix="/reminders", tags=["reminders"])

# Agent 7 — Unified Client Domain: AI Continuity Layer
from app.api.game_crm import router as game_crm_router

api_router.include_router(game_crm_router, prefix="/game/clients", tags=["game-crm"])

# Agent 8 — PvP Battle
from app.api.pvp import router as pvp_router

api_router.include_router(pvp_router, prefix="/pvp", tags=["pvp"])
