import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserRole(str, enum.Enum):
    manager = "manager"
    rop = "rop"
    methodologist = "methodologist"
    admin = "admin"


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    users: Mapped[list["User"]] = relationship(back_populates="team")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.manager, nullable=False)
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    preferences: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Phase C (2026-04-20): Arena-specific tutorial completion. NULL = show
    # "Новичок? Пройди тренировку" banner on /pvp and gate the first match.
    arena_tutorial_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None,
    )
    google_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    yandex_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Email verification — OAuth-registered users are auto-verified since
    # the provider (Google/Yandex) already checked the email. Password
    # signups must click a tokenized link sent via SMTP to flip this flag.
    email_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    email_verification_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    team: Mapped[Team | None] = relationship(back_populates="users")
    consents: Mapped[list["UserConsent"]] = relationship(back_populates="user")
    sent_friendships: Mapped[list["UserFriendship"]] = relationship(
        back_populates="requester",
        foreign_keys="UserFriendship.requester_id",
    )
    received_friendships: Mapped[list["UserFriendship"]] = relationship(
        back_populates="addressee",
        foreign_keys="UserFriendship.addressee_id",
    )


class UserFriendship(Base):
    __tablename__ = "user_friendships"
    __table_args__ = (
        UniqueConstraint("requester_id", "addressee_id", name="uq_user_friendships_pair"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    requester_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    addressee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    requester: Mapped["User"] = relationship(
        back_populates="sent_friendships",
        foreign_keys=[requester_id],
    )
    addressee: Mapped["User"] = relationship(
        back_populates="received_friendships",
        foreign_keys=[addressee_id],
    )


class UserConsent(Base):
    __tablename__ = "user_consents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    consent_type: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="consents")


class ManagerKpiTarget(Base):
    """Per-manager KPI targets surfaced in the Команда panel.

    All target columns are nullable: ``None`` means "no target set" — the
    UI hides the progress indicator instead of showing a 0/X bar. Bounds
    enforced by CHECK constraints (migration ``20260501_002``):
      * ``target_sessions_per_month >= 0``
      * ``target_avg_score`` ∈ [0, 100]
      * ``target_max_days_without_session >= 0``

    1:1 with ``users.id`` (PK is the user_id), CASCADE on user delete so
    we don't carry orphan KPI rows.
    """

    __tablename__ = "manager_kpi_targets"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    target_sessions_per_month: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    target_avg_score: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    target_max_days_without_session: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "target_sessions_per_month IS NULL OR target_sessions_per_month >= 0",
            name="ck_kpi_target_sessions_nonneg",
        ),
        CheckConstraint(
            "target_avg_score IS NULL OR (target_avg_score >= 0 AND target_avg_score <= 100)",
            name="ck_kpi_target_score_in_range",
        ),
        CheckConstraint(
            "target_max_days_without_session IS NULL OR target_max_days_without_session >= 0",
            name="ck_kpi_target_days_nonneg",
        ),
    )
