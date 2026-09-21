# SPDX-FileCopyrightText: 2021-present M. Coleman, J. Cook, F. Franza
# SPDX-FileCopyrightText: 2021-present I.A. Maione, S. McIntosh
# SPDX-FileCopyrightText: 2021-present J. Morris, D. Short
#
# SPDX-License-Identifier: LGPL-2.1-or-later
from dataclasses import dataclass
from typing import Any

import numpy as np

from bluemira.geometry.optimisation.typed import (
    GeomClsOptimiserCallable,
    GeomConstraintT,
    GeomOptimiserCallable,
    GeomOptimiserObjective,
)
from bluemira.geometry.parameterisations import GeometryParameterisation
from bluemira.geometry.tools import (
    _extract_2d_points,
    fast_2d_distance,
    signed_distance_2D_polygon,
)
from bluemira.geometry.wire import BluemiraWire
from bluemira.optimisation import ConstraintT, ObjectiveCallable, OptimiserCallable
from bluemira.optimisation.error import GeometryOptimisationError


@dataclass
class KeepOutZone:
    """Definition of a keep-out zone for a geometry optimisation."""

    wire: BluemiraWire
    """Closed wire defining the keep-out zone."""
    byedges: bool = True
    """Whether to discretise the keep-out zone by edges or not."""
    dl: float | None = None
    """
    The discretisation length for the keep-out zone.

    This overrides ``n_discr`` if given.
    """
    n_discr: int = 100
    """The number of points to discretise the keep-out zone into."""
    shape_n_discr: int = 100
    """The number of points to discretise the geometry being optimised into."""
    tol: float = 1e-8
    """The tolerance for the keep-out zone constraint."""


def wire_length_objective(geom: GeometryParameterisation) -> float:
    """
    Standard objective function evaluating perimeter wire length.

    Leverages lightweight pure-NumPy calculate_length if available on the
    parameterisation, falling back to CAD wire length.

    Parameters
    ----------
    geom:
        The geometry parameterisation being evaluated.

    Returns
    -------
    float:
        The perimeter length of the geometry [m].
    """
    if hasattr(geom, "calculate_length"):
        return geom.calculate_length()
    return float(geom.create_shape().length)


class GeomOptimisationContext:
    """
    Context that caches parameterisation state and discretized coordinates across
    multiple callbacks (objective, gradient, constraints, keep-out zones) evaluated
    at the same parameter vector x during an optimisation iteration.
    """

    def __init__(self, geom: GeometryParameterisation):
        self.geom = geom
        self._last_x: np.ndarray | None = None
        self._coords_cache: dict[int, Any] = {}

    def update_x(self, x: np.ndarray):
        """Update geometry parameter values if x has changed, clearing coordinates cache."""
        if self._last_x is not None and np.array_equal(x, self._last_x):
            return
        self._last_x = np.array(x, copy=True)
        self.geom.variables.set_values_from_norm(x)
        self._coords_cache.clear()

    def get_coords(self, n_points: int) -> Any:
        """Get discretized coordinates, cached for the current x and resolution."""
        if n_points not in self._coords_cache:
            if hasattr(self.geom, "discretise_coords"):
                self._coords_cache[n_points] = self.geom.discretise_coords(n_points)
            else:
                self._coords_cache[n_points] = self.geom.create_shape().discretise(
                    n_points, byedges=False
                )
        return self._coords_cache[n_points]


def to_objective(
    geom_objective: GeomOptimiserObjective,
    geom: GeometryParameterisation,
    context: GeomOptimisationContext | None = None,
) -> ObjectiveCallable:
    """Convert a geometry objective function to a normal objective function.

    Returns
    -------
    :
        The objective function converted from a geometry objective function.
    """
    ctx = context or GeomOptimisationContext(geom)

    def f(x):
        ctx.update_x(x)
        return geom_objective(geom)

    return f


def to_optimiser_callable(
    geom_callable: GeomOptimiserCallable,
    geom: GeometryParameterisation,
    context: GeomOptimisationContext | None = None,
) -> OptimiserCallable:
    """
    Convert a geometry optimiser function to a normal optimiser function.

    For example, a gradient or constraint.

    Returns
    -------
    :
        The optimiser function converted from a geometry optimiser function.
    """
    ctx = context or GeomOptimisationContext(geom)

    def f(x):
        ctx.update_x(x)
        return geom_callable(geom)

    return f


def to_optimiser_callable_from_cls(
    geom_callable: GeomClsOptimiserCallable,
    geom: GeometryParameterisation,
    context: GeomOptimisationContext | None = None,
) -> OptimiserCallable:
    """
    Convert a geometry optimiser function to a normal optimiser function.

    For example, a gradient or constraint.

    Returns
    -------
    :
        The optimiser function converted from a geometry optimiser function.
    """
    ctx = context or GeomOptimisationContext(geom)

    def f(x):
        ctx.update_x(x)
        return geom_callable()

    return f


