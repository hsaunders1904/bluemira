# SPDX-FileCopyrightText: 2021-present M. Coleman, J. Cook, F. Franza
# SPDX-FileCopyrightText: 2021-present I.A. Maione, S. McIntosh
# SPDX-FileCopyrightText: 2021-present J. Morris, D. Short
#
# SPDX-License-Identifier: LGPL-2.1-or-later

"""
Headless parametric scan engine, metric extraction, and constraint verification.
"""

from __future__ import annotations

import concurrent.futures
import copy
import itertools
import json
import time
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import numpy as np

from bluemira.base.parameter_frame import EmptyFrame
from bluemira.base.reactor_config import ReactorConfig
from bluemira.study.error import ScanExecutionError

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from os import PathLike


class ScanStatus(StrEnum):
    """
    Status of an individual point evaluation within a parametric scan.
    """

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    INFEASIBLE = "INFEASIBLE"


@dataclass
class ScanVariable:
    """
    A single variable parameter swept during a parametric scan.

    Parameters
    ----------
    name:
        Dot-path or canonical parameter name (e.g. 'comp A.designer.age').
    values:
        Sequence of values to evaluate for this parameter.
    unit:
        Optional unit string associated with the values.
    """

    name: str
    values: list[Any]
    unit: str | None = None

    @classmethod
    def linear(
        cls,
        name: str,
        start: float,
        stop: float,
        num: int,
        unit: str | None = None,
    ) -> ScanVariable:
        """
        Create a linearly spaced scan variable.

        Parameters
        ----------
        name:
            The parameter dot-path name.
        start:
            The starting scalar value.
        stop:
            The ending scalar value (inclusive).
        num:
            Number of points to generate.
        unit:
            Optional physical unit.

        Returns
        -------
        :
            A new ScanVariable with linearly spaced values.
        """
        vals = [float(v) for v in np.linspace(start, stop, num)]
        return cls(name=name, values=vals, unit=unit)

    @classmethod
    def geometric(
        cls,
        name: str,
        start: float,
        stop: float,
        num: int,
        unit: str | None = None,
    ) -> ScanVariable:
        """
        Create a geometrically (logarithmically) spaced scan variable.

        Parameters
        ----------
        name:
            The parameter dot-path name.
        start:
            The starting scalar value (> 0).
        stop:
            The ending scalar value (> 0).
        num:
            Number of points to generate.
        unit:
            Optional physical unit.

        Returns
        -------
        :
            A new ScanVariable with geometrically spaced values.
        """
        vals = [float(v) for v in np.geomspace(start, stop, num)]
        return cls(name=name, values=vals, unit=unit)


@dataclass
class ScanMetric:
    """
    Specification for a metric extracted from model evaluation results.

    Parameters
    ----------
    name:
        The metric name.
    extractor:
        Callable taking the build function output (and optionally config)
        and returning a scalar or string metric value.
    unit:
        Optional unit string of the extracted metric.
    description:
        Optional human-readable description.
    """

    name: str
    extractor: Callable[[Any], Any]
    unit: str | None = None
    description: str = ""


@dataclass
class ScanConstraint:
    """
    A constraint evaluated on the extracted metrics of a scan point.

    Parameters
    ----------
    name:
        The constraint identifier.
    condition:
        Callable accepting a dictionary of extracted metrics and returning
        True if the point satisfies the constraint, or False if violated.
    description:
        Optional human-readable explanation of the constraint.
    """

    name: str
    condition: Callable[[dict[str, Any]], bool]
    description: str = ""


@dataclass
class PointResult:
    """
    Evaluation result for a single design point in a parametric scan.

    Parameters
    ----------
    index:
        Zero-based index of the scan point.
    variables:
        Dictionary mapping parameter dot-paths to their assigned values.
    metrics:
        Dictionary mapping metric names to their extracted values.
    status:
        Execution status of the point (SUCCESS, FAILED, or INFEASIBLE).
    execution_time:
        Elapsed execution time for the point evaluation in seconds.
    error_message:
        Error message string if execution failed, else None.
    constraints_passed:
        Dictionary mapping constraint names to boolean satisfaction flags.
    """

    index: int
    variables: dict[str, Any]
    metrics: dict[str, Any] = field(default_factory=dict)
    status: ScanStatus = ScanStatus.SUCCESS
    execution_time: float = 0.0
    error_message: str | None = None
    constraints_passed: dict[str, bool] = field(default_factory=dict)

    @property
    def is_feasible(self) -> bool:
        """
        Check if the point succeeded and passed all constraints.

        Returns
        -------
        :
            True if status is SUCCESS and all constraint checks passed.
        """
        if self.status != ScanStatus.SUCCESS:
            return False
        return all(self.constraints_passed.values())

    def to_dict(self) -> dict[str, Any]:
        """
        Convert point result to a serializable dictionary.

        Returns
        -------
        :
            Dictionary representation of this point result.
        """
        data = asdict(self)
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PointResult:
        """
        Construct a PointResult from a dictionary.

        Parameters
        ----------
        data:
            Dictionary matching the PointResult structure.

        Returns
        -------
        :
            Constructed PointResult instance.
        """
        d = dict(data)
        d["status"] = ScanStatus(d["status"])
        return cls(**d)


