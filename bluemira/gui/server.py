# SPDX-FileCopyrightText: 2021-present M. Coleman, J. Cook, F. Franza
# SPDX-FileCopyrightText: 2021-present I.A. Maione, S. McIntosh
# SPDX-FileCopyrightText: 2021-present J. Morris, D. Short
#
# SPDX-License-Identifier: LGPL-2.1-or-later

"""
aiohttp-based asynchronous backend server for the Bluemira Web GUI.
"""

from __future__ import annotations

import json
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING

from aiohttp import web
from rich.console import Console

if TYPE_CHECKING:
    from bluemira.gui.app import GUIAppState

STATIC_DIR = Path(__file__).parent / "static"
STATE_KEY = web.AppKey("state", object)


async def index_handler(_request: web.Request) -> web.Response:  # noqa: RUF029
    """
    Serve single-page index HTML.

    Returns
    -------
    :
        Response containing index.html or 404.
    """
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return web.Response(text="Bluemira GUI index.html not found", status=404)
    return web.FileResponse(index_file)


async def get_schema_handler(request: web.Request) -> web.Response:  # noqa: RUF029
    """
    Return working configuration schema and diffs.

    Returns
    -------
    :
        JSON response with schema and diff dictionaries.
    """
    st: GUIAppState = request.app[STATE_KEY]  # type: ignore[assignment]
    schema = st.get_schema()
    diff = st.get_diff()
    return web.json_response({
        "schema": schema,
        "diff": diff,
        "modified_count": len(diff),
    })


async def update_param_handler(request: web.Request) -> web.Response:
    """
    Update a parameter in the working configuration.

    Returns
    -------
    :
        JSON response with updated status.
    """
    st: GUIAppState = request.app[STATE_KEY]  # type: ignore[assignment]
    try:
        data = await request.json()
    except Exception as exc:  # noqa: BLE001
        return web.json_response({"error": f"Invalid JSON: {exc}"}, status=400)

    path = data.get("path")
    if not path:
        return web.json_response({"error": "Missing parameter path"}, status=400)

    try:
        res = st.update_parameter(
            path,
            data.get("value"),
            unit=data.get("unit"),
            source=data.get("source", "GUI"),
        )
        res["diff"] = st.get_diff()
        return web.json_response(res)
    except Exception as exc:  # noqa: BLE001
        return web.json_response({"error": str(exc)}, status=400)


async def reset_param_handler(request: web.Request) -> web.Response:
    """
    Reset a parameter to baseline.

    Returns
    -------
    :
        JSON response confirming reset.
    """
    st: GUIAppState = request.app[STATE_KEY]  # type: ignore[assignment]
    try:
        data = await request.json()
        path = data.get("path")
        if not path:
            return web.json_response({"error": "Missing parameter path"}, status=400)

        res = st.reset_parameter(path)
        res["diff"] = st.get_diff()
        return web.json_response(res)
    except Exception as exc:  # noqa: BLE001
        return web.json_response({"error": str(exc)}, status=400)


async def reset_all_handler(request: web.Request) -> web.Response:  # noqa: RUF029
    """
    Reset entire configuration to initial baseline.

    Returns
    -------
    :
        JSON response confirming reset.
    """
    st: GUIAppState = request.app[STATE_KEY]  # type: ignore[assignment]
    st.reset_all()
    return web.json_response({"status": "ok", "modified_count": 0})


async def get_diff_handler(request: web.Request) -> web.Response:  # noqa: RUF029
    """
    Get dictionary of all modified parameters.

    Returns
    -------
    :
        JSON response containing diff map.
    """
    st: GUIAppState = request.app[STATE_KEY]  # type: ignore[assignment]
    diff = st.get_diff()
    return web.json_response({"diff": diff, "modified_count": len(diff)})


