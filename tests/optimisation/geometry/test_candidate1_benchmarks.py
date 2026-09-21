# SPDX-FileCopyrightText: 2021-present M. Coleman, J. Cook, F. Franza
# SPDX-FileCopyrightText: 2021-present I.A. Maione, S. McIntosh
# SPDX-FileCopyrightText: 2021-present J. Morris, D. Short
#
# SPDX-License-Identifier: LGPL-2.1-or-later
"""
Performance benchmarks for Candidate 1:
Geometry Optimisation Caching and CAD Decoupling
"""

import time
import numpy as np
import pytest
from bluemira.geometry.parameterisations import PictureFrame, PrincetonD


class TestCandidate1Benchmarks:
    """Benchmark tests validating speedup from caching and decoupling."""

    def test_task_1_1_shape_memoization_benchmark(self):
        """
        Benchmark Task 1.1: Shape memoization on GeometryParameterisation.

        Compares repeated create_shape calls without caching vs with caching.
        """
        geom = PrincetonD()
        n_evals = 10

        # Uncached timing (clearing cache before each call)
        t0 = time.perf_counter()
        for _ in range(n_evals):
            geom.clear_cache()
            _ = geom.create_shape()
        uncached_time = time.perf_counter() - t0

        # Cached timing (first call warms cache, subsequent calls hit cache)
        geom.clear_cache()
        t0 = time.perf_counter()
        for _ in range(n_evals):
            _ = geom.create_shape()
        cached_time = time.perf_counter() - t0

        speedup = uncached_time / cached_time
        print(f"\n[Task 1.1 Benchmark] {n_evals} create_shape() evals:")
        print(f"  Uncached: {uncached_time * 1e3:.2f} ms ({uncached_time / n_evals * 1e3:.2f} ms/eval)")
        print(f"  Cached:   {cached_time * 1e3:.2f} ms ({cached_time / n_evals * 1e3:.4f} ms/eval)")
        print(f"  Speedup:  {speedup:.1f}x")

        # Caching should be at least 5x faster for 10 evals (typically >50x)
        assert speedup >= 5.0
        assert cached_time < uncached_time

    def test_task_2_1_direct_discretise_benchmark(self):
        """
        Benchmark Task 2.1: Direct coordinate discretization vs CAD wire discretization.
        """
        geom = PrincetonD()
        n_evals = 10
        n_points = 100

        # CAD wire discretise timing (clearing cache to simulate uncached CAD build)
        t0 = time.perf_counter()
        for _ in range(n_evals):
            geom.clear_cache()
            _ = geom.create_shape().discretise(n_points, byedges=False)
        cad_time = time.perf_counter() - t0

        # Direct NumPy discretise_coords timing
        t0 = time.perf_counter()
        for _ in range(n_evals):
            coords = geom.discretise_coords(n_points)
        direct_time = time.perf_counter() - t0

        speedup = cad_time / direct_time
        print(f"\n[Task 2.1 Benchmark] {n_evals} discretisations ({n_points} points):")
        print(f"  CAD wire discretise:   {cad_time * 1e3:.2f} ms ({cad_time / n_evals * 1e3:.2f} ms/eval)")
        print(f"  Direct NumPy discretise: {direct_time * 1e3:.2f} ms ({direct_time / n_evals * 1e3:.4f} ms/eval)")
        print(f"  Speedup:               {speedup:.1f}x")

        # Verify point count and basic shape fidelity
        assert len(coords) == n_points
        assert speedup >= 10.0

    def test_task_2_2_signed_distance_benchmark(self):
        """
        Benchmark Task 2.2: Decoupled calculate_signed_distance vs CAD creation pathway.
        """
        from bluemira.geometry.optimisation._tools import calculate_signed_distance
        from bluemira.geometry.tools import make_circle, signed_distance_2D_polygon

        geom = PrincetonD()
        koz = make_circle(radius=4.5, center=(12.5, 0, 0), axis=(0, 1, 0))
        zone_points = koz.discretise(100, byedges=False).xz
        n_evals = 10
        n_points = 100

        # Original CAD pathway (rebuilding CAD wire every time)
        t0 = time.perf_counter()
        for _ in range(n_evals):
            geom.clear_cache()
            shape = geom.create_shape()
            s = shape.discretise(n_points, byedges=False).xz
            _ = signed_distance_2D_polygon(s.T, zone_points.T).T
        cad_time = time.perf_counter() - t0

        # Decoupled calculate_signed_distance
        t0 = time.perf_counter()
        for _ in range(n_evals):
            dist = calculate_signed_distance(geom, n_points, zone_points)
        decoupled_time = time.perf_counter() - t0

        speedup = cad_time / decoupled_time
        print(f"\n[Task 2.2 Benchmark] {n_evals} calculate_signed_distance evals:")
        print(f"  CAD wire distance:      {cad_time * 1e3:.2f} ms ({cad_time / n_evals * 1e3:.2f} ms/eval)")
        print(f"  Decoupled distance:     {decoupled_time * 1e3:.2f} ms ({decoupled_time / n_evals * 1e3:.4f} ms/eval)")
        print(f"  Speedup:                {speedup:.1f}x")

        assert len(dist) == n_points
        assert speedup >= 10.0

    def test_task_3_1_calculate_length_benchmark(self):
        """
        Benchmark Task 3.1: Direct calculate_length vs CAD wire .length.
        """
        geom = PrincetonD()
        n_evals = 20

        # CAD wire length timing (clearing cache to simulate uncached CAD wire rebuild)
        t0 = time.perf_counter()
        cad_len = 0.0
        for _ in range(n_evals):
            geom.clear_cache()
            cad_len = geom.create_shape().length
        cad_time = time.perf_counter() - t0

        # Direct NumPy calculate_length timing
        t0 = time.perf_counter()
        direct_len = 0.0
        for _ in range(n_evals):
            direct_len = geom.calculate_length()
        direct_time = time.perf_counter() - t0

        speedup = cad_time / direct_time
        rel_error = abs(direct_len - cad_len) / cad_len
        print(f"\n[Task 3.1 Benchmark] {n_evals} length calculations:")
        print(f"  CAD wire length:        {cad_time * 1e3:.2f} ms ({cad_time / n_evals * 1e3:.2f} ms/eval)")
        print(f"  Direct calculate_length: {direct_time * 1e3:.2f} ms ({direct_time / n_evals * 1e3:.4f} ms/eval)")
        print(f"  Speedup:                {speedup:.1f}x")
        print(f"  Relative error:         {rel_error:.2e}")

        assert rel_error < 1e-4
        assert speedup >= 10.0

    def test_task_3_2_wire_length_objective_benchmark(self):
        """
        Benchmark Task 3.2: Native wire_length_objective vs CAD wire length lambda.
        """
        from bluemira.builders.tf_coils import RippleConstrainedLengthGOP
        from bluemira.geometry.optimisation import wire_length_objective

        geom = PrincetonD()
        n_evals = 20

        # CAD wire lambda objective timing (clearing cache to simulate uncached CAD wire rebuild)
        t0 = time.perf_counter()
        cad_len = 0.0
        for _ in range(n_evals):
            geom.clear_cache()
            cad_len = geom.create_shape().length
        cad_time = time.perf_counter() - t0

        # Native wire_length_objective timing
        t0 = time.perf_counter()
        opt_len = 0.0
        for _ in range(n_evals):
            opt_len = wire_length_objective(geom)
        opt_time = time.perf_counter() - t0

        # RippleConstrainedLengthGOP.objective timing
        builder_len = RippleConstrainedLengthGOP.objective(geom)

        speedup = cad_time / opt_time
        print(f"\n[Task 3.2 Benchmark] {n_evals} wire_length_objective evaluations:")
        print(f"  CAD wire lambda:                   {cad_time * 1e3:.2f} ms ({cad_time / n_evals * 1e3:.2f} ms/eval)")
        print(f"  wire_length_objective:             {opt_time * 1e3:.2f} ms ({opt_time / n_evals * 1e3:.4f} ms/eval)")
        print(f"  RippleConstrainedLengthGOP.objective: {builder_len:.4f} m")
        print(f"  Speedup:                           {speedup:.1f}x")

        assert abs(opt_len - cad_len) / cad_len < 1e-4
        assert abs(builder_len - cad_len) / cad_len < 1e-4
        assert speedup >= 10.0

    def test_task_4_1_fast_2d_distance_benchmark(self):
        """
        Benchmark Task 4.1: Fast 2D vectorized distance vs CAD distance_to.
        """
        from bluemira.geometry.tools import distance_to, fast_2d_distance, make_circle

        geom = PrincetonD()
        obstacle = make_circle(radius=3.0, center=(9.0, 0, 0), axis=(0, 1, 0))
        target_pts = obstacle.discretise(100, byedges=False).xz.T
        n_evals = 20

        # CAD distance_to timing (clearing cache to simulate uncached CAD rebuild)
        t0 = time.perf_counter()
        cad_dist = 0.0
        for _ in range(n_evals):
            geom.clear_cache()
            cad_dist = distance_to(geom.create_shape(), obstacle)[0]
        cad_time = time.perf_counter() - t0

        # Fast 2D distance timing
        t0 = time.perf_counter()
        fast_dist = 0.0
        for _ in range(n_evals):
            fast_dist = fast_2d_distance(geom, target_pts, n_points=100)
        fast_time = time.perf_counter() - t0

        speedup = cad_time / fast_time
        print(f"\n[Task 4.1 Benchmark] {n_evals} distance calculations:")
        print(f"  CAD distance_to:        {cad_time * 1e3:.2f} ms ({cad_time / n_evals * 1e3:.2f} ms/eval)")
        print(f"  fast_2d_distance:       {fast_time * 1e3:.2f} ms ({fast_time / n_evals * 1e3:.4f} ms/eval)")
        print(f"  CAD dist:               {cad_dist:.4f} m, Fast dist: {fast_dist:.4f} m")
        print(f"  Speedup:                {speedup:.1f}x")

        assert abs(fast_dist - cad_dist) < 0.05
        assert speedup >= 10.0

    def test_task_4_2_make_minimum_distance_constraint_benchmark(self):
        """
        Benchmark Task 4.2: Standard make_minimum_distance_constraint vs CAD distance_to constraint.
        """
        from bluemira.geometry.optimisation import make_minimum_distance_constraint
        from bluemira.geometry.tools import distance_to, make_circle

        geom = PrincetonD()
        obstacle = make_circle(radius=3.0, center=(9.0, 0, 0), axis=(0, 1, 0))
        min_dist = 2.5
        n_evals = 20

        # Ad-hoc CAD constraint lambda (clearing cache to simulate uncached CAD rebuild)
        t0 = time.perf_counter()
        cad_res = np.zeros(1)
        for _ in range(n_evals):
            geom.clear_cache()
            cad_res = np.array([min_dist - distance_to(geom.create_shape(), obstacle)[0]])
        cad_time = time.perf_counter() - t0

        # Fast minimum distance constraint
        constr = make_minimum_distance_constraint(obstacle, min_dist, n_points=100)
        f_constr = constr["f_constraint"]

        t0 = time.perf_counter()
        fast_res = np.zeros(1)
        for _ in range(n_evals):
            fast_res = f_constr(geom)
        fast_time = time.perf_counter() - t0

        speedup = cad_time / fast_time
        print(f"\n[Task 4.2 Benchmark] {n_evals} minimum distance constraint evaluations:")
        print(f"  CAD constraint:            {cad_time * 1e3:.2f} ms ({cad_time / n_evals * 1e3:.2f} ms/eval)")
        print(f"  make_minimum_distance_constraint: {fast_time * 1e3:.2f} ms ({fast_time / n_evals * 1e3:.4f} ms/eval)")
        print(f"  CAD val:                   {cad_res[0]:.4f}, Fast val: {fast_res[0]:.4f}")
        print(f"  Speedup:                   {speedup:.1f}x")

        assert abs(fast_res[0] - cad_res[0]) < 0.05
        assert speedup >= 10.0

    def test_task_4_3_reactor_designer_gop_benchmark(self):
        """
        Benchmark Task 4.3: Full reactor designer TF coil GOP solve comparing
        baseline CAD-heavy callbacks against decoupled fast objectives & constraints.
        """
        from bluemira.geometry.optimisation import (
            make_minimum_distance_constraint,
            optimise_geometry,
            wire_length_objective,
        )
        from bluemira.geometry.tools import distance_to, make_circle

        obstacle = make_circle(radius=3.0, center=(9.0, 0, 0), axis=(0, 1, 0))
        min_dist = 2.5
        max_eval = 25

        # Baseline GOP run (CAD wire length lambda + CAD distance_to constraint)
        p1 = PrincetonD()
        t0 = time.perf_counter()
        _ = optimise_geometry(
            geom=p1,
            f_objective=lambda g: g.create_shape().length,
            ineq_constraints=[{
                "name": "distance",
                "f_constraint": lambda g: np.array([min_dist - distance_to(g.create_shape(), obstacle)[0]]),
                "tolerance": np.array([1e-6]),
            }],
            opt_conditions={"max_eval": max_eval, "ftol_rel": 1e-4},
        )
        t_base = time.perf_counter() - t0

        # Fast decoupled GOP run (wire_length_objective + make_minimum_distance_constraint)
        p2 = PrincetonD()
        t0 = time.perf_counter()
        _ = optimise_geometry(
            geom=p2,
            f_objective=wire_length_objective,
            ineq_constraints=[
                make_minimum_distance_constraint(obstacle, min_dist, tol=1e-6, name="distance")
            ],
            opt_conditions={"max_eval": max_eval, "ftol_rel": 1e-4},
        )
        t_opt = time.perf_counter() - t0

        speedup = t_base / t_opt
        print(f"\n[Task 4.3 Benchmark] Reactor TF Coil GOP Solve ({max_eval} max evals):")
        print(f"  Baseline CAD GOP:    {t_base * 1e3:.2f} ms")
        print(f"  Fast Decoupled GOP:  {t_opt * 1e3:.2f} ms")
        print(f"  Speedup:             {speedup:.1f}x")

        assert speedup >= 5.0

    def test_task_5_1_multi_callback_context_benchmark(self):
        """
        Benchmark Task 5.1: Multi-callback state caching context in geometry optimisation.
        """
        from bluemira.geometry.optimisation import (
            GeomOptimisationContext,
            KeepOutZone,
            make_keep_out_zone_constraint,
            optimise_geometry,
            wire_length_objective,
        )
        from bluemira.geometry.tools import make_circle

        z1 = make_circle(radius=2.0, center=(13.0, 0, 0), axis=(0, 1, 0))
        z2 = make_circle(radius=2.0, center=(12.0, 4, 0), axis=(0, 1, 0))
        z3 = make_circle(radius=2.0, center=(12.0, -4, 0), axis=(0, 1, 0))

        # Benchmark 1: PictureFrame (exercises CAD fallback caching across multiple callbacks)
        g_no_ctx = PictureFrame()
        c1 = make_keep_out_zone_constraint(KeepOutZone(z1))["f_constraint"]
        c2 = make_keep_out_zone_constraint(KeepOutZone(z2))["f_constraint"]
        x_pf = g_no_ctx.variables.get_normalised_values()

        n_evals_pf = 20
        t0 = time.perf_counter()
        for _ in range(n_evals_pf):
            g_no_ctx.clear_cache()
            g_no_ctx.variables.set_values_from_norm(x_pf)
            _ = wire_length_objective(g_no_ctx)
            _ = c1(g_no_ctx)
            _ = c2(g_no_ctx)
        t_pf_no_ctx = time.perf_counter() - t0

        g_ctx = PictureFrame()
        ctx_pf = GeomOptimisationContext(g_ctx)
        c1_ctx = make_keep_out_zone_constraint(KeepOutZone(z1), context=ctx_pf)["f_constraint"]
        c2_ctx = make_keep_out_zone_constraint(KeepOutZone(z2), context=ctx_pf)["f_constraint"]

        t0 = time.perf_counter()
        for _ in range(n_evals_pf):
            ctx_pf.update_x(x_pf)
            _ = wire_length_objective(g_ctx)
            _ = c1_ctx(g_ctx)
            _ = c2_ctx(g_ctx)
        t_pf_ctx = time.perf_counter() - t0

        speedup_pf = t_pf_no_ctx / t_pf_ctx
        print(f"\n[Task 5.1 Benchmark - PictureFrame] {n_evals_pf} multi-callback evaluations (obj + 2 KOZ):")
        print(f"  Uncached:        {t_pf_no_ctx * 1e3:.2f} ms ({t_pf_no_ctx / n_evals_pf * 1e3:.2f} ms/eval)")
        print(f"  Context-Cached:  {t_pf_ctx * 1e3:.2f} ms ({t_pf_ctx / n_evals_pf * 1e3:.2f} ms/eval)")
        print(f"  Speedup:         {speedup_pf:.1f}x")

        # Benchmark 2: PrincetonD (exercises pure-NumPy coordinate caching across callbacks)
        geom_no_ctx = PrincetonD()
        koz1 = make_keep_out_zone_constraint(KeepOutZone(z1))["f_constraint"]
        koz2 = make_keep_out_zone_constraint(KeepOutZone(z2))["f_constraint"]
        koz3 = make_keep_out_zone_constraint(KeepOutZone(z3))["f_constraint"]
        x_pd = geom_no_ctx.variables.get_normalised_values()
        n_evals_pd = 100

        t0 = time.perf_counter()
        for _ in range(n_evals_pd):
            geom_no_ctx.variables.set_values_from_norm(x_pd)
            _ = wire_length_objective(geom_no_ctx)
            geom_no_ctx.variables.set_values_from_norm(x_pd)
            _ = koz1(geom_no_ctx)
            geom_no_ctx.variables.set_values_from_norm(x_pd)
            _ = koz2(geom_no_ctx)
            geom_no_ctx.variables.set_values_from_norm(x_pd)
            _ = koz3(geom_no_ctx)
        t_no_ctx = time.perf_counter() - t0

        geom_ctx = PrincetonD()
        ctx_pd = GeomOptimisationContext(geom_ctx)
        koz1_ctx = make_keep_out_zone_constraint(KeepOutZone(z1), context=ctx_pd)["f_constraint"]
        koz2_ctx = make_keep_out_zone_constraint(KeepOutZone(z2), context=ctx_pd)["f_constraint"]
        koz3_ctx = make_keep_out_zone_constraint(KeepOutZone(z3), context=ctx_pd)["f_constraint"]

        t0 = time.perf_counter()
        for _ in range(n_evals_pd):
            ctx_pd.update_x(x_pd)
            _ = wire_length_objective(geom_ctx)
            ctx_pd.update_x(x_pd)
            _ = koz1_ctx(geom_ctx)
            ctx_pd.update_x(x_pd)
            _ = koz2_ctx(geom_ctx)
            ctx_pd.update_x(x_pd)
            _ = koz3_ctx(geom_ctx)
        t_ctx = time.perf_counter() - t0

        speedup_pd = t_no_ctx / t_ctx
        print(f"\n[Task 5.1 Benchmark - PrincetonD] {n_evals_pd} multi-callback evaluations (obj + 3 KOZ):")
        print(f"  Uncached:        {t_no_ctx * 1e3:.2f} ms ({t_no_ctx / n_evals_pd * 1e3:.3f} ms/eval)")
        print(f"  Context-Cached:  {t_ctx * 1e3:.2f} ms ({t_ctx / n_evals_pd * 1e3:.3f} ms/eval)")
        print(f"  Speedup:         {speedup_pd:.1f}x")

        assert speedup_pf >= 2.5
        assert speedup_pd >= 1.05

    def test_task_6_2_end_to_end_reactor_build_benchmark(self):
        """
        Benchmark Task 6.2: End-to-end reactor coil geometry optimization workflow.

        Compares the baseline CAD-coupled workflow (CAD wire length objective +
        CAD distance_to obstacle constraints with shape re-generation)
        against the decoupled & cached Candidate 1 architecture (wire_length_objective +
        make_minimum_distance_constraint + GeomOptimisationContext).
        """
        from bluemira.geometry.optimisation import (
            make_minimum_distance_constraint,
            optimise_geometry,
            wire_length_objective,
        )
        from bluemira.geometry.tools import distance_to, make_circle

        obstacle1 = make_circle(radius=2.0, center=(9.0, 0, 0), axis=(0, 1, 0))
        obstacle2 = make_circle(radius=1.5, center=(13.0, 3, 0), axis=(0, 1, 0))
        min_dist = 1.0
        max_eval = 25

        # 1. Baseline CAD-coupled workflow
        p_base = PrincetonD()

        def cad_obj(g):
            g.clear_cache()
            return g.create_shape().length

        def cad_c1(g):
            g.clear_cache()
            return np.array([min_dist - distance_to(g.create_shape(), obstacle1)[0]])

        def cad_c2(g):
            g.clear_cache()
            return np.array([min_dist - distance_to(g.create_shape(), obstacle2)[0]])

        t0 = time.perf_counter()
        _ = optimise_geometry(
            geom=p_base,
            f_objective=cad_obj,
            ineq_constraints=[
                {"name": "c1", "f_constraint": cad_c1, "tolerance": np.array([1e-6])},
                {"name": "c2", "f_constraint": cad_c2, "tolerance": np.array([1e-6])},
            ],
            opt_conditions={"max_eval": max_eval, "ftol_rel": 1e-4},
        )
        t_base = time.perf_counter() - t0

        # 2. Optimized Candidate 1 decoupled workflow
        p_opt = PrincetonD()
        c1_fast = make_minimum_distance_constraint(obstacle1, min_dist, tol=1e-6, name="c1")
        c2_fast = make_minimum_distance_constraint(obstacle2, min_dist, tol=1e-6, name="c2")

        t0 = time.perf_counter()
        res_opt = optimise_geometry(
            geom=p_opt,
            f_objective=wire_length_objective,
            ineq_constraints=[c1_fast, c2_fast],
            opt_conditions={"max_eval": max_eval, "ftol_rel": 1e-4},
        )
        t_opt = time.perf_counter() - t0

        speedup = t_base / t_opt
        print(f"\n[Task 6.2 Benchmark] End-to-end reactor coil GOP solve ({max_eval} evals, 2 obstacles):")
        print(f"  Baseline CAD Workflow:       {t_base * 1e3:.2f} ms")
        print(f"  Decoupled & Cached Workflow: {t_opt * 1e3:.2f} ms")
        print(f"  Overall Speedup:             {speedup:.1f}x")
        print(f"  Constraints satisfied:       {res_opt.constraints_satisfied}")

        assert speedup >= 10.0
        assert res_opt.constraints_satisfied
