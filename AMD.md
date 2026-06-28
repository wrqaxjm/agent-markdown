# AMD — Agent Markdown Document

> Spec version: **v1** (draft, 2026-06-28)
> Author: Mavis
> Status: working draft, feedback welcome

## TL;DR

AMD is **markdown, plus structural conventions that make AI agents efficient writers and editors**:

- Every section has a **stable anchor** (`§1`, `§2.1`, `{#custom-id}`) — never search by text
- Frontmatter is **typed metadata** (`$schema`, `$type`, `$locks`) — never parse loose YAML
- Special blocks are **first-class** (`@figure {...}`, `@cite {...}`) — never hand-craft strings
- Every edit is a **reversible patch** with built-in undo — never lose work
- File-level **locks prevent race conditions** — single-writer is enough for most cases
- Pure markdown files still work — **lossy mode**, no anchor / no schema / no lock, but the CLI still helps

## 1. Design Philosophy

Five principles, in order of priority:

1. **Markdown soul preserved** — files still look like markdown in vim. No binary blobs. `git diff` still works.
2. **AI-editable, AI-queryable, AI-diffable** — agents should never need string-matching tricks.
3. **Reversible by default** — every mutation has a built-in inverse. Undo is not a feature, it's the model.
4. **Plain markdown is a valid subset** — zero migration cost. Add AMD metadata incrementally.
5. **Single-writer, multi-reader** — locks are simpler than CRDT and cover 90% of cases.

## 2. File Format

### 2.1 Frontmatter

A YAML frontmatter block, with `$`-prefixed reserved fields:

```yaml
---
$schema: amd/v1                  # required, always this value for v1 files
$id: adam-paper                  # required, unique id within the wiki
$type: source-page               # optional, references a schema name
$fields:                         # optional, typed metadata
  arxiv_id: "1412.6980"
  year: 2014
  authors: ["Kingma, D.P.", "Ba, J."]
  tags: [optimizer, adaptive]
$updated: 2026-06-28T23:00:00Z   # optional, ISO timestamp
$updated_by: "agent:mavis:414131408429400"  # optional, actor id
$locks:                          # optional, single-writer lock
  holder: "agent:mavis:414131408429400"
  acquired: "2026-06-28T23:05:00Z"
  ttl: 30m
---
```

