# SPDX-FileCopyrightText: 2021-present M. Coleman, J. Cook, F. Franza
# SPDX-FileCopyrightText: 2021-present I.A. Maione, S. McIntosh
# SPDX-FileCopyrightText: 2021-present J. Morris, D. Short
#
# SPDX-License-Identifier: LGPL-2.1-or-later

"""
Bridge interface between Bluemira and FreeGSNKE.

This module provides data adapters and execution wrappers to delegate
Grad-Shafranov equilibrium solves from Bluemira to FreeGSNKE.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

# Ensure FreeCAD's bundled 'Ext' directory does not shadow standard lazy_loader
if any(p.endswith(("/Ext", "/Ext/")) for p in sys.path):
    sys.path = [p for p in sys.path if not p.endswith(("/Ext", "/Ext/"))]
if "lazy_loader" in sys.modules and not hasattr(
    sys.modules["lazy_loader"], "attach_stub"
):
    del sys.modules["lazy_loader"]
    if "lazy_loader.lazy_loader" in sys.modules:
        del sys.modules["lazy_loader.lazy_loader"]

import numpy as np
from freegsnke.GSstaticsolver import NKGSsolver
from freegsnke.build_machine import (
    apply_tokamak_components,
    build_tokamak_components,
)
from freegsnke.equilibrium_update import Equilibrium as FreeGSNKE_Equilibrium
from freegsnke.inverse import Inverse_optimizer
from freegsnke.jtor_update import GeneralPprimeFFprime
from freegsnke.machine_update import Machine

from bluemira.base.look_and_feel import bluemira_warn
from bluemira.equilibria.coils import Circuit, Coil, CoilSet, SymmetricCircuit
from bluemira.equilibria.error import EquilibriaError
from bluemira.equilibria.optimisation.constraints import (
    CoilForceConstraints,
    DPsiDxConstraint,
    DPsiDzConstraint,
    FieldNullConstraint,
    IsofluxConstraint,
    MagneticConstraint,
    MagneticConstraintSet,
    PsiBoundaryConstraint,
    PsiConstraint,
    RadialFieldConstraint,
    VerticalFieldConstraint,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from bluemira.equilibria.equilibrium import Equilibrium
    from bluemira.equilibria.grid import Grid
    from bluemira.equilibria.limiter import Limiter
    from bluemira.equilibria.profiles import Profile

_PSI_TOL: float = 1e-12


@dataclass
class ForwardSolveResult:
    """
    Diagnostics and convergence metrics from a FreeGSNKE forward solve.

    Attributes
    ----------
    converged:
        Whether the nonlinear solve met the convergence threshold.
    iterations:
        Total number of Newton-Krylov solver iterations performed.
    relative_error:
        Final relative residual error reached by the solver.
    psi_axis:
        Poloidal magnetic flux at magnetic axis in Wb/rad.
    psi_boundary:
        Poloidal magnetic flux at plasma boundary in Wb/rad.
    plasma_current:
        Total toroidal plasma current Ip in Amperes.
    time_taken:
        Execution time in seconds.
    has_relevant_xpoint:
        Whether a relevant magnetic X-point was detected within the limiter.
    """

    converged: bool
    iterations: int
    relative_error: float
    psi_axis: float
    psi_boundary: float
    plasma_current: float
    time_taken: float
    has_relevant_xpoint: bool


@dataclass
class InverseSolveResult:
    """
    Diagnostics and convergence metrics from a FreeGSNKE inverse solve.

    Attributes
    ----------
    converged:
        Whether the inverse solve met the convergence threshold.
    iterations:
        Total number of solver iterations performed.
    relative_error:
        Final relative residual error reached by the solver.
    psi_axis:
        Poloidal magnetic flux at magnetic axis in Wb/rad.
    psi_boundary:
        Poloidal magnetic flux at plasma boundary in Wb/rad.
    plasma_current:
        Total toroidal plasma current Ip in Amperes.
    time_taken:
        Execution time in seconds.
    has_relevant_xpoint:
        Whether a relevant magnetic X-point was detected within the limiter.
    coil_currents:
        Dictionary mapping coil/circuit name to optimized current in Amperes.
    """

    converged: bool
    iterations: int
    relative_error: float
    psi_axis: float
    psi_boundary: float
    plasma_current: float
    time_taken: float
    has_relevant_xpoint: bool
    coil_currents: dict[str, float]


def coilset_to_freegsnke_tokamak(
    coilset: CoilSet,
    limiter: Limiter | None = None,
    grid: Grid | None = None,
) -> Machine:
    """
    Convert a Bluemira CoilSet and Limiter into a FreeGSNKE Machine.

    Parameters
    ----------
    coilset:
        Bluemira CoilSet containing individual coils and circuits.
    limiter:
        Optional Bluemira Limiter defining the wall/limiter boundary.
    grid:
        Optional Bluemira Grid used as fallback boundary if no limiter provided.

    Returns
    -------
    Machine:
        FreeGSNKE Machine instance ready for forward or inverse solve.

    Raises
    ------
    EquilibriaError
        If neither limiter nor grid boundary is provided.
    """
    active_coils_data = {}
    coil_currents = {}

    for name, item in coilset.items():
        if isinstance(item, (Circuit, SymmetricCircuit)):
            r_coords = [float(coil.x) for coil in item.coils]
            z_coords = [float(coil.z) for coil in item.coils]
            dr_coords = [float(2 * coil.dx) for coil in item.coils]
            dz_coords = [float(2 * coil.dz) for coil in item.coils]
            current = float(item.current)
            active_coils_data[name] = {
                "R": r_coords,
                "Z": z_coords,
                "dR": dr_coords,
                "dZ": dz_coords,
            }
            coil_currents[name] = current
        elif isinstance(item, Coil):
            r = float(item.x)
            z = float(item.z)
            dr = float(2 * item.dx)
            dz = float(2 * item.dz)
            current = float(item.current)
            active_coils_data[name] = {
                "R": [r],
                "Z": [z],
                "dR": [dr],
                "dZ": [dz],
            }
            coil_currents[name] = current

    if limiter is not None:
        limiter_data = [
            {"R": float(r), "Z": float(z)}
            for r, z in zip(limiter.x, limiter.z, strict=False)
        ]
    elif grid is not None:
        dr = 0.01 * (grid.x_max - grid.x_min)
        dz = 0.01 * (grid.z_max - grid.z_min)
        limiter_data = [
            {"R": float(grid.x_min + dr), "Z": float(grid.z_min + dz)},
            {"R": float(grid.x_max - dr), "Z": float(grid.z_min + dz)},
            {"R": float(grid.x_max - dr), "Z": float(grid.z_max - dz)},
            {"R": float(grid.x_min + dr), "Z": float(grid.z_max - dz)},
        ]
    else:
        raise EquilibriaError(
            "A limiter or grid boundary must be provided to construct "
            "a FreeGSNKE Machine."
        )

    components = build_tokamak_components(
        active_coils_data=active_coils_data,
        limiter_data=limiter_data,
    )
    tokamak = Machine(
        components["coil_circuits"],
        wall=components["wall"],
        limiter=components["limiter"],
    )
    apply_tokamak_components(tokamak, components, rebuild_R_and_M=False)

    for name, current in coil_currents.items():
        if name in tokamak.coil_names:
            tokamak.set_coil_current(name, current)

    # Configure controllable coils for inverse solving
    ctrl = getattr(coilset, "control", None)
    control_names = set(ctrl) if ctrl is not None else set(coil_currents.keys())
    for label, coil_elem in tokamak.coils:
        coil_elem.control = bool(label in control_names)

    return tokamak


def profile_to_freegsnke(
    profile: Profile,
    freegsnke_eq: FreeGSNKE_Equilibrium,
    num_points: int = 100,
) -> GeneralPprimeFFprime:
    """
    Convert a Bluemira Profile into a FreeGSNKE GeneralPprimeFFprime profile.

    Parameters
    ----------
    profile:
        Bluemira Profile instance providing pprime and ffprime functions.
    freegsnke_eq:
        FreeGSNKE Equilibrium instance the profile will be assigned to.
    num_points:
        Number of discretization points along normalized poloidal flux psi_n.

    Returns
    -------
    GeneralPprimeFFprime:
        FreeGSNKE profile ready for forward or inverse solve.
    """
    psi_n = np.linspace(0.0, 1.0, num_points)

    pprime_bluemira = profile.pprime(psi_n)
    ffprime_bluemira = profile.ffprime(psi_n)

    pprime_freegsnke = np.asarray(pprime_bluemira, dtype=np.float64)
    ffprime_freegsnke = np.asarray(ffprime_bluemira, dtype=np.float64)

    ip = float(profile.I_p) if profile.I_p is not None else 0.0

    if (
        getattr(profile, "B_0", None) is not None
        and getattr(profile, "R_0", None) is not None
    ):
        fvac = float(profile.R_0 * profile.B_0)
    elif hasattr(profile, "fvac") and callable(profile.fvac):
        fvac = float(profile.fvac())
    else:
        fvac = 1.0

    return GeneralPprimeFFprime(
        freegsnke_eq,
        Ip=ip,
        fvac=fvac,
        psi_n=psi_n,
        pprime_data=pprime_freegsnke,
        ffprime_data=ffprime_freegsnke,
        interpolator="univariate_spline",
    )


def update_bluemira_from_freegsnke(
    bluemira_eq: Equilibrium,
    freegsnke_eq: FreeGSNKE_Equilibrium,
    freegsnke_profiles: GeneralPprimeFFprime,
) -> None:
    """
    Map FreeGSNKE solve state back onto a Bluemira Equilibrium object.

    Parameters
    ----------
    bluemira_eq:
        Bluemira Equilibrium to update in-place.
    freegsnke_eq:
        Solved FreeGSNKE Equilibrium instance.
    freegsnke_profiles:
        FreeGSNKE plasma profile from solve.
    """
    psi_total = freegsnke_eq.psi()
    bluemira_eq._psi = psi_total.copy()
    bluemira_eq.grid._psi = psi_total.copy()

    bluemira_eq._psi_axis = float(freegsnke_eq.psi_axis)
    bluemira_eq._psi_boundary = float(freegsnke_eq.psi_bndry)

    psi_1d = np.ascontiguousarray(bluemira_eq.grid.psi.flatten())
    bluemira_eq._p = freegsnke_profiles.pressure(psi_1d)
    bluemira_eq._fpol = freegsnke_profiles.fpol(psi_1d)
    bluemira_eq._pprime = freegsnke_profiles.pprime(psi_1d)
    bluemira_eq._ffprime = freegsnke_profiles.ffprime(psi_1d)

    j_tor = np.asarray(freegsnke_eq.jtor(), dtype=np.float64)
    bluemira_eq._j_tor = j_tor.copy()

    total_ip = float(freegsnke_eq.plasmaCurrent())
    bluemira_eq._I_p = total_ip

    bluemira_eq._recompute_fields()


def run_forward_solve(
    bluemira_eq: Equilibrium,
    *,
    target_relative_tolerance: float = 1e-6,
    max_iterations: int = 100,
    order: int = 2,
    force_up_down_symmetric: bool | None = None,
    picard_handover: float = 0.11,
    verbose: bool = False,
    suppress: bool = True,
    **solver_kwargs: Any,
) -> ForwardSolveResult:
    """
    Execute FreeGSNKE's static forward Grad-Shafranov solve on a Bluemira Equilibrium.

    Parameters
    ----------
    bluemira_eq:
        Bluemira Equilibrium containing coils, grid, profiles, and optional limiter.
    target_relative_tolerance:
        Relative nonlinear residual convergence threshold. Default is 1e-6.
    max_iterations:
        Maximum nonlinear Newton-Krylov iterations. Default is 100.
    order:
        Finite-difference spatial operator order (2 or 4). Default is 2.
    force_up_down_symmetric:
        Whether to enforce up-down symmetry at each iteration. If None,
        defaults to `bluemira_eq._force_symmetry`.
    picard_handover:
        Residual tolerance handover threshold between Picard and Newton-Krylov steps.
    verbose:
        Enable verbose iteration logging to stdout. Default is False.
    suppress:
        Suppress FreeGSNKE stdout output. Default is True.
    **solver_kwargs:
        Additional keyword arguments forwarded to FreeGSNKE's `NKGSsolver.forward_solve`.

    Returns
    -------
    ForwardSolveResult
        Convergence diagnostics and execution metrics.

    Raises
    ------
    EquilibriaError
        If required equilibrium components are missing or solver fails.
    """
    t0 = time.perf_counter()

    if bluemira_eq.coilset is None or not bluemira_eq.coilset._coils:
        raise EquilibriaError(
            "Cannot perform forward solve: Equilibrium has no coils configured."
        )

    if bluemira_eq.profiles is None:
        raise EquilibriaError(
            "Cannot perform forward solve: Equilibrium has no profiles configured."
        )

    if bluemira_eq.grid is None:
        raise EquilibriaError(
            "Cannot perform forward solve: Equilibrium has no grid configured."
        )

    # 1. Build FreeGSNKE Machine
    tokamak = coilset_to_freegsnke_tokamak(
        bluemira_eq.coilset,
        limiter=bluemira_eq.limiter,
        grid=bluemira_eq.grid,
    )

    # 2. Build FreeGSNKE Equilibrium
    freegsnke_eq = FreeGSNKE_Equilibrium(
        tokamak=tokamak,
        Rmin=float(bluemira_eq.grid.x_min),
        Rmax=float(bluemira_eq.grid.x_max),
        Zmin=float(bluemira_eq.grid.z_min),
        Zmax=float(bluemira_eq.grid.z_max),
        nx=int(bluemira_eq.grid.nx),
        ny=int(bluemira_eq.grid.nz),
    )

    # Warm-start from existing plasma psi if available
    if (
        hasattr(bluemira_eq, "plasma")
        and bluemira_eq.plasma is not None
        and hasattr(bluemira_eq.plasma, "psi")
    ):
        try:
            current_psi = bluemira_eq.plasma.psi()
            if current_psi is not None and np.any(np.abs(current_psi) > _PSI_TOL):
                freegsnke_eq.plasma_psi = np.asarray(
                    current_psi, dtype=np.float64
                ).copy()
        except Exception:  # noqa: BLE001, S110
            pass

    # 3. Build FreeGSNKE Profile
    freegsnke_profiles = profile_to_freegsnke(bluemira_eq.profiles, freegsnke_eq)

    # 4. Configure Symmetry
    symmetric = (
        bool(getattr(bluemira_eq, "force_symmetry", False))
        if force_up_down_symmetric is None
        else bool(force_up_down_symmetric)
    )

    # 5. Build and execute Solver
    solver = NKGSsolver(
        freegsnke_eq,
        gs_operator_order=order,
    )

    solver.forward_solve(
        freegsnke_eq,
        freegsnke_profiles,
        target_relative_tolerance=target_relative_tolerance,
        max_solving_iterations=max_iterations,
        Picard_handover=picard_handover,
        force_up_down_symmetric=symmetric,
        verbose=verbose,
        suppress=suppress,
        **solver_kwargs,
    )

    # 6. Back-propagate solution to Bluemira
    update_bluemira_from_freegsnke(bluemira_eq, freegsnke_eq, freegsnke_profiles)

    time_taken = time.perf_counter() - t0
    rel_error = getattr(solver, "relative_change", float("nan"))
    norm_rel = getattr(solver, "norm_rel_change", [])
    iterations = max(0, len(norm_rel) - 1) if norm_rel else 0
    converged = bool(rel_error <= target_relative_tolerance)

    psi_ax_val = (
        float(bluemira_eq.psi_ax) if bluemira_eq.psi_ax is not None else float("nan")
    )
    psi_b_val = (
        float(bluemira_eq.psi_b) if bluemira_eq.psi_b is not None else float("nan")
    )
    ip_val = float(bluemira_eq._I_p) if bluemira_eq._I_p is not None else float("nan")

    return ForwardSolveResult(
        converged=converged,
        iterations=iterations,
        relative_error=float(rel_error),
        psi_axis=psi_ax_val,
        psi_boundary=psi_b_val,
        plasma_current=ip_val,
        time_taken=time_taken,
        has_relevant_xpoint=bool(getattr(freegsnke_eq, "has_relevant_xpoint", False)),
    )


class ForwardGSSolver:
    """
    Object-oriented runner for FreeGSNKE static forward Grad-Shafranov solves.

    Parameters
    ----------
    eq:
        Bluemira Equilibrium instance to solve.
    target_relative_tolerance:
        Relative convergence tolerance. Default is 1e-6.
    max_iterations:
        Maximum iterations. Default is 100.
    order:
        Finite-difference operator order (2 or 4). Default is 2.
    force_up_down_symmetric:
        Whether to enforce up-down symmetry.
    picard_handover:
        Threshold to switch from Picard to Newton-Krylov.
    """

    def __init__(
        self,
        eq: Equilibrium,
        *,
        target_relative_tolerance: float = 1e-6,
        max_iterations: int = 100,
        order: int = 2,
        force_up_down_symmetric: bool | None = None,
        picard_handover: float = 0.11,
    ):
        self.eq = eq
        self.target_relative_tolerance = target_relative_tolerance
        self.max_iterations = max_iterations
        self.order = order
        self.force_up_down_symmetric = force_up_down_symmetric
        self.picard_handover = picard_handover

    def solve(
        self,
        *,
        verbose: bool = False,
        suppress: bool = True,
        **kwargs: Any,
    ) -> ForwardSolveResult:
        """
        Execute the forward solve.

        Parameters
        ----------
        verbose:
            Print iteration diagnostics.
        suppress:
            Suppress console output.
        **kwargs:
            Additional arguments forwarded to `run_forward_solve`.

        Returns
        -------
        ForwardSolveResult
            Convergence metrics and diagnostics.
        """
        return run_forward_solve(
            self.eq,
            target_relative_tolerance=self.target_relative_tolerance,
            max_iterations=self.max_iterations,
            order=self.order,
            force_up_down_symmetric=self.force_up_down_symmetric,
            picard_handover=self.picard_handover,
            verbose=verbose,
            suppress=suppress,
            **kwargs,
        )


def _extract_isoflux_constraint(c: IsofluxConstraint) -> list[np.ndarray]:
    """
    Extract (R, Z, weights) array for an IsofluxConstraint.

    Parameters
    ----------
    c:
        The IsofluxConstraint instance.

    Returns
    -------
    list[np.ndarray]
        List containing R, Z, and weight arrays.
    """
    rx = np.append(np.atleast_1d(c.x), c.ref_x)
    rz = np.append(np.atleast_1d(c.z), c.ref_z)
    w = getattr(c, "weights", None)
    if w is not None and np.iterable(w):
        rw = np.append(np.atleast_1d(w), 1.0)
    elif w is not None and not np.iterable(w):
        rw = np.ones_like(rx) * float(w)
    else:
        rw = np.ones_like(rx)
    return [rx, rz, rw]


def _extract_psi_constraint(
    c: PsiConstraint | PsiBoundaryConstraint,
) -> tuple[list[float], list[float], list[float]]:
    """
    Extract (R, Z, psi_targets) for direct flux constraints.

    Parameters
    ----------
    c:
        The flux constraint instance.

    Returns
    -------
    tuple[list[float], list[float], list[float]]
        Lists of R coordinates, Z coordinates, and target flux values.
    """
    t_val = getattr(c, "target_value", None)
    if t_val is None:
        t_val = getattr(c, "target", 0.0)
    t_val_arr = np.atleast_1d(t_val)
    xs = np.atleast_1d(c.x)
    zs = np.atleast_1d(c.z)
    if len(t_val_arr) == 1 and len(xs) > 1:
        t_val_arr = np.repeat(t_val_arr, len(xs))
    return list(xs), list(zs), list(t_val_arr)


def _extract_field_constraint(
    c: (
        VerticalFieldConstraint
        | RadialFieldConstraint
        | DPsiDxConstraint
        | DPsiDzConstraint
    ),
) -> tuple[list[float], list[float], list[float], list[float], list[float]]:
    """
    Extract (R, Z, Br, Bz, weight) for field-like constraints.

    Parameters
    ----------
    c:
        The field-like magnetic constraint.

    Returns
    -------
    tuple[list[float], list[float], list[float], list[float], list[float]]
        Lists of R, Z, Br targets, Bz targets, and weights.
    """
    xs = np.atleast_1d(c.x)
    zs = np.atleast_1d(c.z)
    t_val = np.atleast_1d(getattr(c, "target_value", getattr(c, "target", 0.0)))
    if len(t_val) == 1 and len(xs) > 1:
        t_val = np.repeat(t_val, len(xs))
    w_arr = np.atleast_1d(getattr(c, "weights", 1.0))
    if len(w_arr) == 1 and len(xs) > 1:
        w_arr = np.repeat(w_arr, len(xs))

    r_out, z_out, br_out, bz_out, w_out = [], [], [], [], []
    for r, z, val, wt in zip(xs, zs, t_val, w_arr, strict=False):
        r_val = float(r)
        r_out.append(r_val)
        z_out.append(float(z))
        w_out.append(float(wt))
        if isinstance(c, VerticalFieldConstraint):
            br_out.append(np.nan)
            bz_out.append(float(val))
        elif isinstance(c, RadialFieldConstraint):
            br_out.append(float(val))
            bz_out.append(np.nan)
        elif isinstance(c, DPsiDxConstraint):
            br_out.append(np.nan)
            bz_out.append(float(-val / (2.0 * np.pi * r_val)))
        elif isinstance(c, DPsiDzConstraint):
            br_out.append(float(val / (2.0 * np.pi * r_val)))
            bz_out.append(np.nan)

    return r_out, z_out, br_out, bz_out, w_out


def _extract_coil_current_limits(
    coilset: CoilSet | None,
) -> list[list[float | None]] | None:
    """
    Extract upper and lower current limits for controllable coils.

    Parameters
    ----------
    coilset:
        Optional Bluemira CoilSet containing coils and bounds.

    Returns
    -------
    list[list[float | None]] | None
        Pair of upper and lower limits, or None if no limits exist.
    """
    if coilset is None:
        return None

    ctrl = getattr(coilset, "control", None)
    control_names = set(ctrl) if ctrl is not None else None
    control_coils = [
        coil
        for coil in coilset
        if getattr(coil, "control", True)
        and (control_names is None or coil.name in control_names)
    ]
    upper_limits: list[float | None] = []
    lower_limits: list[float | None] = []
    has_limits = False
    for coil in control_coils:
        c_min = getattr(coil, "current_min", None)
        c_max = getattr(coil, "current_max", None)
        if c_min is not None or c_max is not None:
            has_limits = True
        lower_limits.append(float(c_min) if c_min is not None else None)
        upper_limits.append(float(c_max) if c_max is not None else None)

    return [upper_limits, lower_limits] if has_limits else None


def constraints_to_freegsnke(
    constraints: (
        MagneticConstraintSet | list[MagneticConstraint | Any] | MagneticConstraint
    ),
    coilset: CoilSet | None = None,
    *,
    weight_isoflux: float = 1.0,
    weight_nulls: float = 1.0,
    weight_psi: float = 1.0,
    weight_fields: float = 1.0,
    mu_coils: float = 1e5,
    mu_forces: float = 1e4,
) -> Inverse_optimizer:
    """
    Convert Bluemira magnetic constraints into a FreeGSNKE Inverse_optimizer.

    Parameters
    ----------
    constraints:
        Bluemira MagneticConstraintSet, list of constraints, or single constraint.
    coilset:
        Optional Bluemira CoilSet to extract current bounds and controllable coils.
    weight_isoflux:
        Weight for isoflux constraints.
    weight_nulls:
        Weight for null point constraints.
    weight_psi:
        Weight for direct psi value constraints.
    weight_fields:
        Weight for magnetic field (Br, Bz) target constraints.
    mu_coils:
        Penalty factor for coil current limit violations.
    mu_forces:
        Penalty factor for coil force limit violations.

    Returns
    -------
    Inverse_optimizer
        FreeGSNKE Inverse_optimizer initialized with all mapped constraints.
    """
    if isinstance(constraints, Inverse_optimizer):
        return constraints

    if isinstance(constraints, MagneticConstraintSet):
        constraint_list = list(constraints.constraints)
    elif isinstance(constraints, (list, tuple)):
        constraint_list = list(constraints)
    else:
        constraint_list = [constraints]

    isoflux_sets: list[list[np.ndarray]] = []
    r_null: list[float] = []
    z_null: list[float] = []
    r_psi: list[float] = []
    z_psi: list[float] = []
    psi_values: list[float] = []
    r_field: list[float] = []
    z_field: list[float] = []
    br_target: list[float] = []
    bz_target: list[float] = []
    w_field: list[float] = []
    coil_force_limits = None

    for c in constraint_list:
        if isinstance(c, IsofluxConstraint):
            isoflux_sets.append(_extract_isoflux_constraint(c))
        elif isinstance(c, FieldNullConstraint):
            r_null.extend(np.atleast_1d(c.x))
            z_null.extend(np.atleast_1d(c.z))
        elif isinstance(c, (PsiConstraint, PsiBoundaryConstraint)):
            rp, zp, pv = _extract_psi_constraint(c)
            r_psi.extend(rp)
            z_psi.extend(zp)
            psi_values.extend(pv)
        elif isinstance(
            c,
            (
                VerticalFieldConstraint,
                RadialFieldConstraint,
                DPsiDxConstraint,
                DPsiDzConstraint,
            ),
        ):
            rf, zf, brf, bzf, wf = _extract_field_constraint(c)
            r_field.extend(rf)
            z_field.extend(zf)
            br_target.extend(brf)
            bz_target.extend(bzf)
            w_field.extend(wf)
        elif isinstance(c, CoilForceConstraints):
            coil_force_limits = {
                "PF_Fz_max": float(c._args.get("PF_Fz_max", 1e8)),
                "CS_Fz_sum_max": float(c._args.get("CS_Fz_sum_max", 1e8)),
                "CS_Fz_sep_max": float(c._args.get("CS_Fz_sep_max", 1e8)),
            }
        else:
            bluemira_warn(
                f"Constraint {type(c).__name__} is not directly translated to FreeGSNKE."
            )

    coil_current_limits = _extract_coil_current_limits(coilset)
    isoflux_set_arg = [np.vstack(s) for s in isoflux_sets] if isoflux_sets else None
    null_points_arg = (
        [np.array(r_null, dtype=float), np.array(z_null, dtype=float)]
        if r_null
        else None
    )
    psi_vals_arg = (
        [
            np.array(r_psi, dtype=float),
            np.array(z_psi, dtype=float),
            np.array(psi_values, dtype=float),
        ]
        if r_psi
        else None
    )
    field_targets_arg = (
        [
            np.array(r_field, dtype=float),
            np.array(z_field, dtype=float),
            np.array(br_target, dtype=float),
            np.array(bz_target, dtype=float),
            np.array(w_field, dtype=float),
        ]
        if r_field
        else None
    )

    return Inverse_optimizer(
        isoflux_set=isoflux_set_arg,
        null_points=null_points_arg,
        psi_vals=psi_vals_arg,
        coil_current_limits=coil_current_limits,
        field_targets=field_targets_arg,
        coil_force_limits=coil_force_limits,
        weight_isoflux=weight_isoflux,
        weight_nulls=weight_nulls,
        weight_psi=weight_psi,
        weight_fields=weight_fields,
        mu_coils=mu_coils,
        mu_forces=mu_forces,
    )


def run_inverse_solve(
    bluemira_eq: Equilibrium,
    constraints: (
        MagneticConstraintSet
        | list[MagneticConstraint | Any]
        | MagneticConstraint
        | None
    ) = None,
    *,
    target_relative_tolerance: float = 1e-5,
    max_iterations: int = 100,
    max_iter_per_update: int = 5,
    picard_handover: float = 0.15,
    order: int = 2,
    force_up_down_symmetric: bool | None = None,
    callback: Callable[[int, Any, float], None] | None = None,
    weight_isoflux: float = 1.0,
    weight_nulls: float = 1.0,
    weight_psi: float = 1.0,
    weight_fields: float = 1.0,
    mu_coils: float = 1e5,
    mu_forces: float = 1e4,
    verbose: bool = False,
    suppress: bool = True,
    **solver_kwargs: Any,
) -> InverseSolveResult:
    """
    Execute an inverse Grad-Shafranov solve on a Bluemira Equilibrium using FreeGSNKE.

    Parameters
    ----------
    bluemira_eq:
        The Bluemira Equilibrium instance to solve and update in-place.
    constraints:
        Magnetic constraints (MagneticConstraintSet, list of constraints,
        or FreeGSNKE Inverse_optimizer).
    target_relative_tolerance:
        Relative convergence tolerance. Default is 1e-5.
    max_iterations:
        Maximum outer solving iterations. Default is 100.
    max_iter_per_update:
        Inner forward solve iterations per coil update. Default is 5.
    picard_handover:
        Threshold to switch from Picard to Newton-Krylov. Default is 0.15.
    order:
        Finite-difference operator order (2 or 4). Default is 2.
    force_up_down_symmetric:
        Whether to enforce up-down symmetry. Defaults to bluemira_eq.force_symmetry.
    callback:
        Optional hook called after each outer iteration: callback(iter, eq, res).
    weight_isoflux:
        Weight for isoflux constraints. Default is 1.0.
    weight_nulls:
        Weight for null point constraints. Default is 1.0.
    weight_psi:
        Weight for direct psi value constraints. Default is 1.0.
    weight_fields:
        Weight for magnetic field target constraints. Default is 1.0.
    mu_coils:
        Penalty factor for coil current limit violations. Default is 1e5.
    mu_forces:
        Penalty factor for coil force limit violations. Default is 1e4.
    verbose:
        Print iteration diagnostics.
    suppress:
        Suppress console output.
    **solver_kwargs:
        Additional keyword arguments passed to `NKGSsolver.inverse_solve`.

    Returns
    -------
    InverseSolveResult
        Detailed metrics and diagnostics of the inverse solve.

    Raises
    ------
    EquilibriaError
        If constraints are not provided.
    """
    if constraints is None:
        raise EquilibriaError(
            "Inverse solve requires magnetic constraints or an Inverse_optimizer."
        )

    if isinstance(constraints, Inverse_optimizer):
        optimizer = constraints
    else:
        optimizer = constraints_to_freegsnke(
            constraints,
            bluemira_eq.coilset,
            weight_isoflux=weight_isoflux,
            weight_nulls=weight_nulls,
            weight_psi=weight_psi,
            weight_fields=weight_fields,
            mu_coils=mu_coils,
            mu_forces=mu_forces,
        )

    tokamak = coilset_to_freegsnke_tokamak(
        bluemira_eq.coilset,
        limiter=bluemira_eq.limiter,
        grid=bluemira_eq.grid,
    )

    freegsnke_eq = FreeGSNKE_Equilibrium(
        tokamak=tokamak,
        Rmin=float(bluemira_eq.grid.x_min),
        Rmax=float(bluemira_eq.grid.x_max),
        Zmin=float(bluemira_eq.grid.z_min),
        Zmax=float(bluemira_eq.grid.z_max),
        nx=int(bluemira_eq.grid.nx),
        ny=int(bluemira_eq.grid.nz),
    )

    if getattr(bluemira_eq, "_psi", None) is not None:
        freegsnke_eq.plasma_psi = np.asarray(bluemira_eq._psi, dtype=np.float64)
    elif getattr(bluemira_eq, "psi", None) is not None:
        psi_val = bluemira_eq.psi() if callable(bluemira_eq.psi) else bluemira_eq.psi
        if psi_val is not None:
            freegsnke_eq.plasma_psi = np.asarray(psi_val, dtype=np.float64)

    freegsnke_profiles = profile_to_freegsnke(bluemira_eq.profiles, freegsnke_eq)

    symmetric = (
        bool(getattr(bluemira_eq, "force_symmetry", False))
        if force_up_down_symmetric is None
        else bool(force_up_down_symmetric)
    )

    solver = NKGSsolver(freegsnke_eq, gs_operator_order=order)

    t0 = time.perf_counter()
    solver.inverse_solve(
        freegsnke_eq,
        freegsnke_profiles,
        constrain=optimizer,
        target_relative_tolerance=target_relative_tolerance,
        max_solving_iterations=max_iterations,
        max_iter_per_update=max_iter_per_update,
        Picard_handover=picard_handover,
        force_up_down_symmetric=symmetric,
        callback=callback,
        verbose=verbose,
        suppress=suppress,
        **solver_kwargs,
    )
    time_taken = time.perf_counter() - t0

    update_bluemira_from_freegsnke(bluemira_eq, freegsnke_eq, freegsnke_profiles)

    optimized_currents: dict[str, float] = {}
    for label, coil_elem in freegsnke_eq.tokamak.coils:
        curr = float(getattr(coil_elem, "current", 0.0))
        optimized_currents[label] = curr
        if label in bluemira_eq.coilset:
            bluemira_eq.coilset[label].current = curr

    rel_error = getattr(solver, "relative_change", float("nan"))
    norm_rel = getattr(solver, "norm_rel_change", [])
    iterations = max(0, len(norm_rel) - 1) if norm_rel else 0
    converged = bool(rel_error <= target_relative_tolerance)

    psi_ax_val = (
        float(bluemira_eq.psi_ax) if bluemira_eq.psi_ax is not None else float("nan")
    )
    psi_b_val = (
        float(bluemira_eq.psi_b) if bluemira_eq.psi_b is not None else float("nan")
    )
    ip_val = float(bluemira_eq._I_p) if bluemira_eq._I_p is not None else float("nan")

    return InverseSolveResult(
        converged=converged,
        iterations=iterations,
        relative_error=float(rel_error),
        psi_axis=psi_ax_val,
        psi_boundary=psi_b_val,
        plasma_current=ip_val,
        time_taken=time_taken,
        has_relevant_xpoint=bool(getattr(freegsnke_eq, "has_relevant_xpoint", False)),
        coil_currents=optimized_currents,
    )


class InverseGSSolver:
    """
    Object-oriented runner for FreeGSNKE static inverse Grad-Shafranov solves.

    Parameters
    ----------
    eq:
        Bluemira Equilibrium instance to solve.
    constraints:
        Magnetic constraints (MagneticConstraintSet, list of constraints,
        or FreeGSNKE Inverse_optimizer).
    target_relative_tolerance:
        Relative convergence tolerance. Default is 1e-5.
    max_iterations:
        Maximum outer solving iterations. Default is 100.
    max_iter_per_update:
        Inner forward solve iterations per coil update. Default is 5.
    order:
        Finite-difference operator order (2 or 4). Default is 2.
    force_up_down_symmetric:
        Whether to enforce up-down symmetry.
    picard_handover:
        Threshold to switch from Picard to Newton-Krylov.
    callback:
        Optional hook called after each outer iteration: callback(iter, eq, res).
    weight_isoflux:
        Weight for isoflux constraints.
    weight_nulls:
        Weight for null point constraints.
    weight_psi:
        Weight for direct psi value constraints.
    weight_fields:
        Weight for magnetic field target constraints.
    mu_coils:
        Penalty factor for coil current limit violations.
    mu_forces:
        Penalty factor for coil force limit violations.
    """

    def __init__(
        self,
        eq: Equilibrium,
        constraints: (
            MagneticConstraintSet
            | list[MagneticConstraint | Any]
            | MagneticConstraint
            | None
        ) = None,
        *,
        target_relative_tolerance: float = 1e-5,
        max_iterations: int = 100,
        max_iter_per_update: int = 5,
        order: int = 2,
        force_up_down_symmetric: bool | None = None,
        picard_handover: float = 0.15,
        callback: Callable[[int, Any, float], None] | None = None,
        weight_isoflux: float = 1.0,
        weight_nulls: float = 1.0,
        weight_psi: float = 1.0,
        weight_fields: float = 1.0,
        mu_coils: float = 1e5,
        mu_forces: float = 1e4,
    ):
        self.eq = eq
        self.constraints = constraints
        self.target_relative_tolerance = target_relative_tolerance
        self.max_iterations = max_iterations
        self.max_iter_per_update = max_iter_per_update
        self.order = order
        self.force_up_down_symmetric = force_up_down_symmetric
        self.picard_handover = picard_handover
        self.callback = callback
        self.weight_isoflux = weight_isoflux
        self.weight_nulls = weight_nulls
        self.weight_psi = weight_psi
        self.weight_fields = weight_fields
        self.mu_coils = mu_coils
        self.mu_forces = mu_forces

    def solve(
        self,
        *,
        verbose: bool = False,
        suppress: bool = True,
        **kwargs: Any,
    ) -> InverseSolveResult:
        """
        Execute the inverse solve.

        Parameters
        ----------
        verbose:
            Print iteration diagnostics.
        suppress:
            Suppress console output.
        **kwargs:
            Additional arguments forwarded to `run_inverse_solve`.

        Returns
        -------
        InverseSolveResult
            Convergence metrics and diagnostics.
        """
        return run_inverse_solve(
            self.eq,
            constraints=self.constraints,
            target_relative_tolerance=self.target_relative_tolerance,
            max_iterations=self.max_iterations,
            max_iter_per_update=self.max_iter_per_update,
            order=self.order,
            force_up_down_symmetric=self.force_up_down_symmetric,
            picard_handover=self.picard_handover,
            callback=self.callback,
            weight_isoflux=self.weight_isoflux,
            weight_nulls=self.weight_nulls,
            weight_psi=self.weight_psi,
            weight_fields=self.weight_fields,
            mu_coils=self.mu_coils,
            mu_forces=self.mu_forces,
            verbose=verbose,
            suppress=suppress,
            **kwargs,
        )
