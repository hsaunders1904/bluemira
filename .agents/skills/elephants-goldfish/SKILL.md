---
name: elephants-goldfish
description: High-level architectural planning, stakeholder grilling, and atomic PR decomposition following the Elephants & Goldfish methodology.
---

# Elephant & Goldfish Planning & Execution Skill

Use this skill when tackling any non-trivial development request, refactor, or multi-step feature.

## Core Rules

1. **Elephant Mode First**:
   - Understand repository-wide architecture, existing data structures, and invariants before proposing changes.
   - Propose an explicit architecture and roadmap.
   - **Grill the user**: Ask targeted, probing questions regarding public API surface, design assumptions, trade-offs, and edge cases. Do not assume or skip questioning.

2. **Decompose into Atomic PRs**:
   - Break approved plans into tasks where **each task corresponds to exactly one Pull Request**.
   - Keep PR diffs small (< 300–400 lines).
   - Ensure every PR leaves the repository in a green state (all tests pass, linting and formatting pass).
   - Use stacked branches when tasks build sequentially on one another.

3. **Goldfish Mode in Git Worktrees**:
   - Always work inside `.worktrees/<branch-name>`.
   - Never develop directly on main/develop when operating as a task worker.
   - Keep focused solely on the single PR chunk.

4. **Repository Standards Enforcement**:
   - Enforce Python 3.11+ type annotations and NumPy/Google docstring formats.
   - Run tests using the `bluemira` conda/pixi environment:
     ```bash
     conda run -n bluemira pytest
     # or pixi run pytest
     ```
   - Run linter & formatter:
     ```bash
     conda run -n bluemira ruff check .
     conda run -n bluemira ruff format --check .
     ```
