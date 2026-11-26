"""TypeScript, TSX, and JavaScript functions, methods, and complexity.

Decision points follow the same structural rule as crap4java: `if`, loops,
`catch`, `?:`, each `switch` case (including `default`), `&&` / `||`, and the
nullish operators `??` and `?.`. Top-level functions and class methods are
entries. An inline Express route callback (`app.get("/users", handler)` and
the same methods on a router, including `use` and `route().get`) is its own
entry, named `GET /users`. Other nested callbacks stay inside the enclosing
function. A class method's namespace is `module.Class`, which is the
uml-viewer class key. `.js`, `.mjs`, `.cjs`, and `.jsx` use the JavaScript
grammar and these same rules.
"""

from crapper.languages.treesitter import (
    binary_logic,
    child_of_type,
    claim_name,
    complexity,
    descendants,
    end_line,
    node_text,
    parse,
    start_line,
    strip_root,
    strip_src,
)
from crapper.model import Function

_DECISIONS = {
    "if_statement",
    "for_statement",
    "for_in_statement",
    "while_statement",
    "do_statement",
    "catch_clause",
    "ternary_expression",
    "switch_case",
    "switch_default",
}
_SKIP = {
    "class_declaration",
    "abstract_class_declaration",
    "interface_declaration",
}
_FUNCTION_TYPES = {
    "function_declaration",
    "method_definition",
    "arrow_function",
    "function_expression",
}
_ROUTE_METHODS = {
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "head",
    "options",
    "all",
    "use",
}
_CALLBACKS = {"arrow_function", "function_expression"}
_JS_SUFFIXES = (".jsx", ".mjs", ".cjs", ".js")
WRAPPERS = frozenset(
    {
        "parenthesized_expression",
        "as_expression",
        "satisfies_expression",
        "type_assertion",
    }
)
_WRAPPER_SKIP = frozenset({"type_arguments", "comment"})


def _is_nullish(node) -> bool:
    if node.type == "binary_expression":
        return any(child.type == "??" for child in node.children)
    # `a?.b` and `a?.[0]` wrap `?.` in optional_chain. `a?.()` is a bare `?.`
    # in TypeScript and an optional_chain in JavaScript. Count the wrapper
    # once, and a bare token only when nothing wraps it.
    if node.type == "optional_chain":
        return True
    if node.type != "?.":
        return False
    return node.parent is None or node.parent.type != "optional_chain"


def _is_decision(node) -> bool:
    return node.type in _DECISIONS or binary_logic(node) or _is_nullish(node)


def _skip(node) -> bool:
    return node.type in _SKIP


def _grammar(path: str) -> str:
    if path.endswith(".tsx"):
        return "tsx"
    if path.endswith(_JS_SUFFIXES):
        return "javascript"
    return "typescript"


def _strip_script_suffix(relative: str) -> str:
    for suffix in (".tsx", ".mts", ".cts", ".jsx", ".mjs", ".cjs", ".ts", ".js"):
        if relative.endswith(suffix):
            return relative[: -len(suffix)]
    return relative


def _module_namespace(path: str, source_root: str | None) -> str:
    relative = path.replace("\\", "/")
    relative = strip_root(relative, source_root)
    relative = strip_src(relative)
    return _strip_script_suffix(relative).replace("/", ".")


def inside_function(node) -> bool:
    current = node.parent
    while current is not None:
        if current.type in _FUNCTION_TYPES:
            return True
        current = current.parent
    return False


def _class_names(data: bytes, node) -> list[str]:
    names: list[str] = []
    current = node.parent
    while current is not None:
        if current.type in {"class_declaration", "abstract_class_declaration"}:
            ident = child_of_type(current, "type_identifier", "identifier")
            if ident is not None:
                names.append(node_text(data, ident))
        current = current.parent
    names.reverse()
    return names


def has_body(node) -> bool:
    return child_of_type(node, "statement_block") is not None


def _unwrapped_child(node):
    for child in node.children:
        if child.is_named and child.type not in _WRAPPER_SKIP:
            return child
    return None


def unwrap_expression(node):
    current = node
    while current is not None and current.type in WRAPPERS:
        current = _unwrapped_child(current)
    return current


def call_callee(call):
    for child in call.children:
        if child.type not in {"arguments", "type_arguments", "comment"}:
            return child
    return None


def property_name(data: bytes, node) -> str | None:
    if node is None or node.type != "member_expression":
        return None
    ident = child_of_type(node, "property_identifier")
    if ident is None:
        return None
    return node_text(data, ident)


def _route_method(data: bytes, call) -> str | None:
    name = property_name(data, call_callee(call))
    if name is None:
        return None
    lowered = name.lower()
    if lowered in _ROUTE_METHODS:
        return lowered
    return None


def literal_text(data: bytes, node) -> str | None:
    if node.type == "string":
        return "".join(
            node_text(data, child) for child in node.children if child.type == "string_fragment"
        )
    if node.type == "template_string":
        text = node_text(data, node)
        if len(text) >= 2 and text[0] == "`" and text[-1] == "`":
            return text[1:-1]
    return None


def _string_argument(data: bytes, call) -> str | None:
    arguments = child_of_type(call, "arguments")
    if arguments is None:
        return None
    for child in arguments.children:
        expr = unwrap_expression(child)
        if expr is None:
            continue
        text = literal_text(data, expr)
        if text is not None:
            return text
    return None


