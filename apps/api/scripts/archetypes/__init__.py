"""Archetype tooling scripts.

- ``audit.py`` — CI gate: diffs ArchetypeCode enum against legacy dicts and
  reports any archetype that would end up on the neutral fallback path.

- ``generate_catalog.py`` — one-shot codegen: produces
  ``app/archetypes/catalog/<code>.py`` for every archetype, using
  ``loader.build_profile_from_legacy`` as the source. Commit the output to git.
"""
