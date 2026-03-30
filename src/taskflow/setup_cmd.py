"""
setup_cmd.py — taskflow init and setup.

init creates .taskflow.yml in the current directory.
setup regenerates backlog file skeletons and installs git aliases.

The week-plan patching logic that existed in the old standalone script
version is gone — reports.py reads directly from config now.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import click
import yaml

from taskflow.config import CONFIG_FILE, TaskflowConfig

# starter config written by taskflow init
STARTER_CONFIG = """\
# .taskflow.yml
# Run `taskflow setup` after editing to regenerate your backlog.
# All sections except categories and phases are optional.

# ---------------------------------------------------------------------------
# States — file paths and terminal icons for each task state.
# Paths are relative to this file unless absolute.
# Remove this section entirely to use the defaults shown here.
# ---------------------------------------------------------------------------

states:
  now:
    file: ".taskflow/backlog/0-now.md"
    icon: "▶"
  blocked:
    file: ".taskflow/backlog/1-blocked.md"
    icon: "⊘"
  paused:
    file: ".taskflow/backlog/2-paused.md"
    icon: "⏸"
  next:
    file: ".taskflow/backlog/3-next.md"
    icon: "◈"
  later:
    file: ".taskflow/backlog/4-later.md"
    icon: "◇"
  done:
    file: ".taskflow/backlog/done.md"
    icon: "✓"

# ---------------------------------------------------------------------------
# Categories — define whatever makes sense for your project.
# Icons are optional. Colored circles work well: 🔴 🟠 🟡 🟢 🔵 🟣 ⚫ ⚪ 🟤
# ---------------------------------------------------------------------------

categories:
  - name: Engineering
    icon: "🔵"
    aliases: []

  - name: Operations
    icon: "🔴"
    aliases: []

  - name: Product
    icon: "🟡"
    aliases: []

  - name: Business
    icon: "⚫"
    aliases: []

# ---------------------------------------------------------------------------
# Phases — organise the later file into planning horizons.
# No effect on any other backlog file.
# ---------------------------------------------------------------------------

phases:
  - name: "Phase 1 — Foundation"
    description: "Core work needed to get started."

  - name: "Phase 2 — Build"
    description: "Main execution phase."

  - name: "Phase 3 — Growth"
    description: "Expansion and refinement."

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

settings:
  repo_name: "{repo_name}"
  done_weeks: 4
  weekly_plan_dir: ".taskflow/changelog/weekly"
  # archive_path defaults to .taskflow/backlog/archive/ — uncomment to override
  # archive_path: ".taskflow/backlog/archive"
