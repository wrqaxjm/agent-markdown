#!/usr/bin/env python3
"""
mdtool — structural markdown editor for AI agents.

Works on plain .md files. No format changes required.

Usage:
  python mdtool.py edit <file> [--section NAME] [--line N] [--fm-key KEY]
                               --action {replace,insert-after,insert-before,append,prepend,delete,set,unset}
                               [--content TEXT] [--value VAL] [--file CONTENT_FILE]
                               [--dry-run] [--yes]
  python mdtool.py links <dir> [--page PAGE]
  python mdtool.py undo <file>
  python mdtool.py lock <file> --holder ACTOR [--ttl MINUTES]
  python mdtool.py unlock <file>
"""

import sys, os, re, json, shutil, difflib, argparse, glob as glob_mod
from datetime import datetime, timezone, timedelta
from pathlib import Path

# force UTF-8 on Windows (fixes GBK printing of emoji / Chinese)
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

LOG_DIR = ".mdtool"
LOCK_DIR = ".mdlock"

# ═══════════════════════════════════════════
#  YAML (minimal, no PyYAML required)
# ═══════════════════════════════════════════

def _parse_scalar(s):
    s = s.strip()
    if s == 'null' or s == '~':
        return None
    if s == 'true':
        return True
    if s == 'false':
        return False
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s

def _parse_yaml_list(s):
    items = []
    depth = 0
    buf = ''
    for ch in s:
        if ch == '[':
            depth += 1
        elif ch == ']':
            depth -= 1
            if depth == 0:
                if buf.strip():
                    items.append(_parse_scalar(buf))
                break
        elif ch == ',' and depth == 1:
            items.append(_parse_scalar(buf))
            buf = ''
        else:
            buf += ch
    return items

def parse_frontmatter_yaml(text):
    """Parse simple YAML frontmatter. Handles flat k:v, nested dicts not needed."""
    result = {}
    for line in text.split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        m = re.match(r'^(\w[\w_-]*)\s*:\s*(.*)$', line)
        if m:
            key = m.group(1)
            val = m.group(2).strip()
            if val.startswith('[') and val.endswith(']'):
                val = _parse_yaml_list(val[1:-1])
            else:
                val = _parse_scalar(val)
            result[key] = val
    return result

def fmt_yaml_val(v):
    if isinstance(v, list):
        return '[' + ', '.join(fmt_yaml_val(x) for x in v) + ']'
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, (int, float)):
        return str(v)
    if v is None:
        return 'null'
    s = str(v)
    if not s:
        return '""'
    try:
        int(s)
        return f'"{s}"'
    except ValueError:
        pass
    try:
        float(s)
        return f'"{s}"'
    except ValueError:
        pass
    if re.search(r'[:\{\}\[\],#&*?|\-<>=!%@`]', s) or s.startswith("'") or s.startswith('"'):
        return f'"{s}"'
    return s

# ═══════════════════════════════════════════
#  Lock file
# ═══════════════════════════════════════════

def _lock_path(filepath):
    return Path(filepath).resolve().parent / LOCK_DIR / (Path(filepath).name + '.lock')

def acquire_lock(filepath, holder, ttl_minutes):
    lp = _lock_path(filepath)
    lp.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    if lp.exists():
        data = json.loads(lp.read_text(encoding='utf-8'))
        acquired = datetime.fromisoformat(data['acquired'])
        if (now - acquired).total_seconds() < data['ttl'] * 60:
            return False, data['holder']
    lp.write_text(json.dumps({
        'holder': holder,
        'acquired': now.isoformat(),
        'ttl': ttl_minutes
    }), encoding='utf-8')
    return True, None

def release_lock(filepath):
    lp = _lock_path(filepath)
    if lp.exists():
        lp.unlink()

def check_lock(filepath):
    lp = _lock_path(filepath)
    if not lp.exists():
        return None
    data = json.loads(lp.read_text(encoding='utf-8'))
    acquired = datetime.fromisoformat(data['acquired'])
    if (datetime.now(timezone.utc) - acquired).total_seconds() < data['ttl'] * 60:
        return data['holder']
    return None

# ═══════════════════════════════════════════
#  Markdown parser
# ═══════════════════════════════════════════

