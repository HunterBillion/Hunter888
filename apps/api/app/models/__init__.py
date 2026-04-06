from app.models.user import User, Team, UserConsent, UserFriendship
from app.models.character import Character, Objection
from app.models.scenario import Scenario, ScenarioTemplate, ScenarioCode, ScenarioType
from app.models.script import Script, Checkpoint, ScriptEmbedding
from app.models.training import TrainingSession, Message, AssignedTraining
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
    WeeklyReport,
)
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
    # DOC_11: Knowledge v2 models
    DebateSession,
    TeamQuizTeam,
    DailyChallenge,
    DailyChallengeEntry,
)
from app.models.rag import ChunkUsageLog
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
from app.models.prompt_version import PromptVersion
from app.models.cross_recommendation import CrossRecommendationCache
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
    "PromptVersion",
    "CrossRecommendationCache",
]
