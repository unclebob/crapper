"""Kotlin functions and cyclomatic complexity, with Java's rules adapted.

Entries are top-level functions, member functions (classes, objects and
interfaces, with a body), secondary constructors, and property accessors that
have a body (named `prop.get` and `prop.set`). Primary constructors, `init`
blocks, property initializers and compiler-made accessors are not entries.

Names follow the JVM. A top-level function belongs to `package.<File>Kt`, or to
the `@file:JvmName`. A companion object's members belong to the enclosing class
(JaCoCo reports `Class$Companion`; coverage joins on source lines, not class
names, so the two never need matching). Nested classes chain as `pkg.Outer.Inner`.

Decisions: `if` (each `else if` too), `for`, `while`, `do-while`, `catch`, the
elvis `?:`, each `when` branch that has a condition (`else` adds nothing), and
each `&&` / `||`. The safe call `?.` is not counted: it is a null guard, not a
branch the author wrote. Lambdas and local functions stay inside the enclosing
function, so their decisions count toward it. Anonymous objects and local
classes are omitted and add nothing.

Local functions, lambdas and anonymous objects are never entries: the walk does
not descend into a function body, lambda, object literal or `init` block.
"""

import re

from crapper.languages.treesitter import (
    child_of_type,
    complexity,
    enclosing_names,
    end_line,
    node_text,
    parse,
    start_line,
)
from crapper.model import Function

_OWNERS = {"class_declaration", "object_declaration"}
_ENTRIES = {"function_declaration", "secondary_constructor", "getter", "setter"}
_NOT_WALKED = {"lambda_literal", "object_literal", "anonymous_function", "anonymous_initializer"}
_DECISIONS = {
    "if_expression",
    "for_statement",
    "while_statement",
    "do_while_statement",
    "catch_block",
    "elvis_expression",
    "conjunction_expression",
    "disjunction_expression",
}
_OMITTED = {"object_literal"} | _OWNERS
_JVM_NAME = re.compile(r'@file:JvmName\(\s*"([^"]+)"')
_NOT_IDENTIFIER = re.compile(r"\W")


def _is_decision(node) -> bool:
    if node.type == "when_entry":
        return child_of_type(node, "when_condition") is not None
    return node.type in _DECISIONS


def _skip(node) -> bool:
    return node.type in _OMITTED


def _package_name(data: bytes, root) -> str:
    header = child_of_type(root, "package_header")
    ident = child_of_type(header, "identifier") if header is not None else None
    return "".join(node_text(data, ident).split()) if ident is not None else ""


def _file_class(source: str, path: str) -> str:
    named = _JVM_NAME.search(source)
    if named:
        return named.group(1)
    stem = path.replace("\\", "/").rsplit("/", 1)[-1].removesuffix(".kt")
    stem = _NOT_IDENTIFIER.sub("_", stem)
    return stem[:1].upper() + stem[1:] + "Kt"


def _join(*parts: str) -> str:
    return ".".join(part for part in parts if part)


def _owner_names(data: bytes, node) -> list[str]:
    return enclosing_names(data, node, _OWNERS, "type_identifier")


def _property_of(node):
    """The grammar nests an accessor written on the property's line, not one below it."""

    if node.parent.type == "property_declaration":
        return node.parent
    sibling = node.prev_named_sibling
    while sibling is not None and sibling.type in {"getter", "setter"}:
        sibling = sibling.prev_named_sibling
    return sibling


def _accessor_name(data: bytes, node) -> str | None:
    prop = _property_of(node)
    if prop is None or prop.type != "property_declaration":
        return None
    variable = child_of_type(prop, "variable_declaration")
    ident = child_of_type(variable, "simple_identifier") if variable is not None else None
    if ident is None:
        return None
    return f"{node_text(data, ident)}.{node.type[:3]}"


def _entry_name(data: bytes, node, owners: list[str]) -> str | None:
    if node.type == "function_declaration":
        ident = child_of_type(node, "simple_identifier")
        return node_text(data, ident) if ident is not None else None
    if node.type == "secondary_constructor":
        return owners[-1] if owners else None
    return _accessor_name(data, node)


def _has_body(node) -> bool:
    return node.type == "secondary_constructor" or child_of_type(node, "function_body") is not None


def _function(data: bytes, node, path: str, package: str, file_class: str) -> Function | None:
    owners = _owner_names(data, node)
    name = _entry_name(data, node, owners)
    if not name:
        return None
    return Function(
        name=name,
        namespace=_join(package, *owners) if owners else _join(package, file_class),
        complexity=complexity(node, _is_decision, _skip),
        start_line=start_line(node),
        end_line=end_line(node),
        path=path,
        language="kotlin",
    )


def functions_in_source(
    source: str, path: str, project_root: str | None = None
) -> list[Function]:
    del project_root
    data, tree = parse(source, "kotlin")
    package = _package_name(data, tree.root_node)
    file_class = _file_class(source, path)
    found: list[Function] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type in _NOT_WALKED:
            continue
        if node.type not in _ENTRIES:
            stack.extend(reversed(node.children))
        elif _has_body(node):
            entry = _function(data, node, path, package, file_class)
            if entry is not None:
                found.append(entry)
    return found
