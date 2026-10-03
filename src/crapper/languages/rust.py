import tomllib
from pathlib import Path
from shutil import which
from typing import Final

from tree_sitter import Node

from crapper.coverage.formats import LCOV, LCOV_REPORTS, Lines
from crapper.coverage.tool import Argv, run
from crapper.decode import ForeignDocument
from crapper.language import Language, Project
from crapper.languages.treesitter import Grammar, enclosing, find, text
from crapper.model import Source

_NAME: Final = "rust"
_LLVM_COV = ("cargo", "llvm-cov")
_TARPAULIN = ("cargo", "tarpaulin")
_INSTALL = (
    ("rustup", "component", "add", "llvm-tools-preview"),
    ("cargo", "install", "cargo-llvm-cov", "--locked"),
)
_MODULE = frozenset({"mod_item"})
_ROOTS = {"lib", "main"}
_NAMED_TYPES = {"type_identifier", "generic_type", "scoped_type_identifier"}
_TYPE = "(type_identifier) @found"
_QUERY = """
(function_item name: (_) @name body: (_)) @definition
[
  (if_expression)
  (for_expression)
  (while_expression)
  (loop_expression)
  (match_arm)
  (try_expression)
  (binary_expression operator: ["&&" "||"])
] @decision
"""


class CargoPackage(ForeignDocument):
    name: str


class CargoManifest(ForeignDocument):
    package: CargoPackage | None = None


def _crate(manifest: Path) -> str | None:
    package = CargoManifest.read(manifest, tomllib.loads).package
    return package.name.replace("-", "_") if package else None


def _module(source: Source, _: Node) -> tuple[str, ...]:
    file = source.path
    qualified = source.home.qualified(file)
    crate, *directories = qualified.parent.parts if qualified else ("crate",)
    package = directories[1:] if directories[:1] == ["src"] else directories
    if not package and file.stem in _ROOTS:
        return (crate,)
    modules = (*package, *(() if file.stem == "mod" else (file.stem,)))
    return (
        modules[1:]
        if modules[:1] == ("bin",) and len(modules) > 1
        else (crate, *modules)
    )


def _self_type(method: Node) -> list[str]:
    implementation = method.parent.parent if method.parent else None
    if implementation is None or implementation.type != "impl_item":
        return []
    implemented = implementation.child_by_field_name("type")
    if implemented is None or implemented.type not in _NAMED_TYPES:
        return []
    return [text(name) for name in find(_NAME, implemented, _TYPE)[:1]]


def _scope(item: Node) -> list[str] | None:
    modules = enclosing(item, _MODULE)
    local = item.parent is not None and item.parent.type == "block"
    return None if local or "tests" in modules else [*modules, *_self_type(item)]


_GRAMMAR = Grammar(
    name=_NAME, query=_QUERY, separator="::", module=_module, scope=_scope
)


def _installed(tool: Argv) -> bool:
    return which("-".join(tool)) is not None


def ready(root: Path) -> bool:
    return any(map(_installed, (_LLVM_COV, _TARPAULIN))) or all(
        run(step, root) for step in _INSTALL
    )


def measure(project: Project, scratch: Path) -> list[Lines]:
    command = (
        [*_TARPAULIN, "--out", "Lcov", "--output-dir", f"{scratch}"]
        if _installed(_TARPAULIN) and not _installed(_LLVM_COV)
        else [*_LLVM_COV, "--lcov", "--output-path", f"{scratch / LCOV.name}"]
    )
    run(command, project.home.directory)
    return [LCOV.read(scratch)]


RUST = Language(
    name=_NAME,
    extensions=(".rs",),
    manifests=("Cargo.toml",),
    project_name=_crate,
    functions=_GRAMMAR.functions,
    ready=ready,
    measure=measure,
    reports=LCOV_REPORTS,
)
