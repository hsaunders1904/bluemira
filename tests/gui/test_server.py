# SPDX-FileCopyrightText: 2021-present M. Coleman, J. Cook, F. Franza
# SPDX-FileCopyrightText: 2021-present I.A. Maione, S. McIntosh
# SPDX-FileCopyrightText: 2021-present J. Morris, D. Short
#
# SPDX-License-Identifier: LGPL-2.1-or-later

"""
Tests for the Bluemira interactive GUI server and state manager.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from aiohttp.test_utils import TestClient, TestServer
from click.testing import CliRunner

from bluemira.cli import cli
from bluemira.gui.app import GUIAppState
from bluemira.gui.cad import export_mesh_to_obj, generate_tokamak_3d_mesh
from bluemira.gui.server import create_app

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def sample_config_dict() -> dict[str, Any]:
    return {
        "plasma": {
            "designer": {
                "params": {
                    "r_0": {
                        "value": 9.0,
                        "unit": "m",
                        "description": "Major radius",
                    },
                    "minor_radius": {
                        "value": 3.0,
                        "unit": "m",
                        "description": "Minor radius",
                    },
                    "elongation": {
                        "value": 1.75,
                        "unit": "",
                        "description": "Elongation kappa",
                    },
                    "triangularity": {
                        "value": 0.35,
                        "unit": "",
                        "description": "Triangularity delta",
                    },
                }
            }
        },
        "blanket": {
            "designer": {
                "params": {
                    "thickness": {
                        "value": 0.8,
                        "unit": "m",
                        "description": "Blanket thickness",
                    }
                }
            }
        },
    }


def test_app_state_operations(sample_config_dict):
    state = GUIAppState(sample_config_dict)

    # Schema
    schema = state.get_schema()
    assert len(schema) == 5
    assert any(p["path"] == "plasma.designer.r_0" for p in schema)

    # Initial diff
    assert state.get_diff() == {}

    # Update
    res = state.update_parameter("plasma.designer.r_0", 9.5)
    assert res["value"] == pytest.approx(9.5)
    assert res["is_modified"] is True

    diff = state.get_diff()
    assert "plasma.designer.r_0" in diff
    assert diff["plasma.designer.r_0"]["baseline"] == pytest.approx(9.0)
    assert diff["plasma.designer.r_0"]["current"] == pytest.approx(9.5)

    # 2D Shape
    shape = state.get_2d_plasma_shape()
    assert shape["r0"] == pytest.approx(9.5)
    assert len(shape["plasma"]["r"]) == 120

    # Reset
    res_reset = state.reset_parameter("plasma.designer.r_0")
    assert res_reset["value"] == pytest.approx(9.0)
    assert res_reset["is_modified"] is False
    assert state.get_diff() == {}

    # Reset all
    state.update_parameter("plasma.designer.r_0", 10.0)
    state.reset_all()
    assert state.get_diff() == {}
    assert state.working_config.get_param_value("plasma.designer.r_0") == pytest.approx(
        9.0
    )


def test_cad_mesh_generation(sample_config_dict):
    state = GUIAppState(sample_config_dict)
    mesh = generate_tokamak_3d_mesh(
        state.working_config,
        cutaway_deg=60.0,
        num_poloidal=16,
        num_toroidal=20,
        num_tf_coils=8,
    )
    assert "plasma" in mesh
    assert "blanket" in mesh
    assert "vacuum_vessel" in mesh
    assert "tf_coils" in mesh

    # Test OBJ export
    obj_str = export_mesh_to_obj(mesh)
    assert "# Bluemira CAD WebGL Export" in obj_str
    assert "o plasma" in obj_str
    assert "o tf_coils" in obj_str


def test_scan_app_state_and_export(sample_config_dict):
    state = GUIAppState(sample_config_dict)
    assert state.get_last_scan() is None
    assert state.export_scan_csv() == ""

    # Run scan across major radius
    res = state.run_scan(
        variables_spec=[{"name": "plasma.designer.r_0", "values": [8.0, 9.0, 10.0]}]
    )
    assert "points" in res
    assert len(res["points"]) == 3
    assert state.get_last_scan() is not None

    # CSV Export
    csv_str = state.export_scan_csv()
    assert "point_index" in csv_str
    assert "plasma.designer.r_0" in csv_str
    assert "aspect_ratio" in csv_str

    # Apply scan point
    applied = state.apply_scan_point(2)
    assert applied["applied_point"] == 2
    assert applied["variables"]["plasma.designer.r_0"] == pytest.approx(10.0)
    assert state.working_config.get_param_value("plasma.designer.r_0") == pytest.approx(
        10.0
    )


@pytest.mark.anyio
async def test_gui_config_endpoints(sample_config_dict, tmp_path: Path):
    state = GUIAppState(sample_config_dict)
    app = create_app(state)
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()

    try:
        # GET /
        resp_index = await client.get("/")
        assert resp_index.status == 200
        text = await resp_index.text()
        assert "BLUEMIRA" in text
        assert "poloidalCanvas" in text
        assert "cad3dCanvas" in text
        assert "scanModal" in text

        # GET /api/schema
        resp_schema = await client.get("/api/schema")
        assert resp_schema.status == 200
        schema_json = await resp_schema.json()
        assert len(schema_json["schema"]) == 5
        assert schema_json["modified_count"] == 0

        # POST /api/param
        resp_update = await client.post(
            "/api/param",
            json={"path": "plasma.designer.r_0", "value": 9.8, "unit": "m"},
        )
        assert resp_update.status == 200
        update_json = await resp_update.json()
        assert update_json["value"] == pytest.approx(9.8)
        assert update_json["is_modified"] is True
        assert "plasma.designer.r_0" in update_json["diff"]

        # GET /api/diff
        resp_diff = await client.get("/api/diff")
        assert resp_diff.status == 200
        diff_json = await resp_diff.json()
        assert diff_json["modified_count"] == 1

        # GET /api/preview/2d
        resp_2d = await client.get("/api/preview/2d?num_points=60")
        assert resp_2d.status == 200
        shape_json = await resp_2d.json()
        assert shape_json["r0"] == pytest.approx(9.8)
        assert len(shape_json["plasma"]["r"]) == 60

        # POST /api/reset_param
        resp_reset = await client.post(
            "/api/reset_param",
            json={"path": "plasma.designer.r_0"},
        )
        assert resp_reset.status == 200
        reset_json = await resp_reset.json()
        assert reset_json["value"] == pytest.approx(9.0)
        assert reset_json["is_modified"] is False

        # POST /api/param then POST /api/reset_all
        await client.post(
            "/api/param",
            json={"path": "plasma.designer.minor_radius", "value": 3.4},
        )
        resp_reset_all = await client.post("/api/reset_all")
        assert resp_reset_all.status == 200
        assert (await resp_reset_all.json())["modified_count"] == 0

        # GET /api/export
        resp_export = await client.get("/api/export")
        assert resp_export.status == 200
        assert "attachment" in resp_export.headers.get("Content-Disposition", "")

        # POST /api/save
        save_file = tmp_path / "saved_test_cfg.json"
        resp_save = await client.post("/api/save", json={"path": str(save_file)})
        assert resp_save.status == 200
        assert save_file.exists()

    finally:
        await client.close()


@pytest.mark.anyio
async def test_gui_cad_and_scan_endpoints(sample_config_dict):
    state = GUIAppState(sample_config_dict)
    app = create_app(state)
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()

    try:
        # GET /api/cad/mesh
        resp_mesh = await client.get("/api/cad/mesh?cutaway=90")
        assert resp_mesh.status == 200
        mesh_json = await resp_mesh.json()
        assert "plasma" in mesh_json
        assert "blanket" in mesh_json
        assert len(mesh_json["plasma"]["vertices"]) > 0

        # GET /api/cad/export
        resp_cad_export = await client.get("/api/cad/export?format=obj")
        assert resp_cad_export.status == 200
        assert "attachment" in resp_cad_export.headers.get("Content-Disposition", "")
        obj_content = await resp_cad_export.text()
        assert "o plasma" in obj_content
        assert "v " in obj_content

        # POST /api/scan/run
        resp_scan = await client.post(
            "/api/scan/run",
            json={
                "variables": [
                    {
                        "name": "plasma.designer.r_0",
                        "values": [8.5, 9.0, 9.5],
                    }
                ]
            },
        )
        assert resp_scan.status == 200
        scan_data = await resp_scan.json()
        assert len(scan_data["points"]) == 3

        # GET /api/scan/results
        resp_scan_res = await client.get("/api/scan/results")
        assert resp_scan_res.status == 200
        assert len((await resp_scan_res.json())["points"]) == 3

        # GET /api/scan/export?format=csv
        resp_scan_csv = await client.get("/api/scan/export?format=csv")
        assert resp_scan_csv.status == 200
        assert "attachment" in resp_scan_csv.headers.get("Content-Disposition", "")
        csv_text = await resp_scan_csv.text()
        assert "plasma.designer.r_0" in csv_text

        # GET /api/scan/export?format=json
        resp_scan_json = await client.get("/api/scan/export?format=json")
        assert resp_scan_json.status == 200
        assert "attachment" in resp_scan_json.headers.get("Content-Disposition", "")

        # POST /api/scan/apply
        resp_apply = await client.post(
            "/api/scan/apply",
            json={"point_index": 0},
        )
        assert resp_apply.status == 200
        apply_json = await resp_apply.json()
        assert apply_json["variables"]["plasma.designer.r_0"] == pytest.approx(8.5)

    finally:
        await client.close()


def test_cli_ui_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["ui", "--help"])
    assert result.exit_code == 0
    assert "Launch the interactive Bluemira parameter twiddler" in result.output
    assert "--host" in result.output
    assert "--port" in result.output
    assert "--no-browser" in result.output


@pytest.mark.anyio
async def test_gui_flat_params_json(tmp_path: Path):
    flat_params = {
        "A": {
            "value": 2.7,
            "unit": "dimensionless",
            "source": "Input",
            "long_name": "Aspect ratio",
        },
        "R_0": {
            "value": 9.0,
            "unit": "meter",
            "source": "Input",
            "long_name": "Major radius",
        },
        "kappa": {
            "value": 1.792,
            "unit": "dimensionless",
            "source": "Input",
            "long_name": "Elongation",
        },
        "delta": {
            "value": 0.5,
            "unit": "dimensionless",
            "source": "Input",
            "long_name": "Triangularity",
        },
    }
    json_path = tmp_path / "params.json"
    json_path.write_text(json.dumps(flat_params))

    state = GUIAppState(json_path)
    app = create_app(state)
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()

    try:
        # Schema endpoint
        resp = await client.get("/api/schema")
        assert resp.status == 200
        data = await resp.json()
        assert len(data["schema"]) == 4
        a_schema = next(p for p in data["schema"] if p["name"] == "A")
        assert a_schema["description"] == "Aspect ratio"
        assert a_schema["value"] == pytest.approx(2.7)

        # 2D preview
        resp_2d = await client.get("/api/preview/2d")
        assert resp_2d.status == 200
        shape = await resp_2d.json()
        assert shape["r0"] == pytest.approx(9.0)
        assert shape["a"] == pytest.approx(9.0 / 2.7)

        # Update parameter
        resp_upd = await client.post("/api/param", json={"path": "A", "value": 3.0})
        assert resp_upd.status == 200
        upd_data = await resp_upd.json()
        assert upd_data["value"] == pytest.approx(3.0)

        # Diff
        resp_diff = await client.get("/api/diff")
        assert resp_diff.status == 200
        diff_data = await resp_diff.json()
        assert "A" in diff_data["diff"]
        assert diff_data["diff"]["A"]["current"] == pytest.approx(3.0)
        assert diff_data["diff"]["A"]["baseline"] == pytest.approx(2.7)

    finally:
        await client.close()
