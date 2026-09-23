# SPDX-FileCopyrightText: 2021-present M. Coleman, J. Cook, F. Franza
# SPDX-FileCopyrightText: 2021-present I.A. Maione, S. McIntosh
# SPDX-FileCopyrightText: 2021-present J. Morris, D. Short
#
# SPDX-License-Identifier: LGPL-2.1-or-later

"""
Main CLI entrypoint for Bluemira.
"""

from __future__ import annotations

import click

import bluemira
from bluemira.cli.config import config_group
from bluemira.cli.doctor import doctor_cmd
from bluemira.cli.scan import scan_group


@click.group(
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(
    version=getattr(bluemira, "__version__", "unknown"),
    prog_name="bluemira",
)
def cli() -> None:
    """
    Bluemira: Integrated Fusion Reactor Design & Analysis Framework.
    """


@cli.command(name="ui")
@click.argument("config_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--host", default="127.0.0.1", help="Host address to bind.")
@click.option("--port", default=8080, type=int, help="Port to listen on.")
@click.option(
    "--no-browser",
    is_flag=True,
    help="Do not automatically open the web browser.",
)
def ui_cmd(
    config_path: str,
    host: str,
    port: int,
    *,
    no_browser: bool,
) -> None:
    """
    Launch the interactive Bluemira parameter twiddler & 2D preview GUI.

    Parameters
    ----------
    config_path:
        Path to the ReactorConfig file to interactively edit.
    host:
        Host address to bind.
    port:
        Port number to listen on.
    no_browser:
        If True, do not automatically launch the web browser.
    """
    from bluemira.gui import GUIAppState, run_server  # noqa: PLC0415

    state = GUIAppState(config_path)
    run_server(state, host=host, port=port, open_browser=not no_browser)


cli.add_command(doctor_cmd)
cli.add_command(config_group)
cli.add_command(scan_group)
