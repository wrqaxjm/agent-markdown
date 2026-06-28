"""AMD CLI.

Command-line interface for AMD format operations.

Usage:
    amd read <file> [--at ANCHOR]
    amd edit <file> --at ANCHOR --action ACTION [--content TEXT] [--preview|--yes]
    amd validate <file> [--schema NAME]
    amd query <path> "SELECT ..."
    amd lock/unlock <file>
    amd log <file>
    amd undo <file>
    amd checkpoint <file> --name NAME
    amd convert <path> [--batch] [--output DIR]
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import click

from . import __version__
from . import convert as convert_mod
from . import lock as lock_mod
from . import operations as ops
from . import parser as parser_mod
from . import patch as patch_mod
from . import query as query_mod
from . import schema as schema_mod


def _print_diff(before: str, after: str, label: str = "diff") -> None:
    """Print a unified diff with simple line markers."""
    before_lines = before.split("\n")
    after_lines = after.split("\n")

    click.echo(f"--- {label} (before)")
    for line in before_lines:
        click.echo(f"  {line}")
    click.echo(f"+++ {label} (after)")
    for line in after_lines:
        click.echo(f"  {line}")


@click.group()
@click.version_option(version=__version__, prog_name="amd")
def cli():
    """AMD — Agent Markdown Document tool."""


@cli.command()
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--at", "anchor", default=None, help="Show only this anchor's content.")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
def read(file: Path, anchor: str | None, fmt: str):
    """Read and display an AMD file's structure."""
    doc = parser_mod.load_file(file)

    if fmt == "json":
        result = {
            "frontmatter": parser_mod._normalize_for_yaml(doc.frontmatter.to_dict()),
            "headings": [
                {
                    "anchor": h.anchor,
                    "custom_id": h.custom_id,
                    "level": h.level,
                    "text": h.text,
                    "classes": h.classes,
                    "line": h.line,
                }
                for h in doc.headings
            ],
            "blocks": [
                {
                    "type": b.type,
                    "name": b.name,
                    "attrs": b.attrs,
                    "line": b.line,
                }
                for b in doc.blocks
            ],
        }
        click.echo(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # Text format
    if doc.frontmatter.schema or doc.frontmatter.fields:
        click.echo("Frontmatter:")
        click.echo(f"  schema: {doc.frontmatter.schema}")
        click.echo(f"  id:     {doc.frontmatter.id}")
        click.echo(f"  type:   {doc.frontmatter.type}")
        if doc.frontmatter.fields:
            click.echo(f"  fields:")
            for k, v in doc.frontmatter.fields.items():
                click.echo(f"    {k}: {v}")
        click.echo()

    click.echo(f"Headings ({len(doc.headings)}):")
    for h in doc.headings:
        cls_str = ".".join(h.classes) if h.classes else ""
        flag_str = ",".join(h.flags) if h.flags else ""
        parts = [h.anchor or "(no anchor)"]
        if cls_str:
            parts.append(f"class:{cls_str}")
        if flag_str:
            parts.append(f"flag:{flag_str}")
        meta = " ".join(parts)
        click.echo(f"  {meta:<40} h{h.level} line {h.line:>4}  {h.text}")

    if doc.blocks:
        click.echo(f"\nBlocks ({len(doc.blocks)}):")
        for b in doc.blocks:
            name_str = f"-{b.name}" if b.name else ""
            click.echo(f"  @{b.type}{name_str}  L{b.line:>4}  {b.attrs}")


@cli.command()
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--at", "anchor", required=True, help="Anchor to edit (§N, {#id}, line:N, @frontmatter/$fields/X).")
@click.option("--action", required=True, type=click.Choice([
    "replace", "prepend", "append", "insert-after", "insert-before", "delete",
    "set", "unset", "create-block", "delete-block",
]))
@click.option("--content", default=None, help="New content (text or JSON for blocks/metadata).")
@click.option("--value", default=None, help="Alias for --content (for set/unset).")
@click.option("--block-type", default=None, help="Block type for create-block/delete-block.")
@click.option("--block-name", default=None, help="Block name for create-block/delete-block.")
@click.option("--actor", default="human", help="Actor identity (e.g. 'agent:mavis:1234').")
@click.option("--intent", default=None, help="Free-form intent for the patch.")
@click.option("--yes", is_flag=True, help="Skip preview, apply immediately.")
@click.option("--preview/--no-preview", default=True, help="Show diff before applying.")
@click.option("--lock/--no-lock", default=True, help="Acquire/refresh lock.")
def edit(file: Path, anchor: str, action: str, content: str | None,
         value: str | None,
         block_type: str | None, block_name: str | None,
         actor: str, intent: str | None,
         yes: bool, preview: bool, lock: bool):
    """Edit an AMD file at a specific anchor."""
    doc = parser_mod.load_file(file)

    # Check lock
    if lock:
        ok, reason = lock_mod.check_lock(doc, actor)
        if not ok:
            click.echo(f"❌ Cannot edit: {reason}", err=True)
            sys.exit(1)
        if not doc.frontmatter.locks:
            click.echo(f"🔒 Acquiring lock as {actor}")
            lock_mod.acquire_lock(doc, actor)

    # Use --value as alias for --content if both provided
    if value is not None and content is None:
        content = value

    # Parse content for metadata ops
    parsed_value = content
    if action in ("set", "create-block") and content:
        try:
            parsed_value = json.loads(content)
        except json.JSONDecodeError:
            # Treat as plain string
            pass

    # Build target
    target = {"file": str(file), "anchor": anchor}
    if block_type:
        target["block_type"] = block_type
    if block_name:
        target["block_name"] = block_name

    # Map action names to op names
    op_map = {
        "replace": "amd.replace",
        "prepend": "amd.prepend",
        "append": "amd.append",
        "insert-after": "amd.insert-after",
        "insert-before": "amd.insert-before",
        "delete": "amd.delete",
        "set": "amd.set",
        "unset": "amd.unset",
        "create-block": "amd.create-block",
        "delete-block": "amd.delete-block",
    }
    op = op_map[action]

    # Build patch
    patch = ops.Patch(
        op=op,
        target=target,
        value=parsed_value,
        actor=actor,
        intent=intent,
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    # Capture before state for preview
    before_text = parser_mod.write(doc)

    # Apply
    try:
        doc = ops.apply_patch(doc, patch)
    except ops.PatchError as e:
        click.echo(f"❌ Patch failed: {e}", err=True)
        sys.exit(1)

    after_text = parser_mod.write(doc)

    # Preview
    if preview and not yes:
        click.echo("=" * 60)
        click.echo(f"Patch: {op} at {anchor}")
        if intent:
            click.echo(f"Intent: {intent}")
        click.echo("=" * 60)
        _print_diff(before_text, after_text, str(file))
        click.echo("=" * 60)
        if not click.confirm("Apply this change?", default=True):
            click.echo("Aborted.")
            sys.exit(0)

    # Refresh lock timestamp
    if lock and doc.frontmatter.locks:
        lock_mod.refresh_lock(doc, actor)

    # Save
    parser_mod.save_file(doc, file)

    # Append to patch log
    patch_mod.append_patch(file, patch)

    click.echo(f"✅ Applied: {op} at {anchor}")
    if patch.inverse:
        click.echo(f"   Inverse stored in patch log: .amd/patches.jsonl")


@cli.command()
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--schema", "schema_name", default=None, help="Schema name to validate against.")
@click.option("--strict", is_flag=True, help="Treat warnings as errors.")
def validate(file: Path, schema_name: str | None, strict: bool):
    """Validate an AMD file against a schema."""
    doc = parser_mod.load_file(file)

    if schema_name:
        # Find schema file
        schema_path = _find_schema(schema_name)
        if not schema_path:
            click.echo(f"❌ Schema not found: {schema_name}", err=True)
            sys.exit(1)
        schema = schema_mod.Schema.from_file(schema_path)
    else:
        # Use minimal validation
        schema = schema_mod.Schema(id="minimal")

    errors = schema_mod.validate(doc, schema)

    if not errors:
        click.echo(f"✅ {file} is valid.")
        return

    for err in errors:
        icon = "❌" if err.severity == "error" else "⚠️ "
        loc = f" [{err.location}]" if err.location else ""
        click.echo(f"{icon} {err.message}{loc}")

    has_errors = any(e.severity == "error" for e in errors)
    if has_errors or (strict and errors):
        sys.exit(1)


def _find_schema(name: str) -> Path | None:
    """Look for a schema file by name."""
    search_paths = [
        Path.cwd() / "schemas" / f"{name}.yaml",
        Path.cwd() / "schemas" / f"{name}.yml",
        Path(__file__).parent.parent / "schemas" / f"{name}.yaml",
        Path(__file__).parent.parent / "schemas" / f"{name}.yml",
    ]
    for p in search_paths:
        if p.exists():
            return p
    return None


@cli.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.argument("query")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
def query(path: Path, query: str, fmt: str):
    """Run a query against an AMD file or directory."""
    if path.is_dir():
        files = list(path.rglob("*.md"))
    else:
        files = [path]

    results = query_mod.execute(query, files, base_dir=path if path.is_dir() else path.parent)

    if fmt == "json":
        click.echo(json.dumps(results, ensure_ascii=False, indent=2))
        return

    if not results:
        click.echo("No matches.")
        return

    for r in results:
        keys = [f"{k}={v}" for k, v in r.items() if k != "fields"]
        click.echo("  " + "  ".join(keys))


@cli.command()
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--holder", required=True, help="Actor identity holding the lock.")
@click.option("--ttl", default="30m", help="Lock TTL (e.g. 30m, 1h, 2d).")
def lock(file: Path, holder: str, ttl: str):
    """Acquire a lock on an AMD file."""
    doc = parser_mod.load_file(file)

    ok, reason = lock_mod.check_lock(doc, holder)
    if not ok:
        click.echo(f"❌ {reason}", err=True)
        sys.exit(1)

    lock_mod.acquire_lock(doc, holder, ttl)
    parser_mod.save_file(doc, file)
    click.echo(f"🔒 Locked by {holder} (ttl={ttl})")


@cli.command()
@click.argument("file", type=click.Path(exists=True, path_type=Path))
def unlock(file: Path):
    """Release the lock on an AMD file."""
    doc = parser_mod.load_file(file)
    lock_mod.release_lock(doc)
    parser_mod.save_file(doc, file)
    click.echo(f"🔓 Unlocked")


@cli.command(name="locks")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
def list_locks_cmd(path: Path):
    """List all current locks under a directory."""
    if path.is_file():
        paths = [path]
    else:
        paths = list(path.rglob("*.md"))

    locks = []
    for p in paths:
        try:
            doc = parser_mod.load_file(p)
            if doc.frontmatter.locks:
                locks.append({
                    "file": str(p),
                    "holder": doc.frontmatter.locks.get("holder"),
                    "ttl": doc.frontmatter.locks.get("ttl"),
                    "expired": lock_mod.is_lock_expired(doc.frontmatter.locks),
                })
        except Exception:
            continue

    if not locks:
        click.echo("No active locks.")
        return

    for l in locks:
        icon = "🔒" if not l["expired"] else "🔓"
        click.echo(f"{icon} {l['file']}  →  {l['holder']}  (ttl={l['ttl']})")


@cli.command()
@click.argument("file", type=click.Path(exists=True, path_type=Path))
def log(file: Path):
    """Show patch log for an AMD file."""
    patches = patch_mod.read_log(file)
    if not patches:
        click.echo("No patches recorded.")
        return

    for i, p in enumerate(patches):
        status = "✓" if p.applied else "↶"
        intent = f"  ({p.intent})" if p.intent else ""
        click.echo(f"{i:3} {status}  {p.op}  {p.target.get('anchor', '')}{intent}")
        click.echo(f"      actor: {p.actor}  {p.timestamp}")


@cli.command()
@click.argument("file", type=click.Path(exists=True, path_type=Path))
def undo(file: Path):
    """Undo the last applied patch."""
    success, msg = patch_mod.undo_last(file, parser_mod.parse, parser_mod.save_file)
    if success:
        click.echo(f"↶ {msg}")
    else:
        click.echo(f"❌ {msg}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--name", required=True, help="Checkpoint name.")
def checkpoint(file: Path, name: str):
    """Create a named checkpoint of the current file."""
    cp_path = patch_mod.create_checkpoint(file, name)
    click.echo(f"📌 Checkpoint saved: {cp_path}")


@cli.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--output", "out_dir", type=click.Path(), default=None, help="Output directory (default: in-place).")
@click.option("--batch", is_flag=True, help="Process directory recursively.")
@click.option("--infer-anchors/--no-infer-anchors", default=True, help="Add §N anchors to headings.")
@click.option("--add-frontmatter/--no-add-frontmatter", default=True, help="Add minimal frontmatter.")
def convert(path: Path, out_dir: str | None, batch: bool, infer_anchors: bool, add_frontmatter: bool):
    """Convert plain markdown to AMD format."""
    out = Path(out_dir) if out_dir else None

    if path.is_dir():
        out_target = out or path
        converted = convert_mod.convert_dir(path, out_target, add_anchors=infer_anchors)
        for f in converted:
            click.echo(f"  ✓ {f}")
        click.echo(f"\n{len(converted)} file(s) converted.")
    else:
        doc = convert_mod.convert_file(
            path, out,
            add_anchors=infer_anchors,
            add_fm=add_frontmatter,
        )
        click.echo(f"✓ Converted: {path}")


@cli.command()
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--to", "target", type=click.Choice(["plain-markdown", "ast"]), default="plain-markdown")
def render(file: Path, target: str):
    """Render an AMD file to another format."""
    doc = parser_mod.load_file(file)

    if target == "plain-markdown":
        # Strip AMD extensions: custom frontmatter fields → keep $schema only
        from .parser import AmdFrontmatter
        minimal_fm = AmdFrontmatter(
            schema="amd/v1",
            id=doc.frontmatter.id,
        )
        doc.frontmatter = minimal_fm
        click.echo(parser_mod.write(doc), nl=False)
    elif target == "ast":
        result = {
            "frontmatter": parser_mod._normalize_for_yaml(doc.frontmatter.to_dict()),
            "headings": [{"anchor": h.anchor, "level": h.level, "text": h.text} for h in doc.headings],
            "blocks": [{"type": b.type, "name": b.name, "attrs": b.attrs} for b in doc.blocks],
        }
        click.echo(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    cli()


if __name__ == "__main__":
    main()