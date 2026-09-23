# SPDX-FileCopyrightText: 2021-present M. Coleman, J. Cook, F. Franza
# SPDX-FileCopyrightText: 2021-present I.A. Maione, S. McIntosh
# SPDX-FileCopyrightText: 2021-present J. Morris, D. Short
#
# SPDX-License-Identifier: LGPL-2.1-or-later

"""
Configuration inspection, dot-path querying, and mutation commands.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from bluemira.base.error import BluemiraError
from bluemira.base.parameter_frame import EmptyFrame
from bluemira.base.reactor_config import ReactorConfig


def _parse_value(val_str: str) -> Any:
    """
    Attempt to convert string into int, float, or bool if applicable.

    Parameters
    ----------
    val_str:
        Input string from CLI argument.

    Returns
    -------
    :
        Parsed Python type.
    """
    val_lower = val_str.strip().lower()
    if val_lower == "true":
        return True
    if val_lower == "false":
        return False
    try:
        return int(val_str)
    except ValueError:
        pass
    try:
        return float(val_str)
    except ValueError:
        pass
    return val_str


@click.group(name="config")
def config_group() -> None:
    """
    Inspect, query, and modify Bluemira reactor configuration files.
    """


@config_group.command(name="inspect")
@click.argument("config_path", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--filter",
    "-f",
    "filter_str",
    default=None,
    help="Filter parameters matching name or path substring.",
)
@click.option(
    "--json-output",
    "-j",
    is_flag=True,
    help="Output inspection results as structured JSON.",
)
def inspect_config(
    config_path: str,
    filter_str: str | None,
    *,
    json_output: bool,
) -> None:
    """
    Inspect all parameters declared in a ReactorConfig file.

    Parameters
    ----------
    config_path:
        Path to the ReactorConfig file.
    filter_str:
        Optional substring filter.
    json_output:
        If True, print structured JSON.
    """
    cfg = ReactorConfig(config_path, EmptyFrame)
    schema = cfg.get_param_schema()

    if filter_str:
        q = filter_str.lower()
        schema = [
            item
            for item in schema
            if q in item["path"].lower()
            or q in item["name"].lower()
            or q in str(item.get("description", "")).lower()
        ]

    if json_output:
        click.echo(json.dumps(schema, indent=2))
        return

    console = Console()
    table = Table(
        title=f"Configuration Parameters: {Path(config_path).name}", show_lines=True
    )
    table.add_column("Parameter Path", style="cyan", no_wrap=True)
    table.add_column("Value", style="bold green", justify="right")
    table.add_column("Unit", style="magenta")
    table.add_column("Component", style="yellow")
    table.add_column("Description", style="white")

    for item in schema:
        val_str = str(item["value"]) if item["value"] is not None else "None"
        unit_str = item["unit"] or "-"
        comp_str = (
            f"{item['component']}.{item['subcomponent']}"
            if item.get("subcomponent")
            else item.get("component", "")
        )
        desc_str = item.get("description") or ""
        table.add_row(
            item["path"],
            val_str,
            unit_str,
            comp_str,
            desc_str,
        )

    console.print(table)
    console.print(f"[bold]Total parameters listed: {len(schema)}[/bold]")


@config_group.command(name="get")
@click.argument("config_path", type=click.Path(exists=True, dir_okay=False))
@click.argument("param_path", type=str)
@click.option(
    "--value-only",
    "-v",
    is_flag=True,
    help="Print only the raw scalar value without units or labels.",
)
def get_param(
    config_path: str,
    param_path: str,
    *,
    value_only: bool,
) -> None:
    """
    Query a parameter value and unit by its dot-path.

    Parameters
    ----------
    config_path:
        Path to the ReactorConfig file.
    param_path:
        Dot-path parameter name.
    value_only:
        If True, outputs raw value without units or parameter label.

    Raises
    ------
    click.ClickException
        If parameter retrieval fails.
    """
    cfg = ReactorConfig(config_path, EmptyFrame)
    try:
        val = cfg.get_param_value(param_path)
    except (BluemiraError, KeyError, ValueError) as exc:
        raise click.ClickException(
            f"Error querying parameter '{param_path}': {exc}"
        ) from exc

    if value_only:
        click.echo(str(val))
        return

    param_obj = cfg.get_param(param_path)
    param_unit = (
        param_obj.get("unit")
        if isinstance(param_obj, dict)
        else getattr(param_obj, "unit", "")
    )
    unit_str = f" {param_unit}" if param_unit else ""
    click.echo(f"{param_path} = {val}{unit_str}")


@config_group.command(name="set")
@click.argument("config_path", type=click.Path(exists=True, dir_okay=False))
@click.argument("param_path", type=str)
@click.argument("new_value", type=str)
@click.option(
    "--unit",
    "-u",
    default=None,
    help="Optional new physical unit.",
)
@click.option(
    "--out",
    "-o",
    "out_path",
    type=click.Path(dir_okay=False),
    default=None,
    help="Path to save the modified configuration file.",
)
@click.option(
    "--in-place",
    "-i",
    is_flag=True,
    help="Overwrite the input configuration file in-place.",
)
def set_param(
    config_path: str,
    param_path: str,
    new_value: str,
    *,
    unit: str | None,
    out_path: str | None,
    in_place: bool,
) -> None:
    """
    Update a parameter in a ReactorConfig file using dot-path syntax.

    Parameters
    ----------
    config_path:
        Path to the ReactorConfig file.
    param_path:
        Dot-path parameter name.
    new_value:
        New value string.
    unit:
        Optional new unit.
    out_path:
        Optional destination file path.
    in_place:
        If True, save changes in-place.

    Raises
    ------
    click.ClickException
        If parameter mutation fails.
    """
    cfg = ReactorConfig(config_path, EmptyFrame)
    parsed = _parse_value(new_value)

    try:
        cfg.set_param(param_path, parsed, unit=unit)
    except (BluemiraError, KeyError, ValueError) as exc:
        raise click.ClickException(
            f"Error setting parameter '{param_path}': {exc}"
        ) from exc

    save_target = None
    if in_place:
        save_target = config_path
    elif out_path:
        save_target = out_path

    if save_target:
        cfg.save(save_target)
        click.echo(f"Saved modified configuration to: {save_target}")
    else:
        click.echo(json.dumps(cfg.to_dict(), indent=2))