async def preview_2d_handler(request: web.Request) -> web.Response:  # noqa: RUF029
    """
    Compute and return 2D poloidal cross section boundary.

    Returns
    -------
    :
        JSON response with 2D coordinates.
    """
    st: GUIAppState = request.app[STATE_KEY]  # type: ignore[assignment]
    num_pts_str = request.query.get("num_points", "120")
    try:
        num_pts = int(num_pts_str)
    except ValueError:
        num_pts = 120

    shape_data = st.get_2d_plasma_shape(num_points=num_pts)
    return web.json_response(shape_data)


async def get_cad_mesh_handler(request: web.Request) -> web.Response:  # noqa: RUF029
    """
    Generate 3D polygonal mesh for tokamak components.

    Returns
    -------
    :
        JSON response with 3D mesh vertices, normals, and indices.
    """
    st: GUIAppState = request.app[STATE_KEY]  # type: ignore[assignment]
    cutaway_str = request.query.get("cutaway", "90.0")
    try:
        cutaway = float(cutaway_str)
    except ValueError:
        cutaway = 90.0

    mesh_data = st.get_3d_mesh(cutaway_deg=cutaway)
    return web.json_response(mesh_data)


async def export_cad_handler(request: web.Request) -> web.Response:  # noqa: RUF029
    """
    Export current 3D geometry as Wavefront OBJ format file.

    Returns
    -------
    :
        Downloadable OBJ file response.
    """
    st: GUIAppState = request.app[STATE_KEY]  # type: ignore[assignment]
    cutaway_str = request.query.get("cutaway", "90.0")
    try:
        cutaway = float(cutaway_str)
    except ValueError:
        cutaway = 90.0

    obj_text = st.export_cad_obj(cutaway_deg=cutaway)
    return web.Response(
        text=obj_text,
        content_type="text/plain",
        headers={"Content-Disposition": 'attachment; filename="bluemira_tokamak.obj"'},
    )


async def run_scan_handler(request: web.Request) -> web.Response:
    """
    Execute a parametric sweep with requested variables and metrics.

    Returns
    -------
    :
        JSON response with scan results.
    """
    st: GUIAppState = request.app[STATE_KEY]  # type: ignore[assignment]
    try:
        data = await request.json()
        variables = data.get("variables", [])
        metrics = data.get("metrics")
        if not variables:
            return web.json_response({"error": "No scan variables provided"}, status=400)
        res = st.run_scan(variables, metric_names=metrics)
        return web.json_response(res)
    except Exception as exc:  # noqa: BLE001
        return web.json_response({"error": str(exc)}, status=400)


async def get_scan_results_handler(  # noqa: RUF029
    request: web.Request,
) -> web.Response:
    """
    Retrieve results of the last parametric scan.

    Returns
    -------
    :
        JSON response with previous scan results.
    """
    st: GUIAppState = request.app[STATE_KEY]  # type: ignore[assignment]
    res = st.get_last_scan()
    if res is None:
        return web.json_response({"error": "No scan has been run yet"}, status=404)
    return web.json_response(res)


async def export_scan_handler(request: web.Request) -> web.Response:  # noqa: RUF029
    """
    Export results of the last parametric scan as CSV or JSON.

    Returns
    -------
    :
        Downloadable scan data response.
    """
    st: GUIAppState = request.app[STATE_KEY]  # type: ignore[assignment]
    fmt = request.query.get("format", "csv").lower()
    if fmt == "csv":
        csv_text = st.export_scan_csv()
        if not csv_text:
            return web.json_response({"error": "No scan results available"}, status=404)
        return web.Response(
            text=csv_text,
            content_type="text/csv",
            headers={
                "Content-Disposition": 'attachment; filename="bluemira_scan_results.csv"'
            },
        )

    res = st.get_last_scan()
    if res is None:
        return web.json_response({"error": "No scan results available"}, status=404)
    return web.Response(
        text=json.dumps(res, indent=2),
        content_type="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="bluemira_scan_results.json"'
        },
    )


