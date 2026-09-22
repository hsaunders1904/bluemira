# AGENTS.md — "Elephants & Goldfish" Agent Architecture Guide

This document defines how autonomous and interactive agents operate in this repository.
It implements the **"Elephants & Goldfish"** methodology combined with:
- **Git Worktrees** under `.worktrees/` for zero workspace contamination.
- **Podman Containers** for hermetic, isolated worker execution environments.
- **[Beads](https://github.com/gastownhall/beads) (`bd`)** for persistent, graph-based task tracking and agent orchestration.

---

## 1. Core Philosophy: Elephants & Goldfish

- **The Elephant (Strategic Memory & System Architecture)**:
  - Global perspective: understands repository-wide architecture, existing interfaces, long-term roadmap, conventions, and invariants.
  - Formulates the global strategy, challenges ambiguity, creates the task breakdown, and tracks progress.
  - Interacts with the user: **actively grills the user** for feedback and alignment before any code is generated.
  - Registers the task hierarchy in **Beads (`bd`)** with explicit dependency edges.
- **The Goldfish (Tactical Focus & Reviewable Increments)**:
  - Hyper-focused on executing a **single atomic task** (equivalent to exactly one Pull Request).
  - Operates inside an **isolated Podman container** and dedicated **git worktree** (`.worktrees/<branch-name>`).
  - Claims unblocked tasks via `bd ready`, implements the slice cleanly, writes tests, verifies quality gates (`pytest`, `ruff`), and submits a PR.
  - Avoids context bloat or drift because each task diff is strictly small (< 300–400 lines).

---

## 2. The 4-Phase Agent Protocol

Every non-trivial agent workflow follows these four sequential phases:

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Phase 1: Plan  │ ──> │ Phase 2: Grill   │ ──> │ Phase 3: Slice  │ ──> │ Phase 4: Execute│
│  & Research     │     │ & Align          │     │ (PRs + Beads)   │     │ (Podman Worker) │
└─────────────────┘     └──────────────────┘     └─────────────────┘     └─────────────────┘
```

### Phase 1: Planning & Research (Elephant)
1. **Analyze Existing Context**:
   - Inspect existing architecture, interfaces, and patterns in the codebase before inventing new abstractions.
   - Look up relevant modules, tests, types, and documentation (`CONTRIBUTING.md`, `pyproject.toml`).
2. **Draft High-Level Architecture**:
   - Summarize the problem statement.
   - Propose design choices, module boundaries, data structures, and trade-offs.

### Phase 2: Grill the User for Feedback (Elephant)
**Do not skip this step.** Autonomous agents that assume user intent create massive, unmergeable rewrites.
- Actively probe and challenge edge cases, architectural trade-offs, and design assumptions.
- Ask specific, structured questions:
  - *Interface design*: Public API method signatures, parameter names, backwards compatibility.
  - *Data boundaries*: Conventions (e.g. COCOS, units, coordinate systems).
  - *Dependencies*: Adding new libraries vs reusing existing utilities (`numba`, `scipy`, `numpy`).
  - *Verification expectations*: Specific benchmark data or mocking strategies.
- Incorporate user feedback into the architectural document until explicit sign-off is achieved.

### Phase 3: Slice into Atomic PR-Sized Tasks & Register in Beads (Elephant)
Decompose the agreed plan into small, well-defined increments.
- **Strict Rule**: Each task must correspond to **exactly one Pull Request**.
- **Reviewability Budget**: Diff size target is **100–300 lines**, strictly capped at **< 400 lines** (excluding generated data or test fixtures).
- **Self-Contained Quality**: Every single PR must leave the repository in a **working, passing state** (green test suite, formatting and linting pass, zero broken imports).
- **Stacked Branches**: When tasks depend on preceding steps, explicitly document the stack hierarchy:
  - Example: `feature/part-1-types` -> `feature/part-2-core` -> `feature/part-3-cli`.
- **Register in Beads**:
  ```bash
  bd create "Epic: Feature Title" -t epic
  bd create "PR 1: Interfaces and Data Types" --parent <epic-id>
  bd create "PR 2: Core Solver Implementation" --parent <epic-id>
  bd dep add <pr-2-id> <pr-1-id>  # PR 2 blocked by PR 1
  ```

### Phase 4: Tactical Execution Loop (Goldfish in Podman)
For **each** individual unblocked task:
1. **Claim the Task**:
   ```bash
   bd ready
   bd update <task-id> --claim --status in_progress
   ```
2. **Provision Git Worktree**:
   Create a dedicated worktree under `.worktrees/<branch-name>`:
   ```bash
   git worktree add -b feature/<task-name> .worktrees/feature-<task-name> develop
   ```
3. **Launch Isolated Worker Container**:
   Run the task worker inside a hermetic Podman container:
   ```bash
   WORKTREE_DIR=.worktrees/feature-<task-name> podman compose -f docker/compose.worker.yml run --rm worker
   ```
4. **Implement Focused Diff**:
   Implement only what is required for the specific task. Avoid scope creep.
5. **Strict Verification**:
   - Run tests: `conda run -n bluemira pytest <affected_tests>` (or `pytest` inside the container).
   - Run linter & formatter: `conda run -n bluemira ruff check <affected_paths>` and `ruff format --check`.
6. **Commit and Close Task**:
   - Commit with conventional commit message.
   - Close in beads: `bd close <task-id> --reason "PR opened at branch/url"`.

---

## 3. Beads (`bd`) Task Orchestration Standards

- **Task Graph as Truth**: In-progress agent states and dependencies are tracked through Beads rather than ephemeral agent memory.
- **Unblocked Querying**: Workers query `bd ready` to discover tasks whose blockers are resolved.
- **Context Injection**: Use `bd prime` to load task context and persistent constraints into agent sessions.
- **Dependency Chains**: Use `bd dep add <child> <parent>` to enforce stacked PR ordering.

---

## 4. Podman Isolation & Git Worktree Workflow

All agent workers run inside Podman containers to guarantee repeatable, isolated environments.

### Files
- **Containerfile**: `docker/Containerfile.worker` (packaged with python, micromamba/conda, beads `bd`, ruff, git, and compilation toolchains).
- **Compose**: `docker/compose.worker.yml`.

### Worktree Directory Rules
1. Worktrees live strictly under `.worktrees/`:
   ```bash
   mkdir -p .worktrees
   ```
2. **Branching off develop**:
   ```bash
   git worktree add -b feature/<task-name> .worktrees/feature-<task-name> origin/develop
   ```
3. **Stacked branching**:
   ```bash
   git worktree add -b feature/<task-name>-part-2 .worktrees/feature-<task-name>-part-2 feature/<task-name>-part-1
   ```
4. **Running Podman worker against a worktree**:
   ```bash
   WORKTREE_DIR=.worktrees/feature-<task-name> podman compose -f docker/compose.worker.yml run --rm worker
   ```
5. **Cleaning up worktrees**:
   ```bash
   git worktree remove .worktrees/feature-<task-name>
   git branch -d feature/<task-name>
   ```

---

## 5. Repository Coding Practices & Quality Gates

Every chunk must adhere to Bluemira engineering standards:

### 5.1. Code Architecture & Style
- **Object-Oriented Design**:
  - Represent physical and mathematical entities with clean classes.
  - Initialize all instance attributes in `__init__`.
  - Prefix protected/internal methods with an underscore (e.g. `_protected_method`).
  - Use `__slots__` where performance/memory dictates.
- **Typing & Signatures**:
  - Keep functions single-purpose with minimal arguments.
  - Provide full type annotations on all signatures (`int | str | None`, `npt.NDArray[np.float64]`).
  - NumPy / Google style docstrings with `Parameters` and `Returns` sections.
- **Performance**:
  - Prefer vectorised NumPy operations over raw Python loops.
  - Bottlenecks should leverage `@nb.njit` / `numba` where existing patterns in the codebase use them.

### 5.2. Testing Standards
- Every PR adding or modifying features **must include unit tests**.
- Put tests in `tests/<module_path>/test_<module>.py`.
- Tests must execute deterministically and fast (< a few seconds unless marked `@pytest.mark.longrun`).
- Maintain regression guarantees: never disable existing tests without explicit justification and user approval.
- Run:
  ```bash
  conda run -n bluemira pytest tests/<subsystem>/
  ```

### 5.3. Formatting & Linting
- Strictly follow `ruff`:
  ```bash
  conda run -n bluemira ruff check <modified_paths>
  conda run -n bluemira ruff format --check <modified_paths>
  ```
- Line length: 89 characters (configured in `pyproject.toml`).
- Target Python version: 3.11+.

---

## 6. Review-Ready Task Template

When presenting the task roadmap in Phase 3, the Elephant agent must use this template:

```markdown
### PR 1: [Short Title]
- **Beads ID**: `bd-xxxx`
- **Branch**: `feature/<name>-part-1` (branched from `develop`)
- **Worktree**: `.worktrees/feature-<name>-part-1`
- **Scope**:
  - Add base classes / types / dataclass definitions
  - No behavioral change to existing solvers
- **Estimated Diff**: ~120 lines
- **Quality Gates**:
  - [ ] `pytest tests/<module>/test_types.py` passes
  - [ ] `ruff check` and `ruff format` clean
- **Dependencies**: None

### PR 2: [Short Title]
- **Beads ID**: `bd-yyyy` (blocks on `bd-xxxx`)
- **Branch**: `feature/<name>-part-2` (stacked on `feature/<name>-part-1`)
- **Worktree**: `.worktrees/feature-<name>-part-2`
- **Scope**:
  - Implementation of core logic / algorithm
- **Estimated Diff**: ~200 lines
- **Quality Gates**:
  - [ ] Unit tests covering edge cases
  - [ ] Regression suite passes
- **Dependencies**: PR 1 (`bd-xxxx`)
```

---

## 7. Checklist for Agents Before Concluding a Task

- [ ] Task claimed and updated in Beads (`bd`).
- [ ] Task matches the scope of a single pull request.
- [ ] Work was developed and validated inside `.worktrees/<branch>` using Podman worker container.
- [ ] All new logic is backed by pytest tests.
- [ ] No regression in the broader module test suite.
- [ ] `ruff check` passes with 0 errors.
- [ ] `ruff format` confirms formatting compliance.
- [ ] Git diff has been reviewed to ensure zero accidental edits or leftover debug artifacts.
- [ ] Task closed in Beads (`bd close <task-id>`) upon opening PR.

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:46cd31e7 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/core-concepts/sync-concepts.md for details and anti-patterns.

## Agent Context Profiles

The managed Beads block is task-tracking guidance, not permission to override repository, user, or orchestrator instructions.

- **Conservative (default)**: Use `bd` for task tracking. Do not run git commits, git pushes, or Dolt remote sync unless explicitly asked. At handoff, report changed files, validation, and suggested next commands.
- **Minimal**: Keep tool instruction files as pointers to `bd prime`; use the same conservative git policy unless active instructions say otherwise.
- **Team-maintainer**: Only when the repository explicitly opts in, agents may close beads, run quality gates, commit, and push as part of session close. A current "do not commit" or "do not push" instruction still wins.

## Session Completion

This protocol applies when ending a Beads implementation workflow. It is subordinate to explicit user, repository, and orchestrator instructions.

1. **File issues for remaining work** - Create beads for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **Handle git/sync by active profile**:
   ```bash
   # Conservative/minimal/default: report status and proposed commands; wait for approval.
   git status

   # Team-maintainer opt-in only, unless current instructions forbid it:
   git pull --rebase
   bd dolt push
   git push
   git status
   ```
5. **Hand off** - Summarize changes, validation, issue status, and any blocked sync/commit/push step

**Critical rules:**
- Explicit user or orchestrator instructions override this Beads block.
- Do not commit or push without clear authority from the active profile or the current user request.
- If a required sync or push is blocked, stop and report the exact command and error.
<!-- END BEADS INTEGRATION -->

<!-- BEGIN BEADS CODEX SETUP: generated by bd setup codex -->
## Beads Issue Tracker

Use Beads (`bd`) for durable task tracking in repositories that include it. Use the `beads` skill at `.agents/skills/beads/SKILL.md` (project install) or `~/.agents/skills/beads/SKILL.md` (global install) for Beads workflow guidance, then use the `bd` CLI for issue operations.

### Quick Reference

```bash
bd ready                # Find available work
bd show <id>            # View issue details
bd update <id> --claim  # Claim work
bd close <id>           # Complete work
bd prime                # Refresh Beads context
```

### Rules

- Use `bd` for all task tracking; do not create markdown TODO lists.
- Run `bd prime` when Beads context is missing or stale. Codex 0.129.0+ can load Beads context automatically through native hooks; use `/hooks` to inspect or toggle them.
- Keep persistent project memory in Beads via `bd remember`; do not create ad hoc memory files.

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/core-concepts/sync-concepts.md for details and anti-patterns.
<!-- END BEADS CODEX SETUP -->
