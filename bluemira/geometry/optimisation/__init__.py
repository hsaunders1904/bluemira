# SPDX-FileCopyrightText: 2021-present M. Coleman, J. Cook, F. Franza
# SPDX-FileCopyrightText: 2021-present I.A. Maione, S. McIntosh
# SPDX-FileCopyrightText: 2021-present J. Morris, D. Short
#
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Optimisation for geometry"""

from bluemira.geometry.optimisation._optimise import KeepOutZone, optimise_geometry
from bluemira.geometry.optimisation._tools import (
    GeomOptimisationContext,
    make_keep_out_zone_constraint,
    make_minimum_distance_constraint,
    wire_length_objective,
)
from bluemira.geometry.optimisation.problem import GeomOptimisationProblem
from bluemira.geometry.optimisation.typed import (
    GeomClsOptimiserCallable,
    GeomConstraintT,
    GeomOptimiserCallable,
    GeomOptimiserObjective,
)

__all__ = [
    "GeomClsOptimiserCallable",
    "GeomConstraintT",
    "GeomOptimisationContext",
    "GeomOptimisationProblem",
    "GeomOptimiserCallable",
    "GeomOptimiserObjective",
    "KeepOutZone",
    "make_keep_out_zone_constraint",
    "make_minimum_distance_constraint",
    "optimise_geometry",
    "wire_length_objective",
]
