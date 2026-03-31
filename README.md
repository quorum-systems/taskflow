# taskflow

Git-native task management for people who are already in the terminal.

No database. No SaaS. No browser tab to context-switch into. Markdown files, a handful of Python scripts, and git commits that turn your task history into an execution log.

---

## Why this exists

Issue trackers are built for visibility into other people's work. When you're the one doing the work, they're mostly overhead — fields to fill in, statuses to update, ceremonies that exist to prove progress rather than make it.

My workaround was a graph paper notebook: hand-drawn checkboxes, running to-do lists, something I could capture a task in without clicking through three screens. It worked until it didn't — no state tracking, no history, no way to tell what was actually in progress versus just written down and forgotten.

taskflow is what I built instead. It took about 20 minutes to get the first version working. I've been using it on a real infrastructure build since, and it's earned everything I've added to it.

---

## The model

Every task lives in one of six files:

```
.taskflow/backlog/
  0-now.md       ▶  executing this week
  1-blocked.md   ⊘  waiting on something external
  2-paused.md    ⏸  deliberately on hold — not blocked, not forgotten
  3-next.md      ◈  queued for the next window
  4-later.md     ◇  longer-horizon work, organised by phase
  done.md        ✓  append-only completion log
```

Tasks move between files via `taskflow` commands or git aliases. Every move is a commit. Your git log becomes a timeline of what actually happened — not what you said was happening in a standup.

File paths are configurable. If you want your backlog somewhere else, set it in `.taskflow.yml` and `taskflow setup` creates it.

---

## Getting started

### 1. Install

```bash
pip install taskflow
```

Or to install from source:

```bash
git clone https://github.com/quorum-systems/taskflow.git
cd taskflow
pip install -e .
```

### 2. Initialize a project

```bash
cd myproject
taskflow init
```

This creates `.taskflow.yml` with starter configuration, sets up the backlog directory structure, and installs git aliases. If the directory isn't a git repo yet, taskflow will offer to initialize one.

To bootstrap from an existing taskflow configuration:

```bash
taskflow init --from https://github.com/yourorg/taskflow-config.git
```

### 3. Edit `.taskflow.yml`

Define your categories and phases. That's the only configuration you need to touch before you start.

```yaml
categories:
  - name: Backend
    icon: "🔵"
  - name: Frontend
    icon: "🟢"
  - name: DevOps
    icon: "🔴"
  - name: Product
    icon: "🟡"

phases:
  - name: "Phase 1 — MVP"
    description: "Core features needed to ship."
  - name: "Phase 2 — Scale"
    description: "Performance, reliability, and growth."
```

### 4. Run setup

```bash
taskflow setup
```

Generates your backlog file skeletons and installs the git aliases. Re-run whenever you change `.taskflow.yml`. Existing task content is never overwritten unless you pass `--force`.

---

## Daily usage

`taskflow` and the git aliases are identical. Use whichever is faster:

```bash
taskflow start "task"
git start "task"       # same thing
```

### Move a task into active work

```bash
taskflow promote "task"    # ◇ later  → ◈ next
taskflow start   "task"    # ◈ next   → ▶ now
```

### Handle blockers and holds

```bash
taskflow block   "task"    # ▶ now     → ⊘ blocked
taskflow unblock "task"    # ⊘ blocked → ▶ now

taskflow pause   "task"    # ▶ now     → ⏸ paused
taskflow unpause "task"    # ⏸ paused  → ▶ now

taskflow backlog "task"    # ▶ now     → ◈ next (put it back)
```

### Complete a task

```bash
taskflow done "task"
```

Removes the task from now, appends a timestamped entry to `done.md`, commits both.

### Add a task directly

```bash
taskflow add <state> <category> <task text>
```

Add a task to any state without opening a file. Useful for capturing work that's already in flight or already done.

```bash
taskflow add next DevOps "write deployment runbook"
taskflow add now Backend "hotfix: null pointer in auth"
taskflow add done Engineering "emergency patch deployed"   # no prior 'now' needed
```

Category matching is fuzzy and case-insensitive — `taskflow add next dev "..."` finds `DevOps`.

### List tasks

```bash
taskflow list          # defaults to now
taskflow list next
taskflow list blocked
```

### Fuzzy matching

You don't need to type the full task text for any command. All commands match by substring:

```bash
taskflow done "auth"
# works if exactly one task contains "auth"

taskflow done "add"
# → Multiple tasks match 'add' — be more specific:
#     line 4  [Backend]   add JWT auth middleware
#     line 11 [Frontend]  add login form validation
```

The commit message always uses the full matched task text, not your search string.

---

## Reporting and status

### Quick status

```bash
taskflow status
```

```
  taskflow status — Sat Mar 28
  ▶ now: 3   ⊘ blocked: 1   ⏸ paused: 0

  ▶  now
     🔵 Backend
       · add JWT auth middleware
       · write integration tests
     🔴 DevOps
       · configure CI pipeline

  ⊘  blocked
     🔵 Backend
       · integrate payment gateway
```

### This week's completions

```bash
taskflow week
```

