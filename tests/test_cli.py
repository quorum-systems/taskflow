"""
test_cli.py — integration tests for the CLI commands.

Uses Click's CliRunner to invoke commands without spawning subprocesses.
These tests run against a real temp project directory so they catch
wiring bugs that unit tests miss.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from taskflow.cli import main


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def run_in_project(project_root: Path, runner: CliRunner):
    """Return a helper that invokes CLI commands with cwd set to the project root."""
    def invoke(*args, **kwargs):
        with runner.isolated_filesystem(temp_dir=project_root.parent):
            old_cwd = os.getcwd()
            try:
                os.chdir(project_root)
                return runner.invoke(main, args, catch_exceptions=False, **kwargs)
            finally:
                os.chdir(old_cwd)
    return invoke


class TestVersion:
    def test_version_flag(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.3.0" in result.output


class TestInit:
    def test_creates_config(self, runner: CliRunner, tmp_git_repo: Path) -> None:
        with runner.isolated_filesystem(temp_dir=tmp_git_repo.parent):
            os.chdir(tmp_git_repo)
            result = runner.invoke(main, ["init"], catch_exceptions=False)
            assert result.exit_code == 0
            assert (tmp_git_repo / ".taskflow.yml").exists()

    def test_creates_backlog_files(self, runner: CliRunner, tmp_git_repo: Path) -> None:
        with runner.isolated_filesystem(temp_dir=tmp_git_repo.parent):
            os.chdir(tmp_git_repo)
            runner.invoke(main, ["init"], catch_exceptions=False)
            assert (tmp_git_repo / ".taskflow" / "backlog" / "0-now.md").exists()
            assert (tmp_git_repo / ".taskflow" / "backlog" / "done.md").exists()

    def test_error_if_already_exists(self, runner: CliRunner, project_root: Path) -> None:
        os.chdir(project_root)
        result = runner.invoke(main, ["init"])
        assert result.exit_code != 0
        assert "already exists" in result.output


class TestSetup:
    def test_setup_runs(self, run_in_project) -> None:
        result = run_in_project("setup", "--force")
        assert result.exit_code == 0

    def test_setup_dry_run(self, run_in_project) -> None:
        result = run_in_project("setup", "--dry-run")
        assert result.exit_code == 0
        assert "dry-run" in result.output.lower() or "Done" in result.output


class TestShowConfig:
    def test_shows_state_files(self, run_in_project) -> None:
        result = run_in_project("config")
        assert result.exit_code == 0
        assert "now" in result.output
        assert "done" in result.output

    def test_shows_categories(self, run_in_project) -> None:
        result = run_in_project("config")
        assert "Engineering" in result.output


class TestStart:
    def test_moves_task_to_now(self, run_in_project, project_root: Path) -> None:
        result = run_in_project("start", "deployment docs")
        assert result.exit_code == 0
        assert "write deployment docs" in (project_root / ".taskflow/backlog/0-now.md").read_text()
        assert "write deployment docs" not in (project_root / ".taskflow/backlog/3-next.md").read_text()

    def test_commit_uses_full_task_text(self, run_in_project, project_root: Path) -> None:
        import subprocess
        run_in_project("start", "deployment")
        log = subprocess.check_output(
            ["git", "log", "--oneline", "-1"],
            cwd=project_root, text=True
        )
        assert "write deployment docs" in log


class TestDone:
    def test_removes_from_now_and_appends_done(self, run_in_project, project_root: Path) -> None:
        # first move something to now
        run_in_project("start", "deployment docs")
        # then mark it done
        result = run_in_project("done", "deployment")
        assert result.exit_code == 0
        assert "write deployment docs" not in (project_root / ".taskflow/backlog/0-now.md").read_text()
        assert "write deployment docs" in (project_root / ".taskflow/backlog/done.md").read_text()


class TestBlock:
    def test_moves_to_blocked(self, run_in_project, project_root: Path) -> None:
        run_in_project("start", "deployment docs")
        result = run_in_project("block", "deployment")
        assert result.exit_code == 0
        assert "write deployment docs" in (project_root / ".taskflow/backlog/1-blocked.md").read_text()
        assert "write deployment docs" not in (project_root / ".taskflow/backlog/0-now.md").read_text()


class TestUnblock:
    def test_moves_back_to_now(self, run_in_project, project_root: Path) -> None:
        run_in_project("start", "deployment docs")
        run_in_project("block", "deployment")
        result = run_in_project("unblock", "deployment")
        assert result.exit_code == 0
        assert "write deployment docs" in (project_root / ".taskflow/backlog/0-now.md").read_text()


class TestAdd:
    def test_adds_to_next(self, run_in_project, project_root: Path) -> None:
        result = run_in_project("add", "next", "Eng", "evaluate caching")
        assert result.exit_code == 0
        assert "evaluate caching" in (project_root / ".taskflow/backlog/3-next.md").read_text()

    def test_fuzzy_category(self, run_in_project, project_root: Path) -> None:
        result = run_in_project("add", "next", "ops", "update firewall rules")
        assert result.exit_code == 0
        assert "update firewall rules" in (project_root / ".taskflow/backlog/3-next.md").read_text()

    def test_add_done_directly(self, run_in_project, project_root: Path) -> None:
        result = run_in_project("add", "done", "Eng", "emergency hotfix deployed")
        assert result.exit_code == 0
        assert "emergency hotfix deployed" in (project_root / ".taskflow/backlog/done.md").read_text()

    def test_unknown_state_errors(self, run_in_project) -> None:
        result = run_in_project("add", "banana", "Eng", "some task")
        assert result.exit_code != 0


class TestList:
    def test_list_now_default(self, run_in_project) -> None:
        result = run_in_project("list")
        assert result.exit_code == 0
        assert "now" in result.output

    def test_list_next_shows_tasks(self, run_in_project) -> None:
        result = run_in_project("list", "next")
        assert result.exit_code == 0
        assert "write deployment docs" in result.output
        assert "Engineering" in result.output

    def test_list_empty_state(self, run_in_project) -> None:
        result = run_in_project("list", "blocked")
        assert result.exit_code == 0
        assert "empty" in result.output

    def test_no_match_error_includes_hint(self, run_in_project) -> None:
        result = run_in_project("start", "this does not exist")
        assert result.exit_code != 0
        assert "taskflow list" in result.output
    def test_shows_now_tasks(self, run_in_project, project_root: Path) -> None:
        run_in_project("start", "deployment docs")
        result = run_in_project("status")
        assert result.exit_code == 0
        assert "write deployment docs" in result.output

    def test_shows_counts(self, run_in_project) -> None:
        result = run_in_project("status")
        assert result.exit_code == 0
        assert "now:" in result.output


class TestWeek:
    def test_empty_week(self, run_in_project) -> None:
        result = run_in_project("week")
        assert result.exit_code == 0
        assert "no week headings" in result.output or "nothing completed" in result.output or "week of" in result.output

    def test_shows_completions(self, run_in_project, project_root: Path) -> None:
        run_in_project("start", "deployment docs")
        run_in_project("done", "deployment")
        result = run_in_project("week")
        assert result.exit_code == 0
        assert "write deployment docs" in result.output


class TestPipeline:
    def test_shows_table(self, run_in_project) -> None:
        result = run_in_project("pipeline")
        assert result.exit_code == 0
        assert "Engineering" in result.output

    def test_json_output(self, run_in_project) -> None:
        import json as _json
        result = run_in_project("pipeline", "--json")
        assert result.exit_code == 0
        data = _json.loads(result.output)
        assert data["report"] == "pipeline"


class TestProgress:
    def test_shows_table(self, run_in_project) -> None:
        result = run_in_project("progress")
        assert result.exit_code == 0
        assert "Engineering" in result.output

    def test_json_output(self, run_in_project) -> None:
        import json as _json
        result = run_in_project("progress", "--json")
        assert result.exit_code == 0
        data = _json.loads(result.output)
        assert data["report"] == "progress"