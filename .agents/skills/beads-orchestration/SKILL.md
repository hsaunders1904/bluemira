---
name: beads-orchestration
description: Guidelines and CLI workflows for orchestrating multi-agent tasks using beads (bd).
---

# Beads (`bd`) Task Orchestration Skill

All task tracking, dependency modeling, and agent handoffs must use [Beads](https://github.com/gastownhall/beads) (`bd`).

## Why Beads?
- Avoids lost context across long agent sessions by persisting tasks in a distributed, git-aware graph.
- Prevents collision of task IDs across parallel worktrees and agents.
- Enforces clear dependency edges (`blocks`, `parent-child`) so agents only pick up unblocked work (`bd ready`).

## Core CLI Workflows

### 1. Initialize Beads
```bash
bd init
```
This sets up `.beads/` tracking in the repository root.

### 2. Elephant Mode: Creating Epic & PR Tasks
When the Elephant finishes user alignment and decomposes the plan into PR slices:
```bash
# Create the parent epic
bd create "Epic: Implement Feature X" -t epic

# Create atomic PR tasks (child tasks)
bd create "PR 1: Core interface and data types" --parent <epic-id>
bd create "PR 2: Algorithm implementation" --parent <epic-id>
bd create "PR 3: Diagnostic tools & integration" --parent <epic-id>

# Set strict dependency chains (stacked PRs)
bd dep add <pr-2-id> <pr-1-id>  # PR 2 depends on PR 1
bd dep add <pr-3-id> <pr-2-id>  # PR 3 depends on PR 2
```

### 3. Goldfish Mode: Worker Task Execution
In an isolated worker container or worktree:
```bash
# Check what work is unblocked and ready to start
bd ready

# Claim the task
bd update <task-id> --claim --status in_progress

# Inspect details and context
bd show <task-id>
bd prime

# ... Worker creates worktree, writes code, adds tests, runs ruff & pytest ...

# Close the task upon opening the PR
bd close <task-id> --reason "PR opened at <branch/url>"
```
