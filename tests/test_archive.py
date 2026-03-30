"""
test_archive.py — tests for done.md week archiving.

Archiving is the most stateful behavior in the system — it reads done.md,
decides which weeks to move, writes archive files, and rewrites done.md.
Getting the boundaries wrong silently loses history.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from taskflow.archive import archive_month_path, archive_old_weeks, parse_week_blocks


SAMPLE_DONE = """\
# Done

## Week of 2026-01-10

[2026-01-10 09:00:00] done: (Engineering) - task alpha
[2026-01-11 10:00:00] done: (Operations) - task beta

## Week of 2026-01-17

[2026-01-17 09:00:00] done: (Engineering) - task gamma

## Week of 2026-01-24

[2026-01-24 09:00:00] done: (Engineering) - task delta

## Week of 2026-01-31

[2026-01-31 09:00:00] done: (Engineering) - task epsilon
"""


class TestParseWeekBlocks:
    def test_parses_blocks(self) -> None:
        lines = SAMPLE_DONE.splitlines()
        blocks = parse_week_blocks(lines)
        assert len(blocks) == 4
        assert blocks[0]["date"] == "2026-01-10"
        assert blocks[-1]["date"] == "2026-01-31"

    def test_block_contains_entries(self) -> None:
        lines = SAMPLE_DONE.splitlines()
        blocks = parse_week_blocks(lines)
        assert any("task alpha" in l for l in blocks[0]["lines"])

    def test_empty_file_returns_empty(self) -> None:
        assert parse_week_blocks([]) == []


class TestArchiveMonthPath:
    def test_correct_path(self, tmp_path: Path) -> None:
        path = archive_month_path(tmp_path, "2026-01-15")
        assert path == tmp_path / "2026-01-archive.md"

    def test_month_boundary(self, tmp_path: Path) -> None:
        # week starting Jan 28 goes into January archive, not February
        path = archive_month_path(tmp_path, "2026-01-28")
        assert path.name == "2026-01-archive.md"


class TestArchiveOldWeeks:
    def test_no_archive_when_under_limit(self, tmp_path: Path) -> None:
        done = tmp_path / "done.md"
        done.write_text(SAMPLE_DONE)
        archive_dir = tmp_path / "archive"

        # 4 weeks in file, keep_weeks=4 → nothing archived
        archived = archive_old_weeks(done, archive_dir, keep_weeks=4)
        assert archived == 0
        assert not archive_dir.exists()

    def test_archives_when_over_limit(self, tmp_path: Path) -> None:
        done = tmp_path / "done.md"
        done.write_text(SAMPLE_DONE)
        archive_dir = tmp_path / "archive"

        # 4 weeks in file, keep 2 → archive 2
        archived = archive_old_weeks(done, archive_dir, keep_weeks=2)
        assert archived == 2

    def test_keeps_correct_weeks_in_done(self, tmp_path: Path) -> None:
        done = tmp_path / "done.md"
        done.write_text(SAMPLE_DONE)
        archive_dir = tmp_path / "archive"

        archive_old_weeks(done, archive_dir, keep_weeks=2)

        done_text = done.read_text()
        # older weeks should be gone
        assert "2026-01-10" not in done_text
        assert "2026-01-17" not in done_text
        # recent weeks should remain
        assert "2026-01-24" in done_text
        assert "2026-01-31" in done_text

    def test_archived_weeks_in_monthly_file(self, tmp_path: Path) -> None:
        done = tmp_path / "done.md"
        done.write_text(SAMPLE_DONE)
        archive_dir = tmp_path / "archive"

        archive_old_weeks(done, archive_dir, keep_weeks=2)

        archive_file = archive_dir / "2026-01-archive.md"
        assert archive_file.exists()
        archive_text = archive_file.read_text()
        assert "task alpha" in archive_text
        assert "task gamma" in archive_text

    def test_archived_weeks_oldest_first(self, tmp_path: Path) -> None:
        done = tmp_path / "done.md"
        done.write_text(SAMPLE_DONE)
        archive_dir = tmp_path / "archive"

        archive_old_weeks(done, archive_dir, keep_weeks=2)

        archive_text = (archive_dir / "2026-01-archive.md").read_text()
        pos_alpha = archive_text.index("task alpha")
        pos_gamma = archive_text.index("task gamma")
        # alpha (Jan 10) should appear before gamma (Jan 17)
        assert pos_alpha < pos_gamma

    def test_appends_to_existing_archive_file(self, tmp_path: Path) -> None:
        done = tmp_path / "done.md"
        done.write_text(SAMPLE_DONE)
        archive_dir = tmp_path / "archive"
        archive_dir.mkdir()

        # pre-existing archive file
        existing = archive_dir / "2026-01-archive.md"
        existing.write_text("# Archive — 2026-01\n\n## Week of 2026-01-03\n\n[2026-01-03 00:00:00] done: (Eng) - earlier task\n")

        archive_old_weeks(done, archive_dir, keep_weeks=2)

        archive_text = existing.read_text()
        assert "earlier task" in archive_text
        assert "task alpha" in archive_text

    def test_preamble_preserved_in_done(self, tmp_path: Path) -> None:
        done = tmp_path / "done.md"
        done.write_text(SAMPLE_DONE)
        archive_dir = tmp_path / "archive"

        archive_old_weeks(done, archive_dir, keep_weeks=2)

        # preamble lines before first week heading should still be there
        assert "# Done" in done.read_text()

    def test_no_done_file_returns_zero(self, tmp_path: Path) -> None:
        done = tmp_path / "nonexistent.md"
        archive_dir = tmp_path / "archive"
        assert archive_old_weeks(done, archive_dir, keep_weeks=4) == 0