@dataclass
class ScanResult:
    """
    Collection of evaluated design points and summary statistics.

    Parameters
    ----------
    points:
        List of PointResult instances evaluated during the scan.
    variable_names:
        List of parameter names swept in the scan.
    metric_names:
        List of metric names collected in the scan.
    constraint_names:
        List of constraint names evaluated in the scan.
    """

    points: list[PointResult]
    variable_names: list[str] = field(default_factory=list)
    metric_names: list[str] = field(default_factory=list)
    constraint_names: list[str] = field(default_factory=list)

    def __len__(self) -> int:
        """
        Number of evaluated points in the scan result.

        Returns
        -------
        :
            Count of total points.
        """
        return len(self.points)

    def __getitem__(self, index: int) -> PointResult:
        """
        Get PointResult at specified index.

        Parameters
        ----------
        index:
            Point index to retrieve.

        Returns
        -------
        :
            The requested PointResult.
        """
        return self.points[index]

    def successful_points(self) -> list[PointResult]:
        """
        Return points whose build evaluation completed successfully.

        Returns
        -------
        :
            List of successful PointResults.
        """
        return [
            p
            for p in self.points
            if p.status in {ScanStatus.SUCCESS, ScanStatus.INFEASIBLE}
        ]

    def failed_points(self) -> list[PointResult]:
        """
        Return points whose build evaluation raised an unhandled error.

        Returns
        -------
        :
            List of failed PointResults.
        """
        return [p for p in self.points if p.status == ScanStatus.FAILED]

    def feasible_points(self) -> list[PointResult]:
        """
        Return points that succeeded and satisfied all constraints.

        Returns
        -------
        :
            List of feasible PointResults.
        """
        return [p for p in self.points if p.is_feasible]

    def to_records(self) -> list[dict[str, Any]]:
        """
        Flatten results into a tabular list of records.

        Returns
        -------
        :
            List of flat dictionaries containing point variables, metrics,
            status, execution time, and constraint pass flags.
        """
        records: list[dict[str, Any]] = []
        for p in self.points:
            rec: dict[str, Any] = {
                "point_index": p.index,
                "status": p.status.value,
                "feasible": p.is_feasible,
                "execution_time_s": p.execution_time,
            }
            if p.error_message:
                rec["error"] = p.error_message

            rec.update(p.variables)
            rec.update(p.metrics)

            for c_name, c_passed in p.constraints_passed.items():
                rec[f"constraint_{c_name}"] = c_passed

            records.append(rec)
        return records

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize scan result to a JSON-compatible dictionary.

        Returns
        -------
        :
            Dictionary containing metadata and all point records.
        """
        return {
            "variable_names": self.variable_names,
            "metric_names": self.metric_names,
            "constraint_names": self.constraint_names,
            "total_points": len(self.points),
            "points": [p.to_dict() for p in self.points],
        }

    def save(self, path: str | PathLike) -> None:
        """
        Save scan results to a JSON file.

        Parameters
        ----------
        path:
            Target file path to write.
        """
        with Path(path).open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: str | PathLike) -> ScanResult:
        """
        Load a ScanResult from a saved JSON file.

        Parameters
        ----------
        path:
            Source file path to read.

        Returns
        -------
        :
            Loaded ScanResult instance.
        """
        with Path(path).open("r", encoding="utf-8") as f:
            data = json.load(f)
        points = [PointResult.from_dict(pd) for pd in data["points"]]
        return cls(
            points=points,
            variable_names=data.get("variable_names", []),
            metric_names=data.get("metric_names", []),
            constraint_names=data.get("constraint_names", []),
        )

    def summary(self) -> str:
        """
        Return a textual summary of the scan results.

        Returns
        -------
        :
            Formatted summary string.
        """
        total = len(self.points)
        successful = len(self.successful_points())
        failed = len(self.failed_points())
        feasible = len(self.feasible_points())
        times = [p.execution_time for p in self.points]
        avg_time = float(np.mean(times)) if times else 0.0

        lines = [
            "=" * 50,
            "PARAMETRIC SCAN SUMMARY",
            "=" * 50,
            f"Total points evaluated : {total}",
            f"Successful evaluations : {successful}",
            f"Failed evaluations     : {failed}",
            f"Feasible designs       : {feasible}",
            f"Average point runtime  : {avg_time:.3f} s",
            "-" * 50,
            f"Variables swept: {', '.join(self.variable_names)}",
            f"Metrics measured: {', '.join(self.metric_names)}",
        ]
        if self.constraint_names:
            lines.append(f"Constraints: {', '.join(self.constraint_names)}")
        lines.append("=" * 50)
        return "\n".join(lines)


class ParametricScan:
    """
    Parametric study engine for sweeping parameters and extracting metrics.

    Parameters
    ----------
    build_fn:
        Function that accepts a ReactorConfig (or config dict) and builds the
        reactor model, returning a result object or reactor instance.
    base_config:
        Base configuration to start from (ReactorConfig, dict, or file path).
    global_param_frame_type:
        Optional parameter frame type when base_config is loaded from path.
    """

    def __init__(
        self,
        build_fn: Callable[[ReactorConfig], Any],
        base_config: ReactorConfig | dict[str, Any] | str | PathLike,
        global_param_frame_type: Any | None = None,
    ) -> None:
        self.build_fn = build_fn
        self._raw_config = base_config
        if global_param_frame_type is not None:
            self._frame_type = global_param_frame_type
        elif isinstance(base_config, ReactorConfig):
            self._frame_type = type(base_config.global_params)
        else:
            self._frame_type = EmptyFrame
        self.variables: list[ScanVariable] = []
        self.metrics: list[ScanMetric] = []
        self.constraints: list[ScanConstraint] = []

    def _get_base_config_dict(self) -> dict[str, Any]:
        """
        Get the base configuration data as a dictionary.

        Returns
        -------
        :
            Deep-copied configuration dictionary.
        """
        if isinstance(self._raw_config, ReactorConfig):
            return self._raw_config.to_dict()
        if isinstance(self._raw_config, dict):
            return copy.deepcopy(self._raw_config)
        # It's a path
        cfg = ReactorConfig(self._raw_config, self._frame_type)
        return cfg.to_dict()

    def add_variable(
        self,
        name: str,
        values: Sequence[Any],
        unit: str | None = None,
    ) -> ParametricScan:
        """
        Register a variable parameter to sweep over.

        Parameters
        ----------
        name:
            Parameter dot-path name.
        values:
            Sequence of values for this variable.
        unit:
            Optional unit string.

        Returns
        -------
        :
            Self instance for fluent method chaining.
        """
        self.variables.append(ScanVariable(name=name, values=list(values), unit=unit))
        return self

    def add_metric(
        self,
        name: str,
        extractor: Callable[[Any], Any],
        unit: str | None = None,
        description: str = "",
    ) -> ParametricScan:
        """
        Register a metric extractor function.

        Parameters
        ----------
        name:
            Metric identifier.
        extractor:
            Callable mapping build output to metric value.
        unit:
            Optional physical unit.
        description:
            Optional description.

        Returns
        -------
        :
            Self instance for fluent method chaining.
        """
        self.metrics.append(
            ScanMetric(
                name=name,
                extractor=extractor,
                unit=unit,
                description=description,
            )
        )
        return self

    def add_constraint(
        self,
        name: str,
        condition: Callable[[dict[str, Any]], bool],
        description: str = "",
    ) -> ParametricScan:
        """
        Register a design constraint.

        Parameters
        ----------
        name:
            Constraint identifier.
        condition:
            Callable returning True if metric values satisfy constraint.
        description:
            Optional description.

        Returns
        -------
        :
            Self instance for fluent method chaining.
        """
        self.constraints.append(
            ScanConstraint(
                name=name,
                condition=condition,
                description=description,
            )
        )
        return self

    def grid_points(self) -> list[dict[str, Any]]:
        """
        Generate Cartesian product of all registered scan variables.

        Returns
        -------
        :
            List of variable value assignments for each grid point.
        """
        if not self.variables:
            return [{}]

        keys = [v.name for v in self.variables]
        val_lists = [v.values for v in self.variables]
        return [
            dict(zip(keys, combo, strict=True))
            for combo in itertools.product(*val_lists)
        ]

    def _evaluate_point(
        self,
        index: int,
        var_assignments: dict[str, Any],
        base_dict: dict[str, Any],
        *,
        fail_fast: bool,
    ) -> PointResult:
        """
        Evaluate a single design point.

        Parameters
        ----------
        index:
            Index of the point.
        var_assignments:
            Variables assigned to this point.
        base_dict:
            Base configuration dictionary.
        fail_fast:
            If True, exceptions during build_fn are re-raised immediately.

        Returns
        -------
        :
            PointResult for this evaluation.

        Raises
        ------
        ScanExecutionError
            If model evaluation fails and fail_fast is True.
        """
        # Create dedicated ReactorConfig clone for this point
        cfg_dict = copy.deepcopy(base_dict)
        cfg = ReactorConfig(cfg_dict, self._frame_type)

        # Apply variables to configuration
        for var_name, var_val in var_assignments.items():
            cfg.set_param(var_name, var_val)

        t_start = time.perf_counter()
        status = ScanStatus.SUCCESS
        error_msg: str | None = None
        extracted_metrics: dict[str, Any] = {}
        constraints_passed: dict[str, bool] = {}

        try:
            build_output = self.build_fn(cfg)
        except Exception as exc:
            # User model execution can raise any arbitrary exception
            if fail_fast:
                raise ScanExecutionError(
                    f"Point {index} failed with error: {exc}"
                ) from exc
            status = ScanStatus.FAILED
            error_msg = str(exc)
        else:
            # Extract metrics
            for m in self.metrics:
                try:
                    extracted_metrics[m.name] = m.extractor(build_output)
                except Exception as m_exc:  # noqa: BLE001
                    extracted_metrics[m.name] = None
                    if not error_msg:
                        error_msg = f"Metric extraction failed for '{m.name}': {m_exc}"

            # Evaluate constraints
            for c in self.constraints:
                try:
                    passed = bool(c.condition(extracted_metrics))
                    constraints_passed[c.name] = passed
                    if not passed and status == ScanStatus.SUCCESS:
                        status = ScanStatus.INFEASIBLE
                except Exception:  # noqa: BLE001
                    constraints_passed[c.name] = False
                    status = ScanStatus.INFEASIBLE

        t_elapsed = time.perf_counter() - t_start

        return PointResult(
            index=index,
            variables=var_assignments,
            metrics=extracted_metrics,
            status=status,
            execution_time=t_elapsed,
            error_message=error_msg,
            constraints_passed=constraints_passed,
        )

    def run(
        self,
        *,
        n_workers: int = 1,
        fail_fast: bool = False,
        progress_callback: Callable[[int, int, PointResult], None] | None = None,
        pool_type: Literal["thread", "process"] = "thread",
    ) -> ScanResult:
        """
        Execute the parametric sweep across all generated points.

        Parameters
        ----------
        n_workers:
            Number of parallel workers. Default is 1 (sequential).
        fail_fast:
            If True, abort on the first failure.
        progress_callback:
            Optional callback invoked after each point finishes with
            `(completed_count, total_points, point_result)`.
        pool_type:
            Parallel executor type: 'thread' (default) or 'process'.

        Returns
        -------
        :
            ScanResult containing all evaluated points and metadata.

        Raises
        ------
        ScanError
            If configuration or execution encounters a fatal setup issue.
        """
        base_dict = self._get_base_config_dict()
        grid = self.grid_points()
        total = len(grid)
        results: list[PointResult] = [None] * total  # type: ignore[list-item]

        var_names = [v.name for v in self.variables]
        metric_names = [m.name for m in self.metrics]
        constraint_names = [c.name for c in self.constraints]

        if n_workers <= 1 or total <= 1:
            # Sequential execution
            for idx, pt_vars in enumerate(grid):
                res = self._evaluate_point(idx, pt_vars, base_dict, fail_fast=fail_fast)
                results[idx] = res
                if progress_callback:
                    progress_callback(idx + 1, total, res)
        else:
            # Parallel execution
            executor_cls = (
                concurrent.futures.ProcessPoolExecutor
                if pool_type == "process"
                else concurrent.futures.ThreadPoolExecutor
            )
            completed_count = 0
            with executor_cls(max_workers=n_workers) as executor:
                future_to_idx = {
                    executor.submit(
                        self._evaluate_point,
                        idx,
                        pt_vars,
                        base_dict,
                        fail_fast=fail_fast,
                    ): idx
                    for idx, pt_vars in enumerate(grid)
                }

                for future in concurrent.futures.as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    res = future.result()
                    results[idx] = res
                    completed_count += 1
                    if progress_callback:
                        progress_callback(completed_count, total, res)

        return ScanResult(
            points=results,
            variable_names=var_names,
            metric_names=metric_names,
            constraint_names=constraint_names,
        )
