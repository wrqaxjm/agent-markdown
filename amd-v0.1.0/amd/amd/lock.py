"""Locking for AMD files.

Single-writer lock stored in frontmatter $locks field.
The CLI checks locks before edits to prevent concurrent modification.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .parser import AmdDocument, AmdFrontmatter


def parse_iso(s: str) -> datetime:
    """Parse ISO 8601 timestamp."""
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_lock_expired(lock: dict, now: datetime | None = None) -> bool:
    """Check if a lock is expired based on its ttl and acquired time."""
    if not lock:
        return True
    now = now or datetime.now(timezone.utc)
    try:
        acquired = parse_iso(lock.get("acquired", ""))
    except (ValueError, TypeError):
        return True

    ttl_str = lock.get("ttl", "30m")
    ttl = _parse_ttl(ttl_str)
    return now > acquired + ttl


def _parse_ttl(ttl: str) -> timedelta:
    """Parse a TTL like '30m', '1h', '2d'."""
    m = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    if not ttl:
        return timedelta(minutes=30)
    unit = ttl[-1]
    if unit not in m:
        return timedelta(minutes=30)
    try:
        n = int(ttl[:-1])
    except ValueError:
        return timedelta(minutes=30)
    return timedelta(seconds=n * m[unit])


def check_lock(doc: AmdDocument, actor: str) -> tuple[bool, str]:
    """Check if actor can edit the document.

    Returns (ok, reason). ok=True means edit is allowed.
    """
    lock = doc.frontmatter.locks
    if not lock:
        return True, "no lock held"

    holder = lock.get("holder", "")
    if holder == actor:
        return True, "you hold the lock"

    if is_lock_expired(lock):
        return True, f"lock expired (was held by {holder})"

    return False, f"locked by {holder} since {lock.get('acquired', '?')}"


def acquire_lock(doc: AmdDocument, actor: str, ttl: str = "30m") -> AmdDocument:
    """Acquire a lock on the document. Mutates and returns the doc."""
    doc.frontmatter.locks = {
        "holder": actor,
        "acquired": now_iso(),
        "ttl": ttl,
    }
    return doc


def release_lock(doc: AmdDocument) -> AmdDocument:
    """Release the lock on the document. Mutates and returns the doc."""
    doc.frontmatter.locks = None
    return doc


def refresh_lock(doc: AmdDocument, actor: str) -> AmdDocument:
    """Refresh lock timestamp (sliding lock)."""
    if doc.frontmatter.locks and doc.frontmatter.locks.get("holder") == actor:
        doc.frontmatter.locks["acquired"] = now_iso()
    return doc


def list_locks(wiki_dir: Path) -> list[dict]:
    """List all locks in a directory tree."""
    locks = []
    for md_file in wiki_dir.rglob("*.md"):
        try:
            text = md_file.read_text(encoding="utf-8")
            if "$locks" in text:
                from .parser import parse as parse_amd
                doc = parse_amd(text)
                if doc.frontmatter.locks:
                    locks.append({
                        "file": str(md_file),
                        "lock": doc.frontmatter.locks,
                        "expired": is_lock_expired(doc.frontmatter.locks),
                    })
        except Exception:
            continue
    return locks