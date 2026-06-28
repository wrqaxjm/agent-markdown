"""Schema validation for AMD files.

Schemas are YAML files that declare required fields, section structure,
block requirements, etc.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .parser import AmdDocument


@dataclass
class ValidationError:
    """A single validation error."""

    severity: str  # "error" or "warning"
    message: str
    location: str = ""  # e.g. "§2", "frontmatter/$fields/year"


@dataclass
class Schema:
    """A parsed schema definition."""

    id: str
    version: int = 1
    description: str = ""

    require_frontmatter: bool = True
    require_schema_field: bool = True

    required_fields: list[str] = None  # type: ignore
    field_types: dict[str, str] = None  # type: ignore

    required_sections: list[str] = None  # type: ignore
    section_rules: dict[str, dict] = None  # type: ignore
    backlink_rules: dict = None  # type: ignore
    require_blocks: list[dict] = None  # type: ignore

    @classmethod
    def from_file(cls, path: Path) -> "Schema":
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "Schema":
        return cls(
            id=data.get("$id", "unnamed"),
            version=data.get("$version", 1),
            description=data.get("$description", ""),
            require_frontmatter=data.get("require_frontmatter", True),
            require_schema_field=data.get("require_schema_field", True),
            required_fields=data.get("required_fields") or [],
            field_types=data.get("field_types") or {},
            required_sections=data.get("required_sections") or [],
            section_rules=data.get("section_rules") or {},
            backlink_rules=data.get("backlink_rules") or {},
            require_blocks=data.get("require_blocks") or [],
        )


def _check_type(value: Any, type_str: str) -> bool:
    """Check if a value matches a simple type string."""
    type_str = type_str.strip()
    if type_str == "string":
        return isinstance(value, str)
    if type_str == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_str == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if type_str == "boolean":
        return isinstance(value, bool)
    if type_str == "array":
        return isinstance(value, list)
    if type_str == "object":
        return isinstance(value, dict)
    if type_str.startswith("array<"):
        inner = type_str[len("array<"):-1]
        return isinstance(value, list) and all(_check_type(v, inner) for v in value)
    return True  # unknown type → permissive


def validate(doc: AmdDocument, schema: Schema) -> list[ValidationError]:
    """Run schema validation, return list of errors (empty = valid)."""
    errors = []

    # Frontmatter checks
    if schema.require_frontmatter:
        if not doc.frontmatter.schema:
            errors.append(ValidationError("error", "missing $schema in frontmatter", "frontmatter"))
        elif doc.frontmatter.schema != "amd/v1":
            errors.append(ValidationError(
                "warning",
                f"unexpected $schema value: {doc.frontmatter.schema}",
                "frontmatter",
            ))

    if schema.require_schema_field:
        if not doc.frontmatter.id:
            errors.append(ValidationError("error", "missing $id in frontmatter", "frontmatter"))

    # Required fields
    for field_name in schema.required_fields:
        if field_name not in doc.frontmatter.fields:
            errors.append(ValidationError(
                "error",
                f"missing required field: {field_name}",
                f"frontmatter/$fields/{field_name}",
            ))

    # Field types
    for field_name, type_str in schema.field_types.items():
        if field_name in doc.frontmatter.fields:
            value = doc.frontmatter.fields[field_name]
            if not _check_type(value, type_str):
                errors.append(ValidationError(
                    "error",
                    f"field {field_name} has wrong type: expected {type_str}, got {type(type_value := value).__name__}",
                    f"frontmatter/$fields/{field_name}",
                ))

    # Required sections
    section_anchors = {h.anchor for h in doc.headings}
    for req in schema.required_sections:
        if req not in section_anchors:
            errors.append(ValidationError(
                "error",
                f"missing required section: {req}",
                req,
            ))

    # Section rules
    for section_anchor, rules in schema.section_rules.items():
        # Find the section
        section = None
        for h in doc.headings:
            if h.anchor == section_anchor or h.custom_id == section_anchor:
                section = h
                break
        if not section:
            continue

        if "require_class" in rules:
            required_class = rules["require_class"]
            if required_class not in section.classes:
                errors.append(ValidationError(
                    "error",
                    f"section {section_anchor} missing required class: {required_class}",
                    section_anchor,
                ))

        if "max_blocks" in rules:
            # Count blocks under this section
            section_line = section.line
            next_section_line = None
            for h2 in doc.headings:
                if h2.line > section_line and h2.level <= section.level:
                    next_section_line = h2.line
                    break
            if next_section_line is None:
                next_section_line = len(doc.body_text.split("\n")) + 1

            block_count = sum(
                1 for b in doc.blocks
                if section_line < b.line < next_section_line
            )
            if block_count > rules["max_blocks"]:
                errors.append(ValidationError(
                    "error",
                    f"section {section_anchor} has {block_count} blocks, max is {rules['max_blocks']}",
                    section_anchor,
                ))

    # Required blocks
    block_types = [b.type for b in doc.blocks]
    for req in schema.require_blocks:
        req_type = req.get("type")
        min_count = req.get("min_count", 1)
        actual = block_types.count(req_type)
        if actual < min_count:
            errors.append(ValidationError(
                "error",
                f"need at least {min_count} {req_type} block(s), found {actual}",
                f"@{req_type}",
            ))

    # Backlink rules
    if schema.backlink_rules:
        min_count = schema.backlink_rules.get("min_count", 0)
        backlinks = [b for b in doc.blocks if b.type == "backlink"]
        if len(backlinks) < min_count:
            errors.append(ValidationError(
                "error" if min_count > 0 else "warning",
                f"need at least {min_count} backlink(s), found {len(backlinks)}",
                "@backlink",
            ))

    return errors