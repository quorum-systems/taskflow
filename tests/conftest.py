"""
conftest.py — shared fixtures for all tests.

Most tests need a temp directory with a git repo and a .taskflow.yml.
The fixtures here keep that boilerplate out of individual test files.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def tmp_git_repo(tmp_path: Path) -> Path:
    """A temp directory with git initialized and a basic user config."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


@pytest.fixture
def basic_config_data() -> dict:
    """Minimal valid config data — enough for most tests."""
    return {
        "categories": [
            {"name": "Engineering", "icon": "🔵", "aliases": []},
            {"name": "Operations", "icon": "🔴", "aliases": ["Ops"]},
            {"name": "Product", "icon": "🟡", "aliases": []},
        ],
        "phases": [
            {"name": "Phase 1 — Foundation", "description": "Get started."},
            {"name": "Phase 2 — Build", "description": "Main work."},
        ],
        "settings": {
            "repo_name": "Test Project",
            "done_weeks": 2,
        },
    }


@pytest.fixture
def project_root(tmp_git_repo: Path, basic_config_data: dict) -> Path:
    """
    A full temp project: git repo + .taskflow.yml + basic backlog files.
    Use this when you need a working taskflow project to run commands against.
    """
    config_path = tmp_git_repo / ".taskflow.yml"
    with config_path.open("w") as f:
        yaml.dump(basic_config_data, f)

    # create minimal backlog structure
    backlog = tmp_git_repo / ".taskflow" / "backlog"
    backlog.mkdir(parents=True)

    for name, content in [
        ("0-now.md", "# Now\n\n---\n\n### 🔵 Engineering\n\n---\n"),
        ("1-blocked.md", "# Blocked\n\n---\n"),
        ("2-paused.md", "# Paused\n\n---\n"),
        ("3-next.md", "# Next\n\n---\n\n### 🔵 Engineering\n* write deployment docs\n* set up monitoring\n\n---\n\n### 🔴 Operations\n* configure alerting\n\n---\n"),
        ("4-later.md", "# Later\n\n---\n\n## Phase 1 — Foundation\n\n### 🔵 Engineering\n* evaluate caching layer\n\n---\n"),
        ("done.md", "# Done\n\nCompleted tasks.\n\n---\n"),
    ]:
        (backlog / name).write_text(content, encoding="utf-8")

    # initial commit so git operations work
    subprocess.run(["git", "add", "."], cwd=tmp_git_repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_git_repo, check=True, capture_output=True)

    return tmp_git_repo
