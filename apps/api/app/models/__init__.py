from app.models.user import User, Team, UserConsent, UserFriendship
from app.models.character import Character, Objection
from app.models.scenario import Scenario, ScenarioTemplate, ScenarioVersion, ScenarioCode, ScenarioType
from app.models.script import Script, Checkpoint, ScriptEmbedding
from app.models.training import TrainingSession, Message, AssignedTraining, CallRecord, SessionReport
from app.models.analytics import Achievement, UserAchievement, LeaderboardSnapshot, ApiLog
from app.models.roleplay import (
    ArchetypeCode,
    LeadSource,
    ProfessionCategory,
    ProfessionProfile,
    ArchetypeEmotionProfile,
    Trap,
    ObjectionChain,
    ClientProfile,
)
from app.models.emotion import (
    EmotionTransition,
    ArchetypeEmotionConfig,
    FakeTransitionDef,
    EmotionSessionLog,
)
from app.models.traps import (
    TrapDefinition,
    ObjectionChainDef,
    ChainStep,
    TrapCascadeDef,
    CascadeLevel,
    TrapSessionLog,
)
from app.models.progress import (
    ManagerProgress,
    SessionHistory,
    LevelDefinition,
    AchievementDefinition,
    EarnedAchievement,
    WeeklyReport,
    ProgressLeaderboardSnapshot,
    GoalCompletionLog,
    StreakFreeze,
)
from app.models.season_content import ContentSeason, SeasonChapter
from app.models.league import WeeklyLeagueGroup, WeeklyLeagueMembership
from app.models.checkpoint import CheckpointDefinition, UserCheckpoint
from app.models.voice import (
    VoiceProfile,
    EmotionVoiceModifier,
    PauseConfig,
    CoupleVoiceProfile,
    VoiceType,
    AgeRange,
)
from app.models.client import (
    RealClient,
    Attachment,
    ClientConsent,
    ClientInteraction,
    ClientNotification,
    ManagerReminder,
    AuditLog,
    ClientStatus,
    ConsentType,
    ConsentChannel,
    InteractionType,
    NotificationChannel,
    NotificationStatus,
    AuditAction,
    ALLOWED_STATUS_TRANSITIONS,
    STATUS_TIMEOUTS,
)
from app.models.reputation import (
    ManagerReputation,
    ReputationTier,
)
from app.models.roleplay import (
    ClientStory,
    EpisodicMemory,
    PersonalityProfile,
    StoryStageDirection,
    TrapCascade,
)
from app.models.behavior import (
    BehaviorSnapshot,
    EmotionProfile,
    ProgressTrend,
    DailyAdvice,
)
from app.models.game_crm import (
    GameClientEvent,
    GameEventType,
    GameClientStatus,
)
from app.models.pvp import (
    PvPDuel,
    PvPRating,
    PvPMatchQueue,
    AntiCheatLog,
    PvPSeason,
    DuelStatus,
    MatchQueueStatus,
    AntiCheatCheckType,
    AntiCheatAction,
    PvPRankTier,
    DuelDifficulty,
    UserFingerprint,
    # DOC_09-13: New PvP/PvE/Rating models
    PvPTeam,
    GauntletRun,
    RapidFireMatch,
    PvELadderRun,
    PvEBossRun,
    PromotionSeries,
    SeasonReward,
    APPurchase,
)
from app.models.custom_character import CustomCharacter
from app.models.knowledge import (
    KnowledgeQuizSession,
    QuizParticipant,
    KnowledgeAnswer,
    QuizChallenge,
    QuizMode,
    QuizSessionStatus,
    UserAnswerHistory,
    # DOC_11: Knowledge v2 models
    DebateSession,
    TeamQuizTeam,
    DailyChallenge,
    DailyChallengeEntry,
)
from app.models.rag import (
    ChunkUsageLog,
    LegalKnowledgeChunk,
    LegalValidationResult,
    PersonalityChunk,
    PersonalityExample,
    TraitCategory,
    PersonalityChunkSource,
)
from app.models.tournament import (
    BracketMatch,
    BracketMatchStatus,
    Tournament,
    TournamentEntry,
    TournamentFormat,
    TournamentParticipant,
    # DOC_12: Tournament v2 models
    TournamentTheme,
    TournamentTeam,
    TeamMatch,
)
from app.models.xp_log import XPLog
from app.models.xp_event import XPEvent
# FIND-002 fix (2026-04-19): register LegalDocument in Base.metadata so
# Alembic autogenerate doesn't mistake it for an orphan and propose a DROP.
# The table holds ~4400 RAG documents — dropping would be catastrophic.
from app.models.legal_document import LegalDocument  # noqa: F401
from app.models.rating_contribution import RatingContribution, RatingSource
from app.models.prompt_version import PromptVersion
from app.models.cross_recommendation import CrossRecommendationCache
from app.models.manager_wiki import (
    ManagerWiki,
    WikiPage,
    WikiUpdateLog,
    ManagerPattern,
    ManagerTechnique,
    WikiStatus,
    WikiAction,
    WikiPageType,
    PatternCategory,
)
from app.models.review import Review
from app.models.outbox import OutboxEvent, OutboxStatus
from app.models.team_challenge import (
    TeamChallenge,
    TeamChallengeProgress,
    ChallengeStatus as TeamChallengeStatus,
    ChallengeType as TeamChallengeType,
)
from app.models.subscription import UserSubscription, PlanType as SubscriptionPlanType
from app.models.story_state import UserStoryState
from app.models.morning_drill import MorningDrillSession
from app.models.lead_client import LeadClient
from app.models.domain_event import DomainEvent
from app.models.crm_projection import CrmTimelineProjectionState
from app.models.persona_snapshot import PersonaSnapshot
# TZ-4 D1 — canonical persona memory (alembic 20260427_001).
# Coexists with the older PersonaSnapshot above (which is the TZ-1
# PersonaSnapshot — different scope; see TZ-4 §6.6 coexistence rules).
from app.models.persona import (
    MemoryPersona,
    SessionPersonaSnapshot,
    ADDRESS_FORMS,
    GENDERS,
    TONES,
    PERSONA_CAPTURED_FROM,
)
from app.models.ws_outbox import WsOutboxEvent, WsOutboxStatus
from app.services.web_push import PushSubscription

