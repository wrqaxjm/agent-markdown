"""Convert plain markdown to AMD format.

Heuristics for inferring anchors:
- Each `## Heading` becomes `## §N Heading {#id}`
- The id is a slugified version of the heading text
"""

from __future__ import annotations

import re
from pathlib import Path

from .parser import AmdDocument, AmdFrontmatter, parse, write


def slugify(text: str) -> str:
    """Turn 'Kingma & Ba (2014)' into 'kingma-ba-2014'."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def infer_anchors(doc: AmdDocument) -> AmdDocument:
    """Add §N anchors and {#id} slugs to all headings.

    Mutates and returns the doc.
    """
    lines = doc.body_text.split("\n")
    counter = 0
    seen_anchors = set()

    for h in doc.headings:
        # Skip if already has anchor
        if h.anchor and h.anchor.startswith("§") and h.anchor not in seen_anchors:
            seen_anchors.add(h.anchor)
            continue
        # Generate
        counter += 1
        anchor = f"§{counter}"
        slug = slugify(h.text)
        h.anchor = anchor
        h.custom_id = slug
        seen_anchors.add(anchor)

        # Rewrite the heading line to include the anchor attributes
        if h.line - 1 < len(lines):
            old_line = lines[h.line - 1]
            # Strip existing {attrs}
            old_line_clean = re.sub(r"\s*\{[^}]*\}\s*$", "", old_line).rstrip()
            new_line = f"{old_line_clean} {{#{slug}}}"
            lines[h.line - 1] = new_line

    doc.body_text = "\n".join(lines)
    return doc


def add_minimal_frontmatter(doc: AmdDocument, file_path: Path) -> AmdDocument:
    """Add minimal AMD frontmatter if missing."""
    if not doc.frontmatter.schema:
        doc.frontmatter.schema = "amd/v1"
    if not doc.frontmatter.id:
        doc.frontmatter.id = file_path.stem
    if doc.frontmatter.updated is None:
        from datetime import datetime, timezone
        doc.frontmatter.updated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return doc


def convert_file(src: Path, dst: Path | None = None, add_anchors: bool = True, add_fm: bool = True) -> AmdDocument:
    """Convert a single markdown file to AMD.

    If dst is None, overwrites src.
    """
    text = src.read_text(encoding="utf-8")
    doc = parse(text)

    if add_anchors:
        doc = infer_anchors(doc)
    if add_fm:
        doc = add_minimal_frontmatter(doc, src)

    out_path = dst or src
    out_path.write_text(write(doc), encoding="utf-8")
    return doc


def convert_dir(src_dir: Path, out_dir: Path | None = None, add_anchors: bool = True) -> list[Path]:
    """Convert all .md files in a directory to AMD.

    Returns list of converted files.
    """
    out_dir = out_dir or src_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    converted = []
    for md_file in src_dir.rglob("*.md"):
        if md_file.name.startswith("."):
            continue
        rel = md_file.relative_to(src_dir)
        dst = out_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        convert_file(md_file, dst, add_anchors=add_anchors)
        converted.append(dst)

    return converted