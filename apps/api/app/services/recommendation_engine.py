"""
Recommendation Engine — Rule-based analysis of loss patterns → training suggestions.

ТЗ v2, Task X5:
- Анализ причин потерь (lost_reason, status → lost transitions)
- Группировка по паттернам (ранние потери, поздние потери, повторные потери)
- Рекомендация сценариев тренировок для менеджера
- Статистика эффективности по этапам воронки

Реализация: чистый rule-based engine (без ML).
Каждое правило — Pattern → Recommendation с приоритетом и обоснованием.
"""

import logging
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Sequence

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import (
    ClientInteraction,
    ClientStatus,
    InteractionType,
    RealClient,
)
from app.models.scenario import ScenarioCode

logger = logging.getLogger(__name__)


# ─── Data Classes ────────────────────────────────────────────────────────────


@dataclass
class LossPattern:
    """Detected pattern of client losses."""

    pattern_id: str
    name: str
    description: str
    count: int
    severity: str  # "low" | "medium" | "high" | "critical"
    affected_statuses: list[str] = field(default_factory=list)
    sample_client_ids: list[str] = field(default_factory=list)


@dataclass
class TrainingRecommendation:
    """Recommended training scenario with rationale."""

    scenario_code: str
    scenario_name: str
    priority: int  # 1 = highest
    reason: str
    pattern_id: str  # link to detected pattern
    expected_impact: str  # "high" | "medium" | "low"


@dataclass
class ManagerReport:
    """Full recommendation report for a manager."""

    manager_id: str
    manager_name: str
    generated_at: str
    period_days: int
    # Stats
    total_clients: int
    total_lost: int
    loss_rate: float  # 0.0 - 1.0
    conversion_rate: float
    avg_days_to_loss: float
    # Analysis
    funnel_stats: dict[str, dict]  # status → {count, lost_count, conversion_rate}
    patterns: list[LossPattern]
    recommendations: list[TrainingRecommendation]


# ─── Pattern → Scenario Mapping Rules ────────────────────────────────────────

# Status at which client was lost → relevant training scenarios
LOSS_STAGE_SCENARIO_MAP: dict[str, list[ScenarioCode]] = {
    # Lost at early contact stage → cold call / warm callback training
    "new": [ScenarioCode.cold_base, ScenarioCode.cold_ad, ScenarioCode.cold_referral],
    "contacted": [ScenarioCode.warm_callback, ScenarioCode.warm_noanswer, ScenarioCode.warm_refused],
    # Lost during interest/consultation → objection handling, rescue
    "interested": [ScenarioCode.in_website, ScenarioCode.in_hotline, ScenarioCode.rescue],
    "consultation": [ScenarioCode.in_hotline, ScenarioCode.rescue, ScenarioCode.couple_call],
    # Lost during thinking → persistence / rescue training
    "thinking": [ScenarioCode.warm_dropped, ScenarioCode.rescue, ScenarioCode.warm_refused],
    # Lost after consent → document collection failures → upsell/vip
    "consent_given": [ScenarioCode.upsell, ScenarioCode.vip_debtor],
    "contract_signed": [ScenarioCode.upsell, ScenarioCode.vip_debtor],
    # Consent revoked → rescue / couple call
    "consent_revoked": [ScenarioCode.rescue, ScenarioCode.couple_call],
    # Paused → warm follow-up
    "paused": [ScenarioCode.warm_callback, ScenarioCode.warm_dropped],
}

# lost_reason keywords → additional scenario recommendations
REASON_KEYWORD_MAP: dict[str, list[ScenarioCode]] = {
    "цена": [ScenarioCode.rescue, ScenarioCode.upsell],
    "дорого": [ScenarioCode.rescue, ScenarioCode.upsell],
    "конкурент": [ScenarioCode.rescue, ScenarioCode.vip_debtor],
    "передумал": [ScenarioCode.warm_refused, ScenarioCode.rescue],
    "не берёт": [ScenarioCode.warm_noanswer, ScenarioCode.warm_dropped],
    "не отвечает": [ScenarioCode.warm_noanswer, ScenarioCode.warm_dropped],
    "супруг": [ScenarioCode.couple_call],
    "жена": [ScenarioCode.couple_call],
    "муж": [ScenarioCode.couple_call],
    "не доверяет": [ScenarioCode.cold_referral, ScenarioCode.in_social],
    "auto_timeout": [ScenarioCode.warm_dropped, ScenarioCode.warm_noanswer],
    "рефинанс": [ScenarioCode.rescue, ScenarioCode.vip_debtor],
    "партнёр": [ScenarioCode.cold_partner, ScenarioCode.couple_call],
}

