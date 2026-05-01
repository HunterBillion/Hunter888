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
from app.api.home import router as home_router
from app.api.morning_drill import router as morning_drill_router
from app.api.routes.emotion_traps import router as emotion_traps_router
from app.api.routes.progress import router as progress_router

api_router = APIRouter()

api_router.include_router(health_router, tags=["monitoring"])
api_router.include_router(home_router, tags=["home"])
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(users_router, prefix="/users", tags=["users"])
api_router.include_router(consent_router, prefix="/consent", tags=["consent"])
api_router.include_router(scenarios_router, prefix="/scenarios", tags=["scenarios"])
api_router.include_router(training_router, prefix="/training", tags=["training"])
# 2026-04-17: morning warm-up (3-5 sequential mini-questions) — parallel to
# legacy /daily-drill chat flow; separate endpoint prefix, independent XP.
api_router.include_router(morning_drill_router, tags=["morning-drill"])
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

# Agent 9 — Knowledge Quiz (127-FZ testing)
from app.api.knowledge import router as knowledge_router

api_router.include_router(knowledge_router, prefix="/knowledge", tags=["knowledge"])

# Module 5 — ROP Tools (formerly Methodologist).
# Mounted at TWO prefixes during the migration window:
#   * `/rop/*`           — canonical destination for new FE code.
#   * `/methodologist/*` — backward-compat alias kept until the FE pages
#     under apps/web/src/app/methodologist/ migrate to the dashboard
#     MethodologyPanel (PR B2). After that lands in prod, drop the alias
#     in PR B3 alongside enum-value removal.
from app.api.rop import router as rop_router

api_router.include_router(rop_router, prefix="/rop", tags=["rop"])
api_router.include_router(rop_router, prefix="/methodologist", tags=["rop", "deprecated"])

# Module 5 — CRM Integrations
from app.api.integrations import router as integrations_router

api_router.include_router(integrations_router, prefix="/integrations", tags=["integrations"])

# Module 2 — Behavioral Intelligence
from app.api.behavior import router as behavior_router

api_router.include_router(behavior_router, tags=["behavior"])

# Navigator — curated quote library (6-hour rotation)
from app.api.navigator import router as navigator_router

api_router.include_router(navigator_router, tags=["navigator"])

# Progression — Hunter Score, Arena Points, Catch-Up (DOC_14/DOC_13/DOC_04)
from app.api.progression import router as progression_router_v2

api_router.include_router(progression_router_v2, prefix="/progression", tags=["progression"])

# Prompt Registry CRUD — Methodologist/Admin prompt management (DOC_16)
from app.api.prompts import router as prompts_router

api_router.include_router(prompts_router, prefix="/prompts", tags=["prompts"])

# Manager Wiki — Karpathy LLM Wiki pattern (persistent knowledge base per manager)
from app.api.manager_wiki import router as wiki_router

api_router.include_router(wiki_router, tags=["wiki"])

# Reviews — public landing page testimonials
from app.api.reviews import router as reviews_router

api_router.include_router(reviews_router, tags=["reviews"])

# S3-03: Subscription & Entitlement
from app.api.subscription import router as subscription_router

api_router.include_router(subscription_router, prefix="/subscription", tags=["subscription"])

# Story — 'Путь Охотника' 12-chapter narrative arc
from app.api.story import router as story_router

api_router.include_router(story_router, prefix="/story", tags=["story"])

# TZ-1 — Unified Client Domain ops (parity + repair; admin-only)
from app.api.client_domain_ops import router as client_domain_ops_router

api_router.include_router(client_domain_ops_router, tags=["client-domain-ops"])

# Phase 5 — WS Outbox polling fallback (Roadmap §10.3)
from app.api.pending_events import router as pending_events_router

api_router.include_router(pending_events_router, tags=["pending-events"])

# TZ-4 §8 — Knowledge review queue + manual review action (rop|admin)
from app.api.admin_knowledge import router as admin_knowledge_router

api_router.include_router(admin_knowledge_router)

# TZ-4 §13.4.1 — AI quality dashboard (rop|admin); aggregates
# conversation_policy / persona_conflict signals over a rolling window.
from app.api.ai_quality import router as ai_quality_router

api_router.include_router(ai_quality_router)

# TZ-4 §6.3/§6.4 — per-client persona memory read endpoint, drives
# the "Память клиента" card on the client detail page.
from app.api.persona_view import router as persona_view_router

api_router.include_router(persona_view_router)

# Team panel optimisations (rop|admin) — bulk assign + team analytics
# + CSV user import. See `app/api/team.py`.
from app.api.team import router as team_router

api_router.include_router(team_router, prefix="/team", tags=["team"])

# Команда v2 follow-up — per-manager KPI targets (rop|admin).
# Lives on /team/* alongside the bulk-assign + analytics endpoints
# from team.py. TODO(post-#122-merge): consolidate this module into
# team.py — kept separate originally so #151 could land before/after
# #122 without conflicts.
from app.api.team_kpi import router as team_kpi_router

api_router.include_router(team_kpi_router, prefix="/team", tags=["team", "kpi"])
