import re
from pathlib import Path
from typing import Final

from tree_sitter import Node

from crapper.coverage.formats import GO_PROFILE, REPORT_DIR, Lines, Report
from crapper.coverage.tool import run
from crapper.decode import decoded
from crapper.language import Language, Project
from crapper.languages.treesitter import Grammar, find, text
from crapper.model import Source

_NAME: Final = "go"
_MODULE = re.compile(r"^\s*module\s+(\S+)", re.MULTILINE)
_PACKAGE = "(package_identifier) @found"
_TYPE = "(type_identifier) @found"
_QUERY = """
(function_declaration name: (_) @name body: (_)) @definition
(method_declaration name: (_) @name body: (_)) @definition
[
  (if_statement)
  (for_statement)
  (expression_case)
  (type_case)
  (communication_case)
  (default_case)
  (binary_expression operator: ["&&" "||"])
] @decision
"""


def _declared(manifest: Path) -> str | None:
    declared = _MODULE.search(decoded(manifest, str))
    return declared[1] if declared else None


def _module(source: Source, tree: Node) -> list[str]:
    qualified = source.home.qualified(source.path)
    package = find(_NAME, tree, _PACKAGE)[:1]
    return [qualified.parent.as_posix()] if qualified else [*map(text, package)]


def _scope(declaration: Node) -> list[str] | None:
    if declaration.type == "function_declaration":
        return []
    receiver = declaration.child_by_field_name("receiver")
    named = find(_NAME, receiver, _TYPE) if receiver else []
    return [text(named[0])] if named else None


_GRAMMAR = Grammar(name=_NAME, query=_QUERY, module=_module, scope=_scope)


def measure(project: Project, scratch: Path) -> list[Lines]:
    profile = scratch / GO_PROFILE.name
    run(["go", "test", "./...", f"-coverprofile={profile}"], project.home.directory)
    return [GO_PROFILE.read(scratch)]


GO = Language(
    name=_NAME,
    extensions=(".go",),
    tests=("*_test.go",),
    skip=frozenset({"vendor", "testdata"}),
    manifests=("go.mod",),
    project_name=_declared,
    functions=_GRAMMAR.functions,
    measure=measure,
    reports=(
        Report(format=GO_PROFILE, path=REPORT_DIR),
        Report(format=GO_PROFILE, path=Path("coverage.out")),
    ),
)