```
  ✓  week of 2026-03-28 — 11 completed

  🔴 Infrastructure
    · deploy MaaS 3.7
    · commission first compute node
    · validate Ubuntu 24.04 deploys cleanly
  🟣 Engineering
    · validate network_switching role
    · write latency rotation script
```

### Pipeline — work in flight

```bash
taskflow pipeline
taskflow pipeline --json
```

```
  pipeline — work in flight and completed this week

+----------------+---------+--------+----------+-----------+-------+----------+
| Category       | ◇ Later | ◈ Next | ⏸ Paused | ⊘ Blocked | ▶ Now | ✓ Mar 28 |
+----------------+---------+--------+----------+-----------+-------+----------+
| 🔵 Backend      |       3 |      2 |        0 |         1 |     2 |        1 |
| 🔴 DevOps       |       1 |      2 |        0 |         0 |     1 |        1 |
| 🟢 Frontend     |       1 |      2 |        0 |         0 |     0 |        1 |
| 🟡 Product      |       0 |      0 |        1 |         0 |     0 |        0 |
+----------------+---------+--------+----------+-----------+-------+----------+
```

### Progress — completions over time

```bash
taskflow progress
taskflow progress --json
```

```
  progress — now vs. completed by week

+------------+-------+----------+----------+----------+----------+
| Category   | ▶ Now | ✓ Mar 28 | ✓ Mar 21 | ✓ Mar 14 | ✓ Mar  7 |
+------------+-------+----------+----------+----------+----------+
| 🔵 Backend  |     2 |        1 |        2 |        2 |        2 |
| 🔴 DevOps   |     1 |        1 |        1 |        1 |        2 |
| 🟢 Frontend |     0 |        1 |        1 |        1 |        1 |
+------------+-------+----------+----------+----------+----------+
```

That table wasn't written. It emerged from doing the work and running one command.

---

## Task format

Plain bullets under a category heading. No checkboxes.

```markdown
### 🔵 Backend
* add JWT auth middleware
* write integration tests for /api/users
  * happy path
  * 401 on missing token
  * 403 on insufficient scope

---
```

Subtasks indent two spaces and move with their parent. Nesting can go deeper — any level of indentation is preserved.

---

## How to structure your tasks

Each file has a different job. The structure you put in them should match.

### now — what you're actually doing this week

Keep it short. If it doesn't fit in a single focused session or sprint, it probably isn't `now` yet. A good `now` file has 3–7 tasks, not 20.

**Write tasks as concrete actions, not topics:**

```markdown
### 🔵 Backend
* add input validation to /api/users POST handler
* fix null pointer crash when auth token is missing
```

Not `"auth work"` or `"backend stuff"`. The task text becomes the commit message — it should read like a record of what happened.

**Use subtasks to capture known steps without splitting into separate tasks:**

```markdown
* deploy staging environment
  * provision EC2 instance
  * run Ansible playbook
  * verify health checks pass
```

The parent task stays in `now` until you're ready to call the whole thing done. Subtasks give you a checklist without polluting the top-level list.

---

### next — queued, not started

`next` is your input buffer. Tasks here are defined, prioritized, and ready to start — just not this window.

**Write tasks clearly enough that future-you knows what to do:**

```markdown
### 🔴 DevOps
* write Terraform module for RDS provisioning
* add CloudWatch alarm for CPU > 85%
```

**Don't write tasks that are still vague:**

```markdown
### 🔴 DevOps
* do something about monitoring         ← too vague
* think about database scaling          ← not an action
```

If you're not sure what the task actually is, put it in `later` and figure it out when it becomes relevant. `next` should contain executable work.

**Order matters within categories.** Tasks that come first in the file get started first. If you manually reorder lines in `next`, that's your priority signal.

---

### paused — on hold by choice

`paused` means you chose to set it aside — not because something is blocking you, but because priorities shifted. The task is still valid. It'll come back.

**Add a note to yourself when you pause a task** by editing the file directly after the move:

```markdown
### 🔵 Backend
* refactor auth middleware to support OAuth2
  * paused: deprioritized for MVP — revisit in Phase 2
```

This isn't enforced — it's just good practice. When something has been paused for two weeks and you've forgotten why, you'll want that note.

**Don't let paused grow into a junk drawer.** If something's been paused long enough that you genuinely don't know if you'll ever do it, move it back to `later` or delete it. `paused` is for work you intend to resume.

---

### blocked — waiting on something external

`blocked` means you can't make progress right now because something outside your control hasn't happened yet.

**Always note what's blocking the task.** Edit the file after moving it:

```markdown
### 🔴 DevOps
* configure production VPN
  * blocked: waiting on network team to provision the ASA firewall rules (ticket: NET-441)
```

This note is what makes `blocked` useful. Without it, you have a list of things you can't do and no idea what would unblock them.

**Check blocked regularly.** Blockers resolve and tasks sit there forgotten. During your weekly review, look at each blocked item and ask whether the blocker is still real.

---

### later — everything else

`later` is where work lives until it's ready to become `next`. It's organized by phase, which lets you plan across time horizons without mixing near-term and long-term work.

**Use phases to separate planning horizons:**

