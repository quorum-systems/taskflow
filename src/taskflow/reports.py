"""
reports.py — pipeline and progress reports.

Both reports read from the backlog files and produce either a terminal
table or JSON. State file paths come from config so nothing here is
hardcoded. Category ordering follows the config, extras are alphabetical,
uncategorized is always last.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Optional

from taskflow.config import TaskflowConfig
from taskflow.tasklib import WEEK_HEADING_RE

CATEGORY_RE = re.compile(
    r"^###\s+(?:[\U0001F300-\U0001FFFE\u2600-\u26FF\u2700-\u27BF]\s*)?(.*\S.*?)\s*$"
)
PHASE_RE   = re.compile(r"^##\s+(?!Week of)(.*\S.*?)\s*$")
DIVIDER_RE = re.compile(r"^---\s*$")
DONE_RE    = re.compile(r"^\[[\d\s:\-]+\]\s+done:\s+\(([^)]+)\)\s+-\s+.+$")
TASK_RE    = re.compile(r"^\s*[*-]\s+\S")

UNCATEGORIZED = "Uncategorized"


def _strip_emoji(name: str) -> str:
    return re.sub(r"^[\U0001F300-\U0001FFFE\u2600-\u26FF\u2700-\u27BF]\s*", "", name).strip()


def count_tasks_by_category(path: Path) -> dict[str, int]:
    """Count top-level (non-indented) tasks per category in a backlog file."""
    if not path.exists():
        return {}

    counts: dict[str, int] = defaultdict(int)
    current_cat: Optional[str] = None

    for line in path.read_text(encoding="utf-8").splitlines():
        if PHASE_RE.match(line):
            continue
        m = CATEGORY_RE.match(line)
        if m:
            current_cat = _strip_emoji(m.group(1))
            continue
        if DIVIDER_RE.match(line):
            current_cat = None
            continue
        # only count top-level tasks — subtasks start with whitespace
        if TASK_RE.match(line) and not line.startswith("  "):
            counts[current_cat or UNCATEGORIZED] += 1

    return dict(counts)


def parse_done_by_week(done_path: Path) -> list[tuple[str, dict[str, int]]]:
    """
    Parse done.md into (week_date_str, {category: count}) tuples, newest first.
    Week date comes from the ## Week of YYYY-MM-DD heading.
    """
    if not done_path.exists():
        return []

    weeks: list[tuple[str, dict[str, int]]] = []
    current_week: Optional[str] = None
    current_counts: dict[str, int] = defaultdict(int)

    for line in done_path.read_text(encoding="utf-8").splitlines():
        m_week = WEEK_HEADING_RE.match(line)
        if m_week:
            if current_week is not None:
                weeks.append((current_week, dict(current_counts)))
            current_week = m_week.group(1)
            current_counts = defaultdict(int)
            continue

        m_done = DONE_RE.match(line)
        if m_done and current_week is not None:
            cat = _strip_emoji(m_done.group(1).strip())
            current_counts[cat] += 1

    if current_week is not None:
        weeks.append((current_week, dict(current_counts)))

    # newest first
    weeks.sort(key=lambda x: x[0], reverse=True)
    return weeks


def ordered_categories(
    backlog_counts: dict[str, dict[str, int]],
    week_counts: list[tuple[str, dict[str, int]]],
    config: TaskflowConfig,
) -> list[str]:
    """
    Category order: config order first, then alphabetical extras, uncategorized last.
    """
    seen: set[str] = set()
    ordered: list[str] = []

    # config order wins
    for name in config.category_names():
        if name not in seen:
            ordered.append(name)
            seen.add(name)

    # anything in the files that isn't in config — alphabetical
    extras: set[str] = set()
    for counts in backlog_counts.values():
        extras.update(c for c in counts if c != UNCATEGORIZED and c not in seen)
    for _, counts in week_counts:
        extras.update(c for c in counts if c != UNCATEGORIZED and c not in seen)
    for name in sorted(extras):
        ordered.append(name)
        seen.add(name)

    # uncategorized always last, only if present
    has_unc = any(
        UNCATEGORIZED in counts
        for counts in list(backlog_counts.values()) + [c for _, c in week_counts]
    )
    if has_unc:
        ordered.append(UNCATEGORIZED)

    return ordered


# ---------------------------------------------------------------------------
# Table renderer
# ---------------------------------------------------------------------------

def _pad(s: str, width: int, align: str = "left") -> str:
    s = str(s)
    return s.rjust(width) if align == "right" else s.ljust(width)


def render_table(headers: list[str], rows: list[list[str]], col_aligns: Optional[list[str]] = None) -> str:
    n = len(headers)
    col_aligns = col_aligns or ["left"] * n
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < n:
                widths[i] = max(widths[i], len(str(cell)))

    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    hdr = "|" + "|".join(f" {_pad(h, widths[i])} " for i, h in enumerate(headers)) + "|"

    lines = [sep, hdr, sep]
    for row in rows:
        cells = []
        for i in range(n):
            val = row[i] if i < len(row) else ""
            cells.append(f" {_pad(val, widths[i], col_aligns[i] if i < len(col_aligns) else 'left')} ")
        lines.append("|" + "|".join(cells) + "|")
    lines.append(sep)
    return "\n".join(lines)


def _fmt_week(d: str) -> str:
    try:
        dt = date.fromisoformat(d)
        return dt.strftime("%b %-d")
    except Exception:
        return d


def _cat_label(name: str, config: TaskflowConfig) -> str:
    icon = config.category_icon(name)
    return f"{icon} {name}".strip() if icon else name


# ---------------------------------------------------------------------------
# progress report
# ---------------------------------------------------------------------------

def report_progress(config: TaskflowConfig, as_json: bool = False, max_weeks: int = 5) -> str:
    now_counts   = count_tasks_by_category(config.state_path("now"))
    done_by_week = parse_done_by_week(config.state_path("done"))
    weeks        = done_by_week[:max_weeks]
    categories   = ordered_categories({"now": now_counts}, weeks, config)

    if as_json:
        data = {
            "report": "progress",
            "columns": ["now"] + [w for w, _ in weeks],
            "rows": [],
        }
        for cat in categories:
            row: dict = {"category": cat, "now": now_counts.get(cat, 0)}
            for wd, counts in weeks:
                row[wd] = counts.get(cat, 0)
            data["rows"].append(row)
        return json.dumps(data, indent=2)

    now_icon  = config.state_icon("now")
    done_icon = config.state_icon("done")

    headers    = ["Category", f"{now_icon} Now".strip()] + [f"{done_icon} {_fmt_week(w)}".strip() for w, _ in weeks]
    col_aligns = ["left"] + ["right"] * (1 + len(weeks))
    rows = [
        [_cat_label(cat, config), str(now_counts.get(cat, 0))]
        + [str(c.get(cat, 0)) for _, c in weeks]
        for cat in categories
    ]
    return f"\n  progress — now vs. completed by week\n\n{render_table(headers, rows, col_aligns)}\n"


# ---------------------------------------------------------------------------
# pipeline report
# ---------------------------------------------------------------------------

def report_pipeline(config: TaskflowConfig, as_json: bool = False) -> str:
    later_counts   = count_tasks_by_category(config.state_path("later"))
    next_counts    = count_tasks_by_category(config.state_path("next"))
    paused_counts  = count_tasks_by_category(config.state_path("paused"))
    blocked_counts = count_tasks_by_category(config.state_path("blocked"))
    now_counts     = count_tasks_by_category(config.state_path("now"))
    done_by_week   = parse_done_by_week(config.state_path("done"))

    this_week_counts = done_by_week[0][1] if done_by_week else {}
    this_week_date   = done_by_week[0][0] if done_by_week else None

    all_counts = {
        "later": later_counts, "next": next_counts,
        "paused": paused_counts, "blocked": blocked_counts,
        "now": now_counts, "this_week": this_week_counts,
    }
    categories = ordered_categories(all_counts, [], config)

    if as_json:
        return json.dumps({
            "report": "pipeline",
            "columns": ["later", "next", "paused", "blocked", "now", "this_week"],
            "this_week_heading": this_week_date,
            "rows": [{
                "category": cat,
                "later":     later_counts.get(cat, 0),
                "next":      next_counts.get(cat, 0),
                "paused":    paused_counts.get(cat, 0),
                "blocked":   blocked_counts.get(cat, 0),
                "now":       now_counts.get(cat, 0),
                "this_week": this_week_counts.get(cat, 0),
            } for cat in categories],
        }, indent=2)

    def si(key: str, fallback: str) -> str:
        return config.state_icon(key) or fallback

    week_label = (
        f"{si('done', '✓')} {_fmt_week(this_week_date)}".strip()
        if this_week_date else "This Week"
    )

    headers = [
        "Category",
        f"{si('later', '◇')} Later".strip(),
        f"{si('next', '◈')} Next".strip(),
        f"{si('paused', '⏸')} Paused".strip(),
        f"{si('blocked', '⊘')} Blocked".strip(),
        f"{si('now', '▶')} Now".strip(),
        week_label,
    ]
    col_aligns = ["left"] + ["right"] * 6
    rows = [[
        _cat_label(cat, config),
        str(later_counts.get(cat, 0)),
        str(next_counts.get(cat, 0)),
        str(paused_counts.get(cat, 0)),
        str(blocked_counts.get(cat, 0)),
        str(now_counts.get(cat, 0)),
        str(this_week_counts.get(cat, 0)),
    ] for cat in categories]

    return f"\n  pipeline — work in flight and completed this week\n\n{render_table(headers, rows, col_aligns)}\n"
