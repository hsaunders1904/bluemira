# SPDX-FileCopyrightText: 2021-present M. Coleman, J. Cook, F. Franza
# SPDX-FileCopyrightText: 2021-present I.A. Maione, S. McIntosh
# SPDX-FileCopyrightText: 2021-present J. Morris, D. Short
#
# SPDX-License-Identifier: LGPL-2.1-or-later

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from bluemira.base.constants import EPS, raw_uc
from bluemira.base.error import ParameterError, ReactorConfigError
from bluemira.base.logs import get_log_level, set_log_level
from bluemira.base.parameter_frame import (
    EmptyFrame,
    Parameter,
    ParameterFrame,
    make_parameter_frame,
)
from bluemira.base.reactor_config import ReactorConfig


@dataclass
class TestGlobalParams(ParameterFrame):
    __test__ = False

    only_global: Parameter[int]
    height: Parameter[float]
    age: Parameter[int]
    extra_global: Parameter[int]


@dataclass
class TestCompADesignerParams(ParameterFrame):
    __test__ = False

    only_global: Parameter[int]
    height: Parameter[float]
    age: Parameter[int]
    name: Parameter[str]
    location: Parameter[str]


test_config_path = Path(__file__).parent / "data" / "reactor_config.test.json"
empty_config_path = Path(__file__).parent / "data" / "reactor_config.empty.json"
nested_config_path = Path(__file__).parent / "data" / "reactor_config.nested_config.json"
nested_params_config_path = (
    Path(__file__).parent / "data" / "reactor_config.nested_params.json"
)
nesting_config_path = Path(__file__).parent / "data" / "reactor_config.nesting.json"


