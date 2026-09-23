# SPDX-FileCopyrightText: 2021-present M. Coleman, J. Cook, F. Franza
# SPDX-FileCopyrightText: 2021-present I.A. Maione, S. McIntosh
# SPDX-FileCopyrightText: 2021-present J. Morris, D. Short
#
# SPDX-License-Identifier: LGPL-2.1-or-later

"""
Parametric scan inspection and execution subcommands for Bluemira CLI.
"""

from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from bluemira.study.scan import ScanResult


@click.group(name="scan")
def scan_group() -> None:
    """
    Execute and inspect parametric reactor studies.
    """


@scan_group.command(name="inspect")
@click.argument("results_path", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--json-output",
    "-j",
    is_flag=True,
    help="Output full scan results as structured JSON.",
)
@click.option(
    "--failed-only",
    is_flag=True,
    help="Display only points that failed or were infeasible.",
)
def inspect_scan(
    results_path: str,
    *,
    json_output: bool,
    failed_only: bool,
) -> None:
    """
    Inspect the results of a previously completed ParametricScan.

    Parameters
    ----------
    results_path:
        Path to the saved scan result JSON file.
    json_output:
        If True, print structured JSON.
    failed_only:
        If True, display only infeasible or failed evaluation points.
    """
    scan_result = ScanResult.load(results_path)

    if json_output:
        click.echo(json.dumps(scan_result.to_dict(), indent=2))
        return

    console = Console()
    console.print(scan_result.summary())

    points = scan_result.points
    if failed_only:
        points = [p for p in points if not p.is_feasible]

    if not points:
        console.print("[green]No failed or infeasible points found.[/green]")
        return

    table = Table(
        title=f"Scan Evaluation Points: {Path(results_path).name}", show_lines=True
    )
    table.add_column("Point #", justify="right", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Runtime (s)", justify="right")

    for var_name in scan_result.variable_names:
        table.add_column(var_name, justify="right", style="magenta")

    for metric_name in scan_result.metric_names:
        table.add_column(metric_name, justify="right", style="green")

    for p in points:
        status_style = "green" if p.is_feasible else "red"
        row = [
            str(p.index),
            f"[{status_style}]{p.status.value}[/{status_style}]",
            f"{p.execution_time:.3f}",
        ]
        row.extend(str(p.variables.get(v, "-")) for v in scan_result.variable_names)
        for m in scan_result.metric_names:
            val = p.metrics.get(m, "-")
            row.append(f"{val:.4g}" if isinstance(val, (int, float)) else str(val))
        table.add_row(*row)

    console.print(table)
