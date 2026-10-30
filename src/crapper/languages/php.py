"""PHP functions, methods, and cyclomatic complexity.

The namespace is the PHP namespace with dots, plus the class for a method
(`App.Foo.Bar`), because uml-viewer nests namespaces on `.`. A function
outside any namespace takes the file's dotted path.
"""

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
    "conditional_expression",
    "case_statement",
    "default_statement",
    "match_conditional_expression",
    "match_default_expression",
    "nullsafe_member_access_expression",
    "nullsafe_member_call_expression",
}
_LOGIC = {"&&", "||", "and", "or", "??"}
_TYPES = {
    "class_declaration",
    "trait_declaration",
    "enum_declaration",
    "interface_declaration",
}
_FUNCTIONS = {"function_definition", "method_declaration"}


def _is_decision(node) -> bool:
    if node.type in _DECISIONS:
        return True
    return node.type == "binary_expression" and any(
        child.type in _LOGIC for child in node.children
    )


def _skip(node) -> bool:
    return node.type == "anonymous_class" or node.type in _TYPES


def _inside(node, types) -> bool:
    current = node.parent
    while current is not None:
        if current.type in types:
            return True
        current = current.parent
    return False


def _type_name(data: bytes, node) -> str | None:
    current = node.parent
    while current is not None:
        if current.type in _TYPES:
            ident = child_of_type(current, "name")
            return node_text(data, ident) if ident is not None else None
        current = current.parent
    return None


def _namespace_name(data: bytes, definition) -> str:
    name = child_of_type(definition, "namespace_name")
    if name is None:
        return ""
    return node_text(data, name).replace("\\", ".")


def _namespace_of(data: bytes, node, statements: list) -> str:
    current = node.parent
    while current is not None:
        if current.type == "namespace_definition":
            return _namespace_name(data, current)
        current = current.parent
    found = ""
    for definition in statements:
        if definition.start_byte < node.start_byte:
            found = _namespace_name(data, definition)
    return found


def _module_path(path: str, source_root: str | None) -> str:
    relative = path.replace("\\", "/")
    root = (source_root or "").replace("\\", "/").rstrip("/")
    if root and root != "." and relative.startswith(root + "/"):
        relative = relative[len(root) + 1 :]
    if relative.startswith("./"):
        relative = relative[2:]
    if relative.startswith("src/"):
        relative = relative[4:]
    elif "/src/" in relative:
        relative = relative.split("/src/", 1)[1]
    if relative.endswith(".php"):
        relative = relative[: -len(".php")]
    return relative.replace("/", ".")


def _qualify(namespace: str, name: str | None) -> str:
    return ".".join(part for part in (namespace, name) if part)


def _owner(data: bytes, node, namespace: str, path: str, source_root) -> str | None:
    """Namespace for an entry, or None when `node` is not one."""

    if child_of_type(node, "compound_statement") is None:
        return None
    if node.type == "method_declaration":
        if _inside(node, {"anonymous_class"}):
            return None
        type_name = _type_name(data, node)
        return _qualify(namespace, type_name) if type_name else None
    if _inside(node, _FUNCTIONS):
        return None
    return namespace or _module_path(path, source_root)


def functions_in_source(
    source: str, path: str, source_root: str | None = None
) -> list[Function]:
    data, tree = parse(source, "php")
    statements = [
        child
        for child in tree.root_node.children
        if child.type == "namespace_definition"
        and child_of_type(child, "compound_statement") is None
    ]
    found: list[Function] = []
    for node in descendants(tree.root_node):
        if node.type not in _FUNCTIONS:
            continue
        owner = _owner(data, node, _namespace_of(data, node, statements), path, source_root)
        ident = child_of_type(node, "name")
        if owner is None or ident is None:
            continue
        found.append(
            Function(
                name=node_text(data, ident),
                namespace=owner,
                complexity=complexity(node, _is_decision, _skip),
                start_line=start_line(node),
                end_line=end_line(node),
                path=path,
                language="php",
            )
        )
    return found
