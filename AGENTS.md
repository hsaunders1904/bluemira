# AGENTS.md — "Elephants & Goldfish" Architecture Guide

This document defines how autonomous and interactive agents work on this repository.
It implements the **"Elephants & Goldfish"** pattern designed to maximize architectural coherence, maintain high code quality standards, and provide small, reviewable increments for human reviewers on GitHub/GitLab.

---

## 1. Core Philosophy: Elephants & Goldfish

- **The Elephant (Strategic Memory & System Architecture)**:
  - Remembers everything: architecture, requirements, interfaces, long-term roadmap, conventions, and invariants.
  - Formulates the global strategy, challenges ambiguity, creates the task breakdown, and tracks progress.
  - Never rushes directly into editing code across the repository without upfront alignment.
- **The Goldfish (Tactical Focus & Reviewable Increments)**:
  - Short memory, hyper-focused on executing a **single atomic task**.
  - Operates strictly in an isolated workspace (git worktree), implements the slice cleanly, writes tests, runs linters, verifies quality gates, and submits a single PR/commit branch.
  - Does not suffer from context bloat or drift because each task is small enough to fit completely in human review limits (< 300–400 lines of diff).

---

## 2. The 4-Phase Agent Protocol

Every non-trivial agent workflow must follow these four sequential phases:

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Phase 1: Plan  │ ──> │ Phase 2: Grill   │ ──> │ Phase 3: Slice  │ ──> │ Phase 4: Execute│
│  & Research     │     │ & Align          │     │ (PR Roadmap)    │     │ (Worktree Loop) │
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
**Do not skip this step.** Autonomous agents that assume user intent end up creating massive, unmergeable rewrites.
- Actively probe and challenge edge cases, architectural trade-offs, and design assumptions.
- Ask specific, structured questions:
  - *Interface design*: Public API method signatures, parameter names, backwards compatibility.
  - *Data boundaries*: Conventions (e.g. COCOS, units, coordinate systems).
  - *Dependencies*: Adding new libraries vs reusing existing utilities (`numba`, `scipy`, `numpy`).
  - *Verification expectations*: Specific benchmark data or mocking strategies.
- Incorporate user feedback into the architectural document until explicit sign-off is achieved.

### Phase 3: Slice into Atomic PR-Sized Tasks (Elephant)
Decompose the agreed plan into small, well-defined increments.
- **Strict Rule**: Each task must correspond to **exactly one Pull Request**.
- **Reviewability Budget**: Diff size target is **100–300 lines**, strictly capped at **< 400 lines** (excluding generated data or test fixtures).
- **Self-Contained Quality**: Every single PR must leave the repository in a **working, passing state** (green test suite, formatting and linting pass, zero broken imports).
- **Stacked Branches**: When tasks depend on preceding steps, explicitly document the stack hierarchy:
  - Example: `feature/part-1-types` -> `feature/part-2-core` -> `feature/part-3-cli`.
  - Maintain a checklist in the plan tracking current status of each PR chunk.

### Phase 4: Tactical Execution Loop (Goldfish)
For **each** individual task in the roadmap:
1. **Provision Git Worktree**:
   - Create a dedicated worktree under `.worktrees/<branch-name>`.
2. **Implement Focused Diff**:
   - Implement only what is required for the specific task. Avoid scope creep.
3. **Strict Verification**:
   - Run tests: `pytest <affected_tests>`.
   - Run linter & formatter: `ruff check` and `ruff format`.
   - Run type checks / docstring checks where applicable.
4. **Prepare Review Artifact**:
   - Inspect git diff (`git diff --stat`, `git diff`).
   - Create commit with conventional commit message.
   - Present summary of changes and test results to the user / PR description.

---

## 3. Git Worktree Workflow Guidelines

All development work must be performed in isolated worktrees located under `.worktrees/`. This ensures the main workspace stays clean and enables seamless switching or stacked branching.

