"""Dart functions and cyclomatic complexity.

A Dart function is a signature followed by a sibling `function_body`.
Entries are top-level functions, methods of classes, mixins, extensions and
enums, getters (`size`), setters (`size=`), operators (`operator +`), and
factory constructors (`A.fromJson` is `fromJson`, `factory A` is `A`).
Generative constructors, abstract and `external` members have no entry.
Local functions and closures count toward the function that holds them.

The namespace is the package name from the nearest `pubspec.yaml` plus the
path under `lib/` (`gap_core.src.models.user`), then the enclosing type.
"""

import re
from pathlib import Path

from crapper.languages.treesitter import (
    absolute_path,
    child_of_type,
    end_line,
    node_text,
    parse,
    start_line,
)
from crapper.model import Function

_TOP_SIGNATURES = {"function_signature", "getter_signature", "setter_signature"}
_BETWEEN = {"comment", "documentation_comment", "annotation"}
_INSIDE_FUNCTION = {"function_body", "function_expression"}
_TYPES = {
    "class_definition",
    "mixin_declaration",
    "extension_declaration",
    "enum_declaration",
    "extension_type_declaration",
}
_DECISIONS = {
    "if_statement",
    "if_element",
    "for_statement",
    "for_element",
    "while_statement",
    "do_statement",
    "conditional_expression",
    "switch_statement_case",
    "switch_statement_default",
    "switch_expression_case",
    "logical_and_operator",
    "logical_or_operator",
    "if_null_expression",
    "conditional_assignable_selector",
}
_PACKAGE_NAME = re.compile(r"^name:\s*['\"]?([\w.]+)", re.MULTILINE)


def _handlers(node) -> int:
    """`on E {}` and `catch (e) {}` each end in a block; so do `try` and `finally`."""

    blocks = sum(1 for child in node.children if child.type == "block")
    has_finally = any(child.type == "finally" for child in node.children)
    return blocks - 1 - int(has_finally)


def _complexity(body) -> int:
    score = 1
    stack = [body]
    while stack:
        current = stack.pop()
        if current.type in _DECISIONS:
            score += 1
        elif current.type == "try_statement":
            score += _handlers(current)
        stack.extend(current.children)
    return score


def _inside(node, types: set[str]) -> bool:
    current = node.parent
    while current is not None:
        if current.type in types:
            return True
        current = current.parent
    return False


def _is_signature(node) -> bool:
    if node.type == "method_signature":
        return True
    return node.type in _TOP_SIGNATURES and node.parent.type != "method_signature"


def _body_of(signature):
    current = signature.next_sibling
    while current is not None and current.type in _BETWEEN:
        current = current.next_sibling
    if current is not None and current.type == "function_body":
        return current
    return None


def _operator_name(data: bytes, node) -> str:
    symbol = []
    after = False
    for child in node.children:
        if child.type == "formal_parameter_list":
            break
        if after:
            symbol.append(node_text(data, child))
        after = after or child.type == "operator"
    return "operator " + "".join(symbol)


def _factory_name(data: bytes, node) -> str:
    names = [child for child in node.children if child.type == "identifier"]
    return node_text(data, names[-1])


def _plain_name(data: bytes, node) -> str | None:
    ident = child_of_type(node, "identifier")
    return node_text(data, ident) if ident is not None else None


def _name(data: bytes, signature) -> str | None:
    node = signature
    if node.type == "method_signature":
        node = next((child for child in node.children if child.is_named), None)
    if node is None:
        return None
    if node.type == "operator_signature":
        return _operator_name(data, node)
    if node.type == "factory_constructor_signature":
        return _factory_name(data, node)
    if node.type == "setter_signature":
        name = _plain_name(data, node)
        return name + "=" if name else None
    if node.type in _TOP_SIGNATURES:
        return _plain_name(data, node)
    return None


def _type_name(data: bytes, node) -> str:
    ident = child_of_type(node, "identifier")
    return node_text(data, ident) if ident is not None else "extension"


def _type_chain(data: bytes, node) -> list[str]:
    names: list[str] = []
    current = node.parent
    while current is not None:
        if current.type in _TYPES:
            names.append(_type_name(data, current))
        current = current.parent
    names.reverse()
    return names


def _package_of(file: Path) -> tuple[str, Path] | None:
    for folder in file.parents:
        pubspec = folder / "pubspec.yaml"
        if pubspec.is_file():
            match = _PACKAGE_NAME.search(pubspec.read_text(errors="replace"))
            return (match.group(1), folder) if match else None
    return None


def _dotted(relative: Path) -> list[str]:
    return list(relative.with_suffix("").parts)


def module_name(path: str, project_root: str | None) -> str:
    file = Path(absolute_path(path, project_root))
    package = _package_of(file)
    if package is None:
        return ".".join(_dotted(Path(path)))
    name, folder = package
    relative = file.relative_to(folder)
    if relative.parts[0] == "lib":
        relative = relative.relative_to("lib")
    return ".".join([name, *_dotted(relative)])


def functions_in_source(
    source: str, path: str, project_root: str | None = None
) -> list[Function]:
    data, tree = parse(source, "dart")
    module = module_name(path, project_root)
    found: list[Function] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        stack.extend(reversed(node.children))
        if not _is_signature(node) or _inside(node, _INSIDE_FUNCTION):
            continue
        body = _body_of(node)
        name = _name(data, node) if body is not None else None
        if name is None:
            continue
        found.append(
            Function(
                name=name,
                namespace=".".join([module, *_type_chain(data, node)]),
                complexity=_complexity(body),
                start_line=start_line(node),
                end_line=end_line(body),
                path=path,
                language="dart",
                start_byte=node.start_byte,
                end_byte=body.end_byte,
            )
        )
    return found
