"""Hotfix regression pin: app.api.training.py must import every name
it uses from settings at module scope.

The TZ-2 Phase 4 commit (9a1b2ad, 2026-04-26) added four references to
`settings.tz2_guard_*_enabled` to apps/api/app/api/training.py without
adding `from app.config import settings`. With all four guard flags
defaulting to False the bug was easy to miss in unit tests, but at
runtime Python still evaluates the attribute access — every POST to
/api/training/sessions/{id}/end raised NameError → 500.

This test would have caught it: import the module and read each flag
that the module references. If a future contributor uses
`settings.X_enabled` again without importing settings, this fails.
"""

import re
from pathlib import Path


_TRAINING_API_PATH = (
    Path(__file__).parent.parent / "app" / "api" / "training.py"
)


def test_settings_is_imported_at_module_scope():
    """Static check: the module must contain a top-level
    ``from app.config import settings``."""
    src = _TRAINING_API_PATH.read_text()
    assert re.search(
        r"^\s*from\s+app\.config\s+import\s+(?:[\w,\s]+,\s*)?settings\b",
        src,
        re.MULTILINE,
    ), (
        "app/api/training.py uses settings.X but does not import settings. "
        "Hotfix: add `from app.config import settings` to the imports block."
    )


def test_every_settings_reference_resolves_at_runtime():
    """Behavioural check: import the module, walk over each
    ``settings.<name>`` reference grepped from the source, and assert
    that the attribute resolves on the live Settings object."""
    from app.api import training  # forces import of `settings` into module

    src = _TRAINING_API_PATH.read_text()
    referenced_names = set(re.findall(r"settings\.([a-zA-Z_][a-zA-Z0-9_]*)", src))
    # Read off the live instance the module imported, not a fresh one —
    # we want to detect "name typo" regressions, not "config schema drift".
    settings_obj = training.settings
    missing = [n for n in referenced_names if not hasattr(settings_obj, n)]
    assert not missing, (
        f"app/api/training.py references settings attributes that do not "
        f"exist on the Settings object: {missing}. Either rename in the "
        f"source or add the field to apps/api/app/config.py."
    )