### Setup & Directory Rules
1. Worktrees live strictly under `.worktrees/`:
   ```bash
   # Ensure .worktrees/ is ignored in the root .gitignore
   mkdir -p .worktrees
   ```
2. **Creating a new worktree**:
   ```bash
   # From root or develop branch
   git fetch origin develop
   git worktree add -b <branch-name> .worktrees/<branch-name> origin/develop
   ```
3. **Creating a stacked worktree**:
   ```bash
   # Branching off preceding task branch
   git worktree add -b <part-2-branch> .worktrees/<part-2-branch> <part-1-branch>
   ```
4. **Environment in Worktrees**:
   - Pixi / virtual environments are shared across worktrees.
   - Always run commands inside the worktree using the project's environment python:
     ```bash
     cd .worktrees/<branch-name>
     /home/user/.pixi/envs/bluemira/bin/pytest tests/...
     /home/user/.pixi/envs/bluemira/bin/ruff check .
     ```
5. **Cleaning up worktrees**:
   ```bash
   git worktree remove .worktrees/<branch-name>
   git branch -d <branch-name> # after merge
   ```

---

## 4. Repository Coding Practices & Quality Gates

Every chunk must adhere to Bluemira engineering standards:

### 4.1. Code Architecture & Style
- **Object-Oriented Design**:
  - Represent physical and mathematical entities with clean classes.
  - Initialize all instance attributes in `__init__`.
  - Prefix protected/internal methods with an underscore (e.g. `_protected_method`).
  - Use `__slots__` where performance/memory dictates.
- **Typing & Signatures**:
  - Keep functions single-purpose with minimal arguments.
  - Provide full type annotations on all signatures (`int | str | None`, `npt.NDArray[np.float64]`).
  - Use docstrings following project style (NumPy / Google style docstrings, clean parameter descriptions).
- **Performance**:
  - Prefer vectorised NumPy operations over raw Python loops.
  - Bottlenecks should leverage `@nb.njit` / `numba` where existing patterns in the codebase use them.

### 4.2. Testing Standards
- Every PR adding or modifying features **must include unit tests**.
- Put tests in `tests/<module_path>/test_<module>.py`.
- Tests must execute deterministically and fast (< a few seconds unless marked `@pytest.mark.longrun`).
- Maintain regression guarantees: never disable existing tests without explicit user discussion.
- Run:
  ```bash
  /home/user/.pixi/envs/bluemira/bin/pytest tests/<subsystem>/
  ```

### 4.3. Formatting & Linting
- Strictly follow `ruff`:
  ```bash
  /home/user/.pixi/envs/bluemira/bin/ruff check <modified_paths>
  /home/user/.pixi/envs/bluemira/bin/ruff format --check <modified_paths>
  ```
- Line length: 89 characters (configured in [pyproject.toml](file:///home/user/codes/workspace/bluemira/pyproject.toml)).
- Target Python version: 3.11+.

---

## 5. Review-Ready Task Template

When presenting the task roadmap in Phase 3, the Elephant agent must use this template:

```markdown
### PR 1: [Short Title]
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
- **Branch**: `feature/<name>-part-2` (stacked on `feature/<name>-part-1`)
- **Worktree**: `.worktrees/feature-<name>-part-2`
- **Scope**:
  - Implementation of core logic / algorithm
- **Estimated Diff**: ~200 lines
- **Quality Gates**:
  - [ ] Unit tests covering edge cases
  - [ ] Regression suite passes
- **Dependencies**: PR 1
```

---

## 6. Checklist for Agents Before Concluding a Task

- [ ] Current task matches the scope of a single pull request.
- [ ] Work was developed and validated inside `.worktrees/<branch>`.
- [ ] All new logic is backed by pytest tests.
- [ ] No regression in the broader module test suite.
- [ ] `ruff check` passes with 0 errors.
- [ ] `ruff format` confirms formatting compliance.
- [ ] Git diff has been reviewed to ensure zero accidental edits or leftover debug artifacts.
- [ ] User is given a crisp summary with links to changed files and test reports.