class TestReactorConfigClass:
    """
    Tests for the Reactor Config class functionality.
    """

    def setup_method(self):
        self.old_log_level = get_log_level()
        set_log_level("DEBUG")

    def teardown_method(self):
        set_log_level(self.old_log_level)

    def test_file_loading_with_empty_config(self, caplog):
        reactor_config = ReactorConfig(empty_config_path, EmptyFrame)

        # want to know explicitly if it is an EmptyFrame
        assert type(reactor_config.global_params) is EmptyFrame

        p_dne = reactor_config.params_for("dne")
        c_dne = reactor_config.config_for("dne")

        assert len(caplog.records) == 2
        for record in caplog.records:
            assert record.levelname == "DEBUG"

        assert len(p_dne.local_params) == 0
        assert len(c_dne) == 0

    def test_incorrect_global_config_type_empty_config(self):
        with pytest.raises(ValueError):  # noqa: PT011
            ReactorConfig(empty_config_path, TestGlobalParams)

    def test_incorrect_global_config_type_non_empty_config(self):
        with pytest.raises(ValueError):  # noqa: PT011
            ReactorConfig(test_config_path, EmptyFrame)

    def test_throw_on_too_specific_arg(self):
        reactor_config = ReactorConfig(test_config_path, TestGlobalParams)

        with pytest.raises(ReactorConfigError):
            reactor_config.config_for("comp A", "config_a", "a_value")

    def test_set_global_params(self, caplog):
        reactor_config = ReactorConfig(test_config_path, TestGlobalParams)

        cp = reactor_config.params_for("comp A", "designer")

        assert len(caplog.records) == 1
        for record in caplog.records:
            assert record.levelname == "DEBUG"

        cpf = make_parameter_frame(cp, TestCompADesignerParams)

        # instance checks
        assert cpf.only_global is reactor_config.global_params.only_global
        assert cpf.height is reactor_config.global_params.height
        assert cpf.age is reactor_config.global_params.age

        self._compa_designer_param_value_checks(cpf)

        cpf.only_global.value = raw_uc(2, "years", "s")
        assert cpf.only_global.value == raw_uc(2, "years", "s")
        assert reactor_config.global_params.only_global.value == raw_uc(2, "years", "s")
        assert cpf.only_global is reactor_config.global_params.only_global

    def _compa_designer_param_value_checks(self, cpf):
        assert cpf.only_global.value == raw_uc(1, "years", "s")
        assert cpf.height.value == pytest.approx(1.8, rel=0, abs=EPS)
        assert cpf.age.value == raw_uc(30, "years", "s")
        assert cpf.name.value == "Comp A"
        assert cpf.location.value == "here"

    def test_params_for_warnings_make_param_frame_type_value_overrides(self, caplog):
        reactor_config = ReactorConfig(test_config_path, TestGlobalParams)

        cp = reactor_config.params_for("comp A", "designer")

        assert len(caplog.records) == 1
        for record in caplog.records:
            assert record.levelname == "DEBUG"

        cpf = make_parameter_frame(cp, TestCompADesignerParams)

        self._compa_designer_param_value_checks(cpf)

        # instance checks
        assert cpf.only_global is reactor_config.global_params.only_global
        assert cpf.height is reactor_config.global_params.height
        assert cpf.age is reactor_config.global_params.age

    def test_config_for_warnings_value_overrides(self, caplog):
        reactor_config = ReactorConfig(test_config_path, TestGlobalParams)

        cf_comp_a = reactor_config.config_for("comp A")
        cf_comp_a_des = reactor_config.config_for("comp A", "designer")

        assert len(caplog.records) == 1
        for record in caplog.records:
            assert record.levelname == "DEBUG"

        assert cf_comp_a["config_a"] == cf_comp_a_des["config_a"]
        assert cf_comp_a["config_b"] == cf_comp_a_des["config_b"]
        assert cf_comp_a_des["config_c"]["c_value"] == "c_value"

    def test_no_params_warning(self, caplog):
        reactor_config = ReactorConfig({"comp A": {"designer": {}}}, EmptyFrame)

        cp = reactor_config.params_for("comp A", "designer")
        cp_dne = reactor_config.params_for("comp A", "designer", "dne")

        assert len(caplog.records) == 2
        for record in caplog.records:
            assert record.levelname == "DEBUG"

        assert len(cp.local_params) == 0
        assert len(cp_dne.local_params) == 0

    def test_no_config_warning(self, caplog):
        reactor_config = ReactorConfig({"comp A": {"designer": {}}}, EmptyFrame)

        cf_comp_a = reactor_config.config_for("comp A")
        cf_comp_a_des = reactor_config.config_for("comp A", "designer")
        cf_comp_a_des_dne = reactor_config.config_for("comp A", "designer", "dne")

        assert len(caplog.records) == 2
        for record in caplog.records:
            assert record.levelname == "DEBUG"

        assert len(cf_comp_a) == 1
        assert len(cf_comp_a_des) == 0
        assert len(cf_comp_a_des_dne) == 0

    def test_invalid_rc_initialisation(self):
        with pytest.raises(ReactorConfigError):
            ReactorConfig(["wrong"], EmptyFrame)

    def test_args_arent_str(self):
        reactor_config = ReactorConfig({"comp A": {"designer": {}}}, EmptyFrame)

        with pytest.raises(ReactorConfigError):
            reactor_config.config_for("comp A", 1)

    def test_file_path_loading_in_json_nested_params(self):
        out_dict = {
            "height": {"value": 1.8, "unit": "m"},
            "age": {"value": 946728000, "unit": "s"},
            "only_global": {"value": 31557600, "unit": "s"},
            "extra_global": {"value": 1, "unit": "s"},
        }
        reactor_config = ReactorConfig(nested_params_config_path, EmptyFrame)
        pf = make_parameter_frame(reactor_config.params_for("Tester"), TestGlobalParams)
        assert pf == TestGlobalParams.from_dict(out_dict)

    def test_file_path_loading_in_json_nested_config(self):
        reactor_config = ReactorConfig(nested_config_path, EmptyFrame)

        pf = make_parameter_frame(
            reactor_config.params_for("Tester", "comp A", "designer"),
            TestCompADesignerParams,
        )

        self._compa_designer_param_value_checks(pf)

        compa_designer_config = reactor_config.config_for("Tester", "comp A", "designer")
        assert compa_designer_config["config_a"] == {"a_value": "overridden_value"}
        assert compa_designer_config["config_b"] == {"b_value": "b_value"}
        assert compa_designer_config["config_c"] == {"c_value": "c_value"}

    def test_deeply_nested_files(self):
        reactor_config = ReactorConfig(nesting_config_path, EmptyFrame)

        assert reactor_config.config_for("nest_a")["a_val"] == "nest_a"
        assert reactor_config.config_for("nest_b")["a_val"] == "nest_b"

        assert reactor_config.params_for("nest_a").local_params["a_param"] == "nest_a"
        assert reactor_config.params_for("nest_b").local_params["a_param"] == "nest_b"

    def test_path_expansion(self):
        reactor_config = ReactorConfig(test_config_path, TestGlobalParams)

        assert (
            reactor_config.config_for("comp A")["test_expand_dir"]
            == test_config_path.parent.as_posix()
        )
        assert (
            reactor_config.config_for("comp A")["test_expand_file"]
            == (Path(test_config_path.parent) / "nest_a/nest_a.config.json").as_posix()
        )

    def test_param_dot_path_access(self):
        reactor_config = ReactorConfig(test_config_path, TestGlobalParams)
        p = reactor_config.get_param("comp A.designer.age")
        assert p["value"] == 3
        assert p["unit"] == "years"

        # Canonical path with .params. also works
        p_canon = reactor_config.get_param("comp A.designer.params.age")
        assert p_canon["value"] == 3

        # Global param
        p_global = reactor_config.get_param("params.height")
        assert p_global["value"] == 180
        assert p_global["unit"] == "cm"

        # Short global param name
        assert reactor_config.get_param("height")["value"] == 180

        # get_param_value
        assert reactor_config.get_param_value("comp A.designer.age") == 3
        assert reactor_config.get_param_value("height") == 180

    def test_param_dot_path_set(self):
        reactor_config = ReactorConfig(test_config_path, TestGlobalParams)
        reactor_config.set_param("comp A.designer.age", 15)
        assert reactor_config.get_param_value("comp A.designer.age") == 15

        # Updating global parameter updates both config_data and global_params frame
        reactor_config.set_param("params.height", 2.2, unit="m")
        assert reactor_config.get_param_value("height") == pytest.approx(
            2.2, rel=0, abs=EPS
        )
        assert reactor_config.global_params.height.value == pytest.approx(
            2.2, rel=0, abs=EPS
        )

    def test_param_bracket_and_contains(self):
        reactor_config = ReactorConfig(test_config_path, TestGlobalParams)
        assert "comp A.designer.age" in reactor_config
        assert "comp A.designer.dne" not in reactor_config
        assert reactor_config["comp A.designer.age"]["value"] == 3

        reactor_config["comp A.designer.age"] = 25
        assert reactor_config["comp A.designer.age"]["value"] == 25

    def test_dot_in_param_path_segment_error(self):
        reactor_config = ReactorConfig(test_config_path, TestGlobalParams)
        with pytest.raises(ParameterError, match="must not contain full stops"):
            reactor_config.get_param(["comp A", "designer.age"])

    def test_param_not_found_raises_reactor_config_error(self):
        reactor_config = ReactorConfig(test_config_path, TestGlobalParams)
        with pytest.raises(ReactorConfigError, match="not found in configuration"):
            reactor_config.get_param("nonexistent.component.param")

    def test_list_params(self):
        reactor_config = ReactorConfig(test_config_path, TestGlobalParams)
        params = reactor_config.list_params()
        assert "params.height" in params
        assert "comp A.name" in params
        assert "comp A.designer.age" in params

        canonical = reactor_config.list_params(canonical=True)
        assert "params.height" in canonical
        assert "comp A.params.name" in canonical
        assert "comp A.designer.params.age" in canonical

    def test_get_param_schema(self):
        reactor_config = ReactorConfig(test_config_path, TestGlobalParams)
        schema = reactor_config.get_param_schema()
        assert len(schema) > 0
        names = [item["name"] for item in schema]
        assert "height" in names
        assert "age" in names
        des_age = next(item for item in schema if item["path"] == "comp A.designer.age")
        assert des_age["component"] == "comp A"
        assert des_age["subcomponent"] == "designer"
        assert des_age["value"] == 3

    def test_to_dict_and_save(self, tmp_path):
        reactor_config = ReactorConfig(test_config_path, TestGlobalParams)
        data_copy = reactor_config.to_dict()
        assert isinstance(data_copy, dict)
        assert data_copy == reactor_config.config_data
        assert data_copy is not reactor_config.config_data

        save_path = tmp_path / "saved_config.json"
        reactor_config.save(save_path)
        assert save_path.exists()
        reloaded = ReactorConfig(save_path, TestGlobalParams)
        assert reloaded.get_param_value("comp A.designer.age") == 3

    def test_flat_parameter_dictionary_and_empty_frame(self, tmp_path):
        flat_dict = {
            "A": {
                "value": 2.7,
                "unit": "dimensionless",
                "source": "Input",
                "long_name": "Plasma aspect ratio",
            },
            "B_0": {
                "value": 6.0,
                "unit": "tesla",
                "source": "Input",
                "long_name": "Toroidal field at R_0",
            },
            "R_0": {
                "value": 9.0,
                "unit": "meter",
                "source": "Input",
                "long_name": "Major radius",
            },
        }
        json_file = tmp_path / "flat_params.json"
        with open(json_file, "w") as f:
            json.dump(flat_dict, f)

        cfg = ReactorConfig(json_file, EmptyFrame)
        params = cfg.list_params()
        assert len(params) == 3
        assert "A" in params
        assert "B_0" in params
        assert "R_0" in params

        assert cfg.get_param_value("A") == pytest.approx(2.7)
        assert cfg.get_param_value("params.A") == pytest.approx(2.7)
        assert cfg.get_param_value("R_0") == pytest.approx(9.0)

        schema = cfg.get_param_schema()
        assert len(schema) == 3
        a_schema = next(s for s in schema if s["name"] == "A")
        assert a_schema["description"] == "Plasma aspect ratio"
        assert a_schema["component"] == "global"

        cfg.set_param("A", 3.1)
        assert cfg.get_param_value("A") == pytest.approx(3.1)
        assert cfg.config_data["A"]["value"] == pytest.approx(3.1)
