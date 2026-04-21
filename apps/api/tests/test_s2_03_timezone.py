"""Tests for S2-03: Timezone Normalization.

Covers:
- All production code uses datetime.now(timezone.utc) instead of datetime.utcnow()
- All production code uses datetime.now(timezone.utc).date() instead of date.today()
- No server-local timezone leaks
"""

import re
from pathlib import Path

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# No datetime.utcnow() in Production Code
# ═══════════════════════════════════════════════════════════════════════════════


class TestNoUtcnow:
    """Verify datetime.utcnow() is eliminated from all production code."""

    PROD_ROOT = Path(__file__).resolve().parent.parent / "app"

    def _scan_python_files(self, pattern: str) -> list[str]:
        """Scan all .py files under app/ for a pattern. Returns list of 'file:line' matches."""
        matches = []
        for py_file in self.PROD_ROOT.rglob("*.py"):
            rel = py_file.relative_to(self.PROD_ROOT.parent)
            for i, line in enumerate(py_file.read_text().splitlines(), 1):
                # Skip comments
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                if pattern in line:
                    matches.append(f"{rel}:{i}: {line.strip()}")
        return matches

    def test_no_utcnow_in_services(self):
        """No datetime.utcnow() in app/services/."""
        matches = self._scan_python_files("datetime.utcnow()")
        # Filter to services only
        service_matches = [m for m in matches if "/services/" in m]
        assert not service_matches, \
            f"datetime.utcnow() found in services:\n" + "\n".join(service_matches)

    def test_no_utcnow_in_api(self):
        """No datetime.utcnow() in app/api/."""
        matches = self._scan_python_files("datetime.utcnow()")
        api_matches = [m for m in matches if "/api/" in m]
        assert not api_matches, \
            f"datetime.utcnow() found in API:\n" + "\n".join(api_matches)

    def test_no_utcnow_in_ws(self):
        """No datetime.utcnow() in app/ws/."""
        matches = self._scan_python_files("datetime.utcnow()")
        ws_matches = [m for m in matches if "/ws/" in m]
        assert not ws_matches, \
            f"datetime.utcnow() found in WS:\n" + "\n".join(ws_matches)

    def test_no_utcnow_in_main(self):
        """No datetime.utcnow() in app/main.py."""
        main_path = self.PROD_ROOT / "main.py"
        content = main_path.read_text()
        lines = [
            f"main.py:{i}: {line.strip()}"
            for i, line in enumerate(content.splitlines(), 1)
            if "datetime.utcnow()" in line and not line.lstrip().startswith("#")
        ]
        assert not lines, \
            f"datetime.utcnow() found in main.py:\n" + "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# No date.today() in Production Code
# ═══════════════════════════════════════════════════════════════════════════════


class TestNoDateToday:
    """Verify date.today() is eliminated from production code."""

    PROD_ROOT = Path(__file__).resolve().parent.parent / "app"

    def _scan_for_date_today(self) -> list[str]:
        """Scan for date.today() usage in production code."""
        matches = []
        for py_file in self.PROD_ROOT.rglob("*.py"):
            rel = py_file.relative_to(self.PROD_ROOT.parent)
            for i, line in enumerate(py_file.read_text().splitlines(), 1):
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                if "date.today()" in line:
                    matches.append(f"{rel}:{i}: {line.strip()}")
        return matches

    def test_no_date_today_in_services(self):
        """No date.today() in app/services/."""
        matches = self._scan_for_date_today()
        service_matches = [m for m in matches if "/services/" in m]
        assert not service_matches, \
            f"date.today() found in services:\n" + "\n".join(service_matches)

    def test_no_date_today_in_api(self):
        """No date.today() in app/api/."""
        matches = self._scan_for_date_today()
        api_matches = [m for m in matches if "/api/" in m]
        assert not api_matches, \
            f"date.today() found in API:\n" + "\n".join(api_matches)


# ═══════════════════════════════════════════════════════════════════════════════
# Timezone-Aware Helpers
# ═══════════════════════════════════════════════════════════════════════════════


class TestTimezoneAwareHelpers:
    """Verify key helper functions return timezone-aware datetimes."""

    def test_daily_goals_start_of_today(self):
        from app.services.daily_goals import _start_of_today
        result = _start_of_today()
        assert result.tzinfo is not None, "Must be tz-aware"
        assert result.hour == 0 and result.minute == 0

    def test_daily_goals_start_of_week(self):
        from app.services.daily_goals import _start_of_week
        result = _start_of_week()
        assert result.tzinfo is not None, "Must be tz-aware"
        assert result.weekday() == 0  # Monday

    def test_outbox_event_defaults_tz_aware(self):
        """OutboxEvent.created_at default must be timezone-aware."""
        import inspect
        from app.models.outbox import OutboxEvent
        source = inspect.getsource(OutboxEvent)
        assert "timezone.utc" in source, \
            "OutboxEvent must use timezone.utc for created_at default"
        assert "datetime.utcnow()" not in source


# ═══════════════════════════════════════════════════════════════════════════════
# Critical: Daily Reset Bound to UTC
# ═══════════════════════════════════════════════════════════════════════════════


class TestDailyResetUTC:
    """Verify daily resets use UTC, not server-local time."""

    def test_daily_drill_uses_utc(self):
        """daily_drill must use UTC for 'today' calculation."""
        import inspect
        from app.services.daily_drill import complete_drill
        source = inspect.getsource(complete_drill)
        assert "timezone.utc" in source
        assert "date.today()" not in source
        assert "datetime.utcnow()" not in source

    def test_daily_goals_uses_utc(self):
        """daily_goals helpers must use UTC."""
        import inspect
        from app.services.daily_goals import _start_of_today, _start_of_week
        for fn in [_start_of_today, _start_of_week]:
            source = inspect.getsource(fn)
            assert "timezone.utc" in source, f"{fn.__name__} must use timezone.utc"
            assert "datetime.utcnow()" not in source, f"{fn.__name__} must not use utcnow()"
