# AMD — Agent Markdown Document

> A markdown format and toolset designed for **AI agents** that need to read, edit, and verify markdown files efficiently.

[![status](https://img.shields.io/badge/status-v0.1-blue)]() [![python](https://img.shields.io/badge/python-3.10%2B-blue)]() [![license](https://img.shields.io/badge/license-MIT-green)]()

## What it solves

Markdown is great for humans but painful for AI agents:

- ❌ Editing relies on fragile string matching
- ❌ Sections are identified by text, not by stable IDs
- ❌ No structured metadata, just loose YAML frontmatter
- ❌ No atomic operations, no undo, no locks
- ❌ No schema validation, typos break wikis

**AMD** fixes all of these by adding a thin layer of structure on top of markdown:

- ✅ Every section has a **stable anchor** (`§N`, `{#id}`, `.class`)
- ✅ **Typed frontmatter** with `$schema`, `$type`, `$fields`, `$locks`
- ✅ **Structured blocks** for figures, code, citations, backlinks
- ✅ **Patch log with built-in undo** — every edit is reversible
- ✅ **Single-writer locks** to prevent agent collisions
- ✅ **Schema validation** — catch errors before they corrupt your wiki

And critically: **plain markdown files still work**. AMD is a superset. Existing `.md` files keep working with reduced features.

## Quick start

### Install

```bash
cd /workspace/amd
python3 -m venv .venv
.venv/bin/pip install -e .
```

### Try on the example

```bash
./.venv/bin/amd read examples/adam-paper.amd.md
```

Output:

```
Frontmatter:
  schema: amd/v1
  id:     adam-paper
  type:   source-page
  fields:
    arxiv_id: 1412.6980
    year: 2014
    authors: ['Kingma, D.P.', 'Ba, J.']
    tags: ['optimizer', 'adaptive-gradient', 'deep-learning']

Headings (8):
  (no anchor)                              h1 line    1  Adam: A Method for Stochastic Optimization
  §1 class:abstract flag:required          h2 line    3  §1 Summary
  §2 class:method flag:required            h2 line    7  §2 Method
  §2.1 class:algorithm                     h3 line    9  §2.1 Algorithm
  §2.2                                     h3 line   19  §2.2 Bias Correction
  §3 class:figures flag:required           h2 line   23  §3 Figures
  §4 class:backlinks flag:required         h2 line   39  §4 References
  §5 class:agent-notes                     h2 line   59  §5 Notes

Blocks (5):
  @figure    line 26  {src: ..., alt: ..., caption: ...}
  @figure    line 33  {src: ..., alt: ..., caption: ...}
  @backlink  line 42  {from: "[[Adam]]", kind: defines}
  ...
```

### Edit by anchor (preview by default!)

```bash
./.venv/bin/amd edit examples/adam-paper.amd.md \
    --at "§2.2" \
    --action replace \
    --content "The exponential moving averages are initialized at vectors of zero..."
```

You'll see a diff and be asked to confirm before the file is written.

Skip the preview when you're sure:

```bash
./.venv/bin/amd edit examples/adam-paper.amd.md \
    --at "§2.2" --action replace \
    --content "..." --yes
```

### Set metadata

```bash
./.venv/bin/amd edit examples/adam-paper.amd.md \
    --at "@frontmatter/\$fields/year" \
    --action set \
    --value "2015"
```

### Undo

```bash
./.venv/bin/amd undo examples/adam-paper.amd.md
```

Every edit is logged in `.amd/patches.jsonl` with an inverse patch, so undo always works.

### Validate against a schema

```bash
./.venv/bin/amd validate examples/adam-paper.amd.md --schema source-page
```

Schemas live in `schemas/`. See `schemas/source-page.yaml` for an example.

### Query

```bash
./.venv/bin/amd query examples/adam-paper.amd.md \
    "SELECT file FROM examples WHERE \$fields.year = 2014"
```

### Convert plain markdown

```bash
./.venv/bin/amd convert plain-readme.md --infer-anchors --add-frontmatter
```

This adds `§N` anchors to headings and minimal frontmatter.

### Lock files when collaborating

```bash
./.venv/bin/amd lock examples/adam-paper.amd.md --holder "agent:mavis:abc123" --ttl 30m
./.venv/bin/amd unlock examples/adam-paper.amd.md
```

While locked, other actors cannot edit (unless the lock expires or they explicitly steal).

## The format

### Frontmatter

```yaml
---
$schema: amd/v1              # required
$id: adam-paper              # required, unique
$type: source-page           # optional, references a schema
$fields:                     # optional, typed metadata
  arxiv_id: "1412.6980"
  year: 2014
  authors: ["Kingma, D.P.", "Ba, J."]
  tags: [optimizer, adaptive-gradient]
$updated: 2026-06-28T23:00:00Z
$updated_by: "agent:mavis:abc123"
$locks:                      # optional, single-writer lock
  holder: "agent:mavis:abc123"
  acquired: "2026-06-28T23:05:00Z"
  ttl: 30m
---
```

### Anchored headings

```markdown
## §1 Summary {#s1 .abstract required}
## §2 Method {#s2 .method required}
### §2.1 Algorithm {#s2.1 .algorithm}
```

- `§N.M` is an auto-numbered anchor (use it in `--at`)
- `{#custom-id}` is a stable custom ID (immutable across edits)
- `{.class}` adds a class for filtering (`§2 .method` = "the method section")
- `required` is a boolean flag

### Structured blocks

```markdown
@figure {
  src: "figures/adam-fig1.png"
  alt: "Loss curves on MNIST"
  caption: "Figure 1: Convergence comparison"
  width: 0.8
}

@code {
  lang: "python"
  runnable: false
  body: |
    import torch
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
}

@cite {
  key: "kingma2014adam"
  locator: "eq.3"
  context: "update rule"
}

@backlink {
  from: "[[Adam]]"
  kind: defines
  confidence: 1.0
}
```

Built-in block types: `@figure`, `@table`, `@code`, `@cite`, `@backlink`, `@meta`. Schemas can define more.

### Wikilinks

```markdown
See [[AdamW]] for the decoupled weight decay variant.
```

**Backlinks are computed at render time, not stored as forward links.** The agent never maintains reverse link lists.

### Agent attribution

```markdown
<!-- @actor: agent:mavis:abc123, @confidence: 0.85, @reviewed: false -->
This paragraph was written by agent mavis based on §3.2 of the paper.
```

Hidden in rendered output, visible in source. Tracks who wrote what.

## CLI reference

```bash
amd read <file> [--at ANCHOR] [--format text|json]
amd edit <file> --at ANCHOR --action ACTION [--content TEXT] [--yes] [--preview]
amd validate <file> [--schema NAME] [--strict]
amd query <path> "SELECT ..."
amd lock <file> --holder ACTOR [--ttl 30m]
amd unlock <file>
amd locks <path>            # list all locks
amd log <file>              # patch history
amd undo <file>             # undo last patch
amd checkpoint <file> --name NAME
amd convert <path> [--batch] [--output DIR] [--infer-anchors] [--add-frontmatter]
amd render <file> --to plain-markdown|ast
```

### Anchor syntax for `--at`

| Anchor | Meaning |
|---|---|
| `§N` | Section number (e.g., `§2.1`) |
| `{#custom-id}` | Custom ID |
| `@frontmatter` | Whole frontmatter |
| `@frontmatter/$fields/year` | Specific field |
| `@backlinks` | All backlink blocks |
| `line:N` | Line N (fallback) |

### Edit actions

| Action | Description |
|---|---|
| `replace` | Replace content at anchor |
| `prepend` / `append` | Add to start/end of anchor |
| `insert-after` / `insert-before` | Insert at position |
| `delete` | Remove content at anchor |
| `set` / `unset` | Set/remove a metadata field |
| `create-block` | Add a `@figure`, `@code`, etc. |
| `delete-block` | Remove a named block |

## Architecture

```
amd/
├── parser.py        # AMD document parser (frontmatter, headings, blocks)
├── operations.py    # Patch operations (replace, append, set, etc.)
├── patch.py         # Patch log + undo
├── lock.py          # Single-writer locking
├── schema.py        # Schema validation
├── query.py         # SQL-like query language
├── convert.py       # Plain markdown → AMD
├── cli.py           # Click-based CLI
└── __init__.py
examples/
├── adam-paper.amd.md       # source-page example
├── adam-concept.amd.md     # concept-page example
└── plain-readme.md         # plain markdown (lossy mode)
schemas/
├── source-page.yaml
└── concept-page.yaml
tests/
└── smoke_test.py    # End-to-end smoke test
```

## Why not...?

**Q: Why not just use JSON?**
A: Loses human readability, breaks git diff, alienates non-engineers.

**Q: Why not HTML?**
A: HTML is great for *output* (rendering). Markdown is great for *source* (editing). AMD keeps markdown as source.

**Q: Why not Obsidian's format?**
A: Obsidian has wikilinks and backlinks, but no schema validation, no patches, no locks, no agent attribution. AMD is Obsidian for agents.

**Q: Why not MDX?**
A: MDX is markdown + JSX for React. Different audience. AMD is markdown + structural metadata for AI agents.

**Q: Why not SQLite?**
A: Loses git diff, alienates non-engineers. AMD keeps the markdown file as source of truth.

## 当前局限 / Limitations (v0.1)

These are honest, known weaknesses — not bugs, but design tradeoffs worth being upfront about:

1. **`§N` anchors are fragile.** Inserting a new section between §2 and §3 renumbers all subsequent anchors. `{#custom-id}` mitigates this but shifts the burden to manual maintenance. A content-hash-based stable ID system is not yet implemented.

2. **`@block` syntax is not standard Markdown.** `@figure { key: value }` renders as plain text in GitHub, Obsidian, and every standard renderer. You must run `amd render --to plain-markdown` to produce display-ready output. `.amd.md` is effectively "source code" that needs "compilation."

3. **Schema validation is formal, not semantic.** We can check that `year` is an integer, but not that `year` is between 1900 and 2026. We can't verify that `pdf_path` points to an actual file on disk. Semantic validation rules are not yet implemented.

4. **Query language sits in an awkward middle ground.** Simple queries (`WHERE tags CONTAINS 'foo'`) are faster with `grep -rl`. Complex cross-file relational queries (e.g., "find all pages that reference Figure 3 of paper X") are not yet supported.

5. **Custom parser, not AST-based.** The parser is ~500 lines of hand-written logic rather than a thin layer on a mature AST library. Corner cases — nested blocks, inline anchors, anchor-block coexistence — are under-tested.

6. **Single-writer locks are both too much and not enough.** For a single agent working alone, locks are unnecessary overhead. For multiple agents collaborating in real-time, a single-writer lock is too restrictive. The sweet spot is narrow.

7. **No existing ecosystem.** AMD is not an Obsidian plugin, not a VS Code extension, not a community standard. It is a new format proposal with a reference implementation. Adoption requires buy-in from tooling, platforms, and users.

## Status

**v0.1** — working draft, suitable for evaluation.

| Feature | Status |
|---|---|
| Parse AMD frontmatter / anchors / blocks | ✅ done |
| Edit by anchor (replace/append/prepend/insert/delete) | ✅ done |
| Edit metadata (`@frontmatter/$fields/X`) | ✅ done |
| Edit blocks (`@figure`, etc.) | ✅ done |
| Patch log + undo | ✅ done |
| Single-writer locks | ✅ done |
| Schema validation (required fields, types, sections) | ✅ done (basic) |
| Query language | ✅ done (basic) |
| Convert plain md → AMD | ✅ done |
| Render to plain markdown / AST | ✅ done |
| Multi-agent concurrent edits | ❌ future work |
| Live preview UI | ❌ future work |
| Web render with backlinks | ❌ future work |
| LLM-driven anchor inference | ❌ future work |

## Try it

```bash
# Run the full smoke test
./.venv/bin/python tests/smoke_test.py

# See all CLI commands
./.venv/bin/amd --help

# Read the full spec
cat AMD.md
```

## License

MIT