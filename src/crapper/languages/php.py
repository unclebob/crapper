"""PHP functions, methods, and cyclomatic complexity.

Decision points follow the same structural rule as the other languages:
`if`, `elseif` (and `else if`), `for`, `foreach`, `while`, `do`, `catch`,
each `switch` case (not `default`), each `match` arm (not `default`), the
conditional `?:` in both its forms, and the short-circuit operators `&&`,
`||`, `and`, `or`, `??`, and `??=`. `xor` evaluates both sides and is not a
decision. The nullsafe `?->` is not counted.

Methods with a body in classes, traits, and enums are entries, as are
top-level functions. Closures and arrow functions stay inside the enclosing
function. Methods of anonymous classes (`new class { ... }`, as in every
Laravel migration) are skipped and do not raise the enclosing function.
A method's namespace is the PHP namespace plus the class, joined with dots
(`App.Services.AutoRefill`). A top-level function's namespace is the PHP
namespace, or the file name when the file declares none.
"""

from pathlib import Path

from crapper.languages.treesitter import (
    child_of_type,
    complexity,
    descendants,
    end_line,
    node_text,
    parse,
    start_line,
)
from crapper.model import Function

_DECISIONS = {
    "if_statement",
    "else_if_clause",
    "for_statement",
    "foreach_statement",
    "while_statement",
    "do_statement",
    "catch_clause",
    "case_statement",
    "match_conditional_expression",
    "conditional_expression",
}
_LOGIC = {"&&", "||", "and", "or", "??", "??="}
_LOGIC_NODES = {"binary_expression", "augmented_assignment_expression"}
_CLASS_LIKE = {
    "class_declaration",
    "trait_declaration",
    "enum_declaration",
    "interface_declaration",
    "anonymous_class",
}
_ENCLOSING_FUNCTIONS = {
    "function_definition",
    "method_declaration",
    "anonymous_function",
    "arrow_function",
}


def _is_decision(node) -> bool:
    if node.type in _DECISIONS:
        return True
    return node.type in _LOGIC_NODES and any(child.type in _LOGIC for child in node.children)


def _skip(node) -> bool:
    return node.type in _CLASS_LIKE


def _owner(node):
    current = node.parent
    while current is not None and current.type not in _CLASS_LIKE:
        current = current.parent
    return current


def _is_nested_function(node) -> bool:
    current = node.parent
    while current is not None:
        if current.type in _ENCLOSING_FUNCTIONS:
            return True
        current = current.parent
    return False


def _namespace_of(data: bytes, node) -> str:
    name = child_of_type(node, "namespace_name")
    if name is None:
        return ""
    return node_text(data, name).replace("\\", ".")


def _entry_namespace(data: bytes, node, namespace: str, path: str) -> str | None:
    """The namespace of an entry, or None when `node` is not an entry."""

    if node.type == "function_definition":
        if _is_nested_function(node):
            return None
        return namespace or Path(path).name.removesuffix(".php")
    if node.type != "method_declaration" or child_of_type(node, "compound_statement") is None:
        return None
    owner = _owner(node)
    if owner is None or owner.type == "anonymous_class":
        return None
    class_name = node_text(data, child_of_type(owner, "name"))
    return f"{namespace}.{class_name}" if namespace else class_name


def functions_in_source(
    source: str, path: str, project_root: str | None = None
) -> list[Function]:
    del project_root
    data, tree = parse(source, "php")
    namespace = ""
    found: list[Function] = []
    for node in descendants(tree.root_node):
        if node.type == "namespace_definition":
            namespace = _namespace_of(data, node)
            continue
        owner = _entry_namespace(data, node, namespace, path)
        if owner is None:
            continue
        found.append(
            Function(
                name=node_text(data, child_of_type(node, "name")),
                namespace=owner,
                complexity=complexity(node, _is_decision, _skip),
                start_line=start_line(node),
                end_line=end_line(node),
                path=path,
                language="php",
            )
        )
    return found