"""

SIMPLE_STATE_TITLES = {
    "now":     ("Now",     "Tasks actively being executed this week."),
    "blocked": ("Blocked", "Tasks waiting on something external.\n\nNote what's blocking each one."),
    "paused":  ("Paused",  "Tasks deliberately on hold.\n\nNot blocked, not forgotten — just not now."),
    "next":    ("Next",    "Planned work queued for the next execution window."),
}


def _category_heading(cat: dict) -> str:
    icon = cat.get("icon", "")
    name = cat["name"]
    return f"### {icon} {name}".strip() if icon else f"### {name}"


def _build_simple_file(title: str, description: str, categories: list[dict]) -> str:
    lines = [f"# {title}", "", description.strip(), ""]
    for cat in categories:
        lines += ["---", "", _category_heading(cat), ""]
    lines.append("---")
    return "\n".join(lines) + "\n"


def _build_later_file(categories: list[dict], phases: list[dict]) -> str:
    cat_by_name = {c["name"]: c for c in categories}
    lines = [
        "# Later", "",
        "Longer-horizon work organised by phase.", "",
        "Promote to next when the time is right:", "",
        "```", 'taskflow promote "task text"', "```", "",
    ]
    for phase in phases:
        lines += ["---", "", f"## {phase['name']}"]
        if phase.get("description"):
            lines += ["", f"> {phase['description']}"]
        lines.append("")
        phase_cats = phase.get("categories") or [c["name"] for c in categories]
        for name in phase_cats:
            cat = cat_by_name.get(name)
            if cat:
                lines += [_category_heading(cat), ""]
    lines.append("---")
    return "\n".join(lines) + "\n"


def install_git_aliases(root: Path) -> None:
    """
    Install git aliases that just call `taskflow <subcommand>`.
    Once taskflow is on PATH the aliases are trivial — no path resolution needed.
    Skips silently if not in a git repo — init handles that case.
    """
    # check we're actually in a git repo before attempting
    try:
        subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=str(root), check=True, capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return

    transitions = [
        ("promote", "promote"),
        ("start",   "start"),
        ("block",   "block"),
        ("unblock", "unblock"),
        ("pause",   "pause"),
        ("unpause", "unpause"),
        ("backlog", "backlog"),
        ("done",    "done"),
    ]

    try:
        for alias, subcmd in transitions:
            subprocess.run(
                ["git", "config", f"alias.{alias}", f"!taskflow {subcmd}"],
                cwd=str(root), check=True, capture_output=True,
            )
        click.echo("  git aliases installed")
    except subprocess.CalledProcessError as e:
        click.echo(f"  warning: could not install git aliases: {e}", err=True)
    except FileNotFoundError:
        click.echo("  warning: git not found — skipping alias installation", err=True)


def run_setup(config: TaskflowConfig, force: bool = False, dry_run: bool = False) -> None:
    """
    Regenerate backlog file skeletons from config.
    Skips existing files unless force=True. Respects dry_run.
    """
    categories = config.categories
    phases     = config.phases
    root       = config.root

    click.echo(f"\ntaskflow setup — {config.repo_name}")
    click.echo(f"  {len(categories)} categories, {len(phases)} phases\n")

    changed = []
    skipped = []

    for state_name, (title, description) in SIMPLE_STATE_TITLES.items():
        path = config.state_path(state_name)
        content = _build_simple_file(title, description, categories)
        if not dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not force:
            skipped.append(str(path.relative_to(root)))
        else:
            if not dry_run:
                path.write_text(content, encoding="utf-8")
            changed.append(str(path.relative_to(root)))

    later_path    = config.state_path("later")
    later_content = _build_later_file(categories, phases)
    if not dry_run:
        later_path.parent.mkdir(parents=True, exist_ok=True)
    if later_path.exists() and not force:
        skipped.append(str(later_path.relative_to(root)))
    else:
        if not dry_run:
            later_path.write_text(later_content, encoding="utf-8")
        changed.append(str(later_path.relative_to(root)))

    done_path = config.state_path("done")
    if not dry_run:
        done_path.parent.mkdir(parents=True, exist_ok=True)
    if not done_path.exists():
        if not dry_run:
            done_path.write_text(
                "# Done\n\nCompleted tasks, appended by `taskflow done`.\n\n---\n",
                encoding="utf-8",
            )
        changed.append(str(done_path.relative_to(root)))

    weekly_dir = config.weekly_plan_dir
    if not weekly_dir.exists():
        if not dry_run:
            weekly_dir.mkdir(parents=True, exist_ok=True)
            (weekly_dir / ".gitkeep").touch()
        changed.append(str(weekly_dir.relative_to(root)) + "/")

    archive_dir = config.archive_path
    if not archive_dir.exists() and not dry_run:
        archive_dir.mkdir(parents=True, exist_ok=True)

    if not dry_run:
        install_git_aliases(root)

    if changed:
        click.echo("  created/updated:")
        for f in changed:
            click.echo(f"    + {f}")
    if skipped:
        click.echo("  skipped (already exist — use --force to overwrite):")
        for f in skipped:
            click.echo(f"    ~ {f}")

    click.echo(f"\n  Done. Edit {CONFIG_FILE} and re-run `taskflow setup` to regenerate.\n")