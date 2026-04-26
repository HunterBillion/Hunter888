"""TZ-3 §7.3.1 regression — update_scenario must NOT create a ScenarioVersion.

This is the load-bearing invariant of PR C2. Before this PR every save
auto-published a new version, directly violating §8 invariant 2.
After this PR, save only bumps `draft_revision`. A version is created
only via the explicit `POST /rop/scenarios/{id}/publish` endpoint.

If this test fails, somebody re-introduced the auto-publish — refer
back to spec §7.3.1 before "fixing" this test.

These checks are pure AST/import-graph: no DB needed. The
behavioural side (revision bump + version row count) is covered
by `test_scenario_publisher.py::test_happy_path_publishes_v1`
and the publisher's full suite (which runs against the CI Postgres
service so JSONB columns work).
"""

from __future__ import annotations

import inspect
import re

import pytest


def test_update_handler_source_does_not_reference_create_scenario_version():
    """AST-grep the handler source. If a future refactor inlines the
    auto-publish call, this test catches it before the behavioural
    test even runs.

    NB: the source MAY mention `_create_scenario_version` in a comment
    or docstring (we want explicit deprecation prose pointing at the
    fix). The check below grep's for actual call sites only — naked
    identifier on its own line OR `await _create_scenario_version(...)`.
    """
    from app.api.rop import update_scenario

    src = inspect.getsource(update_scenario)
    # Strip comments — we only care about executable code.
    code_lines = []
    for raw in src.split("\n"):
        line = raw.split("#", 1)[0]  # drop trailing comment
        # Drop docstring lines (very rough — assumes triple-quoted strings
        # don't span hundreds of lines; this handler's docstring is short).
        if line.strip().startswith('"""') or line.strip().startswith("'''"):
            continue
        code_lines.append(line)
    code = "\n".join(code_lines)

    # The forbidden pattern: an actual call (with `(`).
    assert "_create_scenario_version(" not in code, (
        "update_scenario calls _create_scenario_version — "
        "TZ-3 §7.3.1 forbids this. Move the publish action to the "
        "explicit POST /rop/scenarios/{id}/publish endpoint."
    )


def test_update_handler_bumps_draft_revision():
    """The handler must increment draft_revision so the optimistic-
    concurrency token (§15.1) actually reflects edits."""
    from app.api.rop import update_scenario

    src = inspect.getsource(update_scenario)
    # Look for the cursor bump. We don't pin the exact arithmetic
    # form (could be `+= 1` or `int(...) + 1`) — just check that
    # `draft_revision` appears on an LHS assignment.
    assert re.search(r"\.draft_revision\s*=", src), (
        "update_scenario doesn't write to draft_revision. "
        "TZ-3 §15.1 requires the handler to bump the optimistic-"
        "concurrency cursor on every save so concurrent editors notice "
        "each other on publish."
    )


def test_publish_handler_exists_in_rop_module():
    """If somebody removed the publish endpoint by accident, the
    update handler becomes write-only and editors can never go live.
    Pin the handler's existence."""
    from app.api import rop

    assert hasattr(rop, "publish_scenario"), (
        "publish_scenario handler missing from rop.py — every PR C2+ "
        "depends on it. Don't merge without restoring it."
    )


def test_publish_handler_uses_canonical_publisher():
    """The handler must delegate to ``services.scenario_publisher.
    publish_template`` rather than re-implementing publish locally.
    This forces all publishes (REST + future CLI + future cron) through
    the same race-safe SELECT FOR UPDATE path."""
    from app.api.rop import publish_scenario

    src = inspect.getsource(publish_scenario)
    assert "publish_template" in src, (
        "publish_scenario doesn't import or call publish_template — "
        "you've duplicated the publish logic, which means the race-"
        "safety the publisher provides is bypassed."
    )
