#!/usr/bin/env python3
"""
Benchmark comparison script for Geometry Optimisation performance.

This script is forward- and backward-compatible with both `upstream/develop`
and `performance-optimisations`. It measures and outputs execution times and
indicates whether CAD fallback or optimized vectorised routines are active.
"""

from __future__ import annotations

import sys
import time
import numpy as np

# Core Bluemira imports present in both upstream/develop and performance-optimisations
from bluemira.geometry.parameterisations import PrincetonD
from bluemira.geometry.tools import distance_to, make_circle
from bluemira.geometry.optimisation import optimise_geometry

# Detect if current environment/branch has performance optimisations available
HAS_CALCULATE_LENGTH = hasattr(PrincetonD, "calculate_length")

try:
    from bluemira.geometry.tools import fast_2d_distance
    HAS_FAST_2D_DISTANCE = True
except ImportError:
    HAS_FAST_2D_DISTANCE = False

try:
    from bluemira.geometry.optimisation import (
        make_minimum_distance_constraint,
        wire_length_objective,
    )
    HAS_OPT_HELPERS = True
except ImportError:
    HAS_OPT_HELPERS = False

HAS_NEW_ROUTINES = HAS_CALCULATE_LENGTH and HAS_FAST_2D_DISTANCE and HAS_OPT_HELPERS


def print_header(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def run_micro_benchmarks(n_evals: int = 50) -> dict[str, float]:
    print_header(f"1. MICRO-BENCHMARKS ({n_evals} iterations each)")

    geom = PrincetonD()
    obstacle = make_circle(radius=2.5, center=(9.0, 0, 0), axis=(0, 1, 0))

    # --- Length calculation ---
    t0 = time.perf_counter()
    if HAS_CALCULATE_LENGTH:
        mode_len = "PrincetonD.calculate_length() [Optimized NumPy]"
        for _ in range(n_evals):
            _ = geom.calculate_length()
    else:
        mode_len = "geom.create_shape().length [CAD OCC Kernel]"
        for _ in range(n_evals):
            _ = geom.create_shape().length
    t_len = time.perf_counter() - t0

    # --- Clearance distance query ---
    t0 = time.perf_counter()
    if HAS_FAST_2D_DISTANCE:
        mode_dist = "fast_2d_distance() [Vectorized 2D Euclidean]"
        target_pts = obstacle.discretise(100, byedges=False).xz.T
        for _ in range(n_evals):
            _ = fast_2d_distance(geom, target_pts, n_points=100)
    else:
        mode_dist = "distance_to(geom.create_shape(), obstacle) [CAD BRepExtrema]"
        for _ in range(n_evals):
            _ = distance_to(geom.create_shape(), obstacle)[0]
    t_dist = time.perf_counter() - t0

    # --- Shape creation / memoization ---
    t0 = time.perf_counter()
    for _ in range(n_evals):
        _ = geom.create_shape()
    t_shape = time.perf_counter() - t0

    print(f"• Wire Length Evaluation:")
    print(f"    Mode      : {mode_len}")
    print(f"    Total time: {t_len * 1e3:.2f} ms ({t_len / n_evals * 1e3:.3f} ms/call)")

    print(f"• Clearance Distance Query:")
    print(f"    Mode      : {mode_dist}")
    print(f"    Total time: {t_dist * 1e3:.2f} ms ({t_dist / n_evals * 1e3:.3f} ms/call)")

    print(f"• Repeated create_shape() queries:")
    print(f"    Total time: {t_shape * 1e3:.2f} ms ({t_shape / n_evals * 1e3:.3f} ms/call)")

    return {"t_len": t_len, "t_dist": t_dist, "t_shape": t_shape}


def run_gop_benchmark(max_eval: int = 30) -> dict[str, float]:
    print_header(f"2. END-TO-END COIL GEOMETRY OPTIMISATION (SLSQP, max_eval={max_eval})")

    # Initialise parameterisation with identical explicit bounds
    geom = PrincetonD({
        "x1": {"value": 4.0, "lower_bound": 2.0, "upper_bound": 6.0},
        "x2": {"value": 12.0, "lower_bound": 10.0, "upper_bound": 15.0},
    })
    obstacle = make_circle(radius=2.0, center=(9.0, 0, 0), axis=(0, 1, 0))
    min_dist = 1.0

    if HAS_NEW_ROUTINES:
        mode_gop = "Optimized Pipeline (wire_length_objective + make_minimum_distance_constraint + GeomOptimisationContext)"
        f_obj = wire_length_objective
        constraints = [
            make_minimum_distance_constraint(obstacle, min_dist, tol=1e-6, name="distance")
        ]
    else:
        mode_gop = "Baseline Pipeline (CAD create_shape length + CAD distance_to constraint)"
        f_obj = lambda g: g.create_shape().length
        constraints = [{
            "name": "distance",
            "f_constraint": lambda g: np.array([min_dist - distance_to(g.create_shape(), obstacle)[0]]),
            "tolerance": np.array([1e-6]),
        }]

    t0 = time.perf_counter()
    result = optimise_geometry(
        geom=geom,
        f_objective=f_obj,
        ineq_constraints=constraints,
        opt_conditions={"max_eval": max_eval, "ftol_rel": 1e-4},
    )
    t_solve = time.perf_counter() - t0

    print(f"• Mode               : {mode_gop}")
    print(f"• Total Solve Time   : {t_solve * 1e3:.2f} ms")
    print(f"• Number of Evals    : {result.n_evals}")
    print(f"• Final Wire Length  : {result.f_x:.4f} m")
    print(f"• Constraint Met     : {result.constraints_satisfied}")

    return {"t_solve": t_solve, "n_evals": result.n_evals}


if __name__ == "__main__":
    branch_name = "performance-optimisations" if HAS_NEW_ROUTINES else "upstream/develop (or un-optimised)"

    print_header(f"RUNNING BENCHMARK ON: {branch_name}")
    print(f"Python executable      : {sys.executable}")
    print(f"Optimisations active   : {HAS_NEW_ROUTINES}")
    print(f"  - calculate_length   : {HAS_CALCULATE_LENGTH}")
    print(f"  - fast_2d_distance   : {HAS_FAST_2D_DISTANCE}")
    print(f"  - context & helpers  : {HAS_OPT_HELPERS}")

    micro_res = run_micro_benchmarks(n_evals=50)
    gop_res = run_gop_benchmark(max_eval=30)

    print_header("BENCHMARK SUMMARY RECORD")
    print(f"Branch                  : {branch_name}")
    print(f"Length per call         : {micro_res['t_len'] / 50 * 1e3:.3f} ms")
    print(f"Distance per call       : {micro_res['t_dist'] / 50 * 1e3:.3f} ms")
    print(f"create_shape() per call : {micro_res['t_shape'] / 50 * 1e3:.3f} ms")
    print(f"GOP solve total time    : {gop_res['t_solve'] * 1e3:.2f} ms")
    print("=" * 72 + "\n")
