"""
archive.py — done.md week archiving.

When done.md has more weeks than the configured limit, older ones move
to monthly archive files. Archive files are named yyyy-mm-archive.md
and weeks within them run oldest to newest.

The date in the ## Week of heading is what determines which monthly
archive file a week goes into — not the individual entry timestamps.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

WEEK_HEADING_RE = re.compile(r"^##\s+Week of\s+(\d{4}-\d{2}-\d{2})\s*$")


def parse_week_blocks(lines: list[str]) -> list[dict]:
    """
    Split done.md into a list of week blocks.

    Each block:
        date     — YYYY-MM-DD string from the heading
        heading  — the full ## Week of ... line
        lines    — all lines that follow the heading until the next heading
    """
    blocks = []
    current: Optional[dict] = None

    for line in lines:
        m = WEEK_HEADING_RE.match(line)
        if m:
            if current is not None:
                blocks.append(current)
            current = {"date": m.group(1), "heading": line, "lines": []}
        elif current is not None:
            current["lines"].append(line)

    if current is not None:
        blocks.append(current)

    return blocks


def archive_month_path(archive_dir: Path, week_date: str) -> Path:
    """
    Return the archive file path for a given week date string (YYYY-MM-DD).
    Uses the year-month of the week heading date.
    """
    year_month = week_date[:7]  # YYYY-MM
    return archive_dir / f"{year_month}-archive.md"


def render_week_block(block: dict) -> list[str]:
    """Render a week block back to lines, trailing blanks stripped."""
    out = [block["heading"]] + block["lines"]
    while out and out[-1].strip() == "":
        out.pop()
    return out


def archive_old_weeks(done_path: Path, archive_dir: Path, keep_weeks: int) -> int:
    """
    Check done.md and move any weeks beyond keep_weeks into monthly archive files.
    Returns the number of weeks archived.

    Weeks are ordered oldest-to-newest inside each archive file.
    The done.md is rewritten with only the most recent keep_weeks weeks.
    """
    if not done_path.exists():
        return 0

    raw = done_path.read_text(encoding="utf-8").splitlines()

    # separate the preamble (anything before the first ## Week of heading)
    # from the week blocks — we preserve the preamble in done.md
    first_week_idx = None
    for i, line in enumerate(raw):
        if WEEK_HEADING_RE.match(line):
            first_week_idx = i
            break

    preamble = raw[:first_week_idx] if first_week_idx is not None else raw
    week_lines = raw[first_week_idx:] if first_week_idx is not None else []

    blocks = parse_week_blocks(week_lines)

    if len(blocks) <= keep_weeks:
        # nothing to archive
        return 0

    to_archive = blocks[:-keep_weeks]
    to_keep = blocks[-keep_weeks:]

    # write each old week into its monthly archive file
    archive_dir.mkdir(parents=True, exist_ok=True)

    for block in to_archive:
        month_file = archive_month_path(archive_dir, block["date"])

        if month_file.exists():
            existing = month_file.read_text(encoding="utf-8").splitlines()
        else:
            existing = [f"# Archive — {block['date'][:7]}", ""]

        # strip trailing blanks before appending
        while existing and existing[-1].strip() == "":
            existing.pop()

        existing.append("")
        existing.extend(render_week_block(block))

        month_file.write_text("\n".join(existing).rstrip() + "\n", encoding="utf-8")

    # rewrite done.md with only the weeks we're keeping
    kept_lines = []
    for i, block in enumerate(to_keep):
        if i > 0:
            kept_lines.append("")
        kept_lines.extend(render_week_block(block))

    # strip trailing blanks from preamble before rejoining
    while preamble and preamble[-1].strip() == "":
        preamble.pop()

    out_lines = preamble
    if kept_lines:
        out_lines = preamble + [""] + kept_lines if preamble else kept_lines

    done_path.write_text("\n".join(out_lines).rstrip() + "\n", encoding="utf-8")

    return len(to_archive)
