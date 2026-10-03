from pathlib import Path
from typing import Final

from tree_sitter import Node

from crapper.coverage.formats import (
    CLOVERAGE,
    LCOV,
    LCOV_REPORTS,
    REPORT_DIR,
    Lines,
    Report,
)
from crapper.coverage.tool import run
from crapper.language import Language, Project
from crapper.languages.treesitter import Grammar, find, text
from crapper.model import Source
from crapper.paths import module_parts

_NAME: Final = "clojure"
_BRANCHES = {
    "if",
    "if-not",
    "if-let",
    "if-some",
    "when",
    "when-not",
    "when-let",
    "when-some",
    "when-first",
    "and",
    "or",
    "loop",
    "catch",
}
_SYMBOL = "(sym_name) @found"
_NAMESPACE = """
(source
  (list_lit . value: (sym_lit) @head . value: (_) @found)
  (#any-of? @head "ns" "in-ns"))
"""
_QUERY = """
(source
  (list_lit
    . value: (sym_lit) @head
    . value: (sym_lit name: (sym_name) @name)) @definition
  (#any-of? @head "defn" "defn-"))
(dis_expr) @opaque
[(list_lit) (anon_fn_lit)] @decision
"""


def _weight(call: Node) -> int:
    forms = call.children_by_field_name("value")
    if not forms:
        return 0
    operands = len(forms) - 1
    match text(forms[0]):
        case "cond" | "case":
            return operands // 2
        case "condp":
            return max(0, operands - 2) // 2
        case "cond->" | "cond->>":
            return max(0, operands - 1) // 2
        case "some->" | "some->>":
            return max(0, operands - 1)
        case head:
            return int(head in _BRANCHES)


def _module(source: Source, tree: Node) -> list[str]:
    declared = [
        text(symbol)
        for operand in find(_NAME, tree, _NAMESPACE)
        for symbol in find(_NAME, operand, _SYMBOL)[-1:]
    ]
    module = ".".join(module_parts(source.path, source.home.directory))
    return declared[:1] or [module.replace("_", "-")]


_GRAMMAR = Grammar(name=_NAME, query=_QUERY, module=_module, weight=_weight)


def measure(project: Project, scratch: Path) -> list[Lines]:
    run(["clj", "-M:cov", "--output", f"{scratch}", "--lcov"], project.home.directory)
    return [CLOVERAGE.read(scratch), LCOV.read(scratch)]


CLOJURE = Language(
    name=_NAME,
    extensions=(".clj", ".cljc", ".cljs", ".bb"),
    tests=("*_test.clj", "*_test.clj[cs]", "*_test.bb"),
    skip=frozenset({".clj-kondo"}),
    manifests=("deps.edn", "bb.edn"),
    functions=_GRAMMAR.functions,
    measure=measure,
    reports=(Report(format=CLOVERAGE, path=REPORT_DIR), *LCOV_REPORTS),
)
