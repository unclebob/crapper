from pathlib import Path
from typing import Final

from tree_sitter import Node

from crapper.coverage.formats import LCOV, LCOV_REPORTS, Lines
from crapper.coverage.tool import attempt, run
from crapper.decode import decoded
from crapper.language import Language, Project
from crapper.languages.treesitter import Grammar, ancestors, enclosing
from crapper.model import Source
from crapper.paths import has_file, module_parts

_NAME: Final = "python"
_TESTS = ("test_*.py", "*_test.py", "conftest.py")
_PROJECTS = ("pyproject.toml", "setup.cfg", "setup.py", "pytest.ini", "tox.ini")
_PYTEST_FILES = ("pytest.ini", "conftest.py")
_PYTEST_CONFIGS = ("pyproject.toml", "setup.cfg", "tox.ini")
_VENVS = (".venv/bin/python", "venv/bin/python")
_CLASS = frozenset({"class_definition"})
_SCOPES = _CLASS | {"function_definition"}
_QUERY = """
(function_definition name: (_) @name body: (_)) @definition
(class_definition) @opaque
[
  (if_statement)
  (elif_clause)
  (for_statement)
  (while_statement)
  (except_clause)
  (conditional_expression)
  (case_clause)
  (if_clause)
  (boolean_operator)
] @decision
"""


def _module(source: Source, _: Node) -> tuple[str, ...]:
    *package, stem = parts = module_parts(source.path, source.home.directory)
    return tuple(package) if package and stem == "__init__" else parts


def _scope(definition: Node) -> list[str] | None:
    scope = next(
        (found.type for found in ancestors(definition) if found.type in _SCOPES), None
    )
    return None if scope == "function_definition" else enclosing(definition, _CLASS)


_GRAMMAR = Grammar(name=_NAME, query=_QUERY, module=_module, scope=_scope)


def _uses_pytest(package: Path) -> bool:
    return has_file(package, _PYTEST_FILES) or any(
        "pytest" in decoded(path, str)
        for name in _PYTEST_CONFIGS
        if (path := package / name).is_file()
    )


def measure(project: Project, scratch: Path) -> list[Lines]:
    package = project.home.directory
    python = next(
        (f"{venv}" for name in _VENVS if (venv := package / name).is_file()), "python3"
    )
    data = f"--data-file={scratch / '.coverage'}"
    sources = sorted(
        {
            file.relative_to(package).parts[0].removesuffix(".py")
            for file in project.files
        }
    )
    pytest = _uses_pytest(package)
    missing = [
        module
        for module in (("coverage", "pytest") if pytest else ("coverage",))
        if not attempt([python, "-c", f"import {module}"], package)
    ]
    pip = [python, "-m", "pip", "install", "--disable-pip-version-check"]
    if missing and not run([*pip, *missing], package):
        return []
    tests = [
        python,
        "-m",
        "coverage",
        "run",
        data,
        *([f"--source={','.join(sources)}"] if sources else []),
        "-m",
        *(["pytest"] if pytest else ["unittest", "discover", "-s", "."]),
    ]
    run(tests, package)
    lcov = [python, "-m", "coverage", "lcov", data, "-o", f"{scratch / LCOV.name}"]
    run(lcov, package)
    return [LCOV.read(scratch)]


PYTHON = Language(
    name=_NAME,
    extensions=(".py",),
    tests=_TESTS,
    skip=frozenset({".venv", "venv", "__pycache__"}),
    manifests=_PROJECTS,
    functions=_GRAMMAR.functions,
    measure=measure,
    reports=LCOV_REPORTS,
)