**Rules**:
- `$schema`, `$id` are required for AMD files. `$schema` MUST be `amd/v1`.
- `$type` declares which schema to validate against. If absent, only structural validation runs.
- `$fields` is a free-form typed metadata bag. Each schema defines what's allowed.
- `$locks` is the single-writer lock. See [§6](#6-locking).

### 2.2 Anchors

Every section (`## ...`) **should** have an explicit anchor:

```markdown
## §1 Summary {#s1 .abstract required}

Kingma & Ba (2014) propose Adam, an adaptive gradient method...
```

Anchor syntax: `{#id}` and/or `{.class-name}` and/or `{required}` (boolean flag). Multiple classes allowed.

**Built-in section IDs**: any section starting with `§N` (where N is a number or dotted number) automatically gets a numeric anchor. So `## §2.1 Algorithm` is reachable as `--at "§2.1"`.

### 2.3 Block-level annotations

Inline annotations using `{...}` syntax after a heading or paragraph:

```markdown
## §3 Figures {#s3 .figures}

@fig-1 {
  src: "figures/adam-fig1.png"
  alt: "Loss curves on MNIST autoencoder"
  caption: "Figure 1: Convergence comparison"
  width: 0.8
}

@code-1 {
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
  confidence: 0.95
}
```

Standard block types:
- `@figure {src, alt, caption, width}` — image with metadata
- `@table {schema, rows}` — structured table
- `@code {lang, runnable, body}` — code block
- `@cite {key, locator, context}` — citation
- `@backlink {from, kind, confidence}` — semantic link (rendered, not stored as forward)
- `@meta {intent, required, ...}` — agent-attached metadata

Custom block types allowed: schemas can declare and validate additional `@type { ... }` blocks.

### 2.4 Agent attribution

HTML-style comments for agent metadata (per-paragraph or per-section):

```markdown
<!-- @actor: agent:mavis:414131408429400, @confidence: 0.85, @reviewed: false -->
This paragraph was written by agent mavis based on §3.2 of the paper.
```

**Why HTML comments**: they don't break markdown rendering in any standard tool. They survive copy-paste. They're hidden by default but visible on inspection.

### 2.5 Wikilinks

Use Obsidian-style `[[Page]]` syntax for forward references:

```markdown
See also [[AdamW]] for the decoupled weight decay variant.
```

**Backlinks are computed at render time, not stored.** This is the killer feature. The agent never maintains "reverse link" lists — that's the rendering layer's job.

### 2.6 Lossy mode: plain markdown

If a file has no `---` frontmatter, AMD CLI treats it as a plain markdown file:
- No `$schema` → only structural parsing (sections, code, lists)
- No `{#id}` → fallback to line numbers (`--at "line:42"`)
- No `@block { ... }` → blocks are recognized as plain markdown
- No schema validation
- No lock check (advisory only)

**Result**: every existing markdown file is processable. The CLI just gets less smart.

## 3. Anchor Addressing

Anchor syntax for `--at`:

```
§2                       → entire section 2
§2.1                     → section 2.1
§2[2]                    → second block in section 2
§2[fig-1]                → block named fig-1 in section 2
§2.content               → only the content body (not the heading)
§2.heading               → only the heading
@frontmatter             → whole frontmatter
@frontmatter/$fields/year → the year field
@backlinks               → all @backlink blocks
```

Line-number fallback (when no anchor):
```
line:42                   → line 42 (1-indexed)
line:42-50                → lines 42 through 50
```

## 4. Patch Format

Patches are JSON objects, RFC 6902 inspired:

```json
{
  "op": "amd.replace",
  "version": "1",
  "actor": "agent:mavis:414131408429400",
  "intent": "fix typo in algorithm description",
  "checkpoint": "cp-2026-06-28T23:08",
  "timestamp": "2026-06-28T23:08:15Z",
  "target": {
    "file": "sources/adam.amd.md",
    "anchor": "§2.1",
    "scope": "content[1]"
  },
  "value": "new content here",
  "before": "old content here (captured at apply time)",
  "inverse": {
    "op": "amd.replace",
    "target": {"file": "sources/adam.amd.md", "anchor": "§2.1", "scope": "content[1]"},
    "value": "old content here",
    "reason": "undo of cp-2026-06-28T23:08"
  }
}
```

Supported operations:

| op | description |
|---|---|
| `amd.replace` | replace content at anchor |
| `amd.prepend` | prepend content to anchor target |
| `amd.append` | append content to anchor target |
| `amd.insert-after` | insert after anchor |
| `amd.insert-before` | insert before anchor |
| `amd.delete` | delete content at anchor |
| `amd.set` | set a metadata field (`@frontmatter/$fields/X`) |
| `amd.unset` | remove a metadata field |
| `amd.create-block` | add a structured block (`@figure {...}`) |
| `amd.delete-block` | remove a named block |
| `amd.move` | move content from one anchor to another |

**Every patch has an `inverse` field.** The CLI computes inverses automatically at apply time.

**Patches are stored as JSONL** at `.amd/patches.jsonl` alongside each file (one log per file). Checkpoints are stored as `.amd/checkpoints/<name>.json`.

## 5. Schema Validation

Schemas are YAML files. Example `schemas/source-page.yaml`:

```yaml
$id: source-page
$version: 1
$description: "A research paper source page in a wiki."

require_frontmatter: true
require_schema_field: true

required_fields:
  - arxiv_id
  - year
  - authors

field_types:
  arxiv_id: string
  year: integer
  authors: array<string>
  tags: array<string>

required_sections:
  - §1
  - §4

section_rules:
  §1:
    max_blocks: 5
    require_class: abstract
  §3:
    min_blocks: 1
  §4:
    require_actor_meta: true

backlink_rules:
  min_count: 1

require_blocks:
  - type: figure
    min_count: 1
```

`amd validate <file> --schema <name>` reads the schema and runs all checks. Failures are returned as a list, with line/column when possible.

## 6. Locking

Single-writer lock. Stored in frontmatter `$locks` field, plus `.amd/locks.json` for fast lookup.

```yaml
$locks:
  holder: "agent:mavis:414131408429400"
  acquired: "2026-06-28T23:05:00Z"
  ttl: 30m
```

**Lock semantics**:
- `amd edit` checks lock before applying. If held by another actor → refuses (with optional `--steal` flag).
- `amd edit` refreshes `acquired` timestamp on every successful apply (sliding lock).
- If `now > acquired + ttl`, lock is considered expired and can be taken by anyone.
- `amd lock` acquires, `amd unlock` releases. Both are reversible patches too.

**Why single-writer not CRDT**: agents collaborating on the same doc is rare. When it happens, a 30-second human/agent coordination is fine. CRDT complexity is not worth it.

## 7. CLI

```bash
# Read
amd read <file>                      # show AST
amd read <file> --at "§2"            # show only §2
amd read <file> --at "§2.1[2]"       # show specific block

# Edit (always preview by default)
amd edit <file> --at "§2" --action replace --content "..."
amd edit <file> --at "§3" --action append --content "..."
amd edit <file> --at "§2.1" --action delete
amd edit <file> --at "§3[fig-1]" --action replace --content '{"src": "x.png"}'
amd edit <file> --at "@frontmatter/$fields/year" --action set --value 2014
amd edit <file> --at "§1" --action prepend --content "..."
amd edit <file> --at "§2" --action insert-after --content "..."

# Flags
amd edit ... --preview               # show diff, don't write (default: ON)
amd edit ... --yes                   # skip preview, apply immediately
amd edit ... --intent "fix typo"     # attach intent to patch
amd edit ... --actor "agent:mavis"   # explicit actor id

# Validate
amd validate <file> --schema source-page
amd validate <file> --strict
amd validate <dir>/ --recursive

# Query
amd query <file> "sections where class=required"
amd query <dir>/ "files where $fields.tags contains 'optimizer'"
amd query <dir>/ "backlinks to [[Adam]]"
amd query <dir>/ "files updated after 2026-06-01"

# Lock
amd lock <file> --holder "agent:mavis" --ttl 30m
amd unlock <file>
amd locks                           # list all current locks

# History & undo
amd log <file>                      # show patch log
amd undo <file>                     # undo last patch
amd undo <file> --to <checkpoint>    # undo to a named checkpoint
amd checkpoint <file> --name <name>  # create a named checkpoint

# Convert (plain md → AMD)
amd convert <file>.md --to amd --infer-anchors
amd convert <dir>/ --to amd --batch --output <dir>-amd/

# Render
amd render <file> --to plain-markdown    # strip AMD extensions, output pure md
amd render <file> --to ast.json          # export full AST
amd render <dir>/ --to site --with-backlinks  # render wiki to static site

# Schema management
amd schema list
amd schema show <name>
amd schema validate <file> --schema <name>
```

## 8. Query Language

A tiny SQL-like DSL, scoped to AMD structures:

```
SELECT <what>
FROM <source>
[WHERE <condition>]
```

Examples:

```sql
-- Find all required sections in a file
SELECT section
FROM §1, §2, §3, §4
WHERE class = "required"

-- Find all wiki pages about optimizers
SELECT file
FROM wiki/
WHERE $fields.tags CONTAINS "optimizer"

-- Find all pages that link to Adam
SELECT file
FROM wiki/
WHERE content CONTAINS "[[Adam]]"

-- Find files updated recently
SELECT file, $updated
FROM wiki/
WHERE $updated > "2026-06-01"
```

**Why DSL not just grep**: grep can't see structure. `grep "[[Adam]]"` matches everywhere. The query language knows about `$fields`, sections, classes, blocks.

## 9. Implementation Notes

### 9.1 Parser strategy

We use `markdown-it-py` to get the base MDAST. Then we:

1. Walk the tree and extract `$`-prefixed frontmatter fields into typed metadata
2. Parse heading attributes `{#id .class required}` into anchor metadata
3. Recognize `@block-type { ... }` patterns as custom blocks (using a tolerant YAML/JSON parser inside braces)
4. Index sections by their auto-generated `§N` anchors and custom `{#id}` anchors

### 9.2 Why not use pandoc

Pandoc's AST is rich but tightly coupled to its document model. `markdown-it-py` gives us a simpler MDAST that's easy to extend. We don't need pandoc's full power.

### 9.3 Patch log format

`.amd/patches.jsonl`: one JSON object per line. Append-only. Each entry has `applied: true|false` (false = undone).

```
{"op": "amd.replace", "actor": "...", "applied": true, ...}
{"op": "amd.replace", "actor": "...", "applied": false, ...}  ← undone
```

### 9.4 Checkpoint format

`.amd/checkpoints/<name>.json`: snapshot of file content + patch log position. Cheap to create, easy to roll back to.

## 10. What We Don't Do (v1)

Honest scope limits:

- ❌ **Multi-agent concurrent edits** — single-writer locks only. CRDT is future work.
- ❌ **Live preview UI** — CLI only. Web UI is future work.
- ❌ **Binary file support** — text only.
- ❌ **Real-time sync** — no operational transform. Agents take turns.
- ❌ **Render to HTML/PDF** — `amd render --to plain-markdown` is the only render target in v1. Use pandoc/quarto downstream.
- ❌ **Inline code execution** — `@code { runnable: true }` is a marker only. Notebooks are a separate tool.

## 11. Roadmap

### v0.1 (this draft) — parser, CLI, basic ops
- Parse AMD frontmatter + anchors + custom blocks
- `read`, `edit`, `validate`, `query`, `convert`
- Patch log + undo
- Single-writer lock

### v0.2 — schemas & validation
- Full schema language
- `amd validate --strict` with custom rules
- Cross-file reference checking

### v0.3 — backlinks & queries
- Render-time backlink computation
- Wiki-wide queries
- `amd render --with-backlinks`

### v0.4 — collaboration
- Multi-agent lock with intent tracking
- Conflict detection on stale locks
- Optional CRDT mode (off by default)

## 12. Why Not Just Use...?

**Q: Why not JSON?**
A: Loses human readability, breaks git diff, alienates non-engineers.

**Q: Why not HTML?**
A: HTML in source files is verbose, breaks git diff, harder to write by hand. HTML is great for *output*, markdown is great for *source*.

**Q: Why not Obsidian's format?**
A: Obsidian has wikilinks and backlinks, but no schema validation, no patches, no locks, no agent attribution. AMD is Obsidian for agents.

**Q: Why not MDX?**
A: MDX is markdown + JSX for React components. Different audience. AMD is markdown + structural metadata for AI agents.

**Q: Why not SQLite?**
A: Loses human readability, breaks git diff. AMD keeps the markdown file as source of truth.

## 13. Open Questions

1. Should `$fields` be required to match the schema's `field_types`, or should it be free-form?
2. Should we support multi-file atomic patches (transaction across multiple files)?
3. What's the right granularity for `inverse` — per-patch or per-checkpoint?
4. Should agent attribution be visible by default in rendered output, or hidden?
5. Should `amd convert --infer-anchors` use heuristics (heading text → id) or LLM?

Feedback welcome. The spec is intentionally a starting point.