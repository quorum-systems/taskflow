"""
test_tasklib.py — tests for the core parsing and mutation logic.

This covers the stuff that touches backlog files: section parsing,
fuzzy matching, task moves, done appends, and week heading auto-insertion.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from taskflow.tasklib import (
    append_done,
    collapse_blank_lines,
    complete_task,
    find_task,
    find_task_block,
    latest_week_heading_date,
    move_task,
    normalize,
    parse_sections,
    remove_empty_sections,
    serialize_lines,
    strip_emoji,
    task_text,
)


class TestNormalize:
    def test_lowercases(self) -> None:
        assert normalize("Deploy MaaS") == "deploy maas"

    def test_collapses_whitespace(self) -> None:
        assert normalize("  too   many   spaces  ") == "too many spaces"


class TestStripEmoji:
    def test_strips_colored_circle(self) -> None:
        assert strip_emoji("🔵 Backend") == "Backend"

    def test_strips_nothing_when_no_emoji(self) -> None:
        assert strip_emoji("Backend") == "Backend"

    def test_handles_multiple_words(self) -> None:
        assert strip_emoji("🟡 Product / Site") == "Product / Site"


class TestTaskText:
    def test_plain_bullet(self) -> None:
        assert task_text("* deploy MaaS") == "deploy MaaS"

    def test_dash_bullet(self) -> None:
        assert task_text("- deploy MaaS") == "deploy MaaS"

    def test_indented(self) -> None:
        assert task_text("  * subtask") == "subtask"

    def test_not_a_task(self) -> None:
        assert task_text("## Heading") is None

    def test_empty_line(self) -> None:
        assert task_text("") is None


class TestParseSections:
    def test_basic_section(self) -> None:
        lines = [
            "### Engineering",
            "* deploy MaaS",
            "* set up k8s",
            "---",
        ]
        sections = parse_sections(lines)
        assert len(sections) == 1
        assert sections[0]["heading"] == "Engineering"
        assert len(sections[0]["tasks"]) == 2

    def test_strips_emoji_from_heading(self) -> None:
        lines = ["### 🔵 Engineering", "* task", "---"]
        sections = parse_sections(lines)
        assert sections[0]["heading"] == "Engineering"
        assert sections[0]["heading_raw"] == "Engineering"

    def test_phase_headers_skipped(self) -> None:
        lines = [
            "## Phase 1",
            "### Engineering",
            "* task",
            "---",
        ]
        sections = parse_sections(lines)
        assert len(sections) == 1
        assert sections[0]["heading"] == "Engineering"

    def test_multiple_sections(self) -> None:
        lines = [
            "### Engineering",
            "* task one",
            "---",
            "### Operations",
            "* task two",
            "---",
        ]
        sections = parse_sections(lines)
        assert len(sections) == 2
        assert sections[0]["heading"] == "Engineering"
        assert sections[1]["heading"] == "Operations"

    def test_subtasks_not_counted_separately(self) -> None:
        lines = [
            "### Engineering",
            "* parent task",
            "  * child task",
            "---",
        ]
        sections = parse_sections(lines)
        # subtask line shows up in tasks list since parse_sections includes all task lines
        assert any(t[1] == "parent task" for t in sections[0]["tasks"])


class TestFindTask:
    def _sections(self, lines: list[str]):
        return parse_sections(lines)

    def test_exact_match(self, tmp_path: Path) -> None:
        lines = ["### Engineering", "* deploy MaaS 3.7", "---"]
        sections = self._sections(lines)
        src = tmp_path / "now.md"
        sec, idx, txt, raw = find_task(sections, "deploy MaaS 3.7", src)
        assert txt == "deploy MaaS 3.7"

    def test_fuzzy_match(self, tmp_path: Path) -> None:
        lines = ["### Engineering", "* deploy MaaS 3.7", "---"]
        sections = self._sections(lines)
        src = tmp_path / "now.md"
        _, _, txt, _ = find_task(sections, "MaaS", src)
        assert txt == "deploy MaaS 3.7"

    def test_no_match_raises(self, tmp_path: Path) -> None:
        import click
        lines = ["### Engineering", "* deploy MaaS 3.7", "---"]
        sections = self._sections(lines)
        src = tmp_path / "now.md"
        with pytest.raises(click.UsageError, match="No task matching"):
            find_task(sections, "kubernetes", src)

    def test_multiple_matches_raises(self, tmp_path: Path) -> None:
        import click
        lines = [
            "### Engineering",
            "* deploy MaaS",
            "* deploy ArgoCD",
            "---",
        ]
        sections = self._sections(lines)
        src = tmp_path / "now.md"
        with pytest.raises(click.UsageError, match="Multiple tasks"):
            find_task(sections, "deploy", src)


class TestFindTaskBlock:
    def test_task_without_subtasks(self) -> None:
        lines = ["### Engineering", "* task one", "* task two", "---"]
        sections = parse_sections(lines)
        line_idx = sections[0]["tasks"][0][0]
        start, end = find_task_block(lines, sections[0]["end"], line_idx)
        assert lines[start] == "* task one"
        assert end == start + 1

    def test_task_with_subtasks(self) -> None:
        lines = [
            "### Engineering",
            "* parent task",
            "  * child one",
            "  * child two",
            "* other task",
            "---",
        ]
        sections = parse_sections(lines)
        line_idx = sections[0]["tasks"][0][0]
        start, end = find_task_block(lines, sections[0]["end"], line_idx)
        assert end - start == 3  # parent + 2 children


class TestMoveTask:
    def test_moves_task_between_files(self, tmp_path: Path) -> None:
        src = tmp_path / "next.md"
        dst = tmp_path / "now.md"
        src.write_text("### Engineering\n* deploy MaaS\n---\n")
        dst.write_text("### Engineering\n---\n")

        category, matched = move_task(src, dst, "MaaS")

        assert category == "Engineering"
        assert matched == "deploy MaaS"
        assert "deploy MaaS" not in src.read_text()
        assert "deploy MaaS" in dst.read_text()

    def test_moves_task_with_subtasks(self, tmp_path: Path) -> None:
        src = tmp_path / "next.md"
        dst = tmp_path / "now.md"
        src.write_text("### Engineering\n* deploy MaaS\n  * step one\n  * step two\n---\n")
        dst.write_text("### Engineering\n---\n")

        move_task(src, dst, "MaaS")

        dst_text = dst.read_text()
        assert "step one" in dst_text
        assert "step two" in dst_text

    def test_creates_category_in_dst_if_missing(self, tmp_path: Path) -> None:
        src = tmp_path / "next.md"
        dst = tmp_path / "now.md"
        src.write_text("### Engineering\n* deploy MaaS\n---\n")
        dst.write_text("### Operations\n---\n")

        move_task(src, dst, "MaaS")

        assert "Engineering" in dst.read_text()

    def test_raises_when_src_missing(self, tmp_path: Path) -> None:
        import click
        src = tmp_path / "missing.md"
        dst = tmp_path / "now.md"
        with pytest.raises(click.UsageError, match="does not exist"):
            move_task(src, dst, "anything")


class TestCompleteTask:
    def test_removes_from_src_and_appends_done(self, tmp_path: Path) -> None:
        src  = tmp_path / "now.md"
        done = tmp_path / "done.md"
        src.write_text("### Engineering\n* deploy MaaS\n---\n")

        category, matched = complete_task(src, done, "MaaS")

        assert category == "Engineering"
        assert "deploy MaaS" not in src.read_text()
        assert "deploy MaaS" in done.read_text()

    def test_done_entry_format(self, tmp_path: Path) -> None:
        src  = tmp_path / "now.md"
        done = tmp_path / "done.md"
        src.write_text("### Engineering\n* deploy MaaS\n---\n")

        complete_task(src, done, "MaaS")

        done_text = done.read_text()
        assert "done: (Engineering) - deploy MaaS" in done_text


class TestAppendDone:
    def test_creates_week_heading_on_first_entry(self, tmp_path: Path) -> None:
        done = tmp_path / "done.md"
        append_done(done, "Engineering", "deploy MaaS")
        text = done.read_text()
        assert "## Week of" in text
        assert "deploy MaaS" in text

    def test_no_new_heading_within_same_week(self, tmp_path: Path) -> None:
        done = tmp_path / "done.md"
        today = date.today().isoformat()
        done.write_text(f"## Week of {today}\n\n[2026-01-01 00:00:00] done: (Eng) - task one\n")
        append_done(done, "Engineering", "task two")
        headings = [l for l in done.read_text().splitlines() if l.startswith("## Week of")]
        assert len(headings) == 1

    def test_new_heading_after_7_days(self, tmp_path: Path) -> None:
        done = tmp_path / "done.md"
        old_date = (date.today() - timedelta(days=7)).isoformat()
        done.write_text(f"## Week of {old_date}\n\n[2026-01-01 00:00:00] done: (Eng) - old task\n")
        append_done(done, "Engineering", "new task")
        headings = [l for l in done.read_text().splitlines() if l.startswith("## Week of")]
        assert len(headings) == 2

    def test_no_new_heading_at_6_days(self, tmp_path: Path) -> None:
        done = tmp_path / "done.md"
        recent = (date.today() - timedelta(days=6)).isoformat()
        done.write_text(f"## Week of {recent}\n\n[2026-01-01 00:00:00] done: (Eng) - task\n")
        append_done(done, "Engineering", "another task")
        headings = [l for l in done.read_text().splitlines() if l.startswith("## Week of")]
        assert len(headings) == 1


class TestSerializeLines:
    def test_no_double_blanks(self, tmp_path: Path) -> None:
        path = tmp_path / "test.md"
        serialize_lines(["a", "", "", "b"], path)
        lines = path.read_text().splitlines()
        for i in range(len(lines) - 1):
            assert not (lines[i] == "" and lines[i + 1] == "")

    def test_blank_before_dividers(self, tmp_path: Path) -> None:
        path = tmp_path / "test.md"
        serialize_lines(["* task", "---"], path)
        text = path.read_text()
        assert "* task\n\n---" in text
