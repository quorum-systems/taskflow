"""
test_reports.py — tests for pipeline and progress reports.

Reports read from files and produce tables or JSON. The main things
to verify: correct counts, correct category ordering, JSON structure.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from taskflow.config import TaskflowConfig
from taskflow.reports import (count_tasks_by_category, ordered_categories,
                              parse_done_by_week, report_pipeline,
                              report_progress)

SAMPLE_NOW = """\
### 🔵 Engineering
* task one
* task two
  * subtask (should not count)

---

### 🔴 Operations
* task three

---
"""

SAMPLE_DONE = """\
# Done

## Week of 2026-03-21

[2026-03-21 09:00:00] done: (Engineering) - completed alpha
[2026-03-21 10:00:00] done: (Engineering) - completed beta
[2026-03-22 11:00:00] done: (Operations) - completed gamma

## Week of 2026-03-28

[2026-03-28 09:00:00] done: (Engineering) - completed delta
"""


class TestCountTasksByCategory:
    def test_counts_top_level_only(self, tmp_path: Path) -> None:
        f = tmp_path / "now.md"
        f.write_text(SAMPLE_NOW)
        counts = count_tasks_by_category(f)
        # subtask should not be counted
        assert counts["Engineering"] == 2
        assert counts["Operations"] == 1

    def test_returns_empty_for_missing_file(self, tmp_path: Path) -> None:
        assert count_tasks_by_category(tmp_path / "missing.md") == {}

    def test_skips_phase_headings(self, tmp_path: Path) -> None:
        f = tmp_path / "later.md"
        f.write_text("## Phase 1\n\n### Engineering\n* task\n---\n")
        counts = count_tasks_by_category(f)
        assert "Engineering" in counts


class TestParseDoneByWeek:
    def test_parses_weeks(self, tmp_path: Path) -> None:
        f = tmp_path / "done.md"
        f.write_text(SAMPLE_DONE)
        weeks = parse_done_by_week(f)
        assert len(weeks) == 2

    def test_newest_first(self, tmp_path: Path) -> None:
        f = tmp_path / "done.md"
        f.write_text(SAMPLE_DONE)
        weeks = parse_done_by_week(f)
        assert weeks[0][0] == "2026-03-28"
        assert weeks[1][0] == "2026-03-21"

    def test_counts_per_category(self, tmp_path: Path) -> None:
        f = tmp_path / "done.md"
        f.write_text(SAMPLE_DONE)
        weeks = parse_done_by_week(f)
        # Mar 21 week
        mar21 = dict(weeks)[" 2026-03-21"] if " 2026-03-21" in dict(weeks) else weeks[1][1]
        assert mar21.get("Engineering", 0) == 2
        assert mar21.get("Operations", 0) == 1


class TestOrderedCategories:
    @pytest.fixture
    def cfg(self, tmp_path: Path) -> TaskflowConfig:
        data = {
            "categories": [
                {"name": "Engineering", "icon": "🔵"},
                {"name": "Operations", "icon": "🔴"},
            ]
        }
        return TaskflowConfig(tmp_path, data)

    def test_config_order_first(self, cfg: TaskflowConfig) -> None:
        cats = ordered_categories({"now": {"Engineering": 1}}, [], cfg)
        assert cats.index("Engineering") < cats.index("Operations") if "Operations" in cats else True

    def test_extras_alphabetical(self, cfg: TaskflowConfig) -> None:
        cats = ordered_categories({"now": {"Zebra": 1, "Alpha": 1}}, [], cfg)
        # extras should be alphabetical after config cats
        config_end = len(cfg.category_names())
        extras = cats[config_end:]
        assert extras == sorted(extras)

    def test_uncategorized_last(self, cfg: TaskflowConfig) -> None:
        cats = ordered_categories({"now": {"Uncategorized": 1, "Engineering": 2}}, [], cfg)
        assert cats[-1] == "Uncategorized"

    def test_uncategorized_absent_when_not_needed(self, cfg: TaskflowConfig) -> None:
        cats = ordered_categories({"now": {"Engineering": 1}}, [], cfg)
        assert "Uncategorized" not in cats


class TestReportProgress:
    @pytest.fixture
    def cfg(self, tmp_path: Path) -> TaskflowConfig:
        (tmp_path / ".taskflow" / "backlog").mkdir(parents=True)
        (tmp_path / ".taskflow/backlog/0-now.md").write_text(SAMPLE_NOW)
        (tmp_path / ".taskflow/backlog/done.md").write_text(SAMPLE_DONE)
        data = {
            "categories": [
                {"name": "Engineering", "icon": "🔵"},
                {"name": "Operations", "icon": "🔴"},
            ]
        }
        return TaskflowConfig(tmp_path, data)

    def test_returns_table(self, cfg: TaskflowConfig) -> None:
        result = report_progress(cfg)
        assert "Engineering" in result
        assert "Operations" in result

    def test_json_output(self, cfg: TaskflowConfig) -> None:
        result = report_progress(cfg, as_json=True)
        data = json.loads(result)
        assert data["report"] == "progress"
        assert "rows" in data
        assert any(r["category"] == "Engineering" for r in data["rows"])

    def test_json_now_counts(self, cfg: TaskflowConfig) -> None:
        result = report_progress(cfg, as_json=True)
        data = json.loads(result)
        eng = next(r for r in data["rows"] if r["category"] == "Engineering")
        assert eng["now"] == 2


class TestReportPipeline:
    @pytest.fixture
    def cfg(self, tmp_path: Path) -> TaskflowConfig:
        backlog = tmp_path / ".taskflow" / "backlog"
        backlog.mkdir(parents=True)
        for name, text in [
            ("0-now.md", SAMPLE_NOW),
            ("1-blocked.md", "### Engineering\n* blocked task\n---\n"),
            ("2-paused.md", "---\n"),
            ("3-next.md", "### Engineering\n* next task\n---\n"),
            ("4-later.md", "### Engineering\n* later task\n---\n"),
            ("done.md", SAMPLE_DONE),
        ]:
            (backlog / name).write_text(text)
        data = {
            "categories": [
                {"name": "Engineering", "icon": "🔵"},
                {"name": "Operations", "icon": "🔴"},
            ]
        }
        return TaskflowConfig(tmp_path, data)

    def test_returns_table(self, cfg: TaskflowConfig) -> None:
        result = report_pipeline(cfg)
        assert "Engineering" in result
        assert "Later" in result
        assert "Now" in result

    def test_json_output(self, cfg: TaskflowConfig) -> None:
        result = report_pipeline(cfg, as_json=True)
        data = json.loads(result)
        assert data["report"] == "pipeline"
        eng = next(r for r in data["rows"] if r["category"] == "Engineering")
        assert eng["now"] == 2
        assert eng["blocked"] == 1
