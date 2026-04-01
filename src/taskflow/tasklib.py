"""
tasklib.py — shared parsing and file mutation.

All the regex, section parsing, fuzzy matching, and done.md writing
lives here. Nothing in this module knows about git or the CLI — it just
reads and writes backlog files.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

# category headings are ###, with an optional leading emoji
CATEGORY_RE = re.compile(r"^###\s+(?:[\U0001F300-\U0001FFFE\u2600-\u26FF\u2700-\u27BF]\s*)?(.*\S.*?)\s*$")

# phase headings are ## (later.md only) — task operations skip these
PHASE_RE = re.compile(r"^##\s+(.*\S.*?)\s*$")

# week headings in done.md
WEEK_HEADING_RE = re.compile(r"^##\s+Week of\s+(\d{4}-\d{2}-\d{2})\s*$")

DIVIDER_RE = re.compile(r"^---\s*$")

# plain bullets — * or - with optional indent, no checkboxes
TASK_RE = re.compile(r"^(\s*)([*-]\s+)(.*\S.*?)\s*$")


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------


def normalize(text: str) -> str:
    """Collapse whitespace and lowercase — used for task matching."""
    return re.sub(r"\s+", " ", text.strip()).lower()


def strip_emoji(text: str) -> str:
    """Remove a leading emoji and any trailing space from a heading name."""
    return re.sub(r"^[\U0001F300-\U0001FFFE\u2600-\u26FF\u2700-\u27BF]\s*", "", text).strip()


def fuzzy_match(query: str, candidate: str) -> bool:
    """True if query appears anywhere in candidate (normalized, case-insensitive)."""
    return normalize(query) in normalize(candidate)


# ---------------------------------------------------------------------------
# Line classifiers
# ---------------------------------------------------------------------------


def is_category(line: str) -> bool:
    return CATEGORY_RE.match(line) is not None


def is_phase(line: str) -> bool:
    # phase headings are ## but not ###
    return PHASE_RE.match(line) is not None and not is_category(line)


def is_divider(line: str) -> bool:
    return DIVIDER_RE.match(line) is not None


def task_match(line: str) -> Optional[re.Match]:
    return TASK_RE.match(line)


def task_indent(line: str) -> Optional[int]:
    m = task_match(line)
    return len(m.group(1)) if m else None


def task_text(line: str) -> Optional[str]:
    m = task_match(line)
    return m.group(3) if m else None


# ---------------------------------------------------------------------------
# Section parsing
# ---------------------------------------------------------------------------


def parse_sections(lines: list[str]) -> list[dict]:
    """
    Parse a backlog file into category sections.

    Each section:
        heading      — canonical name (emoji stripped)
        heading_raw  — name as written (with emoji)
        start        — line index of the ### heading
        end          — line index of the --- divider (or last line)
        tasks        — list of (line_idx, task_text, raw_line)

    Phase headings (##) are skipped — they're structure, not sections.
    """
    sections = []
    i = 0
    n = len(lines)

    while i < n:
        if is_phase(lines[i]):
            i += 1
            continue

        m = CATEGORY_RE.match(lines[i])
        if not m:
            i += 1
            continue

        heading_raw = m.group(1)
        heading = strip_emoji(heading_raw).strip()
        start = i
        j = i + 1
        tasks = []

        while j < n:
            if is_category(lines[j]) or is_phase(lines[j]) or is_divider(lines[j]):
                break
            txt = task_text(lines[j])
            if txt is not None:
                tasks.append((j, txt, lines[j]))
            j += 1

        end = j if (j < n and is_divider(lines[j])) else j - 1

        sections.append(
            {
                "start": start,
                "end": end,
                "heading": heading,
                "heading_raw": heading_raw,
                "tasks": tasks,
            }
        )

        i = j + 1 if (j < n and is_divider(lines[j])) else j

    return sections


def find_duplicates(sections: list[dict]) -> list[tuple[str, int, int]]:
    """Return (key, line1, line2) for any duplicate task text across sections."""
    seen: dict[str, int] = {}
    dups = []
    for section in sections:
        for line_no, txt, _raw in section["tasks"]:
            key = normalize(txt)
            if key in seen:
                dups.append((key, seen[key] + 1, line_no + 1))
            else:
                seen[key] = line_no
    return dups


def find_task(sections: list[dict], query: str, src_path: Path) -> tuple[dict, int, str, str]:
    """
    Fuzzy-match a task across sections. One match = proceed.
    Zero or multiple = raise with a useful message.
    """
    import click

    matches = []
    for section in sections:
        for line_idx, txt, raw_line in section["tasks"]:
            if fuzzy_match(query, txt):
                matches.append((section, line_idx, txt, raw_line))

    if not matches:
        raise click.UsageError(f"No task matching '{query}' in {src_path.name}\n  Run `taskflow list` to see what's there.")

    if len(matches) > 1:
        lines = "\n".join(f"  line {idx + 1}  [{sec['heading']}]  {txt}" for sec, idx, txt, _ in matches)
        raise click.UsageError(f"Multiple tasks match '{query}' — be more specific:\n{lines}")

    return matches[0]


# ---------------------------------------------------------------------------
# Task block (parent + children)
# ---------------------------------------------------------------------------


def find_task_block(lines: list[str], section_end: int, start_idx: int) -> tuple[int, int]:
    """
    Return [start, end) for a task and all its indented children.
    Children are lines with greater indent than the parent.
    Non-task lines inside the subtree ride along until it ends.
    """
    parent_indent = task_indent(lines[start_idx])
    if parent_indent is None:
        raise ValueError(f"Line {start_idx} is not a task line")

    end = start_idx + 1
    while end < section_end:
        line = lines[end]
        if is_category(line) or is_phase(line) or is_divider(line):
            break
        indent = task_indent(line)
        if indent is not None and indent <= parent_indent:
            break
        end += 1

    return start_idx, end


# ---------------------------------------------------------------------------
# Blank line handling and serialisation
# ---------------------------------------------------------------------------


def collapse_blank_lines(lines: list[str]) -> list[str]:
    """Never let two blank lines sit next to each other."""
    out = []
    prev_blank = False
    for line in lines:
        blank = line.strip() == ""
        if blank and prev_blank:
            continue
        out.append(line)
        prev_blank = blank
    return out


def ensure_blank_before_dividers(lines: list[str]) -> list[str]:
    """Every --- gets a blank line before it."""
    out = []
    for line in lines:
        if DIVIDER_RE.match(line) and out and out[-1].strip() != "":
            out.append("")
        out.append(line)
    return out


def serialize_lines(lines: list[str], path: Path) -> None:
    lines = collapse_blank_lines(lines)
    lines = ensure_blank_before_dividers(lines)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Empty section removal
# ---------------------------------------------------------------------------


def remove_empty_sections(lines: list[str]) -> list[str]:
    sections = parse_sections(lines)
    remove_ranges = []

    for section in sections:
        if not section["tasks"]:
            start = section["start"]
            end = section["end"]
            while end + 1 < len(lines) and lines[end + 1].strip() == "":
                end += 1
            while start - 1 >= 0 and lines[start - 1].strip() == "":
                start -= 1
            remove_ranges.append((start, end))

    if not remove_ranges:
        return collapse_blank_lines(lines)

    result = []
    idx = 0
    for start, end in sorted(remove_ranges):
        if idx < start:
            result.extend(lines[idx:start])
        idx = end + 1
    if idx < len(lines):
        result.extend(lines[idx:])

    return collapse_blank_lines(result)


# ---------------------------------------------------------------------------
# Destination insertion
# ---------------------------------------------------------------------------


def insert_into_destination(
    dst_lines: list[str],
    moved_block: list[str],
    category: str,
    category_raw: str,
) -> list[str]:
    """
    Insert moved_block into dst_lines under the matching category section.
    Creates the section if it doesn't exist.
    """
    dst_sections = parse_sections(dst_lines)
    inserted = False

    for dsec in dst_sections:
        if dsec["heading"] == category:
            insert_at = dsec["end"]

            # if the line before the divider is blank, insert before the blank
            # so new tasks don't end up after it
            if insert_at > 0 and dst_lines[insert_at - 1].strip() == "":
                insert_at -= 1

            # blank separator only when the preceding task has subtasks
            preceding = dst_lines[insert_at - 1] if insert_at > 0 else ""
            if preceding.strip() != "" and preceding.startswith("  "):
                dst_lines[insert_at:insert_at] = [""] + moved_block
            else:
                dst_lines[insert_at:insert_at] = moved_block

            inserted = True
            break

    if not inserted:
        if dst_lines and dst_lines[-1].strip() != "":
            dst_lines.append("")
        dst_lines.append(f"### {category_raw}")
        dst_lines.extend(moved_block)
        dst_lines.append("---")

    return collapse_blank_lines(dst_lines)


# ---------------------------------------------------------------------------
# Done log
# ---------------------------------------------------------------------------


def latest_week_heading_date(lines: list[str]) -> Optional[date]:
    """Return the date from the most recent ## Week of heading, or None."""
    latest: Optional[date] = None
    for line in lines:
        m = WEEK_HEADING_RE.match(line)
        if m:
            try:
                d = date.fromisoformat(m.group(1))
                if latest is None or d > latest:
                    latest = d
            except ValueError:
                pass
    return latest


def append_done(done_path: Path, category: str, task_text_str: str) -> None:
    """
    Append a timestamped done entry. Auto-inserts a week heading when:
      - no prior heading exists, or
      - most recent heading is >= 7 days old

    The heading date is today — weeks are relative to when work started,
    not a fixed Mon/Sun calendar boundary.
    """
    done_path.parent.mkdir(parents=True, exist_ok=True)
    done_lines = done_path.read_text(encoding="utf-8").splitlines() if done_path.exists() else []

    today = date.today()
    latest = latest_week_heading_date(done_lines)
    needs_heading = (latest is None) or ((today - latest) >= timedelta(days=7))

    if needs_heading:
        if done_lines and done_lines[-1].strip() != "":
            done_lines.append("")
        done_lines.append(f"## Week of {today.isoformat()}")
        done_lines.append("")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    done_lines.append(f"[{timestamp}] done: ({category}) - {task_text_str}")
    serialize_lines(done_lines, done_path)


# ---------------------------------------------------------------------------
# Task move
# ---------------------------------------------------------------------------


def move_task(src_path: Path, dst_path: Path, query: str) -> tuple[str, str]:
    """
    Move a task (and its children) from src to dst.
    Returns (category, matched_task_text) on success.
    Raises click.UsageError on any problem.
    """
    import click

    if not src_path.exists():
        raise click.UsageError(f"Source file does not exist: {src_path}")

    src_lines = src_path.read_text(encoding="utf-8").splitlines()
    src_sections = parse_sections(src_lines)

    dups = find_duplicates(src_sections)
    if dups:
        detail = "\n".join(f"  lines {l1} and {l2}: {k}" for k, l1, l2 in dups)
        raise click.UsageError(f"Duplicate tasks in {src_path.name} — fix before continuing:\n{detail}")

    section, line_idx, txt, _raw = find_task(src_sections, query, src_path)
    category = section["heading"]
    category_raw = section["heading_raw"]

    block_start, block_end = find_task_block(src_lines, section["end"], line_idx)
    moved_block = src_lines[block_start:block_end]

    # strip trailing blanks from the block so insertion doesn't double-space
    while moved_block and moved_block[-1].strip() == "":
        moved_block.pop()

    del src_lines[block_start:block_end]
    src_lines = remove_empty_sections(src_lines)
    serialize_lines(src_lines, src_path)

    dst_lines = dst_path.read_text(encoding="utf-8").splitlines() if dst_path.exists() else []
    dst_lines = insert_into_destination(dst_lines, moved_block, category, category_raw)
    serialize_lines(dst_lines, dst_path)

    return category, txt


def complete_task(src_path: Path, done_path: Path, query: str) -> tuple[str, str]:
    """
    Remove a task from src, append to done.md with timestamp.
    Returns (category, matched_task_text).
    """
    import click

    if not src_path.exists():
        raise click.UsageError(f"Source file does not exist: {src_path}")

    src_lines = src_path.read_text(encoding="utf-8").splitlines()
    src_sections = parse_sections(src_lines)

    dups = find_duplicates(src_sections)
    if dups:
        detail = "\n".join(f"  lines {l1} and {l2}: {k}" for k, l1, l2 in dups)
        raise click.UsageError(f"Duplicate tasks in {src_path.name} — fix before continuing:\n{detail}")

    section, line_idx, txt, _raw = find_task(src_sections, query, src_path)
    category = section["heading"]

    block_start, block_end = find_task_block(src_lines, section["end"], line_idx)
    del src_lines[block_start:block_end]

    # clean up any orphaned blank lines at the deletion site
    while block_start < len(src_lines) and src_lines[block_start].strip() == "":
        del src_lines[block_start]

    src_lines = remove_empty_sections(src_lines)
    serialize_lines(src_lines, src_path)
    append_done(done_path, category, txt)

    return category, txt
