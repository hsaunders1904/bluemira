# SPDX-FileCopyrightText: 2021-present M. Coleman, J. Cook, F. Franza
# SPDX-FileCopyrightText: 2021-present I.A. Maione, S. McIntosh
# SPDX-FileCopyrightText: 2021-present J. Morris, D. Short
#
# SPDX-License-Identifier: LGPL-2.1-or-later

"""
Unit tests for the ParametricScan engine, metric extraction, and constraints.
"""

from dataclasses import dataclass
from operator import itemgetter

import pytest

from bluemira.base.constants import EPS
from bluemira.base.parameter_frame import Parameter, ParameterFrame
from bluemira.base.reactor_config import ReactorConfig
from bluemira.study import (
    ParametricScan,
    ScanExecutionError,
    ScanResult,
    ScanStatus,
    ScanVariable,
)


@dataclass
class SimpleGlobalParams(ParameterFrame):
    __test__ = False

    major_radius: Parameter[float]
    aspect_ratio: Parameter[float]


def mock_plasma_model(config: ReactorConfig) -> dict[str, float]:
    """
    Toy reactor build function for testing parametric scans.
    """
    r_0 = float(config.get_param_value("plasma.designer.r_0"))
    a = float(config.get_param_value("plasma.designer.minor_radius"))
    b_0 = float(config.get_param_value("plasma.designer.b_0"))

    # If magnetic field is negative or unphysical, simulate a model error
    if b_0 < 0:
        raise ValueError(f"Negative magnetic field: {b_0}")

    aspect_ratio = r_0 / a
    plasma_volume = 2.0 * (3.141592653589793**2) * r_0 * (a**2)
    fusion_power = 0.5 * (b_0**4) * (r_0**1.5)

    return {
        "aspect_ratio": aspect_ratio,
        "plasma_volume": plasma_volume,
        "fusion_power": fusion_power,
    }


@pytest.fixture
def base_config_dict() -> dict:
    return {
        "plasma": {
            "designer": {
                "params": {
                    "r_0": {"value": 9.0, "unit": "m"},
                    "minor_radius": {"value": 3.0, "unit": "m"},
                    "b_0": {"value": 5.5, "unit": "T"},
                }
            }
        }
    }


class TestScanVariable:
    def test_linear_variable_generation(self):
        v = ScanVariable.linear("plasma.designer.r_0", 8.0, 10.0, 5, unit="m")
        assert len(v.values) == 5
        assert v.values[0] == pytest.approx(8.0, rel=0, abs=EPS)
        assert v.values[-1] == pytest.approx(10.0, rel=0, abs=EPS)
        assert v.unit == "m"

    def test_geometric_variable_generation(self):
        v = ScanVariable.geometric("plasma.designer.b_0", 1.0, 16.0, 5, unit="T")
        assert len(v.values) == 5
        assert v.values[0] == pytest.approx(1.0, rel=0, abs=EPS)
        assert v.values[2] == pytest.approx(4.0, rel=0, abs=EPS)
        assert v.values[-1] == pytest.approx(16.0, rel=0, abs=EPS)


