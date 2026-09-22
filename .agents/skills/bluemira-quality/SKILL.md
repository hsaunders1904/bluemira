---
name: bluemira-quality
description: Bluemira repository coding conventions, architecture rules, testing, and linting guidelines.
---

# Bluemira Coding & Quality Standards Skill

Follow these guidelines for all code contributed to the Bluemira repository.

## 1. Object-Oriented Architecture
- Represent physical and engineering concepts cleanly using object-oriented abstractions.
- All attributes must be explicitly initialized in `__init__`.
- Non-public methods and attributes must use a single leading underscore: `_method_name`.
- Use `__slots__` where appropriate to optimize memory footprint on classes instantiated in large volumes.
- Keep classes and methods single-purpose with minimal arguments.

## 2. Typing and Conventions
- Require Python 3.11+ type annotations on all function and method signatures.
- Use NumPy typing: `npt.NDArray[np.float64]` for array data.
- Conventions (e.g. COCOS, units in SI, coordinate systems) must be explicitly documented and validated at interface boundaries.
- Include NumPy/Google style docstrings with `Parameters` and `Returns` sections for all public interfaces.

## 3. Performance & Bottlenecks
- Never write nested Python loops over large numerical grids.
- Leverage vectorised NumPy or SciPy operations.
- Use `numba` (`@nb.njit` / `@nb.jit`) for core computational kernels, following existing patterns in `bluemira/equilibria/`.

## 4. Verification & Testing
- Every PR must include unit tests located in `tests/<subsystem>/`.
- Never disable or delete existing tests without explicit justification and user approval.
- Run tests via the `bluemira` conda/pixi environment:
  ```bash
  conda run -n bluemira pytest tests/<path_to_test_file>
  # or pixi run pytest tests/<path_to_test_file>
  ```

## 5. Formatting & Linting
- Formatting is enforced via `ruff format` (line length: 89 characters).
- Linting is enforced via `ruff check`.
- Verify before concluding:
  ```bash
  conda run -n bluemira ruff check <modified_paths>
  conda run -n bluemira ruff format --check <modified_paths>
  # or pixi run ruff check / pixi run ruff format --check
  ```
