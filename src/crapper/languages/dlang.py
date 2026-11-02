"""D functions, methods, and cyclomatic complexity.

Runtime decisions are conditionals, loops, catch clauses, each switch case,
the ternary operator, and logical and/or. Functions inside version(unittest)
are test helpers and are omitted. A nested function stays inside its owner.
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

_AGGREGATES = {
    "class_declaration",
    "interface_declaration",
    "struct_declaration",
    "union_declaration",
}
_DECISIONS = {
    "if_statement",
    "for_statement",
    "foreach_statement",
    "while_statement",
    "do_statement",
    "catch_statement",
    "case_statement",
    "ternary_expression",
}


def _is_decision(node) -> bool:
    return node.type in _DECISIONS | {"logical_and_expression", "logical_or_expression"}


def _skip_complexity(node) -> bool:
    return node.type in _AGGREGATES


def _inside_function(node) -> bool:
    current = node.parent
    while current is not None:
        if current.type == "function_declaration":
            return True
        current = current.parent
    return False


def _conditional_is_unittest(node) -> bool:
    if node.type != "conditional_declaration":
        return False
    condition = child_of_type(node, "condition")
    return any(child.type == "unittest" for child in descendants(condition))


def _inside_unittest(node) -> bool:
    current = node.parent
    while current is not None:
        if current.type == "unittest_declaration" or _conditional_is_unittest(current):
            return True
        current = current.parent
    return False


def _declared_module(data: bytes, root) -> str | None:
    for node in descendants(root):
        if node.type == "module_fqn":
            return node_text(data, node)
    return None


def _relative_path(path: str, project_root: str | None) -> str:
    normalized = path.replace("\\", "/")
    if project_root and Path(path).is_absolute():
        try:
            return Path(path).resolve().relative_to(Path(project_root).resolve()).as_posix()
        except ValueError:
            pass
    return normalized.lstrip("./")


def _fallback_module(path: str, project_root: str | None) -> str:
    relative = _without_source_root(_relative_path(path, project_root))
    relative = _without_d_suffix(relative)
    return relative.strip("/").replace("/", ".") or "app"


def _without_source_root(relative: str) -> str:
    for marker in ("source/", "src/"):
        if relative.startswith(marker):
            return relative[len(marker) :]
        nested = f"/{marker}"
        if nested in relative:
            return relative.split(nested, 1)[1]
    return relative


def _without_d_suffix(relative: str) -> str:
    if relative.endswith("/package.d"):
        return relative[: -len("/package.d")]
    if relative == "package.d":
        return ""
    if relative.endswith(".d"):
        return relative[:-2]
    return relative


def _aggregate_names(data: bytes, node) -> list[str]:
    names: list[str] = []
    current = node.parent
    while current is not None:
        if current.type in _AGGREGATES:
            ident = child_of_type(current, "identifier")
            if ident is not None:
                names.append(node_text(data, ident))
        current = current.parent
    names.reverse()
    return names


def functions_in_source(
    source: str, path: str, project_root: str | None = None
) -> list[Function]:
    data, tree = parse(source, "d")
    module = _declared_module(data, tree.root_node) or _fallback_module(path, project_root)
    found: list[Function] = []
    for node in descendants(tree.root_node):
        if node.type != "function_declaration":
            continue
        if _inside_function(node) or _inside_unittest(node):
            continue
        body = child_of_type(node, "function_body")
        if body is None or not body.named_children:
            continue
        ident = child_of_type(node, "identifier")
        if ident is None:
            continue
        name = node_text(data, ident)
        namespace = ".".join([module, *_aggregate_names(data, node)])
        found.append(
            Function(
                name=name,
                namespace=namespace,
                complexity=complexity(node, _is_decision, _skip_complexity),
                start_line=start_line(node),
                end_line=end_line(node),
                path=path,
                language="d",
                start_byte=node.start_byte,
                end_byte=node.end_byte,
            )
        )
    return found
