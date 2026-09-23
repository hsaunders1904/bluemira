# SPDX-FileCopyrightText: 2021-present M. Coleman, J. Cook, F. Franza
# SPDX-FileCopyrightText: 2021-present I.A. Maione, S. McIntosh
# SPDX-FileCopyrightText: 2021-present J. Morris, D. Short
#
# SPDX-License-Identifier: LGPL-2.1-or-later

"""
CAD mesh generation and Wavefront OBJ export utilities for Bluemira GUI.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from bluemira.base.reactor_config import ReactorConfig


def generate_tokamak_3d_mesh(
    config: ReactorConfig,
    *,
    cutaway_deg: float = 90.0,
    num_poloidal: int = 40,
    num_toroidal: int = 48,
    num_tf_coils: int = 16,
) -> dict[str, Any]:
    """
    Generate 3D polygonal mesh data for tokamak components.

    Parameters
    ----------
    config:
        Bluemira ReactorConfig containing reactor/plasma parameters.
    cutaway_deg:
        Toroidal angle sector in degrees to cut away for internal view (0 to 180).
    num_poloidal:
        Poloidal mesh discretization count.
    num_toroidal:
        Toroidal mesh discretization count.
    num_tf_coils:
        Number of discrete TF coils.

    Returns
    -------
    :
        Dictionary mapping component names to mesh dictionaries:
        {'vertices': list[float], 'normals': list[float], 'indices': list[int],
         'color': str, 'opacity': float}
    """

    def _safe_float(path: str, default: float) -> float:
        try:
            val = config.get_param_value(path)
            return float(val) if val is not None else default
        except Exception:  # noqa: BLE001
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
        or 1.75
    )
    delta = (
        _safe_float("plasma.designer.triangularity", 0.0)
        or _safe_float("plasma.designer.delta", 0.0)
        or _safe_float("delta", 0.0)
        or _safe_float("delta_95", 0.0)
        or 0.35
    )
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
    n_tf_param = int(_safe_float("n_TF", 0.0) or _safe_float("params.n_TF", 0.0))
    if n_tf_param > 0:
        num_tf_coils = n_tf_param

    # Toroidal range based on cutaway
    phi_start = np.radians(max(0.0, min(180.0, cutaway_deg)))
    phi_end = 2 * np.pi
    phis = np.linspace(phi_start, phi_end, num_toroidal)

    theta = np.linspace(0, 2 * np.pi, num_poloidal)
    delta_clamped = max(-0.95, min(0.95, delta))
    asin_delta = np.arcsin(delta_clamped)

    # 1. Plasma Core
    r_plasma = r0 + a * np.cos(theta + asin_delta * np.sin(theta))
    z_plasma = a * kappa * np.sin(theta)
    plasma_mesh = _surface_of_revolution(
        r_plasma, z_plasma, phis, color="#f97316", opacity=0.88
    )

    # 2. Blanket Shell
    r_bb = r0 + (a + blanket_thick) * np.cos(theta + asin_delta * np.sin(theta))
    z_bb = (a + blanket_thick) * kappa * np.sin(theta)
    blanket_mesh = _surface_of_revolution(
        r_bb, z_bb, phis, color="#0284c7", opacity=0.72
    )

    # 3. Vacuum Vessel Shell
    r_vv = r0 + (a + blanket_thick + vv_thick) * np.cos(
        theta + asin_delta * np.sin(theta)
    )
    z_vv = (a + blanket_thick + vv_thick) * kappa * np.sin(theta)
    vv_mesh = _surface_of_revolution(r_vv, z_vv, phis, color="#475569", opacity=0.55)

    # 4. Discrete D-shaped TF Coils
    tf_mesh = _generate_tf_coils(
        r_vv, z_vv, num_tf_coils=num_tf_coils, cutaway_deg=cutaway_deg
    )

    return {
        "plasma": plasma_mesh,
        "blanket": blanket_mesh,
        "vacuum_vessel": vv_mesh,
        "tf_coils": tf_mesh,
    }


def _surface_of_revolution(
    r_coords: np.ndarray,
    z_coords: np.ndarray,
    phis: np.ndarray,
    *,
    color: str,
    opacity: float,
) -> dict[str, Any]:
    """
    Revolve a poloidal contour (R, Z) around the Z axis for specified toroidal angles.

    Returns
    -------
    :
        Dictionary with vertices, normals, indices, color, and opacity.
    """
    num_p = len(r_coords)
    num_t = len(phis)

    vertices: list[float] = []
    normals: list[float] = []
    indices: list[int] = []

    # Build grid of 3D vertices
    for phi in phis:
        cos_phi = np.cos(phi)
        sin_phi = np.sin(phi)
        for r, z in zip(r_coords, z_coords, strict=True):
            x = r * cos_phi
            y = r * sin_phi
            vertices.extend([
                round(float(x), 4),
                round(float(y), 4),
                round(float(z), 4),
            ])
            # Radial outward surface normal approximation
            normals.extend([
                round(float(cos_phi), 4),
                round(float(sin_phi), 4),
                0.0,
            ])

    # Build triangular face indices connecting adjacent toroidal slices
    for t in range(num_t - 1):
        for p in range(num_p - 1):
            v0 = t * num_p + p
            v1 = (t + 1) * num_p + p
            v2 = (t + 1) * num_p + (p + 1)
            v3 = t * num_p + (p + 1)
            indices.extend([v0, v1, v2, v0, v2, v3])

    return {
        "vertices": vertices,
        "normals": normals,
        "indices": indices,
        "color": color,
        "opacity": opacity,
    }


def _generate_tf_coils(
    r_vv: np.ndarray,
    z_vv: np.ndarray,
    *,
    num_tf_coils: int = 16,
    cutaway_deg: float = 90.0,
    coil_width: float = 0.5,
) -> dict[str, Any]:
    """
    Generate 3D polygonal geometries for discrete D-shaped TF coils.

    Returns
    -------
    :
        Dictionary with vertices, normals, indices, color, and opacity.
    """
    r_max = np.max(r_vv) * 1.15
    r_min = max(0.5, np.min(r_vv) * 0.85)
    z_max = np.max(z_vv) * 1.2
    z_min = np.min(z_vv) * 1.2

    theta = np.linspace(0, 2 * np.pi, 24)
    r_center = (r_max + r_min) / 2
    r_rad = (r_max - r_min) / 2
    z_rad = (z_max - z_min) / 2

    # Poloidal ring of coil centerline
    coil_r = r_center + r_rad * np.cos(theta)
    coil_z = z_rad * np.sin(theta)

    vertices: list[float] = []
    normals: list[float] = []
    indices: list[int] = []

    coil_angles = np.linspace(0, 2 * np.pi, num_tf_coils, endpoint=False)
    cutaway_rad = np.radians(max(0.0, min(180.0, cutaway_deg)))

    base_idx = 0
    for phi in coil_angles:
        # Skip coils located in the cutaway window
        if 0 < phi < cutaway_rad:
            continue

        cos_phi = np.cos(phi)
        sin_phi = np.sin(phi)

        for r, z in zip(coil_r, coil_z, strict=True):
            for dr in [-coil_width / 2, coil_width / 2]:
                rr = r + dr
                x = rr * cos_phi
                y = rr * sin_phi
                vertices.extend([
                    round(float(x), 4),
                    round(float(y), 4),
                    round(float(z), 4),
                ])
                normals.extend([
                    round(float(cos_phi), 4),
                    round(float(sin_phi), 4),
                    0.0,
                ])

        num_pts = len(coil_r)
        for i in range(num_pts - 1):
            v0 = base_idx + i * 2
            v1 = base_idx + i * 2 + 1
            v2 = base_idx + (i + 1) * 2 + 1
            v3 = base_idx + (i + 1) * 2
            indices.extend([v0, v1, v2, v0, v2, v3])

        base_idx += num_pts * 2

    return {
        "vertices": vertices,
        "normals": normals,
        "indices": indices,
        "color": "#a855f7",
        "opacity": 0.95,
    }


def export_mesh_to_obj(mesh_dict: dict[str, Any]) -> str:
    """
    Export tokamak 3D mesh dictionary to Wavefront OBJ format.

    Parameters
    ----------
    mesh_dict:
        Dictionary mapping component names to mesh dictionaries.

    Returns
    -------
    :
        Wavefront OBJ formatted string.
    """
    out = io.StringIO()
    out.write("# Bluemira CAD WebGL Export\n")
    out.write("# Units: meters\n\n")

    v_offset = 1
    for comp_name, mesh in mesh_dict.items():
        vertices = mesh.get("vertices", [])
        indices = mesh.get("indices", [])
        if not vertices or not indices:
            continue

        out.write(f"o {comp_name}\n")
        # Write vertices (groups of 3)
        for i in range(0, len(vertices), 3):
            out.write(f"v {vertices[i]} {vertices[i + 1]} {vertices[i + 2]}\n")

        # Write triangular faces (1-based index)
        for i in range(0, len(indices), 3):
            i1 = indices[i] + v_offset
            i2 = indices[i + 1] + v_offset
            i3 = indices[i + 2] + v_offset
            out.write(f"f {i1} {i2} {i3}\n")

        v_offset += len(vertices) // 3
        out.write("\n")

    return out.getvalue()
