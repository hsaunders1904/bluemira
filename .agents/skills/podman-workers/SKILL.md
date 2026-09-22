---
name: podman-workers
description: Guidelines and commands for running agent workers in isolated podman containers.
---

# Podman Worker Containers Skill

All Goldfish agent development and execution must run inside isolated Podman containers using the provided container definition and compose setup.

## Container Files
- Containerfile: `docker/Containerfile.worker`
- Compose file: `docker/compose.worker.yml`

## Usage with Podman

### 1. Build Worker Image
```bash
podman compose -f docker/compose.worker.yml build
```
Or with direct podman build:
```bash
podman build -t bluemira-worker -f docker/Containerfile.worker .
```

### 2. Launch an Interactive Worker Container
```bash
podman compose -f docker/compose.worker.yml run --rm worker
```

### 3. Launching Worker for a Specific Worktree
When executing against a task slice under `.worktrees/<branch>`:
```bash
WORKTREE_DIR=.worktrees/<branch-name> podman compose -f docker/compose.worker.yml run --rm worker
```

### 4. Running Quality Gates inside the Worker
Inside the container:
```bash
# Inside the mounted worktree
cd /workspace/.worktrees/<branch-name>

# Run pytest
pytest tests/<affected_tests>

# Run ruff check and format
ruff check .
ruff format --check .
```
