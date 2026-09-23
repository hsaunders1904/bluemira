# SPDX-FileCopyrightText: 2021-present M. Coleman, J. Cook, F. Franza
# SPDX-FileCopyrightText: 2021-present I.A. Maione, S. McIntosh
# SPDX-FileCopyrightText: 2021-present J. Morris, D. Short
#
# SPDX-License-Identifier: LGPL-2.1-or-later

"""
Unit and integration tests for FreeGSNKE inverse Grad-Shafranov solver bridge.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from bluemira.base.file import get_bluemira_path
from bluemira.equilibria import (
    Circuit,
    Coil,
    CoilSet,
    CustomProfile,
    Equilibrium,
    Grid,
    InverseGSSolver,
    InverseSolveResult,
    constraints_to_freegsnke,
    run_inverse_solve,
)
from bluemira.equilibria.error import EquilibriaError
from bluemira.equilibria.freegsnke_bridge import (
    _extract_coil_current_limits,
    _extract_field_constraint,
    _extract_isoflux_constraint,
    _extract_null_constraint,
    _extract_psi_constraint,
)
from bluemira.equilibria.optimisation.constraints import (
    FieldNullConstraint,
    IsofluxConstraint,
    MagneticConstraintSet,
    PsiConstraint,
    RadialFieldConstraint,
    VerticalFieldConstraint,
)
from bluemira.equilibria.optimisation.problem import TikhonovCurrentCOP
from bluemira.equilibria.solve import PicardIterator


@pytest.fixture
def simple_grid() -> Grid:
    """Fixture providing a standard test grid."""
    return Grid(0.5, 2.5, -2.0, 2.0, 33, 65)


@pytest.fixture
def simple_coilset() -> CoilSet:
    """Fixture providing a simple 2-coil set."""
    c1 = Coil(1.5, 1.0, current=1e5, dx=0.05, dz=0.05, name="PF_upper")
    c2 = Coil(1.5, -1.0, current=1e5, dx=0.05, dz=0.05, name="PF_lower")
    return CoilSet(c1, c2)


@pytest.fixture
def mastu_equilibrium() -> Equilibrium:
    """Fixture providing a configured MAST-U-like Equilibrium."""
    path = get_bluemira_path("equilibria", subfolder="examples")
    with open(Path(path, "MAST-U_like_active_coils.json")) as f:
        coil_dict = json.load(f)

    circuit_currents = {
        "Solenoid": 5000.0,
        "PX": 3696.81,
        "D1": 6941.24,
        "D2": 4390.86,
        "D3": 2924.36,
        "Dp": -2488.20,
        "D5": 249.21,
        "D6": -315.00,
        "D7": 511.08,
        "P4": -3564.38,
        "P5": -3954.24,
        "P6": 0.0,
    }

    circuits = []
    for n, d in coil_dict.items():
        coils = []
        if n == "Solenoid":
            for i, (r, z) in enumerate(zip(d["R"], d["Z"], strict=False)):
                coil = Coil(
                    r,
                    z,
                    current=0.0,
                    dx=d["dR"] / 2.0,
                    dz=0.00489474,
                    ctype="CS",
                    name=f"{n}_{i}",
                )
                coils.append(coil)
        else:
            for i, (r1, z1, r2, z2) in enumerate(
                zip(d["1"]["R"], d["1"]["Z"], d["2"]["R"], d["2"]["Z"], strict=False)
            ):
                coils.extend([
                    Coil(
                        r1,
                        z1,
                        current=0.0,
                        dx=d["1"]["dR"] / 2.0,
                        dz=d["1"]["dZ"] / 2.0,
                        ctype="PF",
                        name=f"{n}U_{i}",
                    ),
                    Coil(
                        r2,
                        z2,
                        current=0.0,
                        dx=d["2"]["dR"] / 2.0,
                        dz=d["2"]["dZ"] / 2.0,
                        ctype="PF",
                        name=f"{n}L_{i}",
                    ),
                ])
        circ = Circuit(*coils)
        circ.current = circuit_currents.get(n, 0.0)
        circuits.append(circ)

    full_coilset = CoilSet(*circuits)
    ref_eq = Equilibrium.from_eqdsk(Path(path, "MASTU-FREEGSNKE.eqdsk"), from_cocos=7)
    pn = np.linspace(0, 1, 50)
    profiles = CustomProfile(
        ref_eq.profiles.pprime(pn),
        ref_eq.ffprime(pn),
        R_0=0.85,
        B_0=0.588,
        I_p=6e5,
    )
    grid = Grid(0.1, 2.0, -2.2, 2.2, 65, 129)
    return Equilibrium(full_coilset, grid, profiles, force_symmetry=True)


class TestConstraintExtraction:
    """Tests for extracting and translating constraints to FreeGSNKE."""

    def test_extract_isoflux_constraint(self):
        """Test extraction of IsofluxConstraint coordinates."""
        isoflux = IsofluxConstraint(
            x=np.array([1.2, 1.4]),
            z=np.array([0.5, -0.5]),
            ref_x=1.0,
            ref_z=0.0,
        )
        arr = _extract_isoflux_constraint(isoflux)
        assert len(arr) == 3
        np.testing.assert_allclose(arr[0], [1.2, 1.4, 1.0])
        np.testing.assert_allclose(arr[1], [0.5, -0.5, 0.0])

    def test_extract_psi_constraint(self):
        """Test extraction of PsiConstraint coordinates and targets."""
        psi_c = PsiConstraint(
            x=np.array([1.0, 1.5]), z=np.array([0.0, 0.1]), target_value=0.25
        )
        r_psi, z_psi, val_psi = _extract_psi_constraint(psi_c)
        assert len(r_psi) == 2
        assert len(z_psi) == 2
        assert len(val_psi) == 2
        np.testing.assert_allclose(val_psi, [0.25, 0.25])

    def test_extract_field_constraint(self):
        """Test extraction of field constraints (nulls and component targets)."""
        nulls = FieldNullConstraint(x=np.array([1.1, 1.1]), z=np.array([0.8, -0.8]))
        r_nulls, z_nulls = _extract_null_constraint(nulls)
        assert len(r_nulls) == 2
        assert len(z_nulls) == 2

        br_c = RadialFieldConstraint(x=1.2, z=0.0, target_value=0.05)
        rf, zf, brf, bzf, wf = _extract_field_constraint(br_c)
        assert len(rf) == 1
        np.testing.assert_allclose(rf[0], 1.2)
        np.testing.assert_allclose(brf[0], 0.05)
        assert np.isnan(bzf[0])

        bz_c = VerticalFieldConstraint(x=1.3, z=0.0, target_value=-0.02)
        rf, zf, brf, bzf, wf = _extract_field_constraint(bz_c)
        assert len(rf) == 1
        assert np.isnan(brf[0])
        np.testing.assert_allclose(bzf[0], -0.02)

    def test_extract_coil_current_limits(self, simple_coilset):
        """Test extraction of coil current limits from a CoilSet or mock collection."""
        limits = _extract_coil_current_limits(simple_coilset)
        assert limits is None

        mock_coils = [
            SimpleNamespace(name="c1", control=True, current_min=-2e5, current_max=2e5),
            SimpleNamespace(name="c2", control=True, current_min=None, current_max=1e5),
        ]
        limits = _extract_coil_current_limits(mock_coils)
        assert limits is not None
        assert limits[0] == [2e5, 1e5]
        assert limits[1] == [-2e5, None]

    def test_constraints_to_freegsnke(self, simple_coilset):
        """Test full translation of constraint container to Inverse_optimizer."""
        nulls = FieldNullConstraint(x=np.array([1.0, 1.0]), z=np.array([0.5, -0.5]))
        isoflux = IsofluxConstraint(x=1.4, z=0.0, ref_x=1.0, ref_z=0.5)
        psi_c = PsiConstraint(x=1.2, z=0.0, target_value=0.1)

        cset = MagneticConstraintSet([nulls, isoflux, psi_c])
        opt = constraints_to_freegsnke(cset, coilset=simple_coilset)

        assert opt.null_points is not None
        assert len(opt.isoflux_set) == 1
        assert opt.psi_vals is not None

    def test_empty_constraints_raises(self, simple_coilset):
        """Test that translating an empty constraint set raises EquilibriaError."""
        cset = MagneticConstraintSet([])
        with pytest.raises(EquilibriaError, match="No valid constraints"):
            constraints_to_freegsnke(cset, coilset=simple_coilset)


class TestInverseSolve:
    """Integration tests for running inverse Grad-Shafranov solve with FreeGSNKE."""

    def test_run_inverse_solve_mastu(self, mastu_equilibrium):
        """Test run_inverse_solve execution on MAST-U equilibrium."""
        rx, zx = 0.6, 1.1
        nulls = FieldNullConstraint(x=np.array([rx, rx]), z=np.array([zx, -zx]))
        isoflux = IsofluxConstraint(
            x=np.array([0.34, 1.4, 1.0, 1.0]),
            z=np.array([0.0, 0.0, 2.0, -2.0]),
            ref_x=rx,
            ref_z=zx,
        )
        cset = MagneticConstraintSet([nulls, isoflux])

        # Exclude Solenoid from control
        mastu_equilibrium.coilset.control = [
            n for n in mastu_equilibrium.coilset.name if not n.startswith("Solenoid")
        ]

        result = run_inverse_solve(
            mastu_equilibrium,
            constraints=cset,
            max_iterations=20,
            target_relative_tolerance=1e-4,
            suppress=True,
        )

        assert isinstance(result, InverseSolveResult)
        assert result.converged
        assert result.iterations >= 1
        assert np.isfinite(result.relative_error)
        assert result.relative_error <= 1e-4
        assert len(result.coil_currents) == 12
        assert np.isfinite(result.psi_axis)
        assert np.isfinite(result.psi_boundary)

    def test_run_inverse_solve_zero_initial_currents(self, mastu_equilibrium):
        """Test that inverse solve updates coil currents when initialized to zero."""
        rx, zx = 0.6, 1.1
        nulls = FieldNullConstraint(x=np.array([rx, rx]), z=np.array([zx, -zx]))
        isoflux = IsofluxConstraint(
            x=np.array([0.34, 1.4, 1.0, 1.0]),
            z=np.array([0.0, 0.0, 2.0, -2.0]),
            ref_x=rx,
            ref_z=zx,
        )
        cset = MagneticConstraintSet([nulls, isoflux])

        control_names = [
            n for n in mastu_equilibrium.coilset.name if not n.startswith("Solenoid")
        ]
        mastu_equilibrium.coilset.control = control_names

        for circ in mastu_equilibrium.coilset._coils:
            if any(cn in control_names for cn in circ.name):
                circ.current = 0.0

        result = run_inverse_solve(
            mastu_equilibrium,
            constraints=cset,
            max_iterations=35,
            target_relative_tolerance=1e-4,
            suppress=True,
        )

        assert isinstance(result, InverseSolveResult)
        assert result.converged
        updated_currents = [
            curr
            for label, curr in result.coil_currents.items()
            if not label.startswith("circuit_0")
        ]
        assert any(abs(c) > 100.0 for c in updated_currents)
        bluemira_pf_currents = [
            float(np.asarray(circ.current).flat[0])
            for circ in mastu_equilibrium.coilset._coils[1:]
        ]
        assert any(abs(c) > 100.0 for c in bluemira_pf_currents)

    def test_equilibrium_inverse_solve_method(self, mastu_equilibrium):
        """Test calling inverse_solve directly on Equilibrium."""
        rx, zx = 0.6, 1.1
        nulls = FieldNullConstraint(x=np.array([rx, rx]), z=np.array([zx, -zx]))
        isoflux = IsofluxConstraint(
            x=np.array([0.34, 1.4, 1.0, 1.0]),
            z=np.array([0.0, 0.0, 2.0, -2.0]),
            ref_x=rx,
            ref_z=zx,
        )
        cset = MagneticConstraintSet([nulls, isoflux])

        mastu_equilibrium.coilset.control = [
            n for n in mastu_equilibrium.coilset.name if not n.startswith("Solenoid")
        ]

        res = mastu_equilibrium.inverse_solve(
            cset,
            max_iterations=20,
            target_relative_tolerance=1e-4,
            suppress=True,
        )
        assert isinstance(res, InverseSolveResult)
        assert res.converged

    def test_inverse_gs_solver_runner(self, mastu_equilibrium):
        """Test InverseGSSolver wrapper class."""
        rx, zx = 0.6, 1.1
        nulls = FieldNullConstraint(x=np.array([rx, rx]), z=np.array([zx, -zx]))
        cset = MagneticConstraintSet([nulls])

        runner = InverseGSSolver(
            mastu_equilibrium,
            constraints=cset,
            max_iterations=4,
            target_relative_tolerance=1e-3,
        )
        res = runner.solve(suppress=True)
        assert isinstance(res, InverseSolveResult)

    def test_callback_invocation(self, mastu_equilibrium):
        """Test iteration callback function invocation during inverse solve."""
        rx, zx = 0.6, 1.1
        nulls = FieldNullConstraint(x=np.array([rx, rx]), z=np.array([zx, -zx]))
        cset = MagneticConstraintSet([nulls])

        call_records: list[tuple[int, float]] = []

        def callback_fn(iteration: int, _eq: Any, residual: float) -> None:
            call_records.append((iteration, residual))

        mastu_equilibrium.inverse_solve(
            cset,
            max_iterations=3,
            target_relative_tolerance=1e-4,
            callback=callback_fn,
            suppress=True,
        )
        assert len(call_records) >= 1
        assert call_records[0][0] == 1


class TestPicardIteratorIntegration:
    """Tests for PicardIterator backend delegation to FreeGSNKE."""

    def test_picard_iterator_freegsnke_backend(self):
        """Test PicardIterator running with backend='freegsnke'."""
        x = [5.4, 14.0, 17.0, 17.01, 14.4, 7.0, 2.9, 2.9, 2.9, 2.9, 2.9]
        z = [
            8.82,
            7.0,
            2.5,
            -2.5,
            -8.4,
            -10.45,
            6.6574,
            3.7503,
            -0.6105,
            -4.9713,
            -7.8784,
        ]
        dx = [0.6, 0.4, 0.5, 0.5, 0.7, 1.0, 0.4, 0.4, 0.4, 0.4, 0.4]
        dz = [0.6, 0.4, 0.5, 0.5, 0.7, 1.0, 1.4036, 1.4036, 2.85715, 1.4036, 1.4036]
        names = [f"PF_{i + 1}" for i in range(6)] + [f"CS_{i + 1}" for i in range(5)]

        coils = [
            Coil(xc, zc, dx=dxc, dz=dzc, name=name, ctype=name[:2])
            for name, xc, zc, dxc, dzc in zip(names, x, z, dx, dz, strict=False)
        ]
        coilset = CoilSet(*coils)
        grid = Grid(4.5, 14, -9, 9, 33, 33)
        profiles = CustomProfile(
            np.linspace(1, 0), -np.linspace(1, 0), R_0=9, B_0=6, I_p=10e6
        )
        eq = Equilibrium(coilset, grid, profiles)

        isoflux = IsofluxConstraint(
            x=np.array([6, 8, 12, 6]),
            z=np.array([0, 7, 0, -8]),
            ref_x=6,
            ref_z=0,
        )
        x_point = FieldNullConstraint(8, -8)
        targets = MagneticConstraintSet([isoflux, x_point])
        opt_problem = TikhonovCurrentCOP(eq, targets, gamma=1e-8)

        iterator = PicardIterator(
            opt_problem, backend="freegsnke", fixed_coils=True, maxiter=3
        )
        res = iterator()
        assert res.coilset is not None
        assert len(res.coilset.current) == len(coils)

    def test_picard_iterator_fallback_warning(self):
        """Test fallback to legacy Picard when fixed_coils=False."""
        x = [5.4, 14.0, 17.0]
        z = [8.82, 7.0, 2.5]
        dx = [0.6, 0.4, 0.5]
        dz = [0.6, 0.4, 0.5]
        names = ["PF_1", "PF_2", "PF_3"]

        coils = [
            Coil(xc, zc, dx=dxc, dz=dzc, name=name, ctype="PF")
            for name, xc, zc, dxc, dzc in zip(names, x, z, dx, dz, strict=False)
        ]
        coilset = CoilSet(*coils)
        grid = Grid(4.5, 14, -9, 9, 33, 33)
        profiles = CustomProfile(
            np.linspace(1, 0), -np.linspace(1, 0), R_0=9, B_0=6, I_p=10e6
        )
        eq = Equilibrium(coilset, grid, profiles)

        isoflux = IsofluxConstraint(
            x=np.array([6, 8, 12]),
            z=np.array([0, 7, 0]),
            ref_x=6,
            ref_z=0,
        )
        targets = MagneticConstraintSet([isoflux])
        opt_problem = TikhonovCurrentCOP(eq, targets, gamma=1e-8)

        # fixed_coils=False causes fallback to legacy
        iterator = PicardIterator(
            opt_problem, backend="freegsnke", fixed_coils=False, maxiter=2
        )
        res = iterator()
        assert res.coilset is not None
