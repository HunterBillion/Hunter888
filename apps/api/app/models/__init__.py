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
    EmotionProfile,
    Trap,
    ObjectionChain,
    ClientProfile,
)
from app.models.tournament import Tournament, TournamentEntry
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
)
from app.models.custom_character import CustomCharacter
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
    "EmotionProfile",
    "Trap",
    "ObjectionChain",
    "ClientProfile",
    "Tournament",
    "TournamentEntry",
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
    # Custom Characters
    "CustomCharacter",
    # Web Push (Task X6)
    "PushSubscription",
]