async def apply_scan_point_handler(request: web.Request) -> web.Response:
    """
    Apply parameters of a specific scan point to the active working config.

    Returns
    -------
    :
        JSON response with updated configuration and diff.
    """
    st: GUIAppState = request.app[STATE_KEY]  # type: ignore[assignment]
    try:
        data = await request.json()
        point_idx = int(data.get("point_index", 0))
        applied_info = st.apply_scan_point(point_idx)
        return web.json_response({
            "status": "applied",
            "point_index": point_idx,
            "variables": applied_info["variables"],
            "diff": st.get_diff(),
        })
    except Exception as exc:  # noqa: BLE001
        return web.json_response({"error": str(exc)}, status=400)


async def save_config_handler(request: web.Request) -> web.Response:
    """
    Save active configuration to disk.

    Returns
    -------
    :
        JSON response with save status and path.
    """
    st: GUIAppState = request.app[STATE_KEY]  # type: ignore[assignment]
    try:
        data = await request.json()
        save_path = data.get("path")
        if not save_path:
            return web.json_response({"error": "No save path provided"}, status=400)
        st.working_config.save(save_path)
        return web.json_response({
            "status": "saved",
            "path": str(save_path),
        })
    except Exception as exc:  # noqa: BLE001
        return web.json_response({"error": str(exc)}, status=400)


async def export_config_handler(request: web.Request) -> web.Response:  # noqa: RUF029
    """
    Export working configuration dictionary as downloadable JSON.

    Returns
    -------
    :
        Downloadable JSON response.
    """
    st: GUIAppState = request.app[STATE_KEY]  # type: ignore[assignment]
    config_dict = st.to_dict()
    headers = {"Content-Disposition": 'attachment; filename="bluemira_config.json"'}
    return web.Response(
        text=json.dumps(config_dict, indent=2),
        content_type="application/json",
        headers=headers,
    )


def create_app(state: GUIAppState) -> web.Application:
    """
    Create and configure the aiohttp application instance.

    Parameters
    ----------
    state:
        The GUIAppState instance managing the active configuration.

    Returns
    -------
    :
        Configured web.Application instance.
    """
    app = web.Application()
    app[STATE_KEY] = state

    app.router.add_get("/", index_handler)
    app.router.add_get("/api/schema", get_schema_handler)
    app.router.add_post("/api/param", update_param_handler)
    app.router.add_post("/api/reset_param", reset_param_handler)
    app.router.add_post("/api/reset_all", reset_all_handler)
    app.router.add_get("/api/diff", get_diff_handler)
    app.router.add_get("/api/preview/2d", preview_2d_handler)
    app.router.add_get("/api/cad/mesh", get_cad_mesh_handler)
    app.router.add_get("/api/cad/export", export_cad_handler)
    app.router.add_post("/api/scan/run", run_scan_handler)
    app.router.add_get("/api/scan/results", get_scan_results_handler)
    app.router.add_get("/api/scan/export", export_scan_handler)
    app.router.add_post("/api/scan/apply", apply_scan_point_handler)
    app.router.add_post("/api/save", save_config_handler)
    app.router.add_get("/api/export", export_config_handler)

    if STATIC_DIR.exists():
        app.router.add_static("/static/", path=str(STATIC_DIR), name="static")

    return app


def run_server(
    state: GUIAppState,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    open_browser: bool = True,
) -> None:
    """
    Run the interactive GUI web server.

    Parameters
    ----------
    state:
        The GUIAppState instance.
    host:
        Host interface to bind to.
    port:
        Port number to listen on.
    open_browser:
        Whether to automatically open the default web browser.
    """
    console = Console()
    app = create_app(state)
    url = f"http://{host}:{port}/"

    console.print(
        f"[bold green]Starting Bluemira GUI server at[/bold green] "
        f"[link={url}]{url}[/link]"
    )
    console.print(
        f"[dim]Working config loaded with {len(state.get_schema())} parameters.[/dim]"
    )

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            console.print("[yellow]Could not open browser automatically.[/yellow]")

    web.run_app(app, host=host, port=port, print=None)