class MDParser:
    def __init__(self, text):
        self.lines = text.split('\n')
        self.fm = {}
        self.fm_start = None
        self.fm_end = None
        self.headings = []  # [(line_idx, level, text)]
        self._parse()

    def _parse(self):
        lines = self.lines
        # frontmatter
        if lines and lines[0].strip() == '---':
            end = None
            for i in range(1, len(lines)):
                if lines[i].strip() == '---':
                    end = i
                    break
            if end is not None:
                self.fm_start = 0
                self.fm_end = end
                self.fm = parse_frontmatter_yaml('\n'.join(lines[1:end]))
        # headings
        for i, line in enumerate(lines):
            m = re.match(r'^(#{1,6})\s+(.+)$', line)
            if m:
                self.headings.append((i, len(m.group(1)), m.group(2).strip()))

    def find_section(self, name):
        """Find (start_line, end_line) of first section whose heading contains `name`."""
        name_lower = name.lower()
        for idx, level, text in self.headings:
            if name_lower in text.lower():
                end = len(self.lines)
                for i2, l2, _ in self.headings:
                    if i2 > idx and l2 <= level:
                        end = i2
                        break
                return idx, end, level, text
        return None, None, None, None

    def has_frontmatter(self):
        return self.fm_start is not None

# ═══════════════════════════════════════════
#  Edit operations
# ═══════════════════════════════════════════

def edit_section(doc, name, action, content):
    start, end, level, heading_text = doc.find_section(name)
    if start is None:
        raise ValueError(f"section not found: '{name}'")

    heading_line = doc.lines[start]       # preserve heading
    content_only = '\n'.join(doc.lines[start + 1:end]) if start + 1 < end else ''
    full_section = '\n'.join(doc.lines[start:end])
    lines = doc.lines[:]
    before = full_section                 # store full section for undo

    if action == 'replace':
        # keep heading, replace content below it
        lines[start + 1:end] = content.split('\n')
    elif action == 'append':
        if end < len(lines) and lines[end - 1].strip() != '':
            lines.insert(end, '')
            end += 1
        lines.insert(end, content)
    elif action == 'prepend':
        insert_at = start + 1
        if insert_at < end and lines[insert_at].strip() != '':
            lines.insert(insert_at, '')
            end += 1
        lines.insert(insert_at, content)
    elif action == 'insert-after':
        if end < len(lines) and lines[end - 1].strip() != '':
            lines.insert(end, '')
            end += 1
        lines.insert(end, content)
    elif action == 'insert-before':
        lines.insert(start, content)
    elif action == 'delete':
        lines[start:end] = []
    else:
        raise ValueError(f"unknown action: {action}")

    new_text = '\n'.join(lines)
    inverse = {'type': 'section', 'name': name, 'start_line': start, 'level': level, 'full_before': before}
    return new_text, inverse

def edit_line(doc, line_num, action, content):
    idx = line_num - 1
    if idx < 0 or idx >= len(doc.lines):
        raise ValueError(f"line {line_num} out of range (1-{len(doc.lines)})")

    lines = doc.lines[:]
    old_line = lines[idx]

    if action == 'replace':
        before = old_line
        lines[idx] = content
        after = content
    elif action == 'insert-before':
        before = ''
        indent = re.match(r'^(\s*)', lines[idx]).group(1)
        lines.insert(idx, indent + content)
        after = content + '\n' + old_line
    elif action == 'insert-after':
        before = ''
        indent = re.match(r'^(\s*)', lines[idx]).group(1)
        lines.insert(idx + 1, indent + content)
        after = old_line + '\n' + content
    elif action == 'delete':
        before = old_line
        del lines[idx]
        after = ''
    elif action == 'append':
        before = ''
        lines.append(content)
        after = content
    elif action == 'prepend':
        before = ''
        lines.insert(0, content)
        after = content
    else:
        raise ValueError(f"unknown action: {action}")

    new_text = '\n'.join(lines)
    inverse = {'type': 'line', 'line': line_num, 'action': 'replace', 'content': before}
    return new_text, inverse

def edit_frontmatter(doc, key, action, value):
    lines = doc.lines[:]

    # find existing key line in frontmatter block
    key_line_idx = None
    if doc.has_frontmatter():
        for i in range(doc.fm_start + 1, doc.fm_end):
            stripped = lines[i].strip()
            if stripped == key + ':' or stripped.startswith(key + ':') or stripped.startswith(key + ' '):
                key_line_idx = i
                break

    if action == 'set':
        before_line = lines[key_line_idx] if key_line_idx is not None else ''
        new_line = f'{key}: {fmt_yaml_val(value)}'
        if key_line_idx is not None:
            indent = re.match(r'^(\s*)', lines[key_line_idx]).group(1)
            lines[key_line_idx] = indent + new_line
        elif doc.has_frontmatter():
            lines.insert(doc.fm_end, new_line)
        else:
            lines[0:0] = ['---', new_line, '---', '']
    elif action == 'unset':
        before_line = lines[key_line_idx] if key_line_idx is not None else ''
        if key_line_idx is not None:
            del lines[key_line_idx]
    else:
        raise ValueError(f"unknown frontmatter action: {action}")

    new_text = '\n'.join(lines)
    inverse = {'type': 'frontmatter', 'key': key, 'restore_line': before_line}
    return new_text, inverse

