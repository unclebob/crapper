"""Kotlin functions and cyclomatic complexity, following java.py.

Every `fun` with a body is an entry: top-level, member, extension, and inside
`object` / `companion object`. An `inline fun` is not: JaCoCo cannot see it run. Local functions and lambdas stay inside the
enclosing function. Secondary constructors and `init` blocks are omitted, as
Java omits constructors.

`:namespace` is the class JaCoCo reports, written with dots
(`pkg.Outer.Inner`, `pkg.Class.Companion`), and `pkg.FileNameKt` (or the
`@file:JvmName`) for a top-level function. The binary name (`pkg.Outer$Inner`)
is kept for coverage lookup.
"""

import re
import sys
from pathlib import Path

from crapper.languages.treesitter import (
    child_of_type,
    complexity,
    end_line,
    node_text,
    parse,
    start_line,
)
from crapper.model import Function

_JVM_NAME = re.compile(r'@file\s*:\s*JvmName\s*\(\s*"([^"]+)"\s*\)')
_MULTIFILE = re.compile(r"@file\s*:\s*JvmMultifileClass\b")
_TYPES = {"class_declaration", "object_declaration", "companion_object"}
# Walked to find entries. Anything else, such as a property initializer or a
# lambda, belongs to a function or is not a function at all.
_CONTAINERS = _TYPES | {
    "source_file",
    "class_body",
    "enum_class_body",
    "enum_entry",
    "ERROR",
}
_OWNED_ELSEWHERE = _TYPES | {"class_body", "enum_class_body", "object_literal"}
_DECISIONS = {
    "if_expression",
    "for_statement",
    "while_statement",
    "do_while_statement",
    "catch_block",
    "when_entry",
    "guard_condition",
    "conjunction_expression",
    "disjunction_expression",
    "elvis_expression",
    "?.",
}


def _is_decision(node) -> bool:
    return node.type in _DECISIONS


def _skip(node) -> bool:
    return node.type in _OWNED_ELSEWHERE


def _package_name(data: bytes, root) -> str | None:
    header = child_of_type(root, "package_header")
    if header is None:
        return None
    ident = child_of_type(header, "identifier")
    if ident is None:
        return None
    return ".".join(
        node_text(data, part) for part in ident.children if part.type == "simple_identifier"
    )


def file_class(path: str, source: str) -> tuple[str, str]:
    """The facade class for top-level functions, and the class JaCoCo reports.

    A `@file:JvmMultifileClass` file compiles its code into `Facade__FileKt`.
    """

    stem = re.sub(r"[^\w$]", "_", Path(path).stem)
    if stem[:1].isdigit():
        stem = "_" + stem
    part = stem[:1].upper() + stem[1:] + "Kt"
    named = _JVM_NAME.search(source)
    if named is None:
        return part, part
    if _MULTIFILE.search(source):
        return named.group(1), f"{named.group(1)}__{part}"
    return named.group(1), named.group(1)


def _type_name(data: bytes, node) -> str:
    ident = child_of_type(node, "type_identifier")
    if ident is not None:
        # The JVM name drops the backticks. A `$` inside them stays a `$`: it
        # is part of the name, not a nesting step, so it is not turned into `.`.
        return node_text(data, ident).strip("`")
    return "Companion"


def _is_interface(node) -> bool:
    return node is not None and node.type == "class_declaration" and child_of_type(node, "interface") is not None


def _enum_entry_name(data: bytes, node) -> str | None:
    if node.type != "enum_entry":
        return None
    ident = child_of_type(node, "simple_identifier")
    return node_text(data, ident) if ident is not None else None


def _type_chain(data: bytes, node) -> tuple[list[str], list[str]]:
    """Source names for `:namespace` and binary names for JaCoCo.

    An enum entry with a body is a class of its own to JaCoCo (`E$A`) but not
    to uml-viewer, and a default method in an interface lives in
    `I$DefaultImpls`.
    """

    names: list[str] = []
    binary: list[str] = []
    current = node.parent
    if current is not None and _is_interface(current.parent):
        binary.append("DefaultImpls")
    while current is not None:
        if current.type in _TYPES:
            names.append(_type_name(data, current))
            binary.append(names[-1])
        entry = _enum_entry_name(data, current)
        if entry is not None:
            binary.append(entry)
        current = current.parent
    names.reverse()
    binary.reverse()
    return names, binary


def _qualify(package: str | None, names: list[str], nested: str) -> str:
    body = nested.join(names)
    return f"{package}.{body}" if package else body


def _is_inline(node) -> bool:
    """An `inline fun`. Its body is copied into each caller, so JaCoCo never
    sees it run. Only the function's own modifiers count: the methods of an
    `inline class` or `@JvmInline value class` are ordinary functions."""

    modifiers = child_of_type(node, "modifiers")
    if modifiers is None:
        return False
    return any(
        child.type == "function_modifier" and child_of_type(child, "inline") is not None
        for child in modifiers.children
    )


def _warn_parse_errors(path: str, tree) -> None:
    if tree.root_node.has_error:
        print(
            f"{path}: Kotlin parse error; scores in this file may be wrong.",
            file=sys.stderr,
        )


class _Reader:
    def __init__(self, source: str, path: str):
        self.path = path
        self.data, self.tree = parse(source, "kotlin")
        self.package = _package_name(self.data, self.tree.root_node)
        self.file_class = file_class(path, source)

    def classes(self, node) -> tuple[str, str]:
        names, binary = _type_chain(self.data, node)
        if not names:
            facade, part = self.file_class
            return _qualify(self.package, [facade], "."), _qualify(self.package, [part], "$")
        return _qualify(self.package, names, "."), _qualify(self.package, binary, "$")

    def function(self, node) -> Function | None:
        ident = child_of_type(node, "simple_identifier")
        if ident is None or child_of_type(node, "function_body") is None:
            return None
        if _is_inline(node):
            return None
        namespace, jacoco_class = self.classes(node)
        return Function(
            name=node_text(self.data, ident),
            namespace=namespace,
            complexity=complexity(node, _is_decision, _skip),
            start_line=start_line(node),
            end_line=end_line(node),
            path=self.path,
            language="kotlin",
            jacoco_class=jacoco_class,
            start_byte=node.start_byte,
            end_byte=node.end_byte,
        )

    def functions(self) -> list[Function]:
        found: list[Function] = []
        stack = [self.tree.root_node]
        while stack:
            node = stack.pop()
            if node.type == "function_declaration":
                function = self.function(node)
                if function is not None:
                    found.append(function)
            elif node.type in _CONTAINERS:
                stack.extend(reversed(node.children))
        return found


def functions_in_source(
    source: str, path: str, project_root: str | None = None
) -> list[Function]:
    del project_root
    reader = _Reader(source, path)
    _warn_parse_errors(path, reader.tree)
    return reader.functions()
