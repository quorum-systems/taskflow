"""
config.py — project root discovery and .taskflow.yml loading.

Everything resolves relative to wherever .taskflow.yml lives. Walk up
from cwd until we find it, or fail clearly. This is the only place that
knows about the config structure — everything else asks this module.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml

CONFIG_FILE = ".taskflow.yml"

# defaults used when states section is missing or partially specified
STATE_DEFAULTS: dict[str, dict] = {
    "now": {"file": ".taskflow/backlog/0-now.md", "icon": "▶"},
    "blocked": {"file": ".taskflow/backlog/1-blocked.md", "icon": "⊘"},
    "paused": {"file": ".taskflow/backlog/2-paused.md", "icon": "⏸"},
    "next": {"file": ".taskflow/backlog/3-next.md", "icon": "◈"},
    "later": {"file": ".taskflow/backlog/4-later.md", "icon": "◇"},
    "done": {"file": ".taskflow/backlog/done.md", "icon": "✓"},
}

# the order transitions are defined matters for help text and validation
WORKFLOW_TRANSITIONS: dict[str, tuple[str, str, str]] = {
    "promote": ("later", "next", "promote"),
    "start": ("next", "now", "start"),
    "block": ("now", "blocked", "block"),
    "unblock": ("blocked", "now", "unblock"),
    "pause": ("now", "paused", "pause"),
    "unpause": ("paused", "now", "unpause"),
    "backlog": ("now", "next", "backlog"),
}


class TaskflowConfig:
    """
    Loaded config for a taskflow project. All path resolution goes through here
    so nothing else has to think about absolute vs relative.
    """

    def __init__(self, root: Path, data: dict) -> None:
        self.root = root
        self._data = data

    # --- state resolution ---

    def state(self, name: str) -> dict:
        """Return merged config for a state — user values over defaults."""
        user = self._data.get("states", {}).get(name, {})
        default = STATE_DEFAULTS.get(name, {})
        return {
            "file": user.get("file") or default.get("file", f"backlog/{name}.md"),
            "icon": user.get("icon") or default.get("icon", ""),
        }

    def state_path(self, name: str) -> Path:
        """Absolute path for a state file."""
        f = self.state(name)["file"]
        p = Path(f)
        # absolute path in config wins; relative resolves from root
        return p if p.is_absolute() else self.root / p

    def state_icon(self, name: str) -> str:
        return self.state(name).get("icon", "")

    # --- categories ---

    @property
    def categories(self) -> list[dict]:
        return self._data.get("categories", [])

    def category_names(self) -> list[str]:
        return [c["name"] for c in self.categories]

    def category_icon(self, name: str) -> str:
        for cat in self.categories:
            if cat["name"].lower() == name.lower():
                return cat.get("icon", "")
        return ""

    def fuzzy_category(self, query: str) -> Optional[str]:
        """
        Case-insensitive substring match against category names and aliases.
        Returns the canonical name if exactly one match, None otherwise.
        Callers are responsible for surfacing ambiguity errors to the user.
        """
        q = query.strip().lower()
        matches = [c["name"] for c in self.categories if q in c["name"].lower()]
        if len(matches) == 1:
            return matches[0]
        # check aliases too — useful when migrating old category names
        if not matches:
            for cat in self.categories:
                for alias in cat.get("aliases", []):
                    if q in alias.lower():
                        matches.append(cat["name"])
        return matches[0] if len(matches) == 1 else None

    def category_aliases(self) -> dict[str, str]:
        """Flat alias → canonical name mapping for week-plan and reports."""
        out: dict[str, str] = {}
        for cat in self.categories:
            name = cat["name"]
            out[name] = name
            for alias in cat.get("aliases", []):
                out[alias] = name
        return out

    # --- phases ---

    @property
    def phases(self) -> list[dict]:
        return self._data.get("phases", [])

    # --- settings ---

    @property
    def repo_name(self) -> str:
        return self._data.get("settings", {}).get("repo_name", "taskflow")

    @property
    def weekly_plan_dir(self) -> Path:
        d = self._data.get("settings", {}).get("weekly_plan_dir", ".taskflow/changelog/weekly")
        p = Path(d)
        return p if p.is_absolute() else self.root / p

    @property
    def done_weeks(self) -> int:
        """How many weeks to keep in done.md before archiving older ones."""
        return int(self._data.get("settings", {}).get("done_weeks", 4))

    @property
    def archive_path(self) -> Path:
        """Where archived week files live. Defaults inside .taskflow/backlog/archive/."""
        default_archive = ".taskflow/backlog/archive"
        d = self._data.get("settings", {}).get("archive_path", default_archive)
        p = Path(d)
        return p if p.is_absolute() else self.root / p

    # --- raw access for anything not covered above ---

    def get(self, key: str, default=None):
        return self._data.get(key, default)


def find_root(start: Optional[Path] = None) -> Optional[Path]:
    """
    Walk up from start (default cwd) looking for .taskflow.yml.
    Returns the directory containing it, or None if not found.
    """
    current = Path(start or os.getcwd()).resolve()
    while True:
        if (current / CONFIG_FILE).exists():
            return current
        parent = current.parent
        if parent == current:
            # hit filesystem root
            return None
        current = parent


def load_config(root: Optional[Path] = None) -> TaskflowConfig:
    """
    Load config from root, or discover root from cwd if not given.
    Raises click.UsageError if no config found — callers get a clean error.
    """
    import click

    if root is None:
        root = find_root()
    if root is None:
        raise click.UsageError("No .taskflow.yml found. Run `taskflow init` to set up a project.")

    config_path = root / CONFIG_FILE
    try:
        with config_path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        raise click.UsageError(f"Could not read {config_path}: {e}")

    return TaskflowConfig(root, data)


def load_config_or_none(root: Optional[Path] = None) -> Optional[TaskflowConfig]:
    """Same as load_config but returns None instead of raising."""
    try:
        return load_config(root)
    except Exception:
        return None
