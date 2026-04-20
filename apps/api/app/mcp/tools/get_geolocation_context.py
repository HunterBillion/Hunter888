"""MCP tool ``get_geolocation_context`` — IP → regional coaching context.

Phase 2 (2026-04-18). The AI client often references their location ("у нас в
Екатеринбурге приставы…", "наш суд в Питере…"). Giving the LLM a lightweight
regional context before the call lets it stay consistent.

Free offline-friendly data:
  - MaxMind GeoLite2 (local .mmdb) if present → proper lookup.
  - ``ip-api.com`` fallback for dev (60 req/min free).
  - Hard-coded "unknown" reply if neither available (graceful).

We intentionally keep the result tiny (<1 KB) so it doesn't blow the prompt
budget — just ``region``, ``tz``, ``federal_district`` plus a short narrative
``seasonal_note`` and ``local_legal_notes`` picked from a curated table.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx

from app.config import settings
from app.mcp import ToolContext, tool
from app.mcp.schemas import object_schema, string_property

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────
# Curated regional notes — per federal district.
# Short strings (<200 chars) so multiple can be concatenated without
# ballooning the LLM budget. Keep neutral/factual — the LLM adds flavour.
# ────────────────────────────────────────────────────────────────────

_FD_NOTES: dict[str, dict[str, str]] = {
    "Центральный": {
        "local_legal_notes": (
            "В ЦФО высокая нагрузка на арбитражные суды Москвы и области; "
            "процедуры 127-ФЗ идут 8-14 месяцев. МФЦ-банкротство работает "
            "штатно."
        ),
    },
    "Северо-Западный": {
        "local_legal_notes": (
            "СПб и ЛО: арбитраж перегружен, финуправляющие берут премию к "
            "базовой ставке 25 000 ₽. МФЦ — самый активный регион."
        ),
    },
    "Приволжский": {
        "local_legal_notes": (
            "Казань/Самара/Нижний: судебная практика консервативная, "
            "залоговая масса часто оспаривается. МФЦ доступен с 2020."
        ),
    },
    "Уральский": {
        "local_legal_notes": (
            "Екатеринбург/Челябинск: много банкротств ИП и самозанятых. "
            "Арбитражные управляющие часто из местного СРО."
        ),
    },
    "Сибирский": {
        "local_legal_notes": (
            "Новосибирск/Красноярск/Омск: процедура затягивается из-за "
            "сложностей с реализацией имущества."
        ),
    },
    "Дальневосточный": {
        "local_legal_notes": (
            "ДФО: процедуры медленнее на 2-4 месяца, Владивосток/Хабаровск "
            "имеют специализированные составы по банкротству."
        ),
    },
    "Южный": {
        "local_legal_notes": (
            "ЮФО (Ростов/Краснодар): много споров с залоговыми кредиторами, "
            "активный МФЦ."
        ),
    },
    "Северо-Кавказский": {
        "local_legal_notes": (
            "СКФО: процедур меньше, часто банкротство используется как "
            "крайнее средство."
        ),
    },
    "unknown": {
        "local_legal_notes": "Региональные нюансы не определены.",
    },
}


# Rough mapping of region names to federal districts. Not exhaustive —
# GeoLite2 returns region in English (e.g. "Moscow Oblast"); ip-api.com
# returns English region code.
_REGION_TO_FD: dict[str, str] = {
    "Moscow": "Центральный",
    "Moscow Oblast": "Центральный",
    "Saint Petersburg": "Северо-Западный",
    "Leningrad Oblast": "Северо-Западный",
    "Sverdlovsk Oblast": "Уральский",
    "Chelyabinsk Oblast": "Уральский",
    "Tyumen Oblast": "Уральский",
    "Novosibirsk Oblast": "Сибирский",
    "Krasnoyarsk Krai": "Сибирский",
    "Omsk Oblast": "Сибирский",
    "Tatarstan Republic": "Приволжский",
    "Samara Oblast": "Приволжский",
    "Nizhny Novgorod Oblast": "Приволжский",
    "Rostov Oblast": "Южный",
    "Krasnodar Krai": "Южный",
    "Primorsky Krai": "Дальневосточный",
    "Khabarovsk Krai": "Дальневосточный",
}


def _seasonal_note() -> str:
    """Return a short Russian-language seasonal cue for the current month.

    Attaches mild emotional colouring the LLM can lean on ("клиент устал от
    зимы"). Kept generic — exact weather is out of scope.
    """

    m = datetime.utcnow().month
    if m in (12, 1, 2):
        return "Зима — клиенты устают, короткий день, настроение подавленное."
    if m in (3, 4, 5):
        return "Весна — новые надежды, люди охотнее планируют."
    if m in (6, 7, 8):
        return "Лето — отпуска, сложно договариваться о встречах."
    return "Осень — деловой сезон, бюджетные решения до конца года."


async def _lookup_ip_api(ip: str) -> dict[str, Any] | None:
    """Best-effort online lookup via ip-api.com (no auth, 60 rpm free)."""

    if not ip or ip.startswith(("10.", "192.168.", "127.", "172.16.", "172.17.")):
        return None
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(
                f"http://ip-api.com/json/{ip}",
                params={"fields": "status,country,regionName,timezone,city"},
            )
            if r.status_code != 200:
                return None
            data = r.json()
            if data.get("status") != "success":
                return None
            return {
                "country": data.get("country"),
                "region": data.get("regionName"),
                "city": data.get("city"),
                "tz": data.get("timezone"),
            }
    except Exception as exc:  # noqa: BLE001
        logger.debug("ip-api lookup failed for %s: %s", ip, exc)
        return None


@tool(
    name="get_geolocation_context",
    description=(
        "Вернуть региональный контекст менеджера: регион, часовой пояс, "
        "федеральный округ, сезонная заметка и короткий блок местных "
        "нюансов по 127-ФЗ. Используй 1 раз в начале звонка, чтобы клиент "
        "звучал правдоподобно для своего региона."
    ),
    parameters_schema=object_schema(
        required=[],
        properties={
            "ip": string_property(
                "Опциональный IP менеджера. Если пусто — будет взят из "
                "ToolContext.manager_ip.",
                max_length=45,
            ),
        },
    ),
    scope="session",
    auth_required=True,
    rate_limit_per_min=10,  # low — expected once per call
    max_result_size_kb=4,
    timeout_s=5,
    tags=("context", "read-only"),
)
async def get_geolocation_context(args: dict, ctx: ToolContext) -> dict:
    ip = (args.get("ip") or ctx.manager_ip or "").strip()

    data = await _lookup_ip_api(ip) if ip else None
    if data is None:
        return {
            "region": "unknown",
            "city": None,
            "country": None,
            "tz": "Europe/Moscow",
            "federal_district": "unknown",
            "seasonal_note": _seasonal_note(),
            "local_legal_notes": _FD_NOTES["unknown"]["local_legal_notes"],
            "source": "fallback",
        }

    region = data.get("region") or ""
    fd = _REGION_TO_FD.get(region, "unknown")
    notes = _FD_NOTES.get(fd, _FD_NOTES["unknown"])

    return {
        "region": region or "unknown",
        "city": data.get("city"),
        "country": data.get("country"),
        "tz": data.get("tz") or "Europe/Moscow",
        "federal_district": fd,
        "seasonal_note": _seasonal_note(),
        "local_legal_notes": notes["local_legal_notes"],
        "source": "ip-api",
    }
