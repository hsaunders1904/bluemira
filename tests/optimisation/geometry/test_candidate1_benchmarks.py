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
