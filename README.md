# taskflow

Git-native task management for people who are already in the terminal.

No database. No SaaS. No browser tab to context-switch into. Markdown files, a handful of Python scripts, and git aliases that turn your commit history into an execution log.

---

## Why this exists

Issue trackers are built for visibility into other people's work. When you're the one doing the work, they're mostly overhead — fields to fill in, statuses to update, ceremonies that exist to prove progress rather than make it.

I already knew this. My workaround was a graph paper notebook: hand-drawn checkboxes, running to-do lists, something I could capture a task in without clicking through three screens. It worked until it didn't — no state tracking, no history, no way to tell what was actually in progress versus just written down and forgotten.

taskflow is what I built instead. It took about 20 minutes to get the first version working. I've been using it on a real infrastructure build since, and it's earned everything I've added to it.

---

## The model

Every task lives in one of six files:

```
backlog/
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

**1. Clone and install the one dependency**

```bash
git clone https://github.com/quorum-systems/taskflow.git myproject
cd myproject
pip install pyyaml
```

pyyaml is only needed for `taskflow setup`. The task scripts are pure stdlib — once setup has run, you can uninstall it.

**2. Edit `.taskflow.yml`**

Define your categories and phases. That's the only configuration you need to touch. Everything else has sensible defaults.

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

**3. Run setup**

```bash
./taskflow setup
```

Generates your backlog file skeletons, installs the git aliases, and configures the weekly plan script. Re-run whenever you change `.taskflow.yml`.

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

Subtasks indent two spaces and move with their parent.

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

By default taskflow uses the standard file layout. You can override any state's file path and icon:

```yaml
states:
  now:
    file: "backlog/0-now.md"
    icon: "▶"
  blocked:
    file: "backlog/1-blocked.md"
    icon: "⊘"
  paused:
    file: "backlog/2-paused.md"
    icon: "⏸"
  next:
    file: "backlog/3-next.md"
    icon: "◈"
  later:
    file: "backlog/4-later.md"
    icon: "◇"
  done:
    file: "backlog/done.md"
    icon: "✓"
```

The entire `states` section is optional. Leave it out and the defaults above apply. Override only what you want to change — partial overrides work fine.

`taskflow setup` creates all state file paths recursively, so you can put them anywhere.

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

## Weekly plan

Generate a full snapshot of active work, grouped by category:

```bash
scripts/git/week-plan               # writes changelog/weekly/YYYY-MM-DD.md
scripts/git/week-plan --stdout      # prints to terminal
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

## Repo structure

```
.taskflow.yml             the only file you need to edit
taskflow                  CLI — setup, workflow, reporting
requirements.txt          pyyaml (setup only — not needed at runtime)

scripts/
  git-aliases.sh          installs git aliases (run by taskflow setup)
  git/
    tasklib.py            shared parsing and mutation library
    task-move             moves a task between backlog files
    task-done             marks a task complete, appends to done.md
    week-plan             generates weekly execution plan markdown
    reports.py            pipeline and progress report logic

backlog/                  generated by taskflow setup, filled in by you
  0-now.md
  1-blocked.md
  2-paused.md
  3-next.md
  4-later.md
  done.md

changelog/
  weekly/                 weekly plan output
```

---

## Philosophy

The backlog exists to support execution, not document it.

`now` should be short. If something is blocking you, move it to `blocked` rather than leaving it to rot in the active list. If something isn't a priority this week, move it back to `next`. The files should reflect reality, not aspiration.

`done.md` is the raw material for a weekly changelog or retrospective. The git log is the long-term record. Nothing else is required.

---

## License

MIT