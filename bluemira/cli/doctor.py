# SPDX-FileCopyrightText: 2021-present M. Coleman, J. Cook, F. Franza
# SPDX-FileCopyrightText: 2021-present I.A. Maione, S. McIntosh
# SPDX-FileCopyrightText: 2021-present J. Morris, D. Short
#
# SPDX-License-Identifier: LGPL-2.1-or-later

"""
Environment and dependency diagnostics subcommand for Bluemira CLI.
"""

from __future__ import annotations

import importlib
import os
import platform
import sys

import click
from rich.console import Console
from rich.table import Table

import bluemira


def check_cad_backend() -> tuple[str, bool]:
    """
    Check availability of the active geometry CAD backend.

    Returns
    -------
    :
        Tuple of (backend_name_with_status, is_healthy).
    """
    backend = os.environ.get("BLUEMIRA_GEOMETRY_BACKEND", "cadquery").lower()
    if backend not in {"cadquery", "freecad"}:
        return f"Unknown ({backend})", False

    mod_name = "cadquery" if backend == "cadquery" else "FreeCAD"
    try:
        importlib.import_module(mod_name)
    except ImportError as exc:
        return f"{backend} (ImportError: {exc})", False
    else:
        name = "CadQuery" if backend == "cadquery" else "FreeCAD"
        return f"{name} (active: {backend})", True


def check_units() -> tuple[str, bool]:
    """
    Check availability of the Pint unit registry.

    Returns
    -------
    :
        Tuple of (status_string, is_healthy).
    """
    try:
        from bluemira.base.constants import ureg  # noqa: PLC0415

        test_val = 10.0 * ureg.meter
        val_str = f"{test_val.magnitude} {test_val.units}"
    except Exception as exc:  # noqa: BLE001
        return f"Error: {exc}", False
    else:
        return f"Operational (e.g. {val_str})", True


def check_qt_env() -> tuple[str, bool]:
    """
    Check the Qt platform configuration.

    Returns
    -------
    :
        Tuple of (status_string, is_healthy).
    """
    qpa = os.environ.get("QT_QPA_PLATFORM", "not set (default)")
    display = os.environ.get("DISPLAY", "not set")
    return f"QT_QPA_PLATFORM={qpa}, DISPLAY={display}", True


@click.command(name="doctor")
def doctor_cmd() -> None:
    """
    Check your Bluemira environment, dependencies, and CAD backends.
    """
    console = Console()
    table = Table(title="Bluemira Environment Diagnostics", show_lines=True)
    table.add_column("Component", style="cyan", no_wrap=True)
    table.add_column("Status / Details", style="green")

    # Bluemira version
    table.add_row("Bluemira Version", getattr(bluemira, "__version__", "unknown"))

    # Python version and OS
    table.add_row(
        "Python Runtime",
        f"{sys.version.split()[0]} ({platform.system()} {platform.machine()})",
    )

    # CAD Backend
    cad_str, cad_ok = check_cad_backend()
    table.add_row("CAD Backend", cad_str, style="green" if cad_ok else "red")

    # Pint Units
    units_str, units_ok = check_units()
    table.add_row("Unit Registry", units_str, style="green" if units_ok else "red")

    # Qt Environment
    qt_str, _ = check_qt_env()
    table.add_row("Qt / Display", qt_str)

    console.print(table)
    console.print("[bold green]Diagnostics complete.[/bold green]")
