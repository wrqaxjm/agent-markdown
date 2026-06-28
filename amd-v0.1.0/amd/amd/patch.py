"""Patch log management.

Stores patches as JSONL alongside each AMD file, in a .amd/ directory.
Supports undo and named checkpoints.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .operations import Patch, apply_inverse


def patch_dir(file_path: Path) -> Path:
    """Return the .amd/ directory for a given file."""
    return file_path.parent / ".amd"


def log_file(file_path: Path) -> Path:
    """Return the path to the patch log file."""
    return patch_dir(file_path) / "patches.jsonl"


def checkpoint_dir(file_path: Path) -> Path:
    return patch_dir(file_path) / "checkpoints"


def ensure_dirs(file_path: Path) -> None:
    """Ensure .amd/ and .amd/checkpoints/ exist."""
    pd = patch_dir(file_path)
    pd.mkdir(parents=True, exist_ok=True)
    (pd / "checkpoints").mkdir(exist_ok=True)


def append_patch(file_path: Path, patch: Patch) -> None:
    """Append a patch to the log."""
    ensure_dirs(file_path)
    with open(log_file(file_path), "a", encoding="utf-8") as f:
        f.write(json.dumps(patch.to_dict(), ensure_ascii=False) + "\n")


def read_log(file_path: Path) -> list[Patch]:
    """Read all patches from the log."""
    lf = log_file(file_path)
    if not lf.exists():
        return []

    patches = []
    with open(lf, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                patches.append(Patch(
                    op=data["op"],
                    target=data["target"],
                    value=data.get("value"),
                    actor=data.get("actor", "anonymous"),
                    intent=data.get("intent"),
                    inverse=data.get("inverse"),
                    applied=data.get("applied", True),
                    timestamp=data.get("timestamp", ""),
                ))
            except (json.JSONDecodeError, KeyError):
                continue
    return patches


def _rewrite_log(file_path: Path, patches: list[Patch]) -> None:
    """Rewrite the patch log with the given patches."""
    lf = log_file(file_path)
    with open(lf, "w", encoding="utf-8") as f:
        for p in patches:
            f.write(json.dumps(p.to_dict(), ensure_ascii=False) + "\n")


def find_last_applied(patches: list[Patch]) -> int:
    """Return the index of the last applied patch."""
    for i in range(len(patches) - 1, -1, -1):
        if patches[i].applied:
            return i
    return -1


def undo_last(file_path: Path, from_parser, to_parser) -> tuple[bool, str]:
    """Undo the last applied patch.

    Returns (success, message).
    """
    patches = read_log(file_path)
    idx = find_last_applied(patches)
    if idx < 0:
        return False, "no patches to undo"

    patch = patches[idx]

    # Load current doc
    text = file_path.read_text(encoding="utf-8")
    doc = from_parser(text)

    # Apply inverse
    doc = apply_inverse(doc, patch)

    # Save
    to_parser(doc, file_path)

    # Mark as not applied
    patches[idx].applied = False
    _rewrite_log(file_path, patches)

    return True, f"undone patch: {patch.op} at {patch.target}"


def create_checkpoint(file_path: Path, name: str) -> Path:
    """Create a named checkpoint of the current file."""
    ensure_dirs(file_path)
    cp_path = checkpoint_dir(file_path) / f"{name}.md"
    text = file_path.read_text(encoding="utf-8")
    cp_path.write_text(text, encoding="utf-8")
    return cp_path


def restore_checkpoint(file_path: Path, name: str) -> bool:
    """Restore a named checkpoint."""
    cp_path = checkpoint_dir(file_path) / f"{name}.md"
    if not cp_path.exists():
        return False
    text = cp_path.read_text(encoding="utf-8")
    file_path.write_text(text, encoding="utf-8")
    return True


def list_checkpoints(file_path: Path) -> list[str]:
    cp_dir = checkpoint_dir(file_path)
    if not cp_dir.exists():
        return []
    return [p.stem for p in cp_dir.glob("*.md")]