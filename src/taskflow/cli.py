"""
cli.py — taskflow command line interface.

All commands live here. Business logic lives in the other modules —
this is just wiring. Each command loads config, does one thing, exits.
"""

from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path
from typing import Optional

import click

from taskflow import __version__
from taskflow.archive import archive_old_weeks
from taskflow.config import WORKFLOW_TRANSITIONS, TaskflowConfig, load_config
from taskflow.reports import report_pipeline, report_progress
from taskflow.setup_cmd import STARTER_CONFIG, run_setup
from taskflow.tasklib import _ACTIVE_STATES, CATEGORY_RE, DIVIDER_RE, PHASE_RE, append_done, check_for_duplicate, collapse_blank_lines, complete_task, move_task

# ---------------------------------------------------------------------------
# Shell completion
# ---------------------------------------------------------------------------


def install_completion(shell: str) -> None:
    """
    Print the shell completion script for the given shell.
    User adds it to their shell profile — we don't write to their system.
    """
    import os

    os.environ["_TASKFLOW_COMPLETE"] = f"{shell}_source"
    try:
        from taskflow.cli import main

        main(standalone_mode=False)
    except SystemExit:
        pass


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def git_root_or_none() -> Optional[Path]:
    try:
        root = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        return Path(root)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def git_commit(files: list[str], message: str, cwd: Path) -> None:
    """Stage and commit specific files. Fails loudly if git isn't available."""
    try:
        subprocess.run(["git", "add"] + files, cwd=str(cwd), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", message], cwd=str(cwd), check=True)
    except subprocess.CalledProcessError as e:
        raise click.ClickException(f"git commit failed: {e}")
    except FileNotFoundError:
        raise click.ClickException("git not found — task was moved but not committed")


def _commit_transition(cfg: TaskflowConfig, src: str, dst: str, verb: str, task_text: str) -> None:
    """Stage the two state files and commit with the standard message format."""
    src_rel = str(cfg.state_path(src).relative_to(cfg.root))
    dst_rel = str(cfg.state_path(dst).relative_to(cfg.root))
    git_commit([src_rel, dst_rel], f"{verb}: {task_text}", cfg.root)


def _commit_done(cfg: TaskflowConfig, task_text: str) -> None:
    now_rel = str(cfg.state_path("now").relative_to(cfg.root))
    done_rel = str(cfg.state_path("done").relative_to(cfg.root))
    git_commit([now_rel, done_rel], f"done: {task_text}", cfg.root)


# ---------------------------------------------------------------------------
# Root command group
# ---------------------------------------------------------------------------


@click.group()
@click.version_option(version=__version__, prog_name="taskflow")
def main() -> None:
    """
    Git-native task management for people who live in the terminal.

    taskflow walks up from your current directory to find .taskflow.yml —
    that directory is the project root. All file paths in the config are
    relative to that root.

    Run `taskflow init` to set up a new project.
    Run `taskflow setup` to regenerate backlog files after editing the config.
    """
    pass


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


@main.command()
@click.option("--from", "from_url", default=None, metavar="URL", help="Fetch starter config from a URL instead of using the built-in template.")
@click.option("--name", default=None, help="Project name (defaults to current directory name).")
def init(from_url: Optional[str], name: Optional[str]) -> None:
    """Set up a new taskflow project in the current directory."""
    cwd = Path.cwd()
    config_path = cwd / ".taskflow.yml"

    if config_path.exists():
        raise click.ClickException(".taskflow.yml already exists. Run `taskflow setup` to regenerate backlog files.")

    repo_name = name or cwd.name

    if from_url:
        import urllib.request

        click.echo(f"  fetching config from {from_url}...")
        try:
            with urllib.request.urlopen(from_url) as resp:
                content = resp.read().decode("utf-8")
        except Exception as e:
            raise click.ClickException(f"Could not fetch config from {from_url}: {e}")
        # substitute repo name if the template has the placeholder
        content = content.replace("{repo_name}", repo_name)
    else:
        content = STARTER_CONFIG.replace("{repo_name}", repo_name)

    config_path.write_text(content, encoding="utf-8")
    click.echo(f"  created {config_path.name}")

    # initialize git if we're not already in a repo — taskflow without git
    # is half the point, so just handle it
    git_root = None
    try:
        result = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(cwd),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        git_root = Path(result)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    if git_root is None:
        try:
            subprocess.run(["git", "init"], cwd=str(cwd), check=True, capture_output=True)
            click.echo("  git init")
        except (subprocess.CalledProcessError, FileNotFoundError):
            click.echo("  note: git not found — skipping git init and alias installation", err=True)

    # load and run setup immediately
    cfg = load_config(cwd)
    run_setup(cfg, force=False, dry_run=False)


# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------


@main.command()
@click.option("--force", is_flag=True, help="Overwrite existing backlog files.")
@click.option("--dry-run", is_flag=True, help="Show what would happen without writing.")
def setup(force: bool, dry_run: bool) -> None:
    """Regenerate backlog files and install git aliases from .taskflow.yml."""
    cfg = load_config()
    run_setup(cfg, force=force, dry_run=dry_run)


# ---------------------------------------------------------------------------
# config (diagnostic)
# ---------------------------------------------------------------------------


@main.command("config")
def show_config() -> None:
    """Show resolved configuration — useful when paths aren't where you expect."""
    cfg = load_config()
    click.echo(f"\n  project root : {cfg.root}")
    click.echo(f"  config file  : {cfg.root / '.taskflow.yml'}")
    click.echo(f"  repo name    : {cfg.repo_name}")
    click.echo(f"  done weeks   : {cfg.done_weeks}")
    click.echo(f"  archive path : {cfg.archive_path}")
    click.echo(f"  weekly plans : {cfg.weekly_plan_dir}")
    click.echo("\n  state files:")
    for state in ("now", "blocked", "paused", "next", "later", "done"):
        path = cfg.state_path(state)
        icon = cfg.state_icon(state)
        exists = "✓" if path.exists() else "✗"
        click.echo(f"    {exists} {icon} {state:8}  {path.relative_to(cfg.root)}")
    click.echo("\n  categories:")
    for cat in cfg.categories:
        icon = cat.get("icon", " ")
        click.echo(f"    {icon} {cat['name']}")
    click.echo()


# ---------------------------------------------------------------------------
# Workflow commands — one for each transition
# ---------------------------------------------------------------------------


def _workflow_command(verb: str, src: str, dst: str):
    """
    Factory that produces a Click command for a task transition.
    All transitions follow the same pattern: find task in src, move to dst, commit.
    """

    @click.argument("task", nargs=-1, required=True)
    def cmd(task: tuple) -> None:
        query = " ".join(task)
        cfg = load_config()

        src_path = cfg.state_path(src)
        dst_path = cfg.state_path(dst)
        dst_path.parent.mkdir(parents=True, exist_ok=True)

        category, matched = move_task(src_path, dst_path, query)
        click.echo(f"Moved: [{category}] {matched}")
        click.echo(f"  {src_path.name} → {dst_path.name}")

        # archive check happens on every done write, but also on promote/start
        # in case the done file accumulated weeks from a previous session
        _maybe_archive(cfg)

        _commit_transition(cfg, src, dst, verb, matched)

    cmd.__name__ = verb
    cmd.__doc__ = f"Move a task: {src} → {dst}."
    return cmd


# register all transitions as commands
for _verb, (_src, _dst, _prefix) in WORKFLOW_TRANSITIONS.items():
    main.command(_verb)(_workflow_command(_prefix, _src, _dst))


# ---------------------------------------------------------------------------
# done
# ---------------------------------------------------------------------------


@main.command()
@click.argument("task", nargs=-1, required=True)
def done(task: tuple) -> None:
    """Complete a task: remove from now, append to done.md, commit."""
    query = " ".join(task)
    cfg = load_config()

    category, matched = complete_task(cfg.state_path("now"), cfg.state_path("done"), query)
    click.echo(f"Done: [{category}] {matched}")

    _maybe_archive(cfg)
    _commit_done(cfg, matched)


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------


@main.command()
@click.argument("state")
@click.argument("category")
@click.argument("task", nargs=-1, required=True)
def add(state: str, category: str, task: tuple) -> None:
    """
    Add a task directly to any state without opening a file.

    \b
    taskflow add next Engineering "write deployment runbook"
    taskflow add now Backend "hotfix: null ptr in auth"
    taskflow add done Engineering "emergency patch deployed"

    Category is fuzzy-matched. State 'done' writes a timestamped entry directly.
    """

    query = " ".join(task)
    cfg = load_config()

    # resolve state — fuzzy match the state name too
    valid = list(["now", "blocked", "paused", "next", "later", "done"])
    if state not in valid:
        matches = [s for s in valid if state.lower() in s.lower()]
        if len(matches) == 1:
            state = matches[0]
        else:
            raise click.UsageError(f"Unknown state '{state}'. Valid: {', '.join(valid)}")

    # resolve category
    if state == "done":
        # for done we still want a category for the log entry
        cat_name = cfg.fuzzy_category(category)
        if not cat_name:
            # not in config — use as-is, don't block the user
            cat_name = category
        append_done(cfg.state_path("done"), cat_name, query)
        click.echo(f"Added to done: ({cat_name}) - {query}")
        _maybe_archive(cfg)
        done_rel = str(cfg.state_path("done").relative_to(cfg.root))
        git_commit([done_rel], f"done: {query}", cfg.root)
        return

    cat_name = cfg.fuzzy_category(category)
    if not cat_name:
        cats = cfg.category_names()
        q = category.strip().lower()
        matches = [c for c in cats if q in c.lower()]
        if len(matches) > 1:
            raise click.UsageError(f"'{category}' matches multiple categories: {', '.join(matches)}")
        raise click.UsageError(f"No category matching '{category}'")

    # find the icon for the category heading
    icon = cfg.category_icon(cat_name)
    cat_raw = f"{icon} {cat_name}".strip() if icon else cat_name

    # reject if the task already exists in any active backlog file
    check_for_duplicate(query, {s: cfg.state_path(s) for s in _ACTIVE_STATES})

    target = cfg.state_path(state)
    target.parent.mkdir(parents=True, exist_ok=True)

    lines = target.read_text(encoding="utf-8").splitlines() if target.exists() else []

    # find the category section and insert before its divider

    insert_at = None
    for i, line in enumerate(lines):
        if PHASE_RE.match(line):
            continue
        m = CATEGORY_RE.match(line)
        if m and m.group(1).strip().lower() == cat_name.lower():
            j = i + 1
            while j < len(lines):
                if DIVIDER_RE.match(lines[j]) or CATEGORY_RE.match(lines[j]) or PHASE_RE.match(lines[j]):
                    break
                j += 1
            # backtrack past trailing blanks
            while j > i + 1 and lines[j - 1].strip() == "":
                j -= 1
            insert_at = j
            break

    if insert_at is not None:
        lines.insert(insert_at, f"* {query}")
    else:
        # category doesn't exist — append a new section
        if lines and lines[-1].strip() != "":
            lines.append("")
        lines.append(f"### {cat_raw}")
        lines.append(f"* {query}")
        lines.append("")
        lines.append("---")

    target.write_text("\n".join(collapse_blank_lines(lines)).rstrip() + "\n", encoding="utf-8")
    click.echo(f"Added to {state} [{cat_name}]: {query}")

    target_rel = str(target.relative_to(cfg.root))
    git_commit([target_rel], f"add ({state}): {query}", cfg.root)


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@main.command("list")
@click.argument("state", default="now", type=click.Choice(["now", "next", "later", "blocked", "paused"]))
def list_tasks(state: str) -> None:
    """
    List tasks in a state. Defaults to 'now'.

    \b
    taskflow list           # tasks in now
    taskflow list next      # tasks queued up
    taskflow list blocked   # what's stuck
    """

    from taskflow.tasklib import TASK_RE

    cfg = load_config()
    path = cfg.state_path(state)
    icon = cfg.state_icon(state)

    if not path.exists():
        click.echo(f"\n  {icon} {state}  (empty)\n")
        return

    lines = path.read_text(encoding="utf-8").splitlines()
    current = None
    printed = set()  # track which categories we've printed headings for
    any_task = False

    click.echo(f"\n  {icon} {state}\n")
    for line in lines:
        if PHASE_RE.match(line):
            phase = line.lstrip("#").strip()
            click.echo(f"  ── {phase}")
            continue
        m = CATEGORY_RE.match(line)
        if m:
            current = m.group(1).strip()  # canonical name (emoji stripped)
            continue
        t = TASK_RE.match(line)
        if t:
            if current and current not in printed and not line.startswith("  "):
                cat_icon = cfg.category_icon(current)
                label = f"{cat_icon} {current}".strip() if cat_icon else current
                click.echo(f"  {label}")
                printed.add(current)
            indent = "      " if line.startswith("  ") else "    "
            click.echo(f"{indent}· {t.group(3)}")
            if not line.startswith("  "):
                any_task = True

    if not any_task:
        click.echo("    (empty)")
    click.echo()


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


@main.command()
def status() -> None:
    """Active tasks, blockers, and holds — the morning view."""
    import re as _re

    from taskflow.tasklib import TASK_RE

    cfg = load_config()

    def read_tasks(state_name: str) -> dict[str, list[str]]:
        path = cfg.state_path(state_name)
        if not path.exists():
            return {}
        tasks: dict[str, list[str]] = {}
        current_cat = None
        for line in path.read_text(encoding="utf-8").splitlines():
            if _re.match(r"^##[^#]", line):
                continue
            m = CATEGORY_RE.match(line)
            if m:
                current_cat = m.group(1).strip()
                continue
            t = TASK_RE.match(line)
            if t and not line.startswith("  ") and current_cat:
                tasks.setdefault(current_cat, []).append(t.group(3))
        return tasks

    now_tasks = read_tasks("now")
    blocked_tasks = read_tasks("blocked")
    paused_tasks = read_tasks("paused")

    total_now = sum(len(v) for v in now_tasks.values())
    total_blocked = sum(len(v) for v in blocked_tasks.values())
    total_paused = sum(len(v) for v in paused_tasks.values())

    def fmt_cat(name: str) -> str:
        icon = cfg.category_icon(name)
        return f"{icon} {name}".strip() if icon else name

    def print_section(label: str, icon: str, tasks: dict[str, list[str]]) -> None:
        if not tasks:
            return
        click.echo(f"\n  {icon}  {label}")
        for cat, items in tasks.items():
            click.echo(f"     {fmt_cat(cat)}")
            for item in items:
                click.echo(f"       · {item}")

    today = date.today().strftime("%a %b %-d")
    ni = cfg.state_icon("now")
    bi = cfg.state_icon("blocked")
    pi = cfg.state_icon("paused")

    click.echo(f"\n  taskflow status — {today}")
    click.echo(f"  {ni} now: {total_now}   {bi} blocked: {total_blocked}   {pi} paused: {total_paused}")

    print_section("now", ni, now_tasks)
    print_section("blocked", bi, blocked_tasks)
    print_section("paused", pi, paused_tasks)
    click.echo()


# ---------------------------------------------------------------------------
# week
# ---------------------------------------------------------------------------


@main.command()
def week() -> None:
    """This week's completions from done.md."""
    import re as _re

    cfg = load_config()
    done_path = cfg.state_path("done")

    if not done_path.exists():
        click.echo("\n  no done.md found.\n")
        return

    from taskflow.tasklib import WEEK_HEADING_RE

    DONE_RE = _re.compile(r"^\[[\d\s:\-]+\]\s+done:\s+\(([^)]+)\)\s+-\s+(.+)$")

    lines = done_path.read_text(encoding="utf-8").splitlines()

    # find the last week heading, collect everything after it
    last_week_idx = None
    week_date_str = None
    for i, line in enumerate(lines):
        m = WEEK_HEADING_RE.match(line)
        if m:
            last_week_idx = i
            week_date_str = m.group(1)

    if last_week_idx is None:
        click.echo("\n  no week headings in done.md yet.\n")
        return

    entries: dict[str, list[str]] = {}
    for line in lines[last_week_idx + 1 :]:
        d = DONE_RE.match(line)
        if d:
            cat, task_text = d.group(1).strip(), d.group(2).strip()
            entries.setdefault(cat, []).append(task_text)

    if not entries:
        click.echo("\n  nothing completed this week yet.\n")
        return

    total = sum(len(v) for v in entries.values())
    icon = cfg.state_icon("done")

    def fmt_cat(name: str) -> str:
        ci = cfg.category_icon(name)
        return f"{ci} {name}".strip() if ci else name

    click.echo(f"\n  {icon}  week of {week_date_str} — {total} completed\n")
    for cat, tasks in entries.items():
        click.echo(f"  {fmt_cat(cat)}")
        for t in tasks:
            click.echo(f"    · {t}")
    click.echo()


# ---------------------------------------------------------------------------
# pipeline / progress
# ---------------------------------------------------------------------------


@main.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def pipeline(as_json: bool) -> None:
    """Work in flight across all states plus this week's completions."""
    cfg = load_config()
    click.echo(report_pipeline(cfg, as_json=as_json))


@main.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def progress(as_json: bool) -> None:
    """Now vs. completed counts across up to 5 historical weeks."""
    cfg = load_config()
    click.echo(report_progress(cfg, as_json=as_json))


# ---------------------------------------------------------------------------
# completion
# ---------------------------------------------------------------------------


@main.command()
@click.argument("shell", type=click.Choice(["bash", "zsh", "fish"]))
def completion(shell: str) -> None:
    """
    Print the shell completion script for the given shell.

    \b
    Add to your shell profile:
      bash: eval "$(taskflow completion bash)"
      zsh:  eval "$(taskflow completion zsh)"
      fish: taskflow completion fish | source
    """
    import os

    env_var = f"_{main.name.upper().replace('-', '_')}_COMPLETE"
    os.environ[env_var] = f"{shell}_source"
    try:
        main(standalone_mode=False)
    except SystemExit:
        pass


# ---------------------------------------------------------------------------
# Archive helper — called after any done write
# ---------------------------------------------------------------------------


def _maybe_archive(cfg: TaskflowConfig) -> None:
    """
    Check done.md week count and archive old weeks if needed.
    Silent on success — only surfaces output if weeks were actually archived.
    """
    archived = archive_old_weeks(
        done_path=cfg.state_path("done"),
        archive_dir=cfg.archive_path,
        keep_weeks=cfg.done_weeks,
    )
    if archived:
        click.echo(f"  archived {archived} week(s) to {cfg.archive_path.relative_to(cfg.root)}/")
