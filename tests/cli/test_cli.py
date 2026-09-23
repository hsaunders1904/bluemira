# SPDX-FileCopyrightText: 2021-present M. Coleman, J. Cook, F. Franza
# SPDX-FileCopyrightText: 2021-present I.A. Maione, S. McIntosh
# SPDX-FileCopyrightText: 2021-present J. Morris, D. Short
#
# SPDX-License-Identifier: LGPL-2.1-or-later

"""
Unit tests for Bluemira CLI entrypoints and commands.
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from bluemira.cli import cli
from bluemira.study.scan import PointResult, ScanResult, ScanStatus


@pytest.fixture
def sample_config_path(tmp_path: Path) -> Path:
    config_dict = {
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
    cfg_file = tmp_path / "mock_reactor.json"
    cfg_file.write_text(json.dumps(config_dict, indent=2), encoding="utf-8")
    return cfg_file


@pytest.fixture
def sample_scan_result_path(tmp_path: Path) -> Path:
    p0 = PointResult(
        index=0,
        variables={"plasma.designer.r_0": 8.0},
        metrics={"aspect_ratio": 2.6667},
        status=ScanStatus.SUCCESS,
        execution_time=0.012,
        constraints_passed={"aspect_ratio_limit": True},
    )
    p1 = PointResult(
        index=1,
        variables={"plasma.designer.r_0": 10.5},
        metrics={"aspect_ratio": 3.5},
        status=ScanStatus.INFEASIBLE,
        execution_time=0.014,
        constraints_passed={"aspect_ratio_limit": False},
    )
    res = ScanResult(
        points=[p0, p1],
        variable_names=["plasma.designer.r_0"],
        metric_names=["aspect_ratio"],
        constraint_names=["aspect_ratio_limit"],
    )
    res_path = tmp_path / "sample_scan.json"
    res.save(res_path)
    return res_path


def test_cli_version_and_help():
    runner = CliRunner()
    res_help = runner.invoke(cli, ["--help"])
    assert res_help.exit_code == 0
    assert "Bluemira: Integrated Fusion Reactor Design" in res_help.output
    assert "doctor" in res_help.output
    assert "config" in res_help.output
    assert "scan" in res_help.output

    res_version = runner.invoke(cli, ["--version"])
    assert res_version.exit_code == 0
    assert "bluemira" in res_version.output


def test_doctor_command():
    runner = CliRunner()
    result = runner.invoke(cli, ["doctor"])
    assert result.exit_code == 0
    assert "Bluemira Environment Diagnostics" in result.output
    assert "Diagnostics complete" in result.output


def test_config_inspect_table(sample_config_path):
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "inspect", str(sample_config_path)])
    assert result.exit_code == 0
    assert "Configuration Parameters" in result.output
    assert "plasma.designer.r_0" in result.output
    assert "plasma.designer.minor_radius" in result.output


def test_config_inspect_json_and_filter(sample_config_path):
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["config", "inspect", str(sample_config_path), "--json-output", "-f", "r_0"],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["path"] == "plasma.designer.r_0"
    assert data[0]["value"] == pytest.approx(9.0)


def test_config_get(sample_config_path):
    runner = CliRunner()
    # Full output
    res_full = runner.invoke(
        cli, ["config", "get", str(sample_config_path), "plasma.designer.r_0"]
    )
    assert res_full.exit_code == 0
    assert "plasma.designer.r_0 = 9.0 m" in res_full.output

    # Value only
    res_val = runner.invoke(
        cli,
        [
            "config",
            "get",
            str(sample_config_path),
            "plasma.designer.r_0",
            "--value-only",
        ],
    )
    assert res_val.exit_code == 0
    assert res_val.output.strip() == "9.0"

    # Non-existent
    res_err = runner.invoke(
        cli, ["config", "get", str(sample_config_path), "plasma.designer.nonexistent"]
    )
    assert res_err.exit_code != 0
    assert "Error querying parameter" in res_err.output


def test_config_set_to_file(sample_config_path, tmp_path):
    runner = CliRunner()
    out_file = tmp_path / "modified_reactor.json"
    result = runner.invoke(
        cli,
        [
            "config",
            "set",
            str(sample_config_path),
            "plasma.designer.r_0",
            "10.25",
            "--out",
            str(out_file),
        ],
    )
    assert result.exit_code == 0
    assert f"Saved modified configuration to: {out_file}" in result.output
    assert out_file.exists()

    # Verify saved file contains 10.25
    with out_file.open("r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["plasma"]["designer"]["params"]["r_0"]["value"] == pytest.approx(10.25)


def test_config_set_in_place(sample_config_path):
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "config",
            "set",
            str(sample_config_path),
            "plasma.designer.minor_radius",
            "3.75",
            "--in-place",
        ],
    )
    assert result.exit_code == 0
    assert "Saved modified configuration to:" in result.output

    # Verify updated in place
    with sample_config_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["plasma"]["designer"]["params"]["minor_radius"][
        "value"
    ] == pytest.approx(3.75)


def test_scan_inspect(sample_scan_result_path):
    runner = CliRunner()
    result = runner.invoke(cli, ["scan", "inspect", str(sample_scan_result_path)])
    assert result.exit_code == 0
    assert "PARAMETRIC SCAN SUMMARY" in result.output
    assert "Total points evaluated : 2" in result.output
    assert "Scan Evaluation Points" in result.output


def test_scan_inspect_json_and_failed_only(sample_scan_result_path):
    runner = CliRunner()
    res_json = runner.invoke(
        cli, ["scan", "inspect", str(sample_scan_result_path), "--json-output"]
    )
    assert res_json.exit_code == 0
    data = json.loads(res_json.output)
    assert data["total_points"] == 2

    res_failed = runner.invoke(
        cli, ["scan", "inspect", str(sample_scan_result_path), "--failed-only"]
    )
    assert res_failed.exit_code == 0
    assert "INFEASIBLE" in res_failed.output
