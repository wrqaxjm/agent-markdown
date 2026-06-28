# AMD v0.1.0 — Delivery

> A markdown format + toolset for AI agents.
> Built 2026-06-28 by Mavis.

## What you got

| File | What it is |
|---|---|
| `amd-v0.1.0.tar.gz` | Source archive (30 KB) — Linux/macOS |
| `amd-v0.1.0.zip` | Source archive (39 KB) — Windows-friendly |
| `amd/` | Working source tree |

## Install

```bash
tar -xzf amd-v0.1.0.tar.gz
cd amd
python3 -m venv .venv
.venv/bin/pip install -e .
```

## Verify

```bash
.venv/bin/python tests/smoke_test.py
# Expected: ✅ All smoke tests passed!
```

## Try it

```bash
# Read an AMD file
.venv/bin/amd read examples/adam-paper.amd.md

# Edit with anchor + preview
.venv/bin/amd edit examples/adam-paper.amd.md \
    --at "§2.2" \
    --action replace \
    --content "new content"

# Validate against schema
.venv/bin/amd validate examples/adam-paper.amd.md --schema source-page
```

## What's inside

- **AMD.md** (467 lines) — full format spec
- **README.md** (344 lines) — user-facing docs
- **amd/** (~2200 lines Python) — parser, operations, patch, lock, schema, query, convert, CLI
- **examples/** — 3 example files (source-page, concept-page, plain md)
- **schemas/** — 2 schema definitions
- **tests/smoke_test.py** — 18 end-to-end tests, all passing

## What works (v0.1)

✅ Parse AMD frontmatter / anchors / blocks
✅ Edit by anchor (replace / append / prepend / insert / delete / set / unset)
✅ Edit blocks (`@figure`, `@code`, `@cite`, `@backlink`, ...)
✅ Patch log with built-in undo
✅ Single-writer locks with TTL
✅ Schema validation (required fields, types, sections, blocks)
✅ SQL-like query language
✅ Convert plain markdown → AMD (infer anchors)
✅ Render to plain markdown / AST

## What's NOT in v0.1 (explicit deferrals)

❌ Multi-agent concurrent edits (CRDT — v0.4)
❌ Web UI / live preview (future)
❌ Wiki-wide backlink rendering (v0.3)
❌ LLM-driven anchor inference (future)

## License

MIT
