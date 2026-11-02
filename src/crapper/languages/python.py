"""Python functions, methods, and cyclomatic complexity.

Decision points follow the same structural rule as the other languages:
`if`, `elif`, `for`, `while`, `except`, each `match` case, a comprehension
filter, a conditional expression, and each `and` / `or`. Module-level
functions and class methods are entries. A nested function stays inside the
enclosing function, unless it is a route handler: a function nested in a
factory and decorated with `@router.get("/users")` (or `.post`, `.put`,
`.patch`, `.delete`, `.head`, `.options`, `.trace`, `.websocket`, `.route`, or
`.api_route`) is its own entry, named `GET /users`, in the module's namespace,
and its decisions are not also charged to the factory. A class method's
namespace is `module.Class`.
"""

from crapper.languages.treesitter import (
    child_of_type,
    claim,
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
    "elif_clause",
    "for_statement",
    "while_statement",
    "except_clause",
    "conditional_expression",
    "case_clause",
    "if_clause",
}
_ROUTE_VERBS = {"get", "post", "put", "patch", "delete", "head", "options", "trace", "websocket"}
_ROUTE_RULES = {"route", "api_route"}
_PATH_KEYWORDS = {"path", "rule"}
_PATH_NAMES = {"identifier", "attribute"}


def _is_decision(node) -> bool:
    if node.type in _DECISIONS:
        return True
    return node.type == "boolean_operator" and any(
        child.type in {"and", "or"} for child in node.children
    )


def _skip(node) -> bool:
    return node.type == "class_definition"


def _string_body(data: bytes, node) -> str:
    return "".join(
        node_text(data, child)
        for child in node.children
        if child.type not in {"string_start", "string_end"}
    )


def _keyword(data: bytes, arguments, names: set[str]):
    for child in arguments.named_children:
        if child.type != "keyword_argument":
            continue
        if node_text(data, child.child_by_field_name("name")) in names:
            return child.child_by_field_name("value")
    return None


def _path_argument(data: bytes, arguments):
    first = next((child for child in arguments.named_children if child.type != "comment"), None)
    if first is not None and first.type != "keyword_argument":
        return first
    return _keyword(data, arguments, _PATH_KEYWORDS)


def _route_path(data: bytes, node) -> str | None:
    """The path a route decorator names, or None when it is not a URL path.

    A plain string must be empty or start with `/`, so `@mock.patch("a.b")`
    is not a route. An f-string keeps its fields; a name keeps its source.
    """

    if node is None:
        return None
    if node.type in _PATH_NAMES:
        return node_text(data, node)
    if node.type != "string":
        return None
    path = _string_body(data, node)
    if child_of_type(node, "interpolation") is not None or path == "" or path.startswith("/"):
        return path
    return None


def _route_verbs(data: bytes, method: str, arguments) -> str:
    if method not in _ROUTE_RULES:
        return method.upper()
    listed = _keyword(data, arguments, {"methods"})
    if listed is None:
        return "GET"
    verbs = [_string_body(data, item).upper() for item in listed.named_children if item.type == "string"]
    return "|".join(verbs) or "GET"


def _route_call(data: bytes, decorator):
    """`(method, arguments)` for `@<object>.<method>(...)` with a route method."""

    call = child_of_type(decorator, "call")
    if call is None:
        return None
    callee = call.child_by_field_name("function")
    if callee is None or callee.type != "attribute":
        return None
    method = node_text(data, callee.child_by_field_name("attribute"))
    if method not in _ROUTE_VERBS and method not in _ROUTE_RULES:
        return None
    return method, call.child_by_field_name("arguments")


def _route_label(data: bytes, decorator) -> str | None:
    found = _route_call(data, decorator)
    if found is None:
        return None
    method, arguments = found
    path = _route_path(data, _path_argument(data, arguments))
    if path is None:
        return None
    verbs = _route_verbs(data, method, arguments)
    return f"{verbs} {path}" if path else verbs


def _route(data: bytes, node) -> str | None:
    """`GET /users` for a function decorated as a route handler, else None."""

    parent = node.parent
    if parent is None or parent.type != "decorated_definition":
        return None
    for decorator in parent.children:
        if decorator.type != "decorator":
            continue
        label = _route_label(data, decorator)
        if label is not None:
            return label
    return None


def _complexity(data: bytes, node) -> int:
    """Complexity of `node`, leaving out the route handlers nested in it."""

    def skip(current) -> bool:
        if current.id == node.id:
            return False
        if current.type == "function_definition" and _route(data, current) is not None:
            return True
        return _skip(current)

    return complexity(node, _is_decision, skip)


def _strip_root(relative: str, source_root: str | None) -> str:
    root = (source_root or "").replace("\\", "/").rstrip("/")
    if root and root != "." and relative.startswith(root + "/"):
        return relative[len(root) + 1 :]
    if relative.startswith("./"):
        return relative[2:]
    return relative


def _strip_src(relative: str) -> str:
    if relative.startswith("src/"):
        return relative[4:]
    if "/src/" in relative:
        return relative.split("/src/", 1)[1]
    return relative


def _strip_module_suffix(relative: str) -> str:
    if relative.endswith(".py"):
        relative = relative[: -len(".py")]
    if relative.endswith("/__init__"):
        return relative[: -len("/__init__")]
    if relative == "__init__":
        return ""
    return relative


def _module_namespace(path: str, source_root: str | None) -> str:
    relative = _strip_module_suffix(_strip_src(_strip_root(path.replace("\\", "/"), source_root)))
    if not relative:
        return "__init__"
    return relative.replace("/", ".")


def _is_nested_function(node) -> bool:
    """A function inside another function, unless it is a method of a class."""

    current = node.parent
    while current is not None:
        if current.type == "class_definition":
            return False
        if current.type == "function_definition":
            return True
        current = current.parent
    return False


def _class_names(data: bytes, node) -> list[str]:
    names: list[str] = []
    current = node.parent
    while current is not None:
        if current.type == "class_definition":
            ident = child_of_type(current, "identifier")
            if ident is not None:
                names.append(node_text(data, ident))
        current = current.parent
    names.reverse()
    return names


def _namespace(data: bytes, node, module: str) -> str:
    classes = _class_names(data, node)
    if not classes:
        return module
    return ".".join([module, *classes]) if module else ".".join(classes)


def _identity(data: bytes, node, module: str, used: set[str]) -> tuple[str, str] | None:
    """Name and namespace of the entry for `node`, or None when it has none."""

    if _is_nested_function(node):
        route = _route(data, node)
        return None if route is None else (claim(used, route), module)
    ident = child_of_type(node, "identifier")
    if ident is None:
        return None
    return node_text(data, ident), _namespace(data, node, module)


def functions_in_source(
    source: str, path: str, source_root: str | None = None
) -> list[Function]:
    data, tree = parse(source, "python")
    module = _module_namespace(path, source_root)
    found: list[Function] = []
    used: set[str] = set()
    for node in descendants(tree.root_node):
        if node.type != "function_definition":
            continue
        identity = _identity(data, node, module, used)
        if identity is None:
            continue
        name, namespace = identity
        found.append(
            Function(
                name=name,
                namespace=namespace,
                complexity=_complexity(data, node),
                start_line=start_line(node),
                end_line=end_line(node),
                path=path,
                language="python",
            )
        )
    return found
