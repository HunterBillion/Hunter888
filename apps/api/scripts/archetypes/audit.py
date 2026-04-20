"""Archetype CI audit.

Run after a deploy OR on every PR that touches ``app/archetypes/`` or
``app/services/client_generator.py``.

The audit reports four independent signals; the script exits with code 0 if
all are OK, 1 if any fails. CI should gate merges on exit code.

Signals:

1. **enum vs ocean dict** — every ``ArchetypeCode`` value has an entry in
   ``client_generator.ARCHETYPE_OCEAN``. Missing entries are HARD fail
   (Registry would silently use neutral OCEAN → awful behaviour drift).

2. **ocean dict vs enum** — every key in ``ARCHETYPE_OCEAN`` exists in the
   enum. Stale keys are HARD fail (someone renamed an archetype and forgot
   to update the legacy dict).

3. **pad / fears coverage warnings** — report counts, not fail. These dicts
   legitimately cover only a subset (~25 of 100). Used to track migration
   progress.

4. **catalog completeness** — report how many ``app/archetypes/catalog/*.py``
   files exist. Not a hard fail until Phase 1.3 lands (catalog populated).

Usage:
    python -m scripts.archetypes.audit
    python -m scripts.archetypes.audit --json         # machine-readable
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _collect_signals() -> dict:
    """Gather the four signals from loaded modules."""

    # Late imports — this script is also runnable from cold repo state.
    from app.archetypes.loader import _GROUP_MEMBERS  # noqa: F401 — sanity only
    from app.models.roleplay import ArchetypeCode
    from app.services.client_generator import (
        ARCHETYPE_OCEAN,
        ARCHETYPE_PAD,
        ARCHETYPE_FEARS,
        ARCHETYPE_SOFT_SPOTS,
        ARCHETYPE_BREAKING_POINTS,
    )

    enum_codes = {c.value for c in ArchetypeCode}
    ocean_codes = set(ARCHETYPE_OCEAN.keys())

    missing_in_ocean = sorted(enum_codes - ocean_codes)
    stale_in_ocean = sorted(ocean_codes - enum_codes)

    pad_missing = sorted(enum_codes - set(ARCHETYPE_PAD.keys()))
    fears_missing = sorted(enum_codes - set(ARCHETYPE_FEARS.keys()))
    softspots_missing = sorted(enum_codes - set(ARCHETYPE_SOFT_SPOTS.keys()))
    breakingpoints_missing = sorted(enum_codes - set(ARCHETYPE_BREAKING_POINTS.keys()))

    catalog_dir = Path(__file__).resolve().parents[2] / "app" / "archetypes" / "catalog"
    catalog_files = (
        sorted(p.stem for p in catalog_dir.glob("*.py") if p.name != "__init__.py")
        if catalog_dir.is_dir()
        else []
    )
    catalog_missing = sorted(enum_codes - set(catalog_files))

    return {
        "enum_count": len(enum_codes),
        "ocean_count": len(ocean_codes),
        "missing_in_ocean": missing_in_ocean,
        "stale_in_ocean": stale_in_ocean,
        "pad_coverage": {
            "covered": len(enum_codes - set(pad_missing)),
            "missing_sample": pad_missing[:10],
            "missing_total": len(pad_missing),
        },
        "fears_coverage": {
            "covered": len(enum_codes - set(fears_missing)),
            "missing_sample": fears_missing[:10],
            "missing_total": len(fears_missing),
        },
        "softspots_coverage": {
            "covered": len(enum_codes - set(softspots_missing)),
            "missing_total": len(softspots_missing),
        },
        "breakingpoints_coverage": {
            "covered": len(enum_codes - set(breakingpoints_missing)),
            "missing_total": len(breakingpoints_missing),
        },
        "catalog_files": len(catalog_files),
        "catalog_missing_count": len(catalog_missing),
        "catalog_missing_sample": catalog_missing[:10],
    }


def _render_report(signals: dict) -> tuple[str, bool]:
    """Return (human-readable report, ok)."""

    lines: list[str] = []
    ok = True

    lines.append("=" * 72)
    lines.append("ARCHETYPE REGISTRY AUDIT")
    lines.append("=" * 72)
    lines.append(f"enum codes: {signals['enum_count']}")
    lines.append(f"ARCHETYPE_OCEAN codes: {signals['ocean_count']}")
    lines.append("")

    # Signal 1 — missing in ocean (HARD)
    if signals["missing_in_ocean"]:
        ok = False
        lines.append(f"FAIL (enum without OCEAN): {len(signals['missing_in_ocean'])}")
        for code in signals["missing_in_ocean"]:
            lines.append(f"  - {code}")
    else:
        lines.append("OK   enum↔ARCHETYPE_OCEAN coverage")

    # Signal 2 — stale in ocean (HARD)
    if signals["stale_in_ocean"]:
        ok = False
        lines.append(
            f"FAIL (OCEAN keys not in enum): {len(signals['stale_in_ocean'])}"
        )
        for code in signals["stale_in_ocean"]:
            lines.append(f"  - {code}")
    else:
        lines.append("OK   no stale OCEAN keys")

    # Signal 3 — pad/fears coverage (SOFT)
    for field in ("pad_coverage", "fears_coverage",
                  "softspots_coverage", "breakingpoints_coverage"):
        c = signals[field]
        lines.append(
            f"INFO {field}: {c['covered']}/{signals['enum_count']} covered "
            f"(missing {c.get('missing_total')})"
        )

    # Signal 4 — catalog migration progress (SOFT)
    lines.append(
        f"INFO catalog: {signals['catalog_files']} files in app/archetypes/catalog/"
        f" — missing for {signals['catalog_missing_count']} codes"
    )
    if signals["catalog_missing_sample"]:
        lines.append(
            f"     sample missing: {', '.join(signals['catalog_missing_sample'])}"
        )

    lines.append("=" * 72)
    lines.append("RESULT: " + ("PASS" if ok else "FAIL"))
    lines.append("=" * 72)
    return "\n".join(lines), ok


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    as_json = "--json" in argv

    signals = _collect_signals()
    report, ok = _render_report(signals)

    if as_json:
        print(json.dumps({"ok": ok, "signals": signals}, ensure_ascii=False, indent=2))
    else:
        print(report)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
