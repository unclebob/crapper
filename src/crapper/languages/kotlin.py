"""Kotlin functions and cyclomatic complexity.

Decision points are `if`, `for`, `while`, `do ... while`, each `when` arm
except `else`, each `catch`, and each `&&`, `||`, `?:`, and `?.`.

Entries are functions with a body that are not inside another function, a
lambda, or an anonymous object; those stay in the enclosing entry.
Constructors, `init` blocks, property accessors, and abstract functions are
not entries. The namespace is the package plus the chain of classes, objects,
companions (`Companion` when unnamed), and enum values with their own body, as
Kotlin imports them; a top-level function's namespace is the package, or the
file stem when there is no `package` line. The JVM class (`pkg.Outer$Inner`,
`pkg.Enum$VALUE`, or `pkg.FileKt` and `@file:JvmName` for top-level functions)
is kept for coverage lookup.
"""

import re
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

_JVM_NAME = re.compile(r'(?m)^\s*@file:JvmName\("([^"]+)"\)')
# `@Composable () -> Unit`: an annotation without arguments, a space, then a
# parenthesis. The grammar reads the parenthesis as the annotation's arguments
# and loses the rest of the file.
_TYPE_ANNOTATION = re.compile(r"@[A-Za-z_][\w.]*(?=[ \t]+\()", re.ASCII)
_TYPES = {"class_declaration", "object_declaration", "companion_object", "enum_entry"}
_NESTING = {"lambda_literal", "object_literal", "anonymous_function"}
_DECISIONS = {
    "if_expression",
    "for_statement",
    "while_statement",
    "do_while_statement",
    "catch_block",
    "&&",
    "||",
    "?:",
    "?.",
}


def _without_type_annotations(source: str) -> str:
    """Blank those annotations, keeping every byte and line in place."""

    return _TYPE_ANNOTATION.sub(lambda found: " " * len(found.group(0)), source)


def _is_decision(node) -> bool:
    if node.type == "when_entry":
        return child_of_type(node, "else") is None
    return node.type in _DECISIONS


def _skip(_node) -> bool:
    return False


def _type_name(data: bytes, node) -> str | None:
    if node.type == "enum_entry":
        if child_of_type(node, "class_body") is None:
            return None
        return node_text(data, child_of_type(node, "simple_identifier"))
    ident = child_of_type(node, "type_identifier")
    if ident is not None:
        return node_text(data, ident)
    return "Companion" if node.type == "companion_object" else None


def _type_chain(data: bytes, node) -> list[str]:
    names: list[str] = []
    current = node.parent
    while current is not None:
        if current.type in _TYPES:
            name = _type_name(data, current)
            if name:
                names.append(name)
        current = current.parent
    names.reverse()
    return names


def _package(data: bytes, root) -> str | None:
    header = child_of_type(root, "package_header")
    ident = child_of_type(header, "identifier") if header is not None else None
    return node_text(data, ident) if ident is not None else None


def _facade(source: str, path: str) -> str:
    """The JVM class that holds a file's top-level functions."""

    found = _JVM_NAME.search(source)
    if found:
        return found.group(1)
    stem = Path(path).stem
    return stem[:1].upper() + stem[1:] + "Kt"


def _qualify(package: str | None, names: list[str], separator: str) -> str:
    return ".".join(part for part in (package, separator.join(names)) if part)


class _Reader:
    def __init__(self, data: bytes, source: str, path: str, package: str | None):
        self.data = data
        self.path = path
        self.package = package
        self.facade = _facade(source, path)
        self.found: list[Function] = []

    def _names(self, chain: list[str]) -> tuple[str, str]:
        if chain:
            return (
                _qualify(self.package, chain, "."),
                _qualify(self.package, chain, "$"),
            )
        namespace = self.package or Path(self.path).stem
        return namespace, _qualify(self.package, [self.facade], "$")

    def read(self, node) -> None:
        ident = child_of_type(node, "simple_identifier")
        if ident is None or child_of_type(node, "function_body") is None:
            return
        namespace, jvm_class = self._names(_type_chain(self.data, node))
        self.found.append(
            Function(
                name=node_text(self.data, ident),
                namespace=namespace,
                complexity=complexity(node, _is_decision, _skip),
                start_line=start_line(node),
                end_line=end_line(node),
                path=self.path,
                language="kotlin",
                jacoco_class=jvm_class,
            )
        )


def functions_in_source(
    source: str, path: str, project_root: str | None = None
) -> list[Function]:
    del project_root
    data, tree = parse(_without_type_annotations(source), "kotlin")
    reader = _Reader(data, source, path, _package(data, tree.root_node))
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type == "function_declaration":
            reader.read(node)
            continue
        if node.type in _NESTING:
            continue
        stack.extend(reversed(node.children))
    return reader.found