def _path_from_route(data: bytes, node) -> str | None:
    """Path from a preceding `.route("/path")` in a chained call."""

    current = node
    while current is not None:
        if current.type == "member_expression":
            current = current.children[0] if current.children else None
            continue
        if current.type != "call_expression":
            return None
        callee = call_callee(current)
        if property_name(data, callee) == "route":
            return _string_argument(data, current)
        current = callee
    return None


def _callbacks(call) -> list:
    arguments = child_of_type(call, "arguments")
    if arguments is None:
        return []
    found = []
    for child in arguments.children:
        expr = unwrap_expression(child)
        if expr is not None and expr.type in _CALLBACKS:
            found.append(expr)
    return found


def _argument_list_parent(node):
    current = node.parent
    while current is not None and current.type in WRAPPERS:
        current = current.parent
    if current is not None and current.type == "arguments":
        return current.parent
    return None


def _is_route_callback(data: bytes, node) -> bool:
    if node.type not in _CALLBACKS:
        return False
    call = _argument_list_parent(node)
    if call is None or call.type != "call_expression":
        return False
    return _route_method(data, call) is not None


def script_complexity(data: bytes, node, *, include_routes: bool = True) -> int:
    root_id = node.id

    def skip(current) -> bool:
        if current.id == root_id:
            return False
        if _skip(current):
            return True
        return include_routes and _is_route_callback(data, current)

    return complexity(node, _is_decision, skip)


def append_function(
    found: list,
    span_node,
    body_node,
    data: bytes,
    *,
    name: str,
    namespace: str,
    path: str,
    language: str = "typescript",
    include_routes: bool = True,
) -> None:
    found.append(
        (
            span_node.start_byte,
            Function(
                name=name,
                namespace=namespace,
                complexity=script_complexity(data, body_node, include_routes=include_routes),
                start_line=start_line(span_node),
                end_line=end_line(span_node),
                path=path,
                language=language,
                start_byte=span_node.start_byte,
                end_byte=span_node.end_byte,
            ),
        )
    )


def _append_function(found, data, node, module, path, language, include_routes) -> None:
    if inside_function(node) or not has_body(node):
        return
    ident = child_of_type(node, "identifier")
    if ident is None:
        return
    append_function(
        found,
        node,
        node,
        data,
        name=node_text(data, ident),
        namespace=module,
        path=path,
        language=language,
        include_routes=include_routes,
    )


def _append_method(found, data, node, module, path, language, include_routes) -> None:
    if not has_body(node):
        return
    ident = child_of_type(node, "property_identifier", "identifier")
    classes = _class_names(data, node)
    if ident is None or not classes:
        return
    append_function(
        found,
        node,
        node,
        data,
        name=node_text(data, ident),
        namespace=f"{module}.{'.'.join(classes)}",
        path=path,
        language=language,
        include_routes=include_routes,
    )


def _declarator_callback(declarator):
    if declarator.type != "variable_declarator":
        return None, None
    ident = child_of_type(declarator, "identifier")
    value = unwrap_expression(declarator.child_by_field_name("value"))
    if ident is None or value is None or value.type not in _CALLBACKS:
        return None, None
    return ident, value


def _append_arrows(found, data, node, module, path, language, include_routes) -> None:
    if inside_function(node):
        return
    for declarator in node.children:
        ident, value = _declarator_callback(declarator)
        if ident is None:
            continue
        append_function(
            found,
            declarator,
            value,
            data,
            name=node_text(data, ident),
            namespace=module,
            path=path,
            language=language,
            include_routes=include_routes,
        )


def _route_label(method: str, path: str | None) -> str:
    label = method.upper()
    if path:
        return f"{label} {path}"
    return label


def _collect_routes(routes: list, data: bytes, call) -> None:
    method = _route_method(data, call)
    if method is None:
        return
    callbacks = _callbacks(call)
    if not callbacks:
        return
    route = _string_argument(data, call)
    if not route:
        route = _path_from_route(data, call_callee(call))
    for callback in callbacks:
        routes.append((callback.start_byte, callback, method, route))


def _append_routes(found, routes, data, module, path, language) -> None:
    used: set[str] = set()
    for _start, callback, method, route in sorted(routes, key=lambda item: item[0]):
        append_function(
            found,
            callback,
            callback,
            data,
            name=claim_name(used, _route_label(method, route)),
            namespace=module,
            path=path,
            language=language,
        )


def _collect_node(found, routes, data, node, module, path, language, include_routes) -> None:
    if node.type == "function_declaration":
        _append_function(found, data, node, module, path, language, include_routes)
    elif node.type == "method_definition":
        _append_method(found, data, node, module, path, language, include_routes)
    elif node.type == "lexical_declaration":
        _append_arrows(found, data, node, module, path, language, include_routes)
    elif include_routes and node.type == "call_expression":
        _collect_routes(routes, data, node)


def extract_tree_functions(
    data: bytes,
    root,
    module: str,
    path: str,
    *,
    language: str = "typescript",
    include_routes: bool = True,
) -> list[tuple[int, Function]]:
    found: list[tuple[int, Function]] = []
    routes: list[tuple[int, object, str, str | None]] = []
    for node in descendants(root):
        _collect_node(found, routes, data, node, module, path, language, include_routes)
    _append_routes(found, routes, data, module, path, language)
    return found


def functions_in_source(
    source: str, path: str, source_root: str | None = None
) -> list[Function]:
    data, tree = parse(source, _grammar(path))
    module = _module_namespace(path, source_root)
    found = extract_tree_functions(data, tree.root_node, module, path)
    found.sort(key=lambda item: item[0])
    return [function for _, function in found]
