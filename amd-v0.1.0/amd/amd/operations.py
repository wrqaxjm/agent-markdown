"""Patch operations on AMD documents.

Each operation is applied to an AmdDocument and returns the modified doc
plus the inverse patch (for undo).

Operations supported:
- replace: replace content at anchor
- prepend / append: add content at start/end of anchor target
- insert-after / insert-before: insert at a position
- delete: remove content
- set: set a metadata field
- create-block: add a structured block
- delete-block: remove a named block
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .parser import AmdBlock, AmdDocument, AmdFrontmatter


@dataclass
class Patch:
    """A single patch operation."""

    op: str
    target: dict[str, Any]
    value: Any = None
    actor: str = "anonymous"
    intent: str | None = None
    inverse: dict[str, Any] | None = None
    applied: bool = True
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "op": self.op,
            "actor": self.actor,
            "intent": self.intent,
            "applied": self.applied,
            "timestamp": self.timestamp,
            "target": self.target,
            "value": self.value,
            "inverse": self.inverse,
        }


class PatchError(Exception):
    """Raised when a patch cannot be applied."""


def _split_body_by_section(doc: AmdDocument) -> list[tuple[int, int, str]]:
    """Split body_text into sections: [(start_line, end_line, raw_text), ...].

    Pre-section (before any heading) is one section.
    Each heading starts a new section that runs until the next same-or-higher-level heading.
    """
    lines = doc.body_text.split("\n")
    sections = []
    if not doc.headings:
        sections.append((1, len(lines), "\n".join(lines)))
        return sections

    # Pre-section (lines before first heading)
    first_heading_line = doc.headings[0].line
    if first_heading_line > 1:
        pre = "\n".join(lines[:first_heading_line - 1])
        if pre.strip():
            sections.append((1, first_heading_line - 1, pre))

    # Each heading section
    for i, h in enumerate(doc.headings):
        start = h.line
        end = len(lines)
        for h2 in doc.headings[i + 1:]:
            if h2.level <= h.level:
                end = h2.line - 1
                break
        sections.append((start, end, "\n".join(lines[start - 1:end])))

    return sections


def _resolve_anchor(doc: AmdDocument, anchor: str) -> tuple[int, int] | None:
    """Resolve an anchor to (start_line, end_line) in body_text.

    Anchor formats:
    - §N / §N.M
    - {#custom-id}
    - @frontmatter
    - @frontmatter/$fields/field
    - @backlinks
    - line:N
    """
    if anchor.startswith("§"):
        target = doc.find_heading_by_anchor(anchor)
        if not target:
            raise PatchError(f"anchor not found: {anchor}")
        sections = _split_body_by_section(doc)
        for start, end, _ in sections:
            if start == target.line:
                return (start, end)
        return (target.line, len(doc.body_text.split("\n")))

    if anchor.startswith("line:"):
        try:
            n = int(anchor[5:])
            return (n, n)
        except ValueError:
            raise PatchError(f"invalid line anchor: {anchor}")

    if anchor.startswith("#"):
        custom_id = anchor[1:]
        for h in doc.headings:
            if h.custom_id == custom_id:
                sections = _split_body_by_section(doc)
                for start, end, _ in sections:
                    if start == h.line:
                        return (start, end)
                return (h.line, len(doc.body_text.split("\n")))
        raise PatchError(f"custom anchor not found: {anchor}")

    if anchor == "@frontmatter":
        # No body lines
        return None

    if anchor.startswith("@frontmatter/$fields/"):
        field_name = anchor[len("@frontmatter/$fields/"):]
        if field_name not in doc.frontmatter.fields:
            raise PatchError(f"field not found: {field_name}")
        return None  # handled specially

    if anchor == "@backlinks":
        return None  # handled specially

    raise PatchError(f"unrecognized anchor: {anchor}")


def apply_patch(doc: AmdDocument, patch: Patch) -> AmdDocument:
    """Apply a patch to a document. Mutates the doc.

    Returns the (mutated) doc. Also fills in patch.inverse if not provided.
    """
    anchor = patch.target.get("anchor", "")
    op = patch.op

    # Dispatch
    if op == "amd.replace":
        return _op_replace(doc, patch, anchor)
    elif op == "amd.prepend":
        return _op_prepend(doc, patch, anchor)
    elif op == "amd.append":
        return _op_append(doc, patch, anchor)
    elif op == "amd.insert-after":
        return _op_insert_after(doc, patch, anchor)
    elif op == "amd.insert-before":
        return _op_insert_before(doc, patch, anchor)
    elif op == "amd.delete":
        return _op_delete(doc, patch, anchor)
    elif op == "amd.set":
        return _op_set(doc, patch, anchor)
    elif op == "amd.unset":
        return _op_unset(doc, patch, anchor)
    elif op == "amd.create-block":
        return _op_create_block(doc, patch, anchor)
    elif op == "amd.delete-block":
        return _op_delete_block(doc, patch, anchor)
    else:
        raise PatchError(f"unknown op: {op}")


def _build_inverse(
    op: str,
    target: dict,
    before: Any,
    actor: str,
) -> dict:
    """Build an inverse patch description."""
    inverse_op_map = {
        "amd.replace": "amd.replace",
        "amd.prepend": "amd.delete",
        "amd.append": "amd.delete",
        "amd.insert-after": "amd.delete",
        "amd.insert-before": "amd.delete",
        "amd.delete": "amd.replace",
        "amd.set": "amd.set",
        "amd.unset": "amd.set",
        "amd.create-block": "amd.delete-block",
        "amd.delete-block": "amd.create-block",
    }
    inverse_op = inverse_op_map.get(op, op)
    return {
        "op": inverse_op,
        "target": target,
        "value": before,
        "actor": actor,
        "reason": f"inverse of {op}",
    }


def _op_replace(doc: AmdDocument, patch: Patch, anchor: str) -> AmdDocument:
    if anchor.startswith("@frontmatter"):
        return _op_set(doc, patch, anchor)

    range_ = _resolve_anchor(doc, anchor)
    if range_ is None:
        raise PatchError(f"cannot replace at anchor: {anchor}")

    lines = doc.body_text.split("\n")
    start, end = range_
    # Convert to 0-indexed
    start_idx = start - 1
    end_idx = end  # exclusive

    before = "\n".join(lines[start_idx:end_idx])

    new_content = str(patch.value) if patch.value is not None else ""
    new_lines = new_content.split("\n")

    # Detect if the original section ended with a trailing blank line (separator)
    # and preserve it so the next section still has its visual break.
    had_trailing_blank = (
        end_idx > start_idx
        and lines[end_idx - 1] == ""
    )
    if had_trailing_blank and (not new_lines or new_lines[-1] != ""):
        new_lines.append("")

    lines[start_idx:end_idx] = new_lines
    doc.body_text = "\n".join(lines)

    if patch.inverse is None:
        patch.inverse = _build_inverse(patch.op, patch.target, before, patch.actor)

    return doc


def _op_prepend(doc: AmdDocument, patch: Patch, anchor: str) -> AmdDocument:
    range_ = _resolve_anchor(doc, anchor)
    if range_ is None:
        raise PatchError(f"cannot prepend at anchor: {anchor}")

    lines = doc.body_text.split("\n")
    start_idx = range_[0] - 1

    new_content = str(patch.value) if patch.value is not None else ""
    lines.insert(start_idx, new_content)
    doc.body_text = "\n".join(lines)

    # Update heading line numbers
    for h in doc.headings:
        if h.line >= range_[0]:
            h.line += 1
    for b in doc.blocks:
        if b.line >= range_[0]:
            b.line += 1

    if patch.inverse is None:
        patch.inverse = _build_inverse(patch.op, patch.target, new_content, patch.actor)

    return doc


def _op_append(doc: AmdDocument, patch: Patch, anchor: str) -> AmdDocument:
    range_ = _resolve_anchor(doc, anchor)
    if range_ is None:
        raise PatchError(f"cannot append at anchor: {anchor}")

    lines = doc.body_text.split("\n")
    end_idx = range_[1]  # exclusive

    new_content = str(patch.value) if patch.value is not None else ""
    lines.insert(end_idx, new_content)
    doc.body_text = "\n".join(lines)

    if patch.inverse is None:
        patch.inverse = _build_inverse(patch.op, patch.target, new_content, patch.actor)

    return doc


def _op_insert_after(doc: AmdDocument, patch: Patch, anchor: str) -> AmdDocument:
    return _op_append(doc, patch, anchor)


def _op_insert_before(doc: AmdDocument, patch: Patch, anchor: str) -> AmdDocument:
    return _op_prepend(doc, patch, anchor)


def _op_delete(doc: AmdDocument, patch: Patch, anchor: str) -> AmdDocument:
    range_ = _resolve_anchor(doc, anchor)
    if range_ is None:
        raise PatchError(f"cannot delete at anchor: {anchor}")

    lines = doc.body_text.split("\n")
    start_idx = range_[0] - 1
    end_idx = range_[1]

    before = "\n".join(lines[start_idx:end_idx])
    del lines[start_idx:end_idx]
    doc.body_text = "\n".join(lines)

    # Update heading line numbers
    deleted_count = end_idx - start_idx
    for h in doc.headings:
        if h.line > range_[1]:
            h.line -= deleted_count
    for b in doc.blocks:
        if b.line > range_[1]:
            b.line -= deleted_count

    if patch.inverse is None:
        patch.inverse = _build_inverse(patch.op, patch.target, before, patch.actor)

    return doc


def _op_set(doc: AmdDocument, patch: Patch, anchor: str) -> AmdDocument:
    if not anchor.startswith("@frontmatter/$fields/"):
        raise PatchError(f"set op requires @frontmatter/$fields/... anchor, got {anchor}")

    field_name = anchor[len("@frontmatter/$fields/"):]
    before = doc.frontmatter.fields.get(field_name)
    doc.frontmatter.fields[field_name] = patch.value

    if patch.inverse is None:
        patch.inverse = _build_inverse(patch.op, patch.target, before, patch.actor)

    return doc


def _op_unset(doc: AmdDocument, patch: Patch, anchor: str) -> AmdDocument:
    if not anchor.startswith("@frontmatter/$fields/"):
        raise PatchError(f"unset op requires @frontmatter/$fields/... anchor")

    field_name = anchor[len("@frontmatter/$fields/"):]
    before = doc.frontmatter.fields.pop(field_name, None)

    if patch.inverse is None:
        patch.inverse = _build_inverse(patch.op, patch.target, before, patch.actor)

    return doc


def _op_create_block(doc: AmdDocument, patch: Patch, anchor: str) -> AmdDocument:
    """Create a structured block (e.g., @figure, @code) at anchor."""
    if not anchor.startswith("§"):
        raise PatchError(f"create-block requires a section anchor, got {anchor}")

    target = doc.find_heading_by_anchor(anchor)
    if not target:
        raise PatchError(f"section not found: {anchor}")

    block_type = patch.target.get("block_type", "block")
    block_name = patch.target.get("block_name")

    # Format the block text
    attrs = patch.value if isinstance(patch.value, dict) else {"value": patch.value}
    attrs_str = "\n".join(f"  {k}: {v}" for k, v in attrs.items())
    name_suffix = f"-{block_name}" if block_name else ""
    block_text = f"@{block_type}{name_suffix} {{\n{attrs_str}\n}}"

    # Append to the section
    range_ = _resolve_anchor(doc, anchor)
    lines = doc.body_text.split("\n")
    end_idx = range_[1]
    lines.insert(end_idx, block_text)
    doc.body_text = "\n".join(lines)

    # Record the new block
    new_block = AmdBlock(
        type=block_type,
        name=block_name,
        attrs=attrs,
        line=end_idx + 1,
    )
    doc.blocks.append(new_block)

    if patch.inverse is None:
        patch.inverse = _build_inverse(patch.op, patch.target, block_text, patch.actor)

    return doc


def _op_delete_block(doc: AmdDocument, patch: Patch, anchor: str) -> AmdDocument:
    """Delete a named block."""
    block_name = patch.target.get("block_name")
    block_type = patch.target.get("block_type")

    target_block = None
    for b in doc.blocks:
        if (block_name and b.name == block_name) or (
            block_type and b.type == block_type and not block_name
        ):
            target_block = b
            break

    if not target_block:
        raise PatchError(f"block not found: {block_name or block_type}")

    lines = doc.body_text.split("\n")
    line_idx = target_block.line - 1
    # Delete the line and any continuation lines (lines starting with whitespace until blank)
    end_idx = line_idx + 1
    while end_idx < len(lines) and (lines[end_idx].startswith(" ") or lines[end_idx].startswith("\t")):
        end_idx += 1

    before = "\n".join(lines[line_idx:end_idx])
    del lines[line_idx:end_idx]
    doc.body_text = "\n".join(lines)

    # Remove from blocks list
    doc.blocks = [b for b in doc.blocks if b is not target_block]

    # Update other blocks' line numbers
    deleted_count = end_idx - line_idx
    for b in doc.blocks:
        if b.line > target_block.line:
            b.line -= deleted_count
    for h in doc.headings:
        if h.line > target_block.line:
            h.line -= deleted_count

    if patch.inverse is None:
        patch.inverse = _build_inverse(patch.op, patch.target, before, patch.actor)

    return doc


def apply_inverse(doc: AmdDocument, patch: Patch) -> AmdDocument:
    """Apply the inverse of a patch to undo it."""
    if not patch.inverse:
        raise PatchError("patch has no inverse")

    inverse = Patch(
        op=patch.inverse["op"],
        target=patch.inverse["target"],
        value=patch.inverse.get("value"),
        actor=patch.inverse.get("actor", "anonymous"),
        intent=patch.inverse.get("reason", "undo"),
    )
    return apply_patch(doc, inverse)