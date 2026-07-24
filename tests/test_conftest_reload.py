from pathlib import Path
from types import SimpleNamespace


def test_project_module_reload_filter_excludes_virtualenv_launchers():
    from conftest import _is_reloadable_project_module

    collectors = Path("/project/collectors")
    launcher = SimpleNamespace(__file__="/project/collectors/venv/bin/pytest", __spec__=None)
    project_module = SimpleNamespace(
        __file__="/project/collectors/analyzer.py",
        __spec__=SimpleNamespace(name="analyzer"),
    )

    assert _is_reloadable_project_module("__main__", launcher, collectors) is False
    assert _is_reloadable_project_module("analyzer", project_module, collectors) is True