__all__ = [
    "User",
    "Team",
    "UserConsent",
    "UserFriendship",
    "Character",
    "Objection",
    "Scenario",
    "ScenarioTemplate",
    "ScenarioCode",
    "ScenarioType",
    "Script",
    "Checkpoint",
    "ScriptEmbedding",
    "TrainingSession",
    "Message",
    "AssignedTraining",
    "LeadClient",
    "DomainEvent",
    "CrmTimelineProjectionState",
    "PersonaSnapshot",
    "WsOutboxEvent",
    "WsOutboxStatus",
    "Achievement",
    "UserAchievement",
    "LeaderboardSnapshot",
    "ApiLog",
    "ArchetypeCode",
    "LeadSource",
    "ProfessionCategory",
    "ProfessionProfile",
    "ArchetypeEmotionProfile",
    "Trap",
    "ObjectionChain",
    "ClientProfile",
    "Tournament",
    "TournamentEntry",
    "TournamentFormat",
    "TournamentParticipant",
    "BracketMatch",
    "BracketMatchStatus",
    "VoiceProfile",
    "EmotionVoiceModifier",
    "PauseConfig",
    "CoupleVoiceProfile",
    "VoiceType",
    "AgeRange",
    "EmotionTransition",
    "ArchetypeEmotionConfig",
    "FakeTransitionDef",
    "EmotionSessionLog",
    "TrapDefinition",
    "ObjectionChainDef",
    "ChainStep",
    "TrapCascadeDef",
    "CascadeLevel",
    "TrapSessionLog",
    "ManagerProgress",
    "SessionHistory",
    "LevelDefinition",
    "AchievementDefinition",
    "WeeklyReport",
    # Agent 7 — Client Communication Module
    "RealClient",
    "ClientConsent",
    "ClientInteraction",
    "ClientNotification",
    "ManagerReminder",
    "AuditLog",
    "ClientStatus",
    "ConsentType",
    "ConsentChannel",
    "InteractionType",
    "NotificationChannel",
    "NotificationStatus",
    "AuditAction",
    "ALLOWED_STATUS_TRANSITIONS",
    "STATUS_TIMEOUTS",
    # Agent 5 — Reputation System
    "ManagerReputation",
    "ReputationTier",
    # Roleplay — story models
    "ClientStory",
    "EpisodicMemory",
    "PersonalityProfile",
    "StoryStageDirection",
    # Game CRM (Agent 7, spec 10.1-10.3)
    "GameClientEvent",
    "GameEventType",
    "GameClientStatus",
    # Agent 8 — PvP Battle
    "PvPDuel",
    "PvPRating",
    "PvPMatchQueue",
    "AntiCheatLog",
    "PvPSeason",
    "DuelStatus",
    "MatchQueueStatus",
    "AntiCheatCheckType",
    "AntiCheatAction",
    "PvPRankTier",
    "DuelDifficulty",
    "UserFingerprint",
    # Custom Characters
    "CustomCharacter",
    # Knowledge Quiz (AI Examiner + PvP Arena)
    "KnowledgeQuizSession",
    "QuizParticipant",
    "KnowledgeAnswer",
    "QuizChallenge",
    "QuizMode",
    "QuizSessionStatus",
    # Web Push (Task X6)
    "PushSubscription",
    # RAG Feedback Loop
    "ChunkUsageLog",
    # DOC_04: Checkpoints
    "CheckpointDefinition",
    "UserCheckpoint",
    # DOC_09-13: PvP/PvE/Rating expansion
    "PvPTeam",
    "GauntletRun",
    "RapidFireMatch",
    "PvELadderRun",
    "PvEBossRun",
    "PromotionSeries",
    "SeasonReward",
    "APPurchase",
    # DOC_11: Knowledge v2
    "DebateSession",
    "TeamQuizTeam",
    "DailyChallenge",
    "DailyChallengeEntry",
    # DOC_12: Tournament v2
    "TournamentTheme",
    "TournamentTeam",
    "TeamMatch",
    # DOC_15-16: Progression + Prompts
    "XPLog",
    "XPEvent",
    "RatingContribution",
    "RatingSource",
    "PromptVersion",
    "CrossRecommendationCache",
    # Previously missing exports (GAP-2 fix)
    "CallRecord",
    "SessionReport",
    "EarnedAchievement",
    "ProgressLeaderboardSnapshot",
    "LegalKnowledgeChunk",
    "LegalValidationResult",
    "PersonalityChunk",
    "PersonalityExample",
    "TraitCategory",
    "PersonalityChunkSource",
    "UserAnswerHistory",
    "BehaviorSnapshot",
    "EmotionProfile",
    "ProgressTrend",
    "DailyAdvice",
    "TrapCascade",
    # Manager Wiki (Karpathy pattern)
    "ManagerWiki",
    "WikiPage",
    "WikiUpdateLog",
    "ManagerPattern",
    "ManagerTechnique",
    "WikiStatus",
    "WikiAction",
    "WikiPageType",
    "PatternCategory",
    # Reviews (landing testimonials)
    "Review",
    # Season Content & Leagues (diagnostic fix)
    "ContentSeason",
    "SeasonChapter",
    "WeeklyLeagueGroup",
    "WeeklyLeagueMembership",
    "GoalCompletionLog",
    "StreakFreeze",
    # S3-01: Team Challenge persistence
    "TeamChallenge",
    "TeamChallengeProgress",
    "TeamChallengeStatus",
    "TeamChallengeType",
    # S3-03: Subscription / Entitlement
    "UserSubscription",
    "SubscriptionPlanType",
    "UserStoryState",
    # Morning warm-up persistence (2026-04-20)
    "MorningDrillSession",
    # RAG v2 (Phase 3.10): legal_document was missing from Base.metadata
    "LegalDocument",
    # TZ-4 D1 — persona memory (alembic 20260427_001)
    "MemoryPersona",
    "SessionPersonaSnapshot",
    "ADDRESS_FORMS",
    "GENDERS",
    "TONES",
    "PERSONA_CAPTURED_FROM",
]