```markdown
## Phase 1 — MVP

### 🔵 Backend
* implement basic authentication
* add rate limiting to public endpoints

---

## Phase 2 — Scale

### 🔵 Backend
* migrate auth to OAuth2
* implement distributed session store
```

**Write tasks at whatever level of fidelity you have.** A task in Phase 2 might be a rough idea — that's fine. It'll sharpen when it becomes `next`.

**Use `later` as a capture zone.** When you think of something while doing something else, `taskflow add later Category "idea"` gets it out of your head and into the backlog without breaking your flow. You can sort and refine later.

**Phases have no mechanical effect.** Tasks can go under any phase regardless of configuration. The phase structure is for your benefit — it's a planning aid, not enforcement.

---

## Configuration

### Categories

Categories are arbitrary labels. There are no built-in ones — define whatever reflects how you actually think about your work:

| Type of project | Example categories |
|---|---|
| Software product | Backend, Frontend, DevOps, Product, Design |
| Consulting practice | Delivery, Business Development, Operations, Writing |
| Research project | Experiments, Writing, Data, Infrastructure |
| Personal | Work, Health, Finance, Home, Learning |

One category per task. Categories aren't load-bearing — rename or restructure them in `.taskflow.yml` and re-run `taskflow setup`. Existing task content is never touched.

#### Icons

Optional but useful — makes headings scannable in editors and file browsers. Coloured circles work well as a set:

```
🔴  🟠  🟡  🟢  🔵  🟣  ⚫  ⚪  🟤
```

**Finding emoji:** macOS `Ctrl+Cmd+Space`, Windows `Win+.`, Linux `Ctrl+Shift+U` + code point, or [emojipedia.org](https://emojipedia.org).

### Phases

Phases organise the later file into planning horizons. They have no effect on any other backlog file.

All categories appear under every phase by default. The `categories` field is an optional filter:

```yaml
phases:
  - name: "Phase 1 — Foundation"
    description: "Infrastructure only."
    categories: [DevOps]        # only DevOps headings pre-generated

  - name: "Phase 2 — Product"
    description: "Full build."
                                # no filter — all categories appear
```

No enforcement. Any task can go under any phase. The filter just controls which headings get pre-generated in the file skeleton.

### States

By default taskflow uses the standard file layout under `.taskflow/backlog/`. You can override any state's file path and icon:

```yaml
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
```

The entire `states` section is optional. Leave it out and the defaults above apply. Override only what you want to change — partial overrides work fine.

`taskflow setup` creates all state file paths recursively, so you can put them anywhere.

### Settings

```yaml
settings:
  repo_name: "myproject"
  done_weeks: 4                             # weeks to retain in done.md before archiving
  weekly_plan_dir: ".taskflow/changelog/weekly"
  archive_path: ".taskflow/backlog/archive"
```

`done_weeks` controls how many completed weeks stay visible in `done.md`. Older weeks are automatically moved to monthly archive files in `archive/` after every `taskflow done`.

---

## The git log

Every task transition commits with a structured message. The log reads like a journal:

```
promote: Post 17: Automating Network Config on Live Hardware
start: Post 17: Automating Network Config on Live Hardware
done: Post 17: Automating Network Config on Live Hardware
start: Post 25: Scope First, Quote Second
done: Post 25: Scope First, Quote Second
```

Diff from the start of the week to the end and you have a concrete record of what changed — not what you said was in progress. Feed that diff to a model and it's working from structured evidence, not trying to reconstruct your week from memory.

---

## Shell completion

```bash
taskflow completion bash >> ~/.bashrc
taskflow completion zsh  >> ~/.zshrc
taskflow completion fish >> ~/.config/fish/completions/taskflow.fish
```

---

## Repo structure

```
.taskflow.yml             the only file you need to edit
pyproject.toml            package metadata

src/taskflow/
  cli.py                  CLI commands and git integration
  tasklib.py              shared parsing and mutation library
  config.py               config loading and path resolution
  setup_cmd.py            init and setup logic
  reports.py              pipeline and progress report logic
  archive.py              done.md week archiving

.taskflow/                generated by taskflow setup
  backlog/
    0-now.md
    1-blocked.md
    2-paused.md
    3-next.md
    4-later.md
    done.md
    archive/              older completed weeks
  changelog/
    weekly/               weekly plan snapshots
```

---

## What this is not

taskflow does not have:

- Due dates or priority scores
- Integrations with anything
- A web UI, mobile app, or notifications
- Collaboration features
- Burndown charts or velocity tracking
- A project manager to manage your project manager

If you **need** those things, there are good tools that provide them. This is explicitly not trying to be those tools. The design point is minimum viable friction for a solo practitioner or small team that lives in the terminal and wants their task state in the same place as their code.

---

## Philosophy

The backlog exists to support execution, not document it.

`now` should be short. If something is blocking you, move it to `blocked` rather than leaving it to rot in the active list. If something isn't a priority this week, move it back to `next`. The files should reflect reality, not aspiration.

`done.md` is the raw material for a weekly changelog or retrospective. The git log is the long-term record. Nothing else is required.

---

## License

MIT