# ═══════════════════════════════════════════
#  Patch log + undo
# ═══════════════════════════════════════════

def _log_dir(filepath):
    return Path(filepath).resolve().parent / LOG_DIR

def _log_file(filepath):
    return _log_dir(filepath) / (Path(filepath).name + '.patches.jsonl')

def log_patch(filepath, patch, inverse, actor=None):
    lf = _log_file(filepath)
    lf.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'actor': actor or 'unknown',
        'patch': patch,
        'inverse': inverse,
    }
    with open(lf, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')

def undo_last(filepath):
    lf = _log_file(filepath)
    if not lf.exists():
        raise FileNotFoundError(f"no patch log for: {filepath}")

    lines = lf.read_text(encoding='utf-8').strip().split('\n')
    if not lines:
        raise ValueError("patch log is empty")

    last = json.loads(lines[-1])
    inverse = last['inverse']

    content = read_file(filepath)
    doc = MDParser(content)
    lines_new = doc.lines[:]

    if inverse['type'] == 'section':
        start, end, level, heading_text = doc.find_section(inverse['name'])
        full_lines = inverse['full_before'].split('\n')
        if start is not None:
            lines_new[start:end] = full_lines
        else:
            # section was deleted; re-insert near original position
            insert_at = min(inverse['start_line'], len(lines_new))
            lines_new[insert_at:insert_at] = full_lines + [''] if insert_at > 0 and lines_new[insert_at-1].strip() else full_lines
        new_text = '\n'.join(lines_new)
    elif inverse['type'] == 'line':
        new_text, _ = edit_line(doc, inverse['line'], inverse['action'], inverse['content'])
    elif inverse['type'] == 'frontmatter':
        key = inverse['key']
        restore = inverse['restore_line']
        # find current key line
        cur_idx = None
        if doc.has_frontmatter():
            for i in range(doc.fm_start + 1, doc.fm_end):
                s = lines_new[i].strip()
                if s == key + ':' or s.startswith(key + ':') or s.startswith(key + ' '):
                    cur_idx = i
                    break
        if restore:
            if cur_idx is not None:
                indent = re.match(r'^(\s*)', lines_new[cur_idx]).group(1)
                lines_new[cur_idx] = indent + restore.lstrip()
            elif doc.has_frontmatter():
                lines_new.insert(doc.fm_end, restore.lstrip())
            else:
                lines_new[0:0] = ['---', restore.lstrip(), '---', '']
        else:
            if cur_idx is not None:
                del lines_new[cur_idx]
        new_text = '\n'.join(lines_new)
    else:
        raise ValueError(f"unknown inverse type: {inverse['type']}")

    write_file(filepath, new_text)
    remaining = lines[:-1]
    lf.write_text('\n'.join(remaining) + ('\n' if remaining else ''), encoding='utf-8')
    return last

# ═══════════════════════════════════════════
#  Wikilinks
# ═══════════════════════════════════════════

WIKILINK_RE = re.compile(r'\[\[([^\]|#]+?)(?:[|#][^\]]+)?\]\]')

def list_wikilinks(path, target_page=None):
    """List all wikilinks in .md files. path can be file or directory."""
    if os.path.isfile(path):
        md_files = [path]
    else:
        md_files = glob_mod.glob(f'{path}/**/*.md', recursive=True)
    results = []
    for md_file in md_files:
        try:
            text = Path(md_file).read_text(encoding='utf-8')
        except Exception:
            continue
        links = WIKILINK_RE.findall(text)
        if links:
            if target_page:
                if target_page in links:
                    results.append((md_file, [l for l in links if l == target_page]))
            else:
                results.append((md_file, links))
    return results

# ═══════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════

def read_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()

def write_file(filepath, content):
    tmp = filepath + '.mdtool.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(content)
    os.replace(tmp, filepath)

def show_diff(old, new, filepath='file'):
    old_lines = old.split('\n')
    new_lines = new.split('\n')
    diff = difflib.unified_diff(old_lines, new_lines, fromfile=filepath, tofile=filepath)
    return '\n'.join(diff)

# ═══════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════

def _content_from_args(args, content, content_file, value):
    if content_file:
        return Path(content_file).read_text(encoding='utf-8')
    if value is not None:
        return value
    if content:
        return content
    return ''

def cmd_edit(args):
    filepath = args.file
    content = _content_from_args(args, args.content, args.content_file, args.value)

    if not os.path.exists(filepath):
        print(f"ERROR: file not found: {filepath}")
        sys.exit(1)

    # Check lock
    holder = check_lock(filepath)
    if holder:
        print(f"ERROR: file locked by '{holder}'. Use --steal to override.")
        if not getattr(args, 'steal', False):
            sys.exit(1)

    old_text = read_file(filepath)
    doc = MDParser(old_text)
    now = datetime.now(timezone.utc).isoformat()

    if args.section:
        new_text, inverse = edit_section(doc, args.section, args.action, content)
        patch = {'type': 'section', 'name': args.section, 'action': args.action, 'content': content}
    elif args.line:
        new_text, inverse = edit_line(doc, args.line, args.action, content)
        patch = {'type': 'line', 'line': args.line, 'action': args.action, 'content': content}
    elif args.fm_key:
        new_text, inverse = edit_frontmatter(doc, args.fm_key, args.action, args.value)
        patch = {'type': 'frontmatter', 'key': args.fm_key, 'action': args.action, 'value': args.value}
    else:
        print("ERROR: specify --section, --line, or --fm-key")
        sys.exit(1)

    diff = show_diff(old_text, new_text, filepath)

    if not diff:
        print("No changes.")
        return

    if args.dry_run:
        print("--- DRY RUN (no changes written) ---")
        print(diff)
        return

    if not args.yes:
        print(diff)
        print(f"\nApply this edit to {filepath}? [y/N] ", end='')
        response = input().strip().lower()
        if response not in ('y', 'yes'):
            print("Cancelled.")
            return

    write_file(filepath, new_text)
    log_patch(filepath, patch, inverse)
    print(f"OK  {filepath}")

def cmd_links(args):
    results = list_wikilinks(args.dir, getattr(args, 'page', None))
    if args.page:
        print(f"Pages referencing [[{args.page}]]:")
        for fpath, links in results:
            print(f"  {fpath} ({len(links)}x)")
    else:
        for fpath, links in results:
            print(f"{fpath}: {links}")

def cmd_undo(args):
    last = undo_last(args.file)
    print(f"Undone: {json.dumps(last['patch'], ensure_ascii=False)}")

def cmd_lock(args):
    ok, existing = acquire_lock(args.file, args.holder, args.ttl)
    if ok:
        print(f"LOCKED {args.file} (holder: {args.holder}, ttl: {args.ttl}m)")
    else:
        print(f"DENIED: locked by '{existing}'")

def cmd_unlock(args):
    release_lock(args.file)
    print(f"UNLOCKED {args.file}")

def main():
    parser = argparse.ArgumentParser(
        description='mdtool — structural markdown editor for AI agents',
        usage='''python mdtool.py <command> [<args>]

Commands:
  edit     Edit a markdown file by section, line, or frontmatter key
  links    List wikilinks across markdown files
  undo     Undo last edit
  lock     Acquire file lock
  unlock   Release file lock
''')
    parser.add_argument('command', choices=['edit', 'links', 'undo', 'lock', 'unlock'])

    # Handle unknown args to pass to command-specific parser
    args, remaining = parser.parse_known_args()

    if args.command == 'edit':
        p = argparse.ArgumentParser(prog='mdtool edit')
        p.add_argument('file')
        t = p.add_mutually_exclusive_group(required=True)
        t.add_argument('--section', '-s', help='Section heading text to match')
        t.add_argument('--line', '-l', type=int, help='Line number (1-indexed)')
        t.add_argument('--fm-key', '-k', help='Frontmatter key')
        p.add_argument('--action', '-a', required=True,
                       choices=['replace','insert-after','insert-before','append','prepend','delete','set','unset'])
        p.add_argument('--content', '-c', help='Text content to insert/replace with')
        p.add_argument('--value', '-v', help='Value for frontmatter set (alias for --content)')
        p.add_argument('--file', '-f', dest='content_file', help='Read content from file')
        p.add_argument('--dry-run', '-n', action='store_true', help='Show diff, do not write')
        p.add_argument('--yes', '-y', action='store_true', help='Skip confirmation prompt')
        p.add_argument('--steal', action='store_true', help='Ignore lock and edit anyway')
        cmd_edit(p.parse_args(remaining))

    elif args.command == 'links':
        p = argparse.ArgumentParser(prog='mdtool links')
        p.add_argument('dir')
        p.add_argument('--page', '-p', help='Find references to this page')
        cmd_links(p.parse_args(remaining))

    elif args.command == 'undo':
        p = argparse.ArgumentParser(prog='mdtool undo')
        p.add_argument('file')
        cmd_undo(p.parse_args(remaining))

    elif args.command == 'lock':
        p = argparse.ArgumentParser(prog='mdtool lock')
        p.add_argument('file')
        p.add_argument('--holder', '-H', required=True)
        p.add_argument('--ttl', type=int, default=30, help='TTL in minutes (default: 30)')
        cmd_lock(p.parse_args(remaining))

    elif args.command == 'unlock':
        p = argparse.ArgumentParser(prog='mdtool unlock')
        p.add_argument('file')
        cmd_unlock(p.parse_args(remaining))


if __name__ == '__main__':
    main()
