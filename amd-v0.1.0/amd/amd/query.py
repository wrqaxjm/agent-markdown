"""Query language for AMD files.

A simple SQL-like DSL. Supports:
- SELECT <what> FROM <source> WHERE <condition>
- what: section, file, block, headings
- source: file path, section anchor, @frontmatter
- condition: <field> [=|!=|CONTAINS|>] <value>

This is intentionally minimal — full SQL would be overkill.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .parser import AmdDocument, load_file


def _eval_condition(doc: AmdDocument, condition: str) -> bool:
    """Evaluate a simple condition against a document."""
    condition = condition.strip()

    # Match: <field> <op> <value>
    # Value can be quoted ("...") or unquoted (number, identifier).
    patterns = [
        (r"^(\S+)\s*=\s*\"([^\"]*)\"$", "eq_str"),
        (r"^(\S+)\s*=\s*(\S+)$", "eq_raw"),
        (r"^(\S+)\s*!=\s*\"([^\"]*)\"$", "ne"),
        (r"^(\S+)\s+CONTAINS\s+\"([^\"]*)\"$", "contains"),
        (r"^(\S+)\s+>\s*(\S+)$", "gt"),
        (r"^(\S+)\s+>\s*\"([^\"]*)\"$", "gt_str"),
    ]

    for pattern, op in patterns:
        m = re.match(pattern, condition)
        if m:
            field_path = m.group(1)
            value = m.group(2)
            return _eval_simple(doc, field_path, op, value)

    return False


def _eval_simple(doc: AmdDocument, field_path: str, op: str, value: str) -> bool:
    """Evaluate a simple field op value condition."""
    actual = _resolve_field(doc, field_path)

    if op == "eq_str":
        return str(actual) == value
    if op == "eq_raw":
        # Try numeric comparison first, then string
        try:
            return float(actual) == float(value)
        except (ValueError, TypeError):
            return str(actual) == value
    if op == "ne":
        return str(actual) != value
    if op == "contains":
        if isinstance(actual, list):
            return value in actual
        if isinstance(actual, str):
            return value in actual
        return False
    if op == "gt":
        try:
            return float(actual) > float(value)
        except (ValueError, TypeError):
            return False
    if op == "gt_str":
        return str(actual) > value

    return False


def _resolve_field(doc: AmdDocument, field_path: str) -> Any:
    """Resolve a field path like $fields.year or §2.class."""
    if field_path == "$id":
        return doc.frontmatter.id
    if field_path == "$type":
        return doc.frontmatter.type
    if field_path.startswith("$fields."):
        return doc.frontmatter.fields.get(field_path[len("$fields."):])
    if field_path == "content":
        return doc.body_text
    if field_path.startswith("$updated"):
        return doc.frontmatter.updated

    # Section reference: §N.class
    m = re.match(r"^(§\S+)\.(\S+)$", field_path)
    if m:
        anchor = m.group(1)
        attr = m.group(2)
        for h in doc.headings:
            if h.anchor == anchor:
                if attr == "class":
                    return h.classes
                if attr == "classes":
                    return h.classes
                if attr == "anchor":
                    return h.anchor
                if attr == "level":
                    return h.level
                if attr == "text":
                    return h.text

    return None


def _parse_query(query: str) -> tuple[str, str, str]:
    """Parse a query into (what, source, condition).

    Very simple parser: SELECT <what> FROM <source> [WHERE <condition>]
    """
    q = query.strip()
    q_upper = q.upper()

    select_idx = q_upper.find("SELECT")
    from_idx = q_upper.find("FROM")
    where_idx = q_upper.find("WHERE")

    if select_idx != 0 or from_idx < 0:
        raise ValueError(f"invalid query syntax: {query}")

    what = q[6:from_idx].strip()
    rest_start = from_idx + 4

    if where_idx > 0:
        source = q[rest_start:where_idx].strip()
        condition = q[where_idx + 5:].strip()
    else:
        source = q[rest_start:].strip()
        condition = ""

    return what, source, condition


def execute(query: str, paths: list[Path], base_dir: Path | None = None) -> list[dict]:
    """Execute a query against one or more files.

    Returns a list of result dicts.
    """
    what, source, condition = _parse_query(query)
    results = []

    for path in paths:
        try:
            doc = load_file(path)
        except Exception:
            continue

        if condition:
            try:
                if not _eval_condition(doc, condition):
                    continue
            except Exception:
                continue

        rel_path = str(path.relative_to(base_dir)) if base_dir and path.is_relative_to(base_dir) else str(path)
        result = {
            "file": rel_path,
            "$id": doc.frontmatter.id,
            "$type": doc.frontmatter.type,
        }

        if what == "file":
            result["file"] = rel_path
            if doc.frontmatter.fields:
                result["fields"] = doc.frontmatter.fields
        elif what == "section":
            for h in doc.headings:
                results.append({
                    "file": rel_path,
                    "section": h.anchor,
                    "text": h.text,
                    "classes": h.classes,
                })
            continue
        elif what == "heading":
            for h in doc.headings:
                results.append({
                    "file": rel_path,
                    "anchor": h.anchor,
                    "text": h.text,
                })
            continue
        elif what == "block":
            for b in doc.blocks:
                results.append({
                    "file": rel_path,
                    "type": b.type,
                    "name": b.name,
                })
            continue

        results.append(result)

    return results