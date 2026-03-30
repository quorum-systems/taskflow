"""
test_config.py — tests for root discovery and config loading.

Root discovery is the foundation of everything. If it breaks, nothing works.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from taskflow.config import TaskflowConfig, find_root


class TestFindRoot:
    def test_finds_config_in_cwd(self, tmp_path: Path) -> None:
        (tmp_path / ".taskflow.yml").write_text("categories: []", encoding="utf-8")
        assert find_root(tmp_path) == tmp_path

    def test_finds_config_in_parent(self, tmp_path: Path) -> None:
        (tmp_path / ".taskflow.yml").write_text("categories: []", encoding="utf-8")
        child = tmp_path / "sub" / "dir"
        child.mkdir(parents=True)
        assert find_root(child) == tmp_path

    def test_returns_none_when_not_found(self, tmp_path: Path) -> None:
        # tmp_path has no .taskflow.yml
        assert find_root(tmp_path) is None

    def test_stops_at_filesystem_root(self, tmp_path: Path) -> None:
        # should not loop forever or raise
        result = find_root(tmp_path)
        assert result is None or isinstance(result, Path)


class TestTaskflowConfig:
    @pytest.fixture
    def cfg(self, tmp_path: Path, basic_config_data: dict) -> TaskflowConfig:
        return TaskflowConfig(tmp_path, basic_config_data)

    def test_state_path_relative(self, cfg: TaskflowConfig, tmp_path: Path) -> None:
        assert cfg.state_path("now") == tmp_path / "backlog" / "0-now.md"

    def test_state_path_absolute_override(self, tmp_path: Path, basic_config_data: dict) -> None:
        basic_config_data["states"] = {"now": {"file": "/absolute/path/now.md"}}
        cfg = TaskflowConfig(tmp_path, basic_config_data)
        assert cfg.state_path("now") == Path("/absolute/path/now.md")

    def test_state_icon_default(self, cfg: TaskflowConfig) -> None:
        assert cfg.state_icon("now") == "▶"

    def test_state_icon_override(self, tmp_path: Path, basic_config_data: dict) -> None:
        basic_config_data["states"] = {"now": {"icon": "★"}}
        cfg = TaskflowConfig(tmp_path, basic_config_data)
        assert cfg.state_icon("now") == "★"

    def test_state_defaults_when_section_missing(self, tmp_path: Path) -> None:
        cfg = TaskflowConfig(tmp_path, {})
        assert "backlog/0-now.md" in str(cfg.state_path("now"))
        assert cfg.state_icon("now") == "▶"

    def test_category_names(self, cfg: TaskflowConfig) -> None:
        assert cfg.category_names() == ["Engineering", "Operations", "Product"]

    def test_category_icon(self, cfg: TaskflowConfig) -> None:
        assert cfg.category_icon("Engineering") == "🔵"

    def test_category_icon_case_insensitive(self, cfg: TaskflowConfig) -> None:
        assert cfg.category_icon("engineering") == "🔵"

    def test_category_icon_missing(self, cfg: TaskflowConfig) -> None:
        assert cfg.category_icon("Nonexistent") == ""

    def test_fuzzy_category_exact(self, cfg: TaskflowConfig) -> None:
        assert cfg.fuzzy_category("Engineering") == "Engineering"

    def test_fuzzy_category_substring(self, cfg: TaskflowConfig) -> None:
        assert cfg.fuzzy_category("Eng") == "Engineering"

    def test_fuzzy_category_case_insensitive(self, cfg: TaskflowConfig) -> None:
        assert cfg.fuzzy_category("eng") == "Engineering"

    def test_fuzzy_category_alias(self, cfg: TaskflowConfig) -> None:
        assert cfg.fuzzy_category("Ops") == "Operations"

    def test_fuzzy_category_ambiguous_returns_none(self, cfg: TaskflowConfig) -> None:
        # "o" matches both Operations and Product... actually just Operations
        # use something that matches multiple
        assert cfg.fuzzy_category("o") is None  # Operations, Product both contain 'o'... wait
        # let's use a query that definitely hits two
        assert cfg.fuzzy_category("e") is None  # Engineering, Operations both have 'e'

    def test_fuzzy_category_no_match_returns_none(self, cfg: TaskflowConfig) -> None:
        assert cfg.fuzzy_category("zzzzz") is None

    def test_done_weeks_default(self, tmp_path: Path) -> None:
        cfg = TaskflowConfig(tmp_path, {})
        assert cfg.done_weeks == 4

    def test_done_weeks_from_config(self, cfg: TaskflowConfig) -> None:
        assert cfg.done_weeks == 2

    def test_archive_path_default(self, cfg: TaskflowConfig, tmp_path: Path) -> None:
        # default should be next to done.md in backlog/archive/
        assert cfg.archive_path == tmp_path / "backlog" / "archive"

    def test_archive_path_override(self, tmp_path: Path, basic_config_data: dict) -> None:
        basic_config_data["settings"]["archive_path"] = "custom/archive"
        cfg = TaskflowConfig(tmp_path, basic_config_data)
        assert cfg.archive_path == tmp_path / "custom" / "archive"
