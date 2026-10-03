import logging
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Final

from tree_sitter import Node

from crapper.coverage.formats import LCOV, LCOV_REPORTS, Lines
from crapper.coverage.tool import run
from crapper.decode import ForeignDocument
from crapper.language import Language, Project
from crapper.languages.treesitter import Grammar, ancestors, enclosing, text
from crapper.model import Function, Source
from crapper.paths import has_file, module_parts

_NAME: Final = "typescript"
_MANIFEST = "package.json"
_VITEST_CONFIGS = tuple(
    f"vitest.config.{suffix}" for suffix in ("ts", "mts", "cts", "js", "mjs", "cjs")
)
_VITEST_PROVIDER = "@vitest/coverage-v8"
_CLASSES = frozenset({"class_declaration", "abstract_class_declaration"})
_CALLBACKS = frozenset({"arrow_function", "function_expression"})
_FUNCTIONS = {"function_declaration", "method_definition", *_CALLBACKS}
_VERBS = ("get", "post", "put", "patch", "delete", "head", "options", "all", "use")
_ROUTE = re.compile(rf"(?:{'|'.join(_VERBS).upper()})(?: .+)?")
_QUERY = f"""
(function_declaration name: (identifier) @name body: (_)) @definition
(method_definition name: (property_identifier) @name body: (_)) @definition
(lexical_declaration
  (variable_declarator
    name: (identifier) @name
    value: [(arrow_function) (function_expression)]) @definition)
(call_expression
  function: (member_expression property: (property_identifier) @name)
  arguments: (arguments
    [
      (arrow_function) @definition @sealed
      (function_expression) @definition @sealed
      (parenthesized_expression (arrow_function) @definition @sealed)
      (parenthesized_expression (function_expression) @definition @sealed)
    ])
  (#match? @name "^(?i:{"|".join(_VERBS)})$"))
[
  (class_declaration)
  (abstract_class_declaration)
  (interface_declaration)
] @opaque
[
  (if_statement)
  (for_statement)
  (for_in_statement)
  (while_statement)
  (do_statement)
  (catch_clause)
  (ternary_expression)
  (switch_case)
  (switch_default)
  (binary_expression operator: ["&&" "||" "??"])
  (optional_chain)
  (call_expression "?.")
] @decision
"""

log = logging.getLogger(__name__)


class PackageJson(ForeignDocument):
    scripts: dict[str, str] = {}
    version: str | None = None


def _module(source: Source, _: Node) -> tuple[str, ...]:
    return module_parts(source.path, source.home.directory)


def _scope(node: Node) -> list[str] | None:
    if node.type in _CALLBACKS:
        return []
    classes = enclosing(node, _CLASSES)
    if node.type == "method_definition":
        return classes or None
    nested = any(ancestor.type in _FUNCTIONS for ancestor in ancestors(node))
    return None if nested else classes


def _calls(call: Node) -> Iterator[Node]:
    current: Node | None = call
    while current is not None and current.type == "call_expression":
        yield current
        callee = current.child_by_field_name("function")
        current = callee and callee.child_by_field_name("object")


def _property(call: Node) -> str | None:
    callee = call.child_by_field_name("function")
    name = callee and callee.child_by_field_name("property")
    return name and text(name)


def _fragments(string: Node) -> str:
    fragments = (part for part in string.children if part.type == "string_fragment")
    return "".join(map(text, fragments))


_LITERALS = {"string": _fragments, "template_string": lambda node: text(node)[1:-1]}


def _literal(call: Node) -> str:
    arguments = call.child_by_field_name("arguments")
    literals = (
        _LITERALS[argument.type](argument)
        for argument in (arguments.named_children if arguments else ())
        if argument.type in _LITERALS
    )
    return next(literals, "")


def _label(definition: Node, name: Node) -> str:
    if definition.type not in _CALLBACKS:
        return text(name)
    call, *chained = _calls(
        next(node for node in ancestors(name) if node.type == "call_expression")
    )
    mounted = (_literal(route) for route in chained if _property(route) == "route")
    path = _literal(call) or next(mounted, "")
    return " ".join(filter(None, (text(name).upper(), path)))


_TS, _TSX = (
    Grammar(name=name, query=_QUERY, module=_module, scope=_scope, label=_label)
    for name in ("typescript", "tsx")
)


def functions(source: Source) -> list[Function]:
    grammar = _TS if source.path.suffix in (".ts", ".mts", ".cts") else _TSX
    found = grammar.functions(source)
    names = [function.name for function in found]
    return [
        function.model_copy(update={"name": f"{function.name}#{earlier + 1}"})
        if _ROUTE.fullmatch(function.name)
        and (earlier := names[:index].count(function.name))
        else function
        for index, function in enumerate(found)
    ]


def _vitest(project: Project, scratch: Path) -> None:
    package = project.home.directory
    modules = package / "node_modules"
    if not (modules / _VITEST_PROVIDER).is_dir():
        vitest = modules / "vitest" / _MANIFEST
        version = PackageJson.read(vitest).version if vitest.is_file() else None
        spec = f"{_VITEST_PROVIDER}@{version}" if version else _VITEST_PROVIDER
        install = ["npm", "install", "--no-save", "--no-package-lock", spec]
        if not run(install, package):
            return
    run(
        [
            "npx",
            "vitest",
            "run",
            "--coverage",
            "--coverage.reporter=lcov",
            f"--coverage.reportsDirectory={scratch}",
            "--coverage.reportOnFailure=true",
            *(
                f"--coverage.include={file.relative_to(package).as_posix()}"
                for file in project.files
            ),
        ],
        package,
    )


def measure(project: Project, scratch: Path) -> list[Lines]:
    package = project.home.directory
    manifest = package / _MANIFEST
    scripts = PackageJson.read(manifest).scripts if manifest.is_file() else {}
    if "coverage" in scripts:
        measured = run(["npm", "run", "coverage"], package)
        return [report.read(package) for report in LCOV_REPORTS] if measured else []
    if "vitest" in scripts.get("test", "") or has_file(package, _VITEST_CONFIGS):
        _vitest(project, scratch)
    elif "test" in scripts:
        c8 = ["npx", "--yes", "c8", "--reporter=lcov", "--reports-dir", f"{scratch}"]
        run([*c8, "npm", "test"], package)
    else:
        log.warning("No test script in %s. TypeScript coverage is 0%%.", package)
        return []
    return [LCOV.read(scratch)]


TYPESCRIPT = Language(
    name=_NAME,
    extensions=(".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"),
    ignored=("*.d.ts", "*.d.[cm]ts"),
    skip=frozenset({"node_modules"}),
    tests=tuple(
        f"*.{kind}.{suffix}"
        for kind in ("test", "spec")
        for suffix in ("ts", "tsx", "[cm]ts", "js", "jsx", "[cm]js")
    ),
    manifests=(_MANIFEST,),
    functions=functions,
    measure=measure,
    reports=LCOV_REPORTS,
)
