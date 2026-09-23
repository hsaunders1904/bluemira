# SPDX-FileCopyrightText: 2021-present M. Coleman, J. Cook, F. Franza
# SPDX-FileCopyrightText: 2021-present I.A. Maione, S. McIntosh
# SPDX-FileCopyrightText: 2021-present J. Morris, D. Short
#
# SPDX-License-Identifier: LGPL-2.1-or-later

"""
State and business logic management for the Bluemira interactive GUI.
"""

from __future__ import annotations

import copy
import csv
import io
import math
from typing import TYPE_CHECKING, Any

import numpy as np

from bluemira.base.error import BluemiraError
from bluemira.base.parameter_frame import EmptyFrame
from bluemira.base.reactor_config import ReactorConfig
from bluemira.study.scan import ParametricScan, ScanMetric

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from os import PathLike

    from bluemira.study.scan import ScanResult


class GUIAppState:
    """
    Encapsulates application state for the parameter twiddler GUI.

    Parameters
    ----------
    config:
        Initial ReactorConfig, configuration dictionary, or path to file.
    build_fn:
        Optional callable accepting `ReactorConfig` and returning a model or
        geometry output.
    """

    def __init__(
        self,
        config: ReactorConfig | dict[str, Any] | str | PathLike,
        build_fn: Callable[[ReactorConfig], Any] | None = None,
    ) -> None:
        if isinstance(config, ReactorConfig):
            self.working_config = copy.deepcopy(config)
            self._baseline_dict = config.to_dict()
        elif isinstance(config, dict):
            self.working_config = ReactorConfig(copy.deepcopy(config), EmptyFrame)
            self._baseline_dict = copy.deepcopy(config)
        else:
            self.working_config = ReactorConfig(config, EmptyFrame)
            self._baseline_dict = self.working_config.to_dict()

        self.build_fn = build_fn
        self._history: list[dict[str, Any]] = []
        self.last_scan_result: ScanResult | None = None

    def to_dict(self) -> dict[str, Any]:
        """
        Return configuration dictionary for GUI state.

        Returns
        -------
        :
            Configuration dictionary.
        """
        return self.working_config.to_dict()

    def get_schema(self) -> list[dict[str, Any]]:
        """
        Return the list of parameter schemas available in the configuration.

        Returns
        -------
        :
            List of parameter metadata dictionaries.
        """
        return self.working_config.get_param_schema()

    def get_diff(self) -> dict[str, dict[str, Any]]:
        """
        Compute diff between current working config and original baseline.

        Returns
        -------
        :
            Dictionary mapping modified parameter path to
            {'baseline': ..., 'current': ..., 'unit': ...}.
        """
        baseline_cfg = ReactorConfig(self._baseline_dict, EmptyFrame)
        diffs: dict[str, dict[str, Any]] = {}

        working_params = self.working_config.list_params()
        for path, curr_dict in working_params.items():
            curr_val = curr_dict.get("value")
            try:
                base_val = baseline_cfg.get_param_value(path)
            except (KeyError, BluemiraError):
                diffs[path] = {
                    "baseline": None,
                    "current": curr_val,
                    "unit": curr_dict.get("unit"),
                }
            else:
                if curr_val != base_val:
                    diffs[path] = {
                        "baseline": base_val,
                        "current": curr_val,
                        "unit": curr_dict.get("unit"),
                    }
        return diffs

    def update_parameter(
        self,
        path: str,
        value: Any,
        *,
        unit: str | None = None,
        source: str = "GUI",
    ) -> dict[str, Any]:
        """
        Update a single parameter value in the working configuration.

        Parameters
        ----------
        path:
            Dot-path of the parameter.
        value:
            New value.
        unit:
            Optional new unit.
        source:
            Source annotation for traceability.

        Returns
        -------
        :
            Dictionary with status, updated path, and current value.
        """
        prev_val = self.working_config.get_param_value(path)
        self.working_config.set_param(path, value, unit=unit, source=source or "GUI")
        self._history.append({
            "action": "update",
            "path": path,
            "previous_value": prev_val,
            "new_value": value,
        })
        curr_p = self.working_config.get_param(path)
        baseline_cfg = ReactorConfig(self._baseline_dict, EmptyFrame)
        try:
            is_mod = curr_p.get("value") != baseline_cfg.get_param_value(path)
        except (KeyError, BluemiraError):
            is_mod = True

        return {
            "path": path,
            "value": curr_p.get("value"),
            "unit": curr_p.get("unit"),
            "is_modified": is_mod,
        }

    def reset_parameter(self, path: str) -> dict[str, Any]:
        """
        Reset a single parameter to its baseline value.

        Parameters
        ----------
        path:
            Dot-path of the parameter.

        Returns
        -------
        :
            Updated parameter dictionary.
        """
        baseline_cfg = ReactorConfig(self._baseline_dict, EmptyFrame)
        orig_dict = baseline_cfg.get_param(path)
        orig_val = orig_dict.get("value")
        orig_unit = orig_dict.get("unit")
        orig_source = orig_dict.get("source", "baseline")

        self.working_config.set_param(path, orig_val, unit=orig_unit, source=orig_source)
        self._history.append({
            "action": "reset_param",
            "path": path,
            "value": orig_val,
        })
        return {
            "path": path,
            "value": orig_val,
            "unit": orig_unit,
            "is_modified": False,
        }

    def reset_all(self) -> dict[str, str]:
        """
        Reset the entire configuration back to baseline.

        Returns
        -------
        :
            Status confirmation.
        """
        self.working_config = ReactorConfig(
            copy.deepcopy(self._baseline_dict), EmptyFrame
        )
        self._history.append({"action": "reset_all"})
        return {"status": "reset_success"}

    def run_build(self) -> dict[str, Any]:
        """
        Execute the model build function if registered.

        Returns
        -------
        :
            Dictionary with build status and results.
        """
        if self.build_fn is None:
            return {
                "status": "noop",
                "message": (
                    "No build function registered. Using parameterized model defaults."
                ),
            }
        try:
            res = self.build_fn(self.working_config)
            return {
                "status": "success",
                "result": str(res) if res is not None else "Complete",
            }
        except Exception as err:  # noqa: BLE001
            return {
                "status": "error",
                "message": f"Build execution failed: {err}",
            }

    def get_2d_plasma_shape(self, num_points: int = 120) -> dict[str, Any]:
        """
        Compute 2D R-Z cross-section coordinates for plasma and concentric shells.

        Uses Miller parameterization:
        R(theta) = R_0 + a * cos(theta + arcsin(delta) * sin(theta))
        Z(theta) = Z_0 + a * kappa * sin(theta)

        Parameters
        ----------
        num_points:
            Number of points for discretization.

        Returns
        -------
        :
            Dictionary containing lists of R and Z coordinates for plasma,
            blanket, and vacuum vessel contours.
        """

        def _safe_float(path: str, default: float) -> float:
            try:
                val = self.working_config.get_param_value(path)
                return float(val) if val is not None else default
            except (KeyError, ValueError, BluemiraError):
                return default

        r0 = (
            _safe_float("plasma.designer.r_0", 0.0)
            or _safe_float("plasma.designer.major_radius", 0.0)
            or _safe_float("R_0", 0.0)
            or _safe_float("params.R_0", 0.0)
            or 9.0
        )
        aspect = _safe_float("A", 0.0) or _safe_float("params.A", 0.0)
        a = (
            _safe_float("plasma.designer.minor_radius", 0.0)
            or _safe_float("plasma.designer.a", 0.0)
            or (r0 / aspect if aspect > 0 else 0.0)
            or _safe_float("a", 0.0)
            or 3.0
        )
        kappa = (
            _safe_float("plasma.designer.elongation", 0.0)
            or _safe_float("plasma.designer.kappa", 0.0)
            or _safe_float("kappa", 0.0)
            or _safe_float("kappa_95", 0.0)
            or 1.8
        )
        delta = (
            _safe_float("plasma.designer.triangularity", 0.0)
            or _safe_float("plasma.designer.delta", 0.0)
            or _safe_float("delta", 0.0)
            or _safe_float("delta_95", 0.0)
            or 0.35
        )
        z0 = _safe_float("plasma.designer.z_0", 0.0) or _safe_float("z_0", 0.0)

        theta = np.linspace(0, 2 * np.pi, num_points)
        delta_clamped = max(-0.95, min(0.95, delta))
        asin_delta = np.arcsin(delta_clamped)
        r_coords = r0 + a * np.cos(theta + asin_delta * np.sin(theta))
        z_coords = z0 + a * kappa * np.sin(theta)

        blanket_thick = (
            _safe_float("blanket.designer.thickness", 0.0)
            or _safe_float("tk_bb_ob", 0.0)
            or _safe_float("tk_bb_ib", 0.0)
            or 0.8
        )
        vv_thick = (
            _safe_float("vacuum_vessel.designer.thickness", 0.0)
            or _safe_float("tk_vv_out", 0.0)
            or _safe_float("tk_vv_in", 0.0)
            or 0.4
        )

        r_bb = r0 + (a + blanket_thick) * np.cos(theta + asin_delta * np.sin(theta))
        z_bb = z0 + (a + blanket_thick) * kappa * np.sin(theta)

        r_vv = r0 + (a + blanket_thick + vv_thick) * np.cos(
            theta + asin_delta * np.sin(theta)
        )
        z_vv = z0 + (a + blanket_thick + vv_thick) * kappa * np.sin(theta)

        return {
            "r0": r0,
            "a": a,
            "kappa": kappa,
            "delta": delta,
            "plasma": {"r": r_coords.tolist(), "z": z_coords.tolist()},
            "blanket": {"r": r_bb.tolist(), "z": z_bb.tolist()},
            "vacuum_vessel": {"r": r_vv.tolist(), "z": z_vv.tolist()},
        }

    def get_3d_mesh(self, cutaway_deg: float = 90.0) -> dict[str, Any]:
        """
        Generate 3D polygonal mesh for the current reactor configuration.

        Parameters
        ----------
        cutaway_deg:
            Cutaway sector angle in degrees (0 to 180).

        Returns
        -------
        :
            Dictionary of component meshes.
        """
        from bluemira.gui.cad import generate_tokamak_3d_mesh  # noqa: PLC0415

        return generate_tokamak_3d_mesh(self.working_config, cutaway_deg=cutaway_deg)

    def export_cad_obj(self, cutaway_deg: float = 90.0) -> str:
        """
        Generate Wavefront OBJ format string of tokamak 3D geometry.

        Parameters
        ----------
        cutaway_deg:
            Cutaway sector angle in degrees.

        Returns
        -------
        :
            OBJ formatted string.
        """
        from bluemira.gui.cad import (  # noqa: PLC0415
            export_mesh_to_obj,
            generate_tokamak_3d_mesh,
        )

        mesh_dict = generate_tokamak_3d_mesh(
            self.working_config, cutaway_deg=cutaway_deg
        )
        return export_mesh_to_obj(mesh_dict)

    def run_scan(
        self,
        variables_spec: list[dict[str, Any]],
        metric_names: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Run a parametric sweep based on user-selected variables.

        Parameters
        ----------
        variables_spec:
            List of variable specification dictionaries:
            `{'name': 'Plasma.designer.R_0', 'values': [8.5, 9.0, 9.5], 'unit': 'm'}`
        metric_names:
            Optional list of metric extractor names to evaluate.

        Returns
        -------
        :
            Dictionary representation of `ScanResult`.
        """

        def _cfg_of(output: Any) -> ReactorConfig:
            return output if isinstance(output, ReactorConfig) else self.working_config

        def _safe_cfg_float(
            cfg: ReactorConfig,
            path: str | Sequence[str],
            default: float,
        ) -> float:
            paths = [path] if isinstance(path, str) else path
            for p in paths:
                try:
                    val = cfg.get_param_value(p)
                    if val is not None:
                        return float(val)
                except (KeyError, ValueError, BluemiraError):
                    continue
            return default

        # Built-in standard fusion reactor metrics
        standard_extractors = [
            ScanMetric(
                name="aspect_ratio",
                extractor=lambda out: round(
                    _safe_cfg_float(_cfg_of(out), ["A", "params.A"], 0.0)
                    or (
                        _safe_cfg_float(
                            _cfg_of(out),
                            ["plasma.designer.r_0", "R_0", "params.R_0"],
                            9.0,
                        )
                        / max(
                            0.01,
                            _safe_cfg_float(
                                _cfg_of(out),
                                [
                                    "plasma.designer.minor_radius",
                                    "plasma.designer.a",
                                    "a",
                                    "params.a",
                                ],
                                3.0,
                            ),
                        )
                    ),
                    3,
                ),
                unit="",
                description="Aspect ratio R0 / a",
            ),
            ScanMetric(
                name="plasma_volume",
                extractor=lambda out: round(
                    _safe_cfg_float(_cfg_of(out), ["V_p", "params.V_p"], 0.0)
                    or (
                        2
                        * (math.pi**2)
                        * _safe_cfg_float(
                            _cfg_of(out),
                            ["plasma.designer.r_0", "R_0", "params.R_0"],
                            9.0,
                        )
                        * (
                            (
                                _safe_cfg_float(
                                    _cfg_of(out),
                                    [
                                        "plasma.designer.minor_radius",
                                        "plasma.designer.a",
                                        "a",
                                        "params.a",
                                    ],
                                    0.0,
                                )
                                or (
                                    _safe_cfg_float(
                                        _cfg_of(out),
                                        [
                                            "plasma.designer.r_0",
                                            "R_0",
                                            "params.R_0",
                                        ],
                                        9.0,
                                    )
                                    / max(
                                        0.01,
                                        _safe_cfg_float(
                                            _cfg_of(out),
                                            ["A", "params.A"],
                                            3.0,
                                        ),
                                    )
                                )
                            )
                            ** 2
                        )
                        * _safe_cfg_float(
                            _cfg_of(out),
                            [
                                "plasma.designer.elongation",
                                "plasma.designer.kappa",
                                "kappa",
                                "kappa_95",
                            ],
                            1.8,
                        )
                    ),
                    2,
                ),
                unit="m^3",
                description="Approximate plasma volume",
            ),
            ScanMetric(
                name="plasma_surface_area",
                extractor=lambda out: round(
                    4
                    * (math.pi**2)
                    * _safe_cfg_float(
                        _cfg_of(out),
                        ["plasma.designer.r_0", "R_0", "params.R_0"],
                        9.0,
                    )
                    * (
                        _safe_cfg_float(
                            _cfg_of(out),
                            [
                                "plasma.designer.minor_radius",
                                "plasma.designer.a",
                                "a",
                                "params.a",
                            ],
                            0.0,
                        )
                        or (
                            _safe_cfg_float(
                                _cfg_of(out),
                                ["plasma.designer.r_0", "R_0", "params.R_0"],
                                9.0,
                            )
                            / max(
                                0.01,
                                _safe_cfg_float(_cfg_of(out), ["A", "params.A"], 3.0),
                            )
                        )
                    )
                    * math.sqrt(
                        (
                            1
                            + _safe_cfg_float(
                                _cfg_of(out),
                                [
                                    "plasma.designer.elongation",
                                    "plasma.designer.kappa",
                                    "kappa",
                                    "kappa_95",
                                ],
                                1.8,
                            )
                            ** 2
                        )
                        / 2.0
                    ),
                    2,
                ),
                unit="m^2",
                description="Approximate plasma surface area",
            ),
            ScanMetric(
                name="blanket_thickness",
                extractor=lambda out: _safe_cfg_float(
                    _cfg_of(out),
                    [
                        "blanket.designer.thickness",
                        "tk_bb_ob",
                        "tk_bb_ib",
                        "params.tk_bb_ob",
                    ],
                    0.8,
                ),
                unit="m",
                description="Blanket radial thickness",
            ),
        ]

        if metric_names:
            extractors = [m for m in standard_extractors if m.name in metric_names]
        else:
            extractors = standard_extractors

        # Use identity build function if none supplied so output passed is config
        build_func = self.build_fn if self.build_fn is not None else (lambda cfg: cfg)

        scan = ParametricScan(
            build_fn=build_func,
            base_config=self.working_config,
        )

        for v in variables_spec:
            scan.add_variable(name=v["name"], values=v["values"], unit=v.get("unit"))

        for m in extractors:
            scan.add_metric(
                name=m.name,
                extractor=m.extractor,
                unit=m.unit,
                description=m.description,
            )

        result = scan.run(n_workers=1)
        self.last_scan_result = result
        return result.to_dict()

    def get_last_scan(self) -> dict[str, Any] | None:
        """
        Get the most recent parameter scan result.

        Returns
        -------
        :
            Dictionary of scan result or None if no scan was executed yet.
        """
        if self.last_scan_result is None:
            return None
        return self.last_scan_result.to_dict()

    def export_scan_csv(self) -> str:
        """
        Export the last scan result as CSV.

        Returns
        -------
        :
            CSV formatted string or empty string if no scan.
        """
        if self.last_scan_result is None:
            return ""

        records = self.last_scan_result.to_records()
        if not records:
            return ""

        out = io.StringIO()
        fieldnames = list(records[0].keys())
        writer = csv.DictWriter(out, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
        return out.getvalue()

    def apply_scan_point(self, point_index: int) -> dict[str, Any]:
        """
        Apply parameter values from a specific scan point to working config.

        Parameters
        ----------
        point_index:
            0-based index of the sweep evaluation to apply.

        Returns
        -------
        :
            Dictionary mapping applied parameter paths to their new values.

        Raises
        ------
        BluemiraError
            If no scan results exist or point_index is out of range.
        """
        if self.last_scan_result is None:
            raise BluemiraError("No scan results available.")

        pts = self.last_scan_result.points
        if point_index < 0 or point_index >= len(pts):
            raise BluemiraError(
                f"Point index {point_index} is out of bounds (0..{len(pts) - 1})."
            )

        pt = pts[point_index]
        applied = {}
        for var_name, val in pt.variables.items():
            self.update_parameter(var_name, val, source=f"Sweep point {point_index}")
            applied[var_name] = val

        return {
            "applied_point": point_index,
            "variables": applied,
        }
