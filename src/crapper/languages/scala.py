"""Scala methods and cyclomatic complexity.

A `def` with a body is one entry. An abstract def, a secondary constructor,
and a def inside a lambda or an anonymous class are not. A lambda or a local
def counts toward the enclosing method, as in Python; an anonymous class body
does not, as in Java. The namespace is the package and the enclosing types,
`pkg.Outer.Inner`, so uml-viewer can attach scores to that class. A top level
def belongs to its package.
"""

from crapper.languages.treesitter import (
    ancestor_names,
    child_of_type,
    complexity,
    enclosed_by,
    end_line,
    node_text,
    parse,
    start_line,
)
from crapper.model import Function

_TYPES = {
    "class_definition",
    "object_definition",
    "trait_definition",
    "enum_definition",
    "package_object",
}
_DECISIONS = {
    "if_expression",
    "while_expression",
    "do_while_expression",
    "for_expression",
    "guard",
    "case_clause",
}
_EXECUTABLE = {"function_definition", "lambda_expression", "instance_expression"}
_COMMENTS = {"comment", "block_comment"}


def _is_logic(data: bytes, node) -> bool:
    if node.type != "infix_expression":
        return False
    operator = child_of_type(node, "operator_identifier")
    return operator is not None and node_text(data, operator) in {"&&", "||"}


def _is_single_catch_case(node) -> bool:
    # Scala 3 `catch case e: E => ...` holds its one case directly, with no case_clause.
    return node.type == "catch_clause" and child_of_type(node, "case") is not None


def _skip(node) -> bool:
    return node.type in _TYPES or node.type == "template_body"


def _package(data: bytes, root) -> list[str]:
    """The flat `package a.b` clauses at the top of the file, in order."""

    names: list[str] = []
    for child in root.children:
        if child.type == "package_clause" and child_of_type(child, "template_body") is None:
            ident = child_of_type(child, "package_identifier")
            if ident is not None:
                names.append(node_text(data, ident))
    return names


def _name_node(node):
    if node.type in _TYPES:
        return child_of_type(node, "identifier")
    if node.type == "package_clause":
        return child_of_type(node, "package_identifier")
    return None


def _last_token(node):
    """The last token of node that is not a comment.

    An indented body runs on through the comments and the indentation that
    follow it, up to the next definition, so the def ends where this token does.
    """

    while True:
        children = [c for c in node.children if c.type not in _COMMENTS]
        if not children:
            return node
        node = children[-1]


def _function(data: bytes, node, package: list[str], path: str) -> Function | None:
    # The name comes first, before the parameters and the body, and is a plain or an
    # operator identifier. A def with no name parses with a missing one.
    ident = child_of_type(node, "identifier", "operator_identifier")
    if ident.is_missing:
        return None
    name = node_text(data, ident)
    if name == "this":
        return None
    return Function(
        name=name,
        namespace=".".join(package + ancestor_names(data, node, _name_node)),
        complexity=complexity(
            node,
            lambda n: n.type in _DECISIONS or _is_logic(data, n) or _is_single_catch_case(n),
            _skip,
        ),
        start_line=start_line(node),
        end_line=end_line(_last_token(node)),
        path=path,
        language="scala",
    )


def functions_in_source(
    source: str, path: str, project_root: str | None = None
) -> list[Function]:
    del project_root
    data, tree = parse(source, "scala")
    package = _package(data, tree.root_node)
    found: list[Function] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type == "function_definition":
            if not enclosed_by(node, _EXECUTABLE):
                function = _function(data, node, package, path)
                if function is not None:
                    found.append(function)
            continue
        stack.extend(reversed(node.children))
    return found