def to_constraint(
    geom_constraint: GeomConstraintT,
    geom: GeometryParameterisation,
    context: GeomOptimisationContext | None = None,
) -> ConstraintT:
    """Convert a geometry constraint to a normal one.

    Returns
    -------
    :
        The consatraint constructed from the geometry constraint.
    """
    ctx = context or GeomOptimisationContext(geom)
    constraint: ConstraintT = {
        "f_constraint": to_optimiser_callable(
            geom_constraint["f_constraint"], geom, context=ctx
        ),
        "df_constraint": None,
        "tolerance": geom_constraint["tolerance"],
    }
    if name := geom_constraint.get("name", None):
        constraint["name"] = name

    if df_constraint := geom_constraint.get("df_constraint", None):
        constraint["df_constraint"] = to_optimiser_callable(
            df_constraint, geom, context=ctx
        )
    return constraint


def calculate_signed_distance(
    parameterisation: GeometryParameterisation,
    n_shape_discr: int,
    zone_points: np.ndarray,
    context: GeomOptimisationContext | None = None,
) -> np.ndarray:
    """
    Signed distance from the parameterised shape to the keep-out/in zone.

    Returns
    -------
    :
        Signed distance from the parameterised shape to the keep-out/in zone.
    """
    # Use context or native coordinate discretization when available to avoid CAD wire
    # creation and CAD-level curve discretization in the inner loop.
    if context is not None:
        s = context.get_coords(n_shape_discr).xz
    elif hasattr(parameterisation, "discretise_coords"):
        s = parameterisation.discretise_coords(n_shape_discr).xz
    else:
        shape = parameterisation.create_shape()
        # Note that we do not discretise by edges here, as the number of
        # points must remain constant so the size of constraint vectors
        # remain constant.
        s = shape.discretise(n_shape_discr, byedges=False).xz
    return signed_distance_2D_polygon(s.T, zone_points.T).T


def make_keep_out_zone_constraint(
    koz: KeepOutZone,
    context: GeomOptimisationContext | None = None,
) -> GeomConstraintT:
    """Make a keep-out zone inequality constraint from a wire.

    Returns
    -------
    :
        The inequality constraint for the keep-out zone.

    Raises
    ------
    GeometryOptimisationError
        Koz wire is not closed
    """
    if not koz.wire.is_closed():
        raise GeometryOptimisationError(
            f"Keep-out zone with label '{koz.wire.label}' is not closed."
        )
    koz_points = koz.wire.discretise(koz.n_discr, byedges=koz.byedges, dl=koz.dl).xz
    # Note that we do not allow discretisation using 'dl' or 'byedges'
    # for the shape being optimised. The size of the constraint cannot
    # change within an optimisation loop (NLOpt will error) and these
    # options do not guarantee a constant number of discretised points.
    shape_n_discr = koz.shape_n_discr

    def _f_constraint(geom: GeometryParameterisation) -> np.ndarray:
        return calculate_signed_distance(
            geom, n_shape_discr=shape_n_discr, zone_points=koz_points, context=context
        )

    return {
        "name": "KOZ",
        "f_constraint": _f_constraint,
        "tolerance": np.full(shape_n_discr, koz.tol),
    }


def make_minimum_distance_constraint(
    target: Any,
    min_distance: float,
    *,
    n_points: int = 100,
    tol: float = 1e-8,
    name: str = "minimum_distance",
    context: GeomOptimisationContext | None = None,
) -> GeomConstraintT:
    """
    Make an inequality constraint enforcing a minimum clearance distance:
        c(x) = min_distance - distance(geom, target) <= 0

    Pre-discretizes the fixed target geometry once and uses fast 2D distance
    in inner optimization loops without invoking the CAD kernel.

    Parameters
    ----------
    target:
        The target wire, boundary, coordinates, or point array to maintain clearance from.
    min_distance:
        Minimum clearance distance [m].
    n_points:
        Discretization resolution for the geometry parameterisation.
    tol:
        Constraint tolerance for the optimizer.
    name:
        Name for the constraint.
    context:
        Optional geometry optimisation context for caching across callbacks.

    Returns
    -------
    GeomConstraintT:
        Geometry constraint dictionary for use with optimise_geometry.
    """
    target_pts = _extract_2d_points(target, n_points)

    def _f_constraint(geom: GeometryParameterisation) -> np.ndarray:
        if context is not None:
            pts = context.get_coords(n_points)
            dist = fast_2d_distance(pts, target_pts, n_points=n_points)
        else:
            dist = fast_2d_distance(geom, target_pts, n_points=n_points)
        return np.array([min_distance - dist])

    return {
        "name": name,
        "f_constraint": _f_constraint,
        "tolerance": np.array([tol]),
    }


def get_shape_ineq_constraint(
    geom: GeometryParameterisation,
    context: GeomOptimisationContext | None = None,
) -> list[ConstraintT]:
    """
    Retrieve the inequality constraints registered for the given parameterisation.

    If no constraints are registered, return an empty list.

    Returns
    -------
    :
        The inequality constraints registered for the given parameterisation.
    """
    if geom.n_ineq_constraints < 1:
        return []
    if df_constraint := getattr(geom, "df_ineq_constraint", None):
        df_constraint = to_optimiser_callable_from_cls(
            df_constraint, geom, context=context
        )
    return [
        {
            "name": geom.name,
            "f_constraint": to_optimiser_callable_from_cls(
                geom.f_ineq_constraint, geom, context=context
            ),
            "df_constraint": df_constraint,
            "tolerance": geom.tolerance,
        }
    ]