SCENARIO_NAMES: dict[str, str] = {
    "cold_ad": "Холодный звонок (реклама)",
    "cold_base": "Холодный звонок (база)",
    "cold_referral": "Холодный звонок (рекомендация)",
    "cold_partner": "Холодный звонок (партнёр)",
    "warm_callback": "Тёплый перезвон",
    "warm_noanswer": "Не отвечает",
    "warm_refused": "Отказ / повторный звонок",
    "warm_dropped": "Потерянный контакт",
    "in_website": "Входящий (сайт)",
    "in_hotline": "Входящий (горячая линия)",
    "in_social": "Входящий (соцсети)",
    "upsell": "Допродажа",
    "rescue": "Спасение клиента",
    "couple_call": "Звонок с супругом",
    "vip_debtor": "VIP-должник",
}


# ─── Engine ──────────────────────────────────────────────────────────────────


class RecommendationEngine:
    """
    Stateless rule-based engine. Call `generate_report()` with a DB session.
    """

    def __init__(self, period_days: int = 90):
        self.period_days = period_days

    async def generate_report(
        self,
        db: AsyncSession,
        manager_id: uuid.UUID,
        manager_name: str = "",
    ) -> ManagerReport:
        """Generate a full analysis report for a manager."""
        since = datetime.now(timezone.utc) - timedelta(days=self.period_days)

        # ── Fetch data ──
        clients = await self._get_manager_clients(db, manager_id)
        lost_clients = [c for c in clients if c.status == ClientStatus.lost]
        completed_clients = [c for c in clients if c.status == ClientStatus.completed]

        # ── Funnel stats ──
        funnel = self._compute_funnel_stats(clients)

        # ── Loss patterns ──
        patterns = self._detect_patterns(lost_clients, funnel, since)

        # ── Recommendations ──
        recommendations = self._generate_recommendations(patterns, lost_clients)

        # ── Avg days to loss ──
        loss_durations = []
        for c in lost_clients:
            if c.created_at and c.last_status_change_at:
                delta = (c.last_status_change_at - c.created_at).days
                loss_durations.append(delta)
        avg_days = sum(loss_durations) / len(loss_durations) if loss_durations else 0

        total = len(clients)
        loss_rate = len(lost_clients) / total if total > 0 else 0
        conversion_rate = len(completed_clients) / total if total > 0 else 0

        return ManagerReport(
            manager_id=str(manager_id),
            manager_name=manager_name,
            generated_at=datetime.now(timezone.utc).isoformat(),
            period_days=self.period_days,
            total_clients=total,
            total_lost=len(lost_clients),
            loss_rate=round(loss_rate, 3),
            conversion_rate=round(conversion_rate, 3),
            avg_days_to_loss=round(avg_days, 1),
            funnel_stats=funnel,
            patterns=patterns,
            recommendations=recommendations,
        )

    # ── Data Access ──

    async def _get_manager_clients(
        self,
        db: AsyncSession,
        manager_id: uuid.UUID,
    ) -> Sequence[RealClient]:
        result = await db.execute(
            select(RealClient).where(RealClient.manager_id == manager_id)
        )
        return list(result.scalars().all())

    # ── Funnel Analysis ──

    def _compute_funnel_stats(
        self,
        clients: Sequence[RealClient],
    ) -> dict[str, dict]:
        """Per-status counts and conversion rates."""
        status_counts: Counter[str] = Counter()
        for c in clients:
            status_counts[c.status.value] += 1

        total = len(clients)
        funnel: dict[str, dict] = {}

        for status in ClientStatus:
            count = status_counts.get(status.value, 0)
            lost_in_status = sum(
                1
                for c in clients
                if c.status == ClientStatus.lost
                and c.lost_reason
                and status.value in (c.lost_reason or "")
            )
            funnel[status.value] = {
                "count": count,
                "percentage": round(count / total * 100, 1) if total > 0 else 0,
                "lost_from_here": lost_in_status,
            }

        return funnel

    # ── Pattern Detection ──

    def _detect_patterns(
        self,
        lost: Sequence[RealClient],
        funnel: dict[str, dict],
        since: datetime,
    ) -> list[LossPattern]:
        patterns: list[LossPattern] = []

        if not lost:
            return patterns

        # Pattern 1: Early losses (new/contacted stage)
        early_losses = [c for c in lost if self._last_active_status(c) in ("new", "contacted")]
        if len(early_losses) >= 2:
            patterns.append(
                LossPattern(
                    pattern_id="early_dropout",
                    name="Ранние потери",
                    description="Клиенты теряются на этапе первого контакта. "
                    "Возможная проблема: слабый скрипт открытия, недостаточная мотивация клиента.",
                    count=len(early_losses),
                    severity="high" if len(early_losses) > 5 else "medium",
                    affected_statuses=["new", "contacted"],
                    sample_client_ids=[str(c.id) for c in early_losses[:5]],
                )
            )

        # Pattern 2: Mid-funnel losses (interested/consultation/thinking)
        mid_losses = [
            c
            for c in lost
            if self._last_active_status(c) in ("interested", "consultation", "thinking")
        ]
        if len(mid_losses) >= 2:
            patterns.append(
                LossPattern(
                    pattern_id="mid_funnel_dropout",
                    name="Потери в середине воронки",
                    description="Клиенты уходят после проявленного интереса. "
                    "Возможная проблема: неумение работать с возражениями, долгие паузы.",
                    count=len(mid_losses),
                    severity="high" if len(mid_losses) > 3 else "medium",
                    affected_statuses=["interested", "consultation", "thinking"],
                    sample_client_ids=[str(c.id) for c in mid_losses[:5]],
                )
            )

        # Pattern 3: Late losses (consent_given/documents)
        late_losses = [
            c
            for c in lost
            if self._last_active_status(c) in ("consent_given", "contract_signed")
        ]
        if late_losses:
            patterns.append(
                LossPattern(
                    pattern_id="late_funnel_dropout",
                    name="Поздние потери",
                    description="Клиенты уходят после дачи согласия. "
                    "Возможная проблема: затянутый сбор документов, утерянное доверие.",
                    count=len(late_losses),
                    severity="critical" if len(late_losses) > 2 else "high",
                    affected_statuses=["consent_given", "contract_signed"],
                    sample_client_ids=[str(c.id) for c in late_losses[:5]],
                )
            )

        # Pattern 4: Auto-timeout losses
        timeout_losses = [c for c in lost if c.lost_reason and "auto_timeout" in c.lost_reason]
        if timeout_losses:
            patterns.append(
                LossPattern(
                    pattern_id="timeout_losses",
                    name="Потери по таймауту",
                    description="Клиенты переведены в «потерян» автоматически из-за отсутствия контакта. "
                    "Менеджер не поддерживает связь с клиентами.",
                    count=len(timeout_losses),
                    severity="critical" if len(timeout_losses) > 3 else "high",
                    affected_statuses=["thinking"],
                    sample_client_ids=[str(c.id) for c in timeout_losses[:5]],
                )
            )

        # Pattern 5: Repeat losses (lost_count > 1)
        repeat_losses = [c for c in lost if c.lost_count > 1]
        if repeat_losses:
            patterns.append(
                LossPattern(
                    pattern_id="repeat_losses",
                    name="Повторные потери",
                    description="Клиенты теряются повторно после возврата в воронку. "
                    "Менеджер не устраняет первопричину отказа.",
                    count=len(repeat_losses),
                    severity="high",
                    affected_statuses=["contacted"],
                    sample_client_ids=[str(c.id) for c in repeat_losses[:5]],
                )
            )

        # Pattern 6: Price/competitor objection pattern
        price_losses = [
            c
            for c in lost
            if c.lost_reason
            and any(kw in c.lost_reason.lower() for kw in ("цена", "дорого", "конкурент", "рефинанс"))
        ]
        if price_losses:
            patterns.append(
                LossPattern(
                    pattern_id="price_objection",
                    name="Ценовые/конкурентные возражения",
                    description="Клиенты уходят из-за цены или к конкурентам. "
                    "Необходима работа с ценовыми возражениями и USP.",
                    count=len(price_losses),
                    severity="medium" if len(price_losses) <= 3 else "high",
                    affected_statuses=["consultation", "thinking"],
                    sample_client_ids=[str(c.id) for c in price_losses[:5]],
                )
            )

        # Pattern 7: Family influence
        family_losses = [
            c
            for c in lost
            if c.lost_reason
            and any(kw in c.lost_reason.lower() for kw in ("супруг", "жена", "муж", "родствен"))
        ]
        if family_losses:
            patterns.append(
                LossPattern(
                    pattern_id="family_influence",
                    name="Влияние семьи",
                    description="Клиенты уходят под давлением родственников. "
                    "Рекомендуется практика совместных звонков.",
                    count=len(family_losses),
                    severity="medium",
                    affected_statuses=["thinking", "consent_given"],
                    sample_client_ids=[str(c.id) for c in family_losses[:5]],
                )
            )

        # Sort by severity
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        patterns.sort(key=lambda p: severity_order.get(p.severity, 99))

        return patterns

    # ── Recommendation Generation ──

    def _generate_recommendations(
        self,
        patterns: list[LossPattern],
        lost: Sequence[RealClient],
    ) -> list[TrainingRecommendation]:
        """Convert detected patterns into training recommendations."""
        recommendations: list[TrainingRecommendation] = []
        seen_scenarios: set[str] = set()

        priority = 1

        for pattern in patterns:
            scenario_codes: list[ScenarioCode] = []

            # Map by affected statuses
            for status in pattern.affected_statuses:
                scenario_codes.extend(LOSS_STAGE_SCENARIO_MAP.get(status, []))

            # Map by lost_reason keywords
            reason_clients = [
                c for c in lost if c.lost_reason and str(c.id) in pattern.sample_client_ids
            ]
            for c in reason_clients:
                reason = (c.lost_reason or "").lower()
                for keyword, codes in REASON_KEYWORD_MAP.items():
                    if keyword in reason:
                        scenario_codes.extend(codes)

            # Deduplicate and score
            code_counter: Counter[str] = Counter(sc.value for sc in scenario_codes)

            for code, _count in code_counter.most_common(3):
                if code in seen_scenarios:
                    continue
                seen_scenarios.add(code)

                impact = "high" if pattern.severity in ("critical", "high") else "medium"

                recommendations.append(
                    TrainingRecommendation(
                        scenario_code=code,
                        scenario_name=SCENARIO_NAMES.get(code, code),
                        priority=priority,
                        reason=f"Связан с паттерном «{pattern.name}» "
                        f"({pattern.count} клиентов, серьёзность: {pattern.severity})",
                        pattern_id=pattern.pattern_id,
                        expected_impact=impact,
                    )
                )
                priority += 1

        return recommendations[:10]  # top 10 recommendations

    # ── Helpers ──

    @staticmethod
    def _last_active_status(client: RealClient) -> str:
        """Infer the last active status before loss from lost_reason or metadata."""
        reason = client.lost_reason or ""

        # auto_timeout format: "auto_timeout_30d" — was in thinking
        if "auto_timeout" in reason:
            return "thinking"

        # Check metadata for last status
        meta = client.metadata_ or {}
        if "last_active_status" in meta:
            return str(meta["last_active_status"])

        # Heuristic: if lost_count > 0 and was contacted, likely early stage
        if client.lost_count > 1:
            return "contacted"

        # Default — unknown, assume early
        return "contacted"


# ─── API Schemas ─────────────────────────────────────────────────────────────

def report_to_dict(report: ManagerReport) -> dict:
    """Serialize ManagerReport to JSON-safe dict."""
    return {
        "manager_id": report.manager_id,
        "manager_name": report.manager_name,
        "generated_at": report.generated_at,
        "period_days": report.period_days,
        "summary": {
            "total_clients": report.total_clients,
            "total_lost": report.total_lost,
            "loss_rate": report.loss_rate,
            "conversion_rate": report.conversion_rate,
            "avg_days_to_loss": report.avg_days_to_loss,
        },
        "funnel": report.funnel_stats,
        "patterns": [
            {
                "id": p.pattern_id,
                "name": p.name,
                "description": p.description,
                "count": p.count,
                "severity": p.severity,
                "affected_statuses": p.affected_statuses,
                "sample_client_ids": p.sample_client_ids,
            }
            for p in report.patterns
        ],
        "recommendations": [
            {
                "scenario_code": r.scenario_code,
                "scenario_name": r.scenario_name,
                "priority": r.priority,
                "reason": r.reason,
                "pattern_id": r.pattern_id,
                "expected_impact": r.expected_impact,
            }
            for r in report.recommendations
        ],
    }
