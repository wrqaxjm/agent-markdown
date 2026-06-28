# mdtool

> minimal structural markdown editor for AI agents. one file, zero format changes.

## What it solves

The 8 pain points from `markdown-agent-edit-design.md`, in 400 lines:

| Pain | Solution |
|---|---|
| 1. GBK encoding | Always UTF-8, atomic write (tmp + rename) |
| 2. Full-file rewrite | Section/line-level edits, no full-file copy |
| 3. Fragile string matching | `--section "Summary"` matches heading text |
| 4. Frontmatter typos | `--fm-key year --action set --value 2025` |
| 5. Image tags | Use `--line N --action insert-after` |
| 6. Wikilink validation | `python mdtool.py links .` lists all `[[...]]` |
| 7. Cross-file refs | `python mdtool.py links . --page AdamW` finds refs |
| 8. Mechanical work | Section-level ops + line ops automate ~30% |

## Install

No install needed. Single file, stdlib only (no PyYAML required).

```bash
python mdtool.py <command>
```

## Commands

### edit — structural editing

```bash
# By section heading (substring match, case-insensitive)
python mdtool.py edit wiki/questions.md --section "Pending" --action insert-after --content "new item"

# By line number
python mdtool.py edit index.md --line 42 --action replace --content "corrected text"

# By frontmatter key
python mdtool.py edit wiki/sources/1412.6980.md --fm-key year --action set --value 2015

# Dry-run (show diff, don't write)
python mdtool.py edit file.md --section Summary --action replace --content "..." --dry-run

# Skip confirmation
python mdtool.py edit file.md --section Notes --action delete --yes

# Read content from file
python mdtool.py edit file.md --section Method --action append --file content.md
```

**Actions**: `replace`, `insert-after`, `insert-before`, `append`, `prepend`, `delete`, `set` (fm), `unset` (fm)

### links — wikilink scanner

```bash
# List all links in a file or directory
python mdtool.py links wiki/

# Find who references a specific page
python mdtool.py links wiki/ --page AdamW
```

### undo — reverse last edit

```bash
python mdtool.py undo wiki/questions.md
```

Every edit logs a JSONL patch with inverse. Undo replays the inverse.

### lock / unlock — single-writer lock

```bash
python mdtool.py lock wiki/log.md --holder agent-1 --ttl 30
python mdtool.py unlock wiki/log.md
```

Locks have TTL (minutes). Expired locks are ignored. Use `--steal` to override.

## Design

- **No markdown format changes** — works on any `.md` file
- **Section headings are anchors** — `## Section Name` is your locator
- **Line-based frontmatter edits** — change one field, rest stays exactly as-is
- **Atomic writes** — write to `.tmp` then `os.replace()` (no partial writes)
- **Append-only patch log** — `.mdtool/<file>.patches.jsonl`
- **~400 lines** — single file, read it in 5 minutes
