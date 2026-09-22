---
name: git-worktrees
description: Guidelines and commands for managing isolated agent workspaces using git worktrees under .worktrees/.
---

# Git Worktrees Management Skill

All agent development activities in this repository must take place inside isolated git worktrees created under `.worktrees/`.

## Why Worktrees?
- Protects the parent repository state from uncommitted diffs or broken intermediate states.
- Enables clean concurrent tasks and cleanly managed stacked PR branches.
- Isolates branch checkout while sharing the git history and local environment.

## Worktree Lifecycle

### 1. Worktree Directory Convention
All worktrees must be located at:
```
.worktrees/<branch-name>
```

### 2. Creating a Worktree
```bash
# Branching from develop
git fetch origin develop
git worktree add -b feature/<task-name> .worktrees/feature-<task-name> origin/develop

# Creating a stacked branch (e.g., part-2 stacked on top of part-1)
git worktree add -b feature/<task-name>-part-2 .worktrees/feature-<task-name>-part-2 feature/<task-name>-part-1
```

### 3. Working inside the Worktree
Always change directory to the worktree root before modifying files or running test tools:
```bash
cd .worktrees/feature-<task-name>

# Execute tests and linters using the environment:
conda run -n bluemira pytest tests/<affected_tests>
conda run -n bluemira ruff check .
conda run -n bluemira ruff format --check .
# or if pixi is used:
# pixi run pytest tests/<affected_tests>
```

### 4. Committing and Pushing
```bash
git add <modified_files>
git commit -m "feat(<subsystem>): <descriptive message>"
git push -u origin <branch-name>
```

### 5. Cleaning up Worktrees
Once a branch has been merged into upstream/develop:
```bash
git worktree remove .worktrees/<worktree-folder>
git branch -d <branch-name>
```