class TestParametricScanExecution:
    def test_single_variable_sequential_scan(self, base_config_dict):
        scan = ParametricScan(build_fn=mock_plasma_model, base_config=base_config_dict)
        scan.add_variable("plasma.designer.r_0", [8.0, 9.0, 10.0])
        scan.add_metric("aspect_ratio", itemgetter("aspect_ratio"))
        scan.add_metric("fusion_power", itemgetter("fusion_power"))

        result = scan.run(n_workers=1)

        assert len(result) == 3
        assert len(result.successful_points()) == 3
        assert len(result.failed_points()) == 0

        # Point 0: r_0 = 8.0, minor_radius = 3.0 -> aspect_ratio = 8/3
        assert result[0].variables["plasma.designer.r_0"] == pytest.approx(8.0)
        assert result[0].metrics["aspect_ratio"] == pytest.approx(8.0 / 3.0)
        assert result[0].status == ScanStatus.SUCCESS

    def test_multi_variable_grid_and_parallel_execution(self, base_config_dict):
        scan = ParametricScan(build_fn=mock_plasma_model, base_config=base_config_dict)
        scan.add_variable("plasma.designer.r_0", [8.0, 9.0])
        scan.add_variable("plasma.designer.b_0", [5.0, 6.0])
        scan.add_metric("fusion_power", itemgetter("fusion_power"))

        grid = scan.grid_points()
        assert len(grid) == 4

        # Run with 2 thread workers
        result = scan.run(n_workers=2)
        assert len(result) == 4
        assert len(result.successful_points()) == 4

    def test_constraints_and_feasibility(self, base_config_dict):
        scan = ParametricScan(build_fn=mock_plasma_model, base_config=base_config_dict)
        scan.add_variable("plasma.designer.r_0", [7.5, 9.0, 10.5])
        scan.add_metric("aspect_ratio", itemgetter("aspect_ratio"))
        # Constraint: aspect ratio must be <= 3.1
        scan.add_constraint(
            "aspect_ratio_limit",
            lambda metrics: metrics["aspect_ratio"] <= 3.1,
            description="Aspect ratio must not exceed 3.1",
        )

        result = scan.run()
        assert len(result) == 3

        # r_0 = 7.5 / 3.0 = 2.5 <= 3.1 -> Feasible
        assert result[0].is_feasible
        assert result[0].status == ScanStatus.SUCCESS

        # r_0 = 9.0 / 3.0 = 3.0 <= 3.1 -> Feasible
        assert result[1].is_feasible
        assert result[1].status == ScanStatus.SUCCESS

        # r_0 = 10.5 / 3.0 = 3.5 > 3.1 -> Infeasible
        assert not result[2].is_feasible
        assert result[2].status == ScanStatus.INFEASIBLE
        assert result[2].constraints_passed["aspect_ratio_limit"] is False

        assert len(result.feasible_points()) == 2

    def test_error_handling_without_fail_fast(self, base_config_dict):
        scan = ParametricScan(build_fn=mock_plasma_model, base_config=base_config_dict)
        # -1.0 triggers an exception in mock_plasma_model
        scan.add_variable("plasma.designer.b_0", [5.0, -1.0, 6.0])
        scan.add_metric("fusion_power", itemgetter("fusion_power"))

        result = scan.run(fail_fast=False)
        assert len(result) == 3
        assert len(result.successful_points()) == 2
        assert len(result.failed_points()) == 1

        failed_pt = result[1]
        assert failed_pt.status == ScanStatus.FAILED
        assert "Negative magnetic field" in failed_pt.error_message

    def test_error_handling_with_fail_fast(self, base_config_dict):
        scan = ParametricScan(build_fn=mock_plasma_model, base_config=base_config_dict)
        scan.add_variable("plasma.designer.b_0", [-1.0, 5.0])
        scan.add_metric("fusion_power", itemgetter("fusion_power"))

        with pytest.raises(ScanExecutionError, match="Point 0 failed with error"):
            scan.run(fail_fast=True)

    def test_progress_callback(self, base_config_dict):
        scan = ParametricScan(build_fn=mock_plasma_model, base_config=base_config_dict)
        scan.add_variable("plasma.designer.r_0", [8.0, 9.0, 10.0])

        calls = []

        def callback(completed, total, point):
            calls.append((completed, total, point.index))

        scan.run(progress_callback=callback)
        assert len(calls) == 3
        assert calls == [(1, 3, 0), (2, 3, 1), (3, 3, 2)]

    def test_records_export_and_json_persistence(self, base_config_dict, tmp_path):
        scan = ParametricScan(build_fn=mock_plasma_model, base_config=base_config_dict)
        scan.add_variable("plasma.designer.r_0", [8.5, 9.5])
        scan.add_metric("aspect_ratio", itemgetter("aspect_ratio"))

        result = scan.run()
        records = result.to_records()
        assert len(records) == 2
        assert records[0]["plasma.designer.r_0"] == pytest.approx(8.5)
        assert "aspect_ratio" in records[0]
        assert records[0]["status"] == "SUCCESS"

        # Save and reload
        save_file = tmp_path / "scan_result.json"
        result.save(save_file)
        assert save_file.exists()

        loaded_result = ScanResult.load(save_file)
        assert len(loaded_result) == 2
        assert loaded_result[0].variables["plasma.designer.r_0"] == pytest.approx(8.5)
        assert loaded_result[1].variables["plasma.designer.r_0"] == pytest.approx(9.5)

        # Summary output
        summary = result.summary()
        assert "PARAMETRIC SCAN SUMMARY" in summary
        assert "Total points evaluated : 2" in summary
