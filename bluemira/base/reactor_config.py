# SPDX-FileCopyrightText: 2021-present M. Coleman, J. Cook, F. Franza
# SPDX-FileCopyrightText: 2021-present I.A. Maione, S. McIntosh
# SPDX-FileCopyrightText: 2021-present J. Morris, D. Short
#
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Class to hold parameters and config values."""

from __future__ import annotations

import copy
import json
import pprint
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bluemira.base.constants import ureg
from bluemira.base.error import ParameterError, ReactorConfigError
from bluemira.base.look_and_feel import bluemira_debug, bluemira_warn
from bluemira.base.parameter_frame import EmptyFrame, make_parameter_frame

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from bluemira.base.parameter_frame._parameter import ParamDictT
    from bluemira.base.parameter_frame.typed import ParameterFrameT


@dataclass
class ConfigParams:
    """Container for the global and local parameters of a `ReactorConfig`."""

    global_params: ParameterFrameT
    local_params: dict[str, ParamDictT]


_PARAMETERS_KEY = "params"
_FILEPATH_PREFIX = "$path:"
_FILEPATH_EXPANSION_PREFIX = "$path_expand:"
_GLOBAL_PARAM_DEPTH = 2
_MIN_SUBCOMP_DEPTH = 2
_DEFAULT_JSON_INDENT = 2


class ReactorConfig:
    """
    Class that provides a simple interface over config JSON files and
    handles overwriting multiply defined attributes.

    If an attribute is defined more than once in a component,
    it will be overwritten in order of inheritance.

    Parameters
    ----------
    config_path:
        Path to the config file, or dictionary with the configuration data.
    global_params_type:
        The type of the global parameters.
    warn_on_duplicate_keys:
        Print a warning when duplicate keys are found,
        whose value will be overwritten.
    warn_on_empty_local_params:
        Print a warning when the local params for some args are empty,
        when calling params_for(args)
    warn_on_empty_config:
        Print a warning when the config for some args are empty,
        when calling config_for(args)

    Example
    -------

    .. code-block:: python

        from bluemira.base.parameter_frame import Parameter, ParameterFrame

        @dataclass
        class GlobalParams(ParameterFrame):
            a: Parameter[int]


        reactor_config = ReactorConfig(
            {
                "params": {"a": {"value": 10, "unit": 'm'}},
                "comp A": {
                    "params": {
                        "a": {"value": 5, "unit": 'm'},
                        "b": {"value": 5, "unit": 'm'},
                    },
                    "designer": {
                        "params": {"a": {"value": 1, "unit": 'm'}},
                        "some_config": "some_value",
                    },
                    "builder": {
                        "params": {
                            "b": {"value": 1, "unit": 'm'},
                            "c": {"value": 1, "unit": 'm'},
                        },
                        "another_config": "another_value",
                    },
                },
                "comp B": {
                    "params": {"b": {"value": 1, "unit": 'm'}},
                    "builder": {
                        "third_config": "third_value",
                    },
                },
            },
            GlobalParams
        )

    """

    def __init__(
        self,
        config_path: str | Path | dict,
        global_params_type: type[ParameterFrameT],
        *,
        warn_on_duplicate_keys: bool = False,
        warn_on_empty_local_params: bool = False,
        warn_on_empty_config: bool = False,
    ):
        self.warn_on_duplicate_keys = warn_on_duplicate_keys
        self.warn_on_empty_local_params = warn_on_empty_local_params
        self.warn_on_empty_config = warn_on_empty_config

        config_data = self._read_or_return(config_path)
        if isinstance(config_path, Path | str):
            self._expand_paths_in_dict(config_data, Path(config_path).parent)

        self.config_data = config_data
        has_explicit_params = _PARAMETERS_KEY in self.config_data
        if has_explicit_params:
            global_dict = self.config_data.get(_PARAMETERS_KEY, {})
            allow_unknown = False
        else:
            global_dict = {
                k: v
                for k, v in self.config_data.items()
                if isinstance(v, dict) and "value" in v
            }
            allow_unknown = (
                issubclass(global_params_type, EmptyFrame)
                if isinstance(global_params_type, type)
                else False
            )

        self.global_params = make_parameter_frame(
            global_dict, global_params_type, allow_unknown=allow_unknown
        )

        if not self.global_params and not global_dict:
            bluemira_warn("Empty global params")

    def __str__(self) -> str:
        """Returns config_data as a nicely pretty formatted string.

        Returns
        -------
        :
            The pretty formatted string of the config_data.
        """
        return self._pprint_dict(self.config_data)

    @staticmethod
    def _warn_or_debug_log(msg: str, *, warn: bool = False) -> None:
        if warn:
            bluemira_warn(msg)
        else:
            bluemira_debug(msg)

    def params_for(self, component_name: str, *args: str) -> ConfigParams:
        """
        Gets the params for the `component_name` from the config file.

        These are all the values defined by a "params"
        key in the config file.

        Parameters
        ----------
        component_name:
            The name of the component to get the params for
        args:
            The subcomponents to get the params for

        Returns
        -------
        :
            A tuple of the global params and the local params
        """
        args = (component_name, *args)
        self._check_args_are_strings(args)

        local_params = self._extract(args, is_config=False)
        if not local_params:
            self._warn_or_debug_log(
                f"local params for {' '.join(args)} is empty",
                warn=self.warn_on_empty_local_params,
            )

        return ConfigParams(self.global_params, local_params)

    def config_for(self, component_name: str, *args: str) -> dict:
        """
        Gets the config for the `component_name` from the config file.

        These are all the values not defined by a "params"
        key in the config file.

        Parameters
        ----------
        component_name:
            The name of the component to get the config for
        args:
            The subcomponents to get the config for

        Returns
        -------
        :
            A dict of the config values
        """
        args = (component_name, *args)
        self._check_args_are_strings(args)

        config = self._extract(args)
        if not config:
            self._warn_or_debug_log(
                f"config for {' '.join(args)} is empty",
                warn=self.warn_on_empty_config,
            )
        return config

    @property
    def components(self) -> dict:
        """
        The components of the config file.

        These are all the top level keys in the config file
        excluding the "params" key.

        Returns
        -------
        :
            A dict of the components
        """
        return {k: v for k, v in self.config_data.items() if k != _PARAMETERS_KEY}

    @property
    def component_names(self) -> list[str]:
        """
        The names of the components in the config file.

        These are all the top level keys in the config file
        excluding the "params" key.

        Returns
        -------
        :
            A list of the component names
        """
        return list(self.components.keys())

    # -------------------------------------------------------------------------
    # Dot-path Parameter Access, Inspection & Persistence
    # -------------------------------------------------------------------------

    @staticmethod
    def _normalize_param_path(path: str | Sequence[str]) -> tuple[str, ...]:
        """
        Normalize a parameter path string or sequence into a tuple of segments.

        Parameters
        ----------
        path:
            A dot-separated string (e.g. 'Plasma.designer.R_0') or a sequence of
            strings (e.g. ['Plasma', 'designer', 'R_0']).

        Returns
        -------
        :
            Tuple of path segment strings.

        Raises
        ------
        ParameterError
            If path is empty, contains empty segments, or sequence elements contain
            full stops.
        """
        if isinstance(path, str):
            parts = tuple(part.strip() for part in path.split("."))
        else:
            parts = tuple(str(part).strip() for part in path)
            for part in parts:
                if "." in part:
                    msg = f"Parameter path segment '{part}' must not contain full stops."
                    raise ParameterError(msg)

        if not parts or any(not p for p in parts):
            msg = f"Invalid parameter path: {path!r}. Path cannot be empty."
            raise ParameterError(msg)
        return parts

    def _resolve_param_target(
        self, path: str | Sequence[str]
    ) -> tuple[dict[str, Any], str, tuple[str, ...]]:
        """
        Locate the dictionary container and key for a parameter path.

        Handles both direct paths (e.g. 'Plasma.designer.params.R_0') and
        concise paths omitting '.params.' (e.g. 'Plasma.designer.R_0'),
        single global parameter names, and top-level flat parameter keys.

        Returns
        -------
        :
            Tuple of (container_dict, leaf_key, canonical_path_tuple).

        Raises
        ------
        ReactorConfigError
            If parameter is not found.
        """
        parts = self._normalize_param_path(path)

        # 1. Direct path traversal
        container: Any = self.config_data
        direct_match = True
        for part in parts[:-1]:
            if isinstance(container, dict) and part in container:
                container = container[part]
            else:
                direct_match = False
                break

        if direct_match and isinstance(container, dict) and parts[-1] in container:
            val = container[parts[-1]]
            if isinstance(val, dict) and "value" in val:
                return container, parts[-1], parts

        # 2. Path omitting ".params." before the parameter name
        # e.g. ("Plasma", "designer", "R_0") -> check Plasma.designer.params.R_0
        if len(parts) >= _GLOBAL_PARAM_DEPTH and parts[-2] != _PARAMETERS_KEY:
            container = self.config_data
            params_match = True
            for part in parts[:-1]:
                if isinstance(container, dict) and part in container:
                    container = container[part]
                else:
                    params_match = False
                    break
            if (
                params_match
                and isinstance(container, dict)
                and _PARAMETERS_KEY in container
                and isinstance(container[_PARAMETERS_KEY], dict)
                and parts[-1] in container[_PARAMETERS_KEY]
            ):
                params_dict = container[_PARAMETERS_KEY]
                val = params_dict[parts[-1]]
                if isinstance(val, dict) and "value" in val:
                    canonical_path = (*parts[:-1], _PARAMETERS_KEY, parts[-1])
                    return params_dict, parts[-1], canonical_path

        # 3. Single parameter name referring to global params or top-level params
        if len(parts) == 1:
            global_params = self.config_data.get(_PARAMETERS_KEY, {})
            if isinstance(global_params, dict) and parts[0] in global_params:
                val = global_params[parts[0]]
                if isinstance(val, dict) and "value" in val:
                    return global_params, parts[0], (_PARAMETERS_KEY, parts[0])
            if parts[0] in self.config_data:
                val = self.config_data[parts[0]]
                if isinstance(val, dict) and "value" in val:
                    return self.config_data, parts[0], (parts[0],)

        # 4. Two-part path with 'params.<name>' when parameters are at top-level
        if (
            len(parts) == _GLOBAL_PARAM_DEPTH
            and parts[0] == _PARAMETERS_KEY
            and parts[1] in self.config_data
        ):
            val = self.config_data[parts[1]]
            if isinstance(val, dict) and "value" in val:
                return self.config_data, parts[1], (parts[1],)

        raise ReactorConfigError(
            f"Parameter '{'.'.join(parts)}' not found in configuration."
        )

    def get_param(self, path: str | Sequence[str]) -> dict[str, Any]:
        """
        Get the parameter dictionary for a given dot-path or path sequence.

        Parameters
        ----------
        path:
            The parameter path, e.g. 'Plasma.designer.R_0' or 'params.height'.

        Returns
        -------
        :
            The parameter dictionary (contains 'value', 'unit', etc.).
        """
        container, key, _ = self._resolve_param_target(path)
        return container[key]

    def get_param_value(self, path: str | Sequence[str]) -> Any:
        """
        Get the value of a parameter for a given dot-path or path sequence.

        Parameters
        ----------
        path:
            The parameter path, e.g. 'Plasma.designer.R_0' or 'params.height'.

        Returns
        -------
        :
            The parameter value.
        """
        return self.get_param(path).get("value")

    def set_param(
        self,
        path: str | Sequence[str],
        value: Any,
        *,
        unit: str | None = None,
        source: str | None = None,
    ) -> None:
        """
        Set the value and optionally unit/source of a parameter.

        Updates both `config_data` and any corresponding `global_params`
        in-place.

        Parameters
        ----------
        path:
            The parameter path, e.g. 'Plasma.designer.R_0' or 'params.height'.
        value:
            The new value for the parameter.
        unit:
            Optionally update the unit.
        source:
            Optionally update the source.
        """
        container, key, canonical_path = self._resolve_param_target(path)
        container[key]["value"] = value
        if unit is not None:
            container[key]["unit"] = unit
        if source is not None:
            container[key]["source"] = source

        # If this is a global parameter, keep self.global_params synchronized
        if (
            (
                canonical_path[0] == _PARAMETERS_KEY
                and len(canonical_path) == _GLOBAL_PARAM_DEPTH
            )
            or len(canonical_path) == 1
        ) and hasattr(self.global_params, key):
            global_param = getattr(self.global_params, key)
            if unit is not None:
                global_param._unit = ureg.Unit(unit)
            global_param.set_value(value, source or "ReactorConfig.set_param")

    def __getitem__(self, path: str | Sequence[str]) -> dict[str, Any]:
        """
        Get parameter dict via bracket notation.

        Parameters
        ----------
        path:
            Parameter dot-path, e.g. 'Plasma.designer.R_0'.

        Returns
        -------
        :
            The parameter dictionary.
        """
        return self.get_param(path)

    def __setitem__(self, path: str | Sequence[str], value: Any) -> None:
        """
        Set parameter value via bracket notation.

        Parameters
        ----------
        path:
            Parameter dot-path, e.g. 'Plasma.designer.R_0'.
        value:
            The new parameter value.
        """
        self.set_param(path, value)

    def __contains__(self, path: str | Sequence[str]) -> bool:
        """
        Check if parameter exists at path.

        Parameters
        ----------
        path:
            The parameter dot-path or path sequence.

        Returns
        -------
        :
            True if parameter exists, False otherwise.
        """
        try:
            self._resolve_param_target(path)
        except (ReactorConfigError, ParameterError):
            return False
        else:
            return True

    def _walk_params(
        self,
        data: dict[str, Any],
        current_path: tuple[str, ...],
    ) -> list[tuple[tuple[str, ...], tuple[str, ...], str, dict[str, Any]]]:
        """
        Recursively walk config data to collect all parameters.

        Returns
        -------
        :
            List of tuples (short_path, canonical_path, param_name, param_dict).
        """
        results = []
        for k, v in data.items():
            if k == _PARAMETERS_KEY and isinstance(v, dict):
                for p_name, p_data in v.items():
                    if isinstance(p_data, dict) and "value" in p_data:
                        canonical = (*current_path, _PARAMETERS_KEY, p_name)
                        short = (
                            (*current_path, p_name)
                            if current_path
                            else (_PARAMETERS_KEY, p_name)
                        )
                        results.append((short, canonical, p_name, p_data))
            elif isinstance(v, dict) and "value" in v:
                canonical = (*current_path, k)
                short = (*current_path, k)
                results.append((short, canonical, k, v))
            elif isinstance(v, dict):
                results.extend(self._walk_params(v, (*current_path, k)))
        return results

    def list_params(self, *, canonical: bool = False) -> dict[str, dict[str, Any]]:
        """
        Return a dictionary of all parameters mapped by their dot-paths.

        Parameters
        ----------
        canonical:
            If True, use canonical paths containing '.params.',
            otherwise use concise paths.

        Returns
        -------
        :
            Dict mapping dot-path to parameter dictionary.
        """
        entries = self._walk_params(self.config_data, ())
        res = {}
        for short_path, canonical_path, _, param_dict in entries:
            key = ".".join(canonical_path if canonical else short_path)
            res[key] = copy.deepcopy(param_dict)
        return res

    def get_param_schema(self) -> list[dict[str, Any]]:
        """
        Return schema metadata for all parameters in the configuration.

        Useful for GUI generation, CLI inspection, and scan setups.

        Returns
        -------
        :
            List of parameter metadata dictionaries.
        """
        entries = self._walk_params(self.config_data, ())
        schema = []
        for short_path, canonical_path, p_name, p_data in entries:
            component = (
                "global"
                if len(short_path) <= 1 or short_path[0] == _PARAMETERS_KEY
                else short_path[0]
            )
            subcomponent = (
                ".".join(short_path[1:-1])
                if len(short_path) > _MIN_SUBCOMP_DEPTH and component != "global"
                else ""
            )
            schema.append({
                "name": p_name,
                "path": ".".join(short_path),
                "canonical_path": ".".join(canonical_path),
                "component": component,
                "subcomponent": subcomponent,
                "value": p_data.get("value"),
                "unit": p_data.get("unit", ""),
                "source": p_data.get("source", ""),
                "long_name": p_data.get("long_name", ""),
                "description": p_data.get("description", "")
                or p_data.get("long_name", ""),
            })
        return schema

    def to_dict(self) -> dict[str, Any]:
        """
        Return a deep copy of the configuration dictionary.

        Returns
        -------
        :
            A deep copy of config_data.
        """
        return copy.deepcopy(self.config_data)

    def save(self, path: str | Path, *, indent: int = _DEFAULT_JSON_INDENT) -> None:
        """
        Save the configuration data to a JSON file.

        Parameters
        ----------
        path:
            Target file path.
        indent:
            JSON indentation level.
        """
        with open(path, "w") as f:
            json.dump(self.config_data, f, indent=indent)

    # -------------------------------------------------------------------------
    # Internal Loading and Extraction Routines
    # -------------------------------------------------------------------------

    @staticmethod
    def _read_or_return(config_path: str | Path | dict) -> dict:
        if isinstance(config_path, str | Path):
            return ReactorConfig._read_json_file(config_path)
        if isinstance(config_path, dict):
            return config_path
        raise ReactorConfigError(
            "config_path must be either a dict, a Path object, or a string, found"
            f" {type(config_path)}."
        )

    @staticmethod
    def _read_json_file(path: Path | str) -> dict:
        with open(path) as f:
            return json.load(f)

    @staticmethod
    def _pprint_dict(d: dict) -> str:
        return pprint.pformat(d, sort_dicts=False, indent=1)

    def _warn_on_duplicate_keys(self, shared_key: str, arg: str, existing_value):
        self._warn_or_debug_log(
            "duplicate config key: "
            f"'{shared_key}' in {arg} wil be overwritten with {existing_value}",
            warn=self.warn_on_duplicate_keys,
        )

    @staticmethod
    def _check_args_are_strings(args: Iterable[str]):
        for a in args:
            if not isinstance(a, str):
                raise ReactorConfigError("args must be strings")

    def _expand_paths_in_dict(self, d: dict[str, Any], rel_path: Path):
        """
        Expand all file paths by replacing their values with the json file's contents.

        Notes
        -----
            This mutates the passed in dict.
        """
        for k in d:  # noqa: PLC0206
            d[k], rel_path_from = self._extract_and_expand_file_data_if_needed(
                d[k], rel_path
            )
            if isinstance(d[k], str):
                d[k] = self._expand_filepath_if_needed(d[k], rel_path_from)

            if isinstance(d[k], dict):
                self._expand_paths_in_dict(d[k], rel_path_from)

    def _extract_and_expand_file_data_if_needed(
        self, value: Any, rel_path: Path
    ) -> tuple[Any | dict, Path]:
        """
        Returns the file data and the path to the file if value is a path.

        Otherwise, returns value and rel_path that was passed in.

        rel_path is the path to the file that the value is in.

        Returns
        -------
        :
            Tuple of the file data and the path to the file if value is a path.

        Raises
        ------
        FileNotFoundError
            Cannot find provided path

        Notes
        -----
        If the value is not a path, returns the value and the passed in rel_path.
        """
        if not isinstance(value, str):
            return value, rel_path
        if not value.startswith(_FILEPATH_PREFIX):
            return value, rel_path

        # remove _FILEPATH_PREFIX
        f_path = value[len(_FILEPATH_PREFIX) :]

        # if the path does not start with a /, it is considered a relative path,
        # relative to the file the path is in (i.e. rel_path)
        f_path = rel_path / f_path if not f_path.startswith("/") else Path(f_path)

        # check if file exists
        if not f_path.is_file():
            raise FileNotFoundError(f"Cannot find file {f_path}")

        f_data = self._read_json_file(f_path)
        return f_data, f_path.parent

    def _extract(self, arg_keys: tuple[str], *, is_config: bool = True) -> dict:
        extracted = {}

        # this routine is designed not to copy any dict's while parsing

        current_layer = self.config_data

        for next_idx, current_arg_key in enumerate(arg_keys, start=1):
            current_layer = current_layer.get(current_arg_key, {})
            next_arg_key = arg_keys[next_idx] if next_idx < len(arg_keys) else None

            to_extract = current_layer
            if not is_config:
                # if doing a params extraction,
                # get the values from the _PARAMETERS_KEY
                to_extract = current_layer.get(_PARAMETERS_KEY, {})

            if not isinstance(to_extract, dict):
                raise ReactorConfigError(
                    f"Arg {current_arg_key} is too specific, "
                    "it must either be another JSON object "
                    "or a path to a JSON file."
                )

            # add all keys not in extracted already
            # if doing a config, ignore the "params" (_PARAMETERS_KEY)
            # and don't add the next arg key
            for k, v in to_extract.items():
                if k in extracted:
                    self._warn_on_duplicate_keys(k, current_arg_key, extracted[k])
                    continue
                if is_config:
                    if k == _PARAMETERS_KEY:
                        continue
                    if next_arg_key and k == next_arg_key:
                        continue
                extracted[k] = v

        return extracted

    @staticmethod
    def _expand_filepath_if_needed(value: str, config_dir: Path) -> str:
        """
        Checks if the value has a path expansion directive and expands it to the absolute
        path with respect to the config directory.

        Returns
        -------
        Absolute path as str
        """
        if not value.startswith(_FILEPATH_EXPANSION_PREFIX):
            return value

        # remove _FILEPATH_PREFIX
        path_str = value[len(_FILEPATH_EXPANSION_PREFIX) :]

        # if the path does not start with a /, it is considered a relative path,
        # relative to the file the path is in (i.e. rel_path)
        path_value = (
            config_dir / path_str if not path_str.startswith("/") else Path(path_str)
        )

        return str(path_value.resolve())
