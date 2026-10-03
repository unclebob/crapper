from pathlib import Path
from typing import Final

from tree_sitter import Node

from crapper.coverage.formats import JACOCO, Lines, Report
from crapper.coverage.tool import run
from crapper.language import Language, Project
from crapper.languages.treesitter import Grammar, ancestors, enclosing, text
from crapper.model import Source

_NAME: Final = "java"
_JACOCO_PLUGIN = "org.jacoco:jacoco-maven-plugin:0.8.12"
_REPORT = Report(format=JACOCO, path=Path("target", "site", "jacoco", "jacoco.xml"))
_TYPES = frozenset(
    {
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "record_declaration",
        "annotation_type_declaration",
    }
)
_EXECUTABLES = {"method_declaration", "constructor_declaration", "lambda_expression"}
_QUERY = """
(method_declaration name: (_) @name body: (_)) @definition
[
  (class_declaration)
  (interface_declaration)
  (enum_declaration)
  (record_declaration)
  (annotation_type_declaration)
  (class_body)
] @opaque
[
  (if_statement)
  (for_statement)
  (enhanced_for_statement)
  (while_statement)
  (do_statement)
  (catch_clause)
  (ternary_expression)
  (switch_label)
  (binary_expression operator: ["&&" "||"])
] @decision
"""


def _module(_: Source, tree: Node) -> list[str]:
    return [
        text(declaration.named_children[-1])
        for declaration in tree.children
        if declaration.type == "package_declaration"
    ]


def _scope(method: Node) -> list[str] | None:
    nested = any(ancestor.type in _EXECUTABLES for ancestor in ancestors(method))
    return None if nested else enclosing(method, _TYPES)


_GRAMMAR = Grammar(name=_NAME, query=_QUERY, module=_module, scope=_scope)


def measure(project: Project, scratch: Path) -> list[Lines]:
    module = project.home.directory
    data = scratch / "jacoco.exec"
    (module / _REPORT.path).unlink(missing_ok=True)
    maven = [
        "mvn",
        "-q",
        f"-Djacoco.destFile={data}",
        f"-Djacoco.dataFile={data}",
        f"{_JACOCO_PLUGIN}:prepare-agent",
        "test",
        f"{_JACOCO_PLUGIN}:report",
    ]
    run(maven, module)
    return [_REPORT.read(module)]


JAVA = Language(
    name=_NAME,
    extensions=(".java",),
    manifests=("pom.xml",),
    functions=_GRAMMAR.functions,
    measure=measure,
    reports=(_REPORT,),
)
