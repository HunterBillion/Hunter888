"""JSON Schema helpers for ``Tool.parameters_schema``.

OpenAI-compatible providers expect the ``parameters`` field of a tool to be
a JSON Schema *object* (i.e. ``type: "object"``). Most tool authors won't
write raw schemas by hand; these helpers let them declare parameters
pythonically and emit the same JSON shape.

Example::

    schema = object_schema(
        required=["prompt", "context"],
        properties={
            "prompt": string_property("1-2 sentence description"),
            "context": enum_property(
                "Kind of image",
                choices=["document", "photo", "screenshot", "receipt"],
            ),
        },
    )
"""

from __future__ import annotations

from typing import Iterable


def object_schema(
    *,
    required: Iterable[str] = (),
    properties: dict[str, dict] | None = None,
    additional_properties: bool = False,
    description: str | None = None,
) -> dict:
    """Top-level ``{"type": "object", ...}`` JSON Schema."""

    schema: dict = {
        "type": "object",
        "properties": dict(properties or {}),
        "additionalProperties": additional_properties,
    }
    if required:
        schema["required"] = list(required)
    if description:
        schema["description"] = description
    return schema


def string_property(description: str = "", *, min_length: int | None = None, max_length: int | None = None) -> dict:
    prop: dict = {"type": "string"}
    if description:
        prop["description"] = description
    if min_length is not None:
        prop["minLength"] = min_length
    if max_length is not None:
        prop["maxLength"] = max_length
    return prop


def enum_property(description: str, *, choices: Iterable[str]) -> dict:
    return {"type": "string", "description": description, "enum": list(choices)}


def integer_property(description: str = "", *, minimum: int | None = None, maximum: int | None = None) -> dict:
    prop: dict = {"type": "integer"}
    if description:
        prop["description"] = description
    if minimum is not None:
        prop["minimum"] = minimum
    if maximum is not None:
        prop["maximum"] = maximum
    return prop


def boolean_property(description: str = "") -> dict:
    prop: dict = {"type": "boolean"}
    if description:
        prop["description"] = description
    return prop
