"""AMD parser.

Wraps markdown-it-py and adds AMD-specific extensions:
- $schema / $type / $id / $fields / $locks frontmatter
- {#id .class required} heading attributes
- @block-type { ... } custom blocks
- Wikilinks [[Page]]
- Auto-generated §N anchors for headings
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from markdown_it import MarkdownIt
from markdown_it.token import Token


@dataclass
class AmdFrontmatter:
    """Typed frontmatter for an AMD file."""

    schema: str | None = None  # e.g. "amd/v1"
    id: str | None = None
    type: str | None = None
    fields: dict[str, Any] = field(default_factory=dict)
    updated: str | None = None
    updated_by: str | None = None
    locks: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AmdFrontmatter":
        return cls(
            schema=data.get("$schema"),
            id=data.get("$id"),
            type=data.get("$type"),
            fields=dict(data.get("$fields", {})),
            updated=data.get("$updated"),
            updated_by=data.get("$updated_by"),
            locks=data.get("$locks"),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.schema:
            result["$schema"] = self.schema
        if self.id:
            result["$id"] = self.id
        if self.type:
            result["$type"] = self.type
        if self.fields:
            result["$fields"] = self.fields
        if self.updated:
            result["$updated"] = self.updated
        if self.updated_by:
            result["$updated_by"] = self.updated_by
        if self.locks:
            result["$locks"] = self.locks
        return result


@dataclass
class AmdHeading:
    """A heading with its AMD attributes."""

    level: int
    text: str
    anchor: str  # auto-generated §N or custom {#id}
    custom_id: str | None = None
    classes: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    line: int = 0

    @property
    def is_numbered(self) -> bool:
        return self.anchor.startswith("§")


@dataclass
class AmdBlock:
    """A structured block (@figure, @code, @cite, etc.)."""

    type: str  # e.g. "figure", "code", "cite"
    name: str | None  # e.g. "fig-1"
    attrs: dict[str, Any]
    line: int = 0


@dataclass
class AmdDocument:
    """Parsed AMD document."""

    frontmatter: AmdFrontmatter
    headings: list[AmdHeading]
    blocks: list[AmdBlock]
    raw_text: str
    body_text: str  # markdown without frontmatter

    def find_heading_by_anchor(self, anchor: str) -> AmdHeading | None:
        for h in self.headings:
            if h.anchor == anchor or h.custom_id == anchor:
                return h
        return None

    def find_block(self, name: str) -> AmdBlock | None:
        for b in self.blocks:
            if b.name == name:
                return b
        return None

    def get_section_body(self, anchor: str) -> str:
        """Get the body text under a section heading, up to the next heading of same/higher level."""
        target = self.find_heading_by_anchor(anchor)
        if not target:
            return ""

        # Find section start and end in raw_text
        lines = self.body_text.split("\n")
        start_line = target.line
        end_line = len(lines)

        for h in self.headings:
            if h.line > start_line and h.level <= target.level:
                end_line = h.line
                break

        return "\n".join(lines[start_line:end_line])


# Regex for heading attributes: {#id .class required}
HEADING_ATTR_RE = re.compile(
    r"^(?P<text>.+?)\s*\{(?P<attrs>[^}]+)\}\s*$"
)
ATTR_TOKEN_RE = re.compile(r"(?P<key>#[^\s]+)|(?P<val>\.[^\s]+)|(?P<flag>[^\s.#]+)")

# Regex for §N.M auto anchor
SECTION_ANCHOR_RE = re.compile(r"^§(\d+(?:\.\d+)*)\s+(.+)$")

# Regex for @block-type { ... } on a single line
BLOCK_RE = re.compile(
    r"^@(?P<type>[a-z][a-z0-9-]*)(?:-(?P<name>[a-z0-9-]+))?\s*\{(?P<attrs>[^}]*)\}\s*$",
    re.IGNORECASE,
)

# Regex for the opening line of a multi-line block (where attrs span multiple lines)
BLOCK_OPEN_RE = re.compile(
    r"^@(?P<type>[a-z][a-z0-9-]*)(?:-(?P<name>[a-z0-9-]+))?\s*\{\s*$",
    re.IGNORECASE,
)


def _parse_heading_attrs(heading_text: str) -> tuple[str, str | None, list[str], list[str]]:
    """Parse heading text with trailing {attrs}.

    Returns (clean_text, custom_id, classes, flags).
    """
    m = HEADING_ATTR_RE.match(heading_text)
    if not m:
        return heading_text, None, [], []

    text = m.group("text").strip()
    attrs_str = m.group("attrs").strip()
    custom_id = None
    classes = []
    flags = []

    for tok in ATTR_TOKEN_RE.finditer(attrs_str):
        if tok.group("key"):
            custom_id = tok.group("key")[1:]  # drop #
        elif tok.group("val"):
            classes.append(tok.group("val")[1:])  # drop .
        elif tok.group("flag"):
            flags.append(tok.group("flag"))

    return text, custom_id, classes, flags


def _parse_block_attrs(attrs_str: str) -> dict[str, Any]:
    """Parse key: value attrs inside a block, tolerant of YAML/JSON."""
    attrs_str = attrs_str.strip()
    if not attrs_str:
        return {}

    # Try JSON first (handles quoted strings)
    try:
        return json.loads("{" + attrs_str + "}")
    except (json.JSONDecodeError, ValueError):
        pass

    # Try YAML
    try:
        parsed = yaml.safe_load(attrs_str)
        if isinstance(parsed, dict):
            return parsed
    except yaml.YAMLError:
        pass

    # Fallback: key=value pairs
    result = {}
    for line in attrs_str.split("\n"):
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        # Strip surrounding quotes
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        result[key] = value
    return result


def _generate_section_anchors(headings: list[AmdHeading]) -> None:
    """Auto-generate §N.M anchors for headings.

    Rules:
    - Level 1 (the document title) never gets a §-anchor.
    - If a heading text starts with §N, use that as the anchor.
    - Otherwise, auto-assign §N based on level-2 numbering.
    - Sub-level (3+) auto-gets §N.M under their parent.
    - Headings without an anchor (no § prefix, no custom id) get one assigned.
    """
    used: set[str] = set()

    # First pass: pick up explicit §N anchors
    for h in headings:
        if h.level == 1:
            # Title never gets a §-anchor; falls back to custom_id or "title"
            continue
        m = SECTION_ANCHOR_RE.match(h.text)
        if m:
            anchor = "§" + m.group(1)
            if anchor not in used:
                h.anchor = anchor
                used.add(anchor)
                continue

    # Second pass: auto-assign §N for level-2 headings without anchors
    section_counter = 0
    parent_stack: list[tuple[int, int]] = []  # (level, section_number)
    for h in headings:
        if h.level == 1:
            continue

        if h.anchor and h.anchor.startswith("§"):
            # Already has anchor (explicit); pop deeper levels
            parent_stack = [(lv, n) for lv, n in parent_stack if lv < h.level]
            continue

        if not h.anchor:
            if h.level == 2:
                section_counter += 1
                anchor = f"§{section_counter}"
                parent_stack = [(2, section_counter)]
            elif h.level == 3 and parent_stack:
                # Use parent's number + sub-counter
                # Find the most recent level-2 ancestor
                parent_num = parent_stack[0][1] if parent_stack else 0
                # Count how many level-3 we've seen under this parent
                sub_count = sum(1 for x in parent_stack if x[0] == 3) + 1
                anchor = f"§{parent_num}.{sub_count}"
                parent_stack.append((3, sub_count))
            else:
                # Skip auto-anchoring for now
                continue

            if anchor not in used:
                h.anchor = anchor
                used.add(anchor)


def parse(text: str) -> AmdDocument:
    """Parse AMD document text into structured form.

    Tolerant: if frontmatter is malformed, treats as plain markdown.
    """
    # Extract frontmatter
    frontmatter = AmdFrontmatter()
    body = text

    if text.startswith("---"):
        end_match = re.search(r"^---\s*$", text[3:], re.MULTILINE)
        if end_match:
            # end_match.end() is in text[3:] coordinates.
            # The match consumes '---' plus trailing newline (4 chars total).
            # In original text, the closing --- starts at end_match.start() + 3.
            # We want fm_text = text[3:start_of_closing_---]
            #            body  = text[after_closing_---:]
            closing_start = end_match.start() + 3  # original-text position of closing ---
            body_start = end_match.end() + 3       # original-text position right after closing --- + \n
            fm_text = text[3:closing_start]
            body = text[body_start:].lstrip("\n")
            try:
                fm_data = yaml.safe_load(fm_text)
                if isinstance(fm_data, dict):
                    frontmatter = AmdFrontmatter.from_dict(fm_data)
            except yaml.YAMLError:
                pass  # keep default frontmatter

    # Use markdown-it to get tokens
    md = MarkdownIt("commonmark", {"html": True})
    tokens = md.parse(body)

    # Walk tokens to extract headings and blocks
    headings: list[AmdHeading] = []
    blocks: list[AmdBlock] = []

    line = 1  # markdown-it doesn't always track lines well, we track our own
    body_lines = body.split("\n")

    for i, tok in enumerate(tokens):
        if tok.type == "heading_open":
            level = int(tok.tag[1])  # h1 -> 1, h2 -> 2, ...
            # Next inline token has the text
            if i + 1 < len(tokens) and tokens[i + 1].type == "inline":
                heading_text = tokens[i + 1].content
                # Find the line in body
                line_no = _find_line_for_token(body_lines, heading_text)
                clean_text, custom_id, classes, flags = _parse_heading_attrs(heading_text)
                anchor = custom_id or ""  # will be filled by _generate_section_anchors
                headings.append(AmdHeading(
                    level=level,
                    text=clean_text,
                    anchor=anchor,
                    custom_id=custom_id,
                    classes=classes,
                    flags=flags,
                    line=line_no,
                ))

    _generate_section_anchors(headings)

    # Find blocks (@figure, @code, etc.) by line scan
    # Handle both single-line and multi-line block syntax
    i = 0
    while i < len(body_lines):
        line_text = body_lines[i]
        # Try single-line block first
        m = BLOCK_RE.match(line_text.strip())
        if m:
            block_type = m.group("type").lower()
            block_name = m.group("name")
            attrs_str = m.group("attrs")
            attrs = _parse_block_attrs(attrs_str)
            blocks.append(AmdBlock(
                type=block_type,
                name=block_name,
                attrs=attrs,
                line=i + 1,
            ))
            i += 1
            continue

        # Try multi-line block opening
        m = BLOCK_OPEN_RE.match(line_text.strip())
        if m:
            block_type = m.group("type").lower()
            block_name = m.group("name")
            # Collect lines until we hit a closing `}`
            attrs_lines = []
            i += 1
            while i < len(body_lines):
                inner = body_lines[i].rstrip()
                if inner.strip() == "}":
                    break
                attrs_lines.append(inner)
                i += 1
            attrs_str = "\n".join(attrs_lines)
            attrs = _parse_block_attrs(attrs_str)
            blocks.append(AmdBlock(
                type=block_type,
                name=block_name,
                attrs=attrs,
                line=i + 1 - len(attrs_lines),  # opening line
            ))
            i += 1
            continue

        i += 1

    return AmdDocument(
        frontmatter=frontmatter,
        headings=headings,
        blocks=blocks,
        raw_text=text,
        body_text=body,
    )


def _find_line_for_token(body_lines: list[str], needle: str) -> int:
    """Find 1-indexed line number containing needle."""
    needle = needle.strip()
    if not needle:
        return 1
    for i, line in enumerate(body_lines):
        if needle in line:
            return i + 1
    return 1


def write(doc: AmdDocument) -> str:
    """Serialize an AMD document back to text."""
    parts = []

    # Frontmatter
    fm_dict = doc.frontmatter.to_dict()
    if fm_dict:
        # Convert datetime back to ISO string for stable serialization
        fm_dict = _normalize_for_yaml(fm_dict)
        parts.append("---")
        parts.append(yaml.safe_dump(fm_dict, sort_keys=False, allow_unicode=True, default_flow_style=False).rstrip())
        parts.append("---")
        parts.append("")

    parts.append(doc.body_text.rstrip())
    parts.append("")

    return "\n".join(parts)


def _normalize_for_yaml(obj):
    """Recursively convert datetime and other non-YAML-native types to strings."""
    import datetime
    if isinstance(obj, dict):
        return {k: _normalize_for_yaml(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_for_yaml(v) for v in obj]
    if isinstance(obj, datetime.datetime):
        return obj.strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(obj, datetime.date):
        return obj.isoformat()
    return obj


def load_file(path: Path) -> AmdDocument:
    """Load and parse an AMD file."""
    text = path.read_text(encoding="utf-8")
    return parse(text)


def save_file(doc: AmdDocument, path: Path) -> None:
    """Serialize and save an AMD file."""
    path.write_text(write(doc), encoding="utf-8")