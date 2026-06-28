#!/usr/bin/env python3
"""End-to-end smoke test for AMD.

Tests the core workflow:
1. Parse an AMD file
2. Display its structure
3. Apply a series of patches
4. Verify undo works
5. Run a query
6. Validate against a schema
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
AMD = REPO / ".venv" / "bin" / "amd"
if not AMD.exists():
    import shutil
    sys_amd = shutil.which("amd")
    if sys_amd:
        AMD = Path(sys_amd)
EXAMPLE = REPO / "examples" / "adam-paper.amd.md"


def run(args, check=True, capture=True):
    """Run amd CLI with given args."""
    cmd = [str(AMD)] + args
    result = subprocess.run(cmd, capture_output=capture, text=True)
    if check and result.returncode != 0:
        print(f"FAILED: {cmd}")
        print(f"stdout: {result.stdout}")
        print(f"stderr: {result.stderr}")
        sys.exit(1)
    return result


def test(label, condition, message=""):
    if condition:
        print(f"  ✅ {label}")
    else:
        print(f"  ❌ {label}: {message}")
        sys.exit(1)


def section(title):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print('=' * 60)


def main():
    # Reset state: remove .amd directory and restore example file
    import shutil
    amd_dir = EXAMPLE.parent / ".amd"
    if amd_dir.exists():
        shutil.rmtree(amd_dir)

    # Restore the example file to canonical state
    canonical = REPO / "examples" / "adam-paper.amd.md"
    if canonical.exists():
        text = canonical.read_text()
        # Ensure §5 section is present
        if "## §5 Notes" not in text:
            section_5 = """\n## §5 Notes {#s5 .agent-notes}\n\n<!-- @actor: agent:mavis:414131408429400, @confidence: 0.90, @reviewed: false -->\nThis paper was foundational for adaptive optimizers in deep learning. The key insight is combining momentum with per-parameter learning rate adaptation. Note that the bias correction is essential during early training \u2014 without it, the effective step size is too small.\n\n<!-- @actor: agent:mavis:414131408429400, @confidence: 0.75 -->\nConnection to RMSProp: Adam can be seen as RMSProp + momentum. The original RMSProp paper is unpublished but referenced widely.\n"""
            canonical.write_text(text.rstrip() + "\n" + section_5)
        # Reset year if it was changed
        text = canonical.read_text()
        import re as _re
        text = _re.sub(r'^(\s+year:\s+).*$', r'\g<1>2014', text, flags=_re.MULTILINE)
        text = _re.sub(r'\$locks:.*?(?=\n\$|\n---|\Z)', '', text, flags=_re.DOTALL)
        canonical.write_text(text)

    section("1. Read AMD file")
    result = run(["read", str(EXAMPLE)])
    test("read shows frontmatter", "schema: amd/v1" in result.stdout)
    test("read shows headings", "§1 Summary" in result.stdout)
    test("read shows blocks", "@figure" in result.stdout)

    section("2. Read as JSON")
    result = run(["read", str(EXAMPLE), "--format", "json"])
    test("json output valid", '"$schema": "amd/v1"' in result.stdout)
    test("json shows blocks", '"type": "figure"' in result.stdout)

    section("3. Edit with metadata set")
    result = run([
        "edit", str(EXAMPLE),
        "--at", "@frontmatter/$fields/year",
        "--action", "set",
        "--value", "2015",
        "--yes",
    ])
    test("set succeeded", "Applied: amd.set" in result.stdout)

    result = run(["read", str(EXAMPLE), "--format", "json"])
    test("year updated to 2015", '"year": 2015' in result.stdout)

    section("4. Undo")
    run(["unlock", str(EXAMPLE)])
    result = run(["undo", str(EXAMPLE)])
    test("undo succeeded", "undone patch" in result.stdout)

    result = run(["read", str(EXAMPLE), "--format", "json"])
    test("year reverted to 2014", '"year": 2014' in result.stdout)

    section("5. Edit body content")
    result = run([
        "edit", str(EXAMPLE),
        "--at", "§5",
        "--action", "append",
        "--content", "\nThis is an additional agent note added by the smoke test.",
        "--yes",
    ])
    test("append succeeded", "Applied: amd.append" in result.stdout)

    result = run(["undo", str(EXAMPLE)])
    test("undo append succeeded", "undone patch" in result.stdout)

    section("6. Validate")
    result = run(["validate", str(EXAMPLE), "--schema", "source-page"], check=False)
    test("validate succeeded", "is valid" in result.stdout)

    section("7. Validate with bad data")
    # First, break the schema
    run([
        "edit", str(EXAMPLE),
        "--at", "@frontmatter/$fields/year",
        "--action", "set",
        "--value", '"not-a-number"',
        "--yes",
    ])
    result = run(["validate", str(EXAMPLE), "--schema", "source-page"], check=False)
    has_error = result.returncode != 0 or "wrong type" in result.stdout
    test("validation caught bad type", has_error)
    run(["undo", str(EXAMPLE)])

    section("8. Query")
    result = run([
        "query", str(EXAMPLE),
        "SELECT file FROM examples/adam-paper.amd.md WHERE $fields.year = 2014",
    ])
    test("query returned a result", "adam-paper" in result.stdout)

    section("9. Lock")
    run(["unlock", str(EXAMPLE)])
    result = run(["lock", str(EXAMPLE), "--holder", "agent:test", "--ttl", "5m"])
    test("lock acquired", "Locked by agent:test" in result.stdout)

    # Try to edit from different actor - should fail
    result = run([
        "edit", str(EXAMPLE),
        "--at", "@frontmatter/$fields/year",
        "--action", "set",
        "--value", "2020",
        "--actor", "agent:other",
        "--yes",
    ], check=False)
    test("locked file rejects other actor", result.returncode != 0)

    run(["unlock", str(EXAMPLE)])

    section("10. Convert plain markdown")
    plain = REPO / "examples" / "plain-readme.md"
    backup = plain.read_text()
    run(["convert", str(plain), "--infer-anchors", "--add-frontmatter"])
    converted = plain.read_text()
    test("frontmatter added", "schema: amd/v1" in converted)
    test("anchors inferred", "§1" in converted or "{#" in converted)
    plain.write_text(backup)  # restore

    section("11. List locks")
    result = run(["locks", str(EXAMPLE)])
    test("locks command works", "No active locks" in result.stdout or "🔒" in result.stdout)

    section("12. Patch log")
    result = run(["log", str(EXAMPLE)])
    test("log shows patches", "amd." in result.stdout)

    print()
    print("=" * 60)
    print("  ✅ All smoke tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()