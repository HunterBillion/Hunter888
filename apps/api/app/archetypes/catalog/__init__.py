"""Per-archetype canonical profiles.

This package is populated by ``scripts/archetypes/generate_catalog.py`` —
one module per archetype code, each exporting a ``PROFILE: ArchetypeProfile``.

Until the codegen is run the package is empty and ``ArchetypeRegistry`` falls
through to ``loader.build_profile_from_legacy`` for every lookup. Nothing
breaks; fallback hits are tracked via ``ArchetypeRegistry.fallback_hits()``.
"""
