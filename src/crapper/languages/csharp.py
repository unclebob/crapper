"""C# methods, accessors, top-level statements, and minimal-API endpoints.

Decision points follow crap4java, spelled in C#: `if`, `for`, `foreach`, `while`,
`do`, `catch` and its `when` filter, `?:`, each `switch` section and its `when`
guard, each switch-expression arm, `&&` / `||`, the null operators `??` and `?.`,
and `and` / `or` inside a pattern. Methods with a body, a block or `=> expression`,
are entries. So are property, indexer, and event accessors with a body, and
expression-bodied properties, under the names the compiler gives them: `get_Count`,
`set_Item`, `add_Changed`. Constructors, operators, and finalizers are omitted, as
crap4java omits constructors. A lambda or a local function stays inside the
enclosing entry.

Top-level statements are one entry, `<Main>$` in `Program`, again the compiler's
name, under the project's root namespace (`RootNamespace` in the nearest .csproj,
else that file's name) so two projects' `Program.cs` do not share a key; a
`partial class Program` declared in source keeps its own key, `Program`. A
minimal-API endpoint registered with a lambda (`app.MapGet("/users", ...)`,
`MapPost`, `MapPut`, `MapPatch`, `MapDelete`, `Map`, `MapMethods`) is its own entry
named `GET /users`, wherever the registration sits; a second lambda on the same route
is `GET /users#2`. Its decisions are not also charged to the enclosing entry. That is
the Express rule from typescript.py.

The namespace is `Namespace.Class`, or `Namespace.Outer.Inner`, the uml-viewer class
key. A file-scoped `namespace X;` covers every type after it. A type outside any
namespace is just `Class`. Coverage is LCOV from coverlet, matched by file path.
"""

import re
from pathlib import Path

from crapper.languages.treesitter import (
    absolute_path,
    claim_name,
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
    "for_statement",
    "foreach_statement",
    "while_statement",
    "do_statement",
    "catch_clause",
    "catch_filter_clause",
    "conditional_expression",
    "switch_section",
    "when_clause",
    "switch_expression_arm",
    "conditional_access_expression",
    "and_pattern",
    "or_pattern",
}
_LOGIC = {"&&", "||", "??"}
_TYPES = {
    "class_declaration",
    "struct_declaration",
    "record_declaration",
    "interface_declaration",
    "enum_declaration",
}
_NAMESPACES = {"namespace_declaration", "file_scoped_namespace_declaration"}
# Members whose accessors, or whose `=> expression`, are entries.
_MEMBERS = {"property_declaration", "indexer_declaration", "event_declaration"}
_ACCESSOR_KINDS = {"get", "set", "init", "add", "remove"}
_CALLBACKS = {"lambda_expression", "anonymous_method_expression"}
_ROUTES = {
    "MapGet": "GET",
    "MapPost": "POST",
    "MapPut": "PUT",
    "MapPatch": "PATCH",
    "MapDelete": "DELETE",
    "Map": "MAP",
    "MapMethods": "MAP",
}
_STRING_PARTS = {"string_literal_content", "escape_sequence", "raw_string_content", "string_content", "interpolation"}
TOP_LEVEL_NAME = "<Main>$"
TOP_LEVEL_NAMESPACE = "Program"
INDEXER_NAME = "Item"
_ROOT_NAMESPACE = re.compile(r"<RootNamespace>\s*([^<\s]+)\s*</RootNamespace>")


def _is_decision(node) -> bool:
    if node.type in _DECISIONS:
        return True
    return node.type == "binary_expression" and any(child.type in _LOGIC for child in node.children)


def _field(node, name: str):
    return node.child_by_field_name(name)


def _name_of(data: bytes, node) -> str | None:
    name = _field(node, "name")
    return node_text(data, name) if name is not None else None


def _file_namespace(data: bytes, root) -> str | None:
    """`namespace X;` names every type declared after it in the file."""

    for child in root.children:
        if child.type == "file_scoped_namespace_declaration":
            return _name_of(data, child)
    return None


def _root_namespace(project: Path) -> str:
    match = _ROOT_NAMESPACE.search(project.read_text(encoding="utf-8", errors="replace"))
    return match.group(1) if match else project.stem


def _program_namespace(path: str, project_root: str | None) -> str:
    """`Program` under the nearest .csproj's root namespace; bare `Program` for a snippet or
    a file with no project above it."""

    if project_root is None:
        return TOP_LEVEL_NAMESPACE
    stop = Path(project_root).resolve()
    current = Path(absolute_path(path, project_root)).parent
    while True:
        projects = sorted(current.glob("*.csproj"))
        if projects:
            return f"{_root_namespace(projects[0])}.{TOP_LEVEL_NAMESPACE}"
        if current == stop or current.parent == current:
            return TOP_LEVEL_NAMESPACE
        current = current.parent


def _namespace(data: bytes, node, file_namespace: str | None, program: str) -> str:
    """`Namespace.Outer.Inner` for a member of Inner; `program` outside every type."""

    names: list[str] = []
    current = node.parent
    while current is not None:
        if current.type in _TYPES or current.type in _NAMESPACES:
            name = _name_of(data, current)
            if name:
                names.append(name)
        current = current.parent
    if file_namespace:
        names.append(file_namespace)
    names.reverse()
    return ".".join(names) if names else program


def _route_verb(data: bytes, call) -> str | None:
    function = _field(call, "function")
    if function is None or function.type != "member_access_expression":
        return None
    name = _field(function, "name")
    if name is None or name.type != "identifier":
        return None
    return _ROUTES.get(node_text(data, name))


def _argument_values(call) -> list:
    arguments = _field(call, "arguments")
    if arguments is None:
        return []
    values = []
    for argument in arguments.named_children:
        if argument.type == "argument" and argument.named_children:
            values.append(argument.named_children[-1])
    return values


def _is_route_callback(data: bytes, node) -> bool:
    if node.type not in _CALLBACKS:
        return False
    argument = node.parent
    if argument is None or argument.type != "argument" or argument.parent is None:
        return False
    call = argument.parent.parent
    if call is None or call.type != "invocation_expression":
        return False
    return _route_verb(data, call) is not None


def _complexity(data: bytes, node) -> int:
    root_id = node.id

    def skip(current) -> bool:
        if current.id == root_id:
            return False
        if current.type in _TYPES or current.type in _NAMESPACES:
            return True
        return _is_route_callback(data, current)

    return complexity(node, _is_decision, skip)


def _append(found: list, node, path: str, **kwargs) -> None:
    found.append(
        (
            node.start_byte,
            Function(
                start_byte=node.start_byte,
                end_byte=node.end_byte,
                path=path,
                language="csharp",
                start_line=start_line(node),
                end_line=end_line(node),
                **kwargs,
            ),
        )
    )


def _append_method(found, data, node, scope, path) -> None:
    # No body: abstract, extern, or an interface signature.
    if _field(node, "body") is None:
        return
    name = _name_of(data, node)
    if name is None:
        return
    _append(
        found,
        node,
        name=name,
        namespace=_namespace(data, node, *scope),
        complexity=_complexity(data, node),
        path=path,
    )


def _member_name(data: bytes, member) -> str:
    if member.type == "indexer_declaration":
        return INDEXER_NAME
    return _name_of(data, member) or INDEXER_NAME


def _accessor_kind(node) -> str | None:
    for child in node.children:
        if not child.is_named and child.type in _ACCESSOR_KINDS:
            return child.type
    return None


def _append_accessor(found, data, node, scope, path) -> None:
    """`get_Count` for a `get` with a body. `get;` of an auto-property is not an entry."""

    if _field(node, "body") is None:
        return
    accessors = node.parent
    member = accessors.parent if accessors is not None else None
    kind = _accessor_kind(node)
    if member is None or member.type not in _MEMBERS or kind is None:
        return
    _append(
        found,
        node,
        name=f"{kind}_{_member_name(data, member)}",
        namespace=_namespace(data, node, *scope),
        complexity=_complexity(data, node),
        path=path,
    )


def _append_expression_bodied(found, data, node, scope, path) -> None:
    """`public int Count => _lines.Count;` is a getter, `get_Count`."""

    clause = next((child for child in node.children if child.type == "arrow_expression_clause"), None)
    if clause is None:
        return
    _append(
        found,
        node,
        name=f"get_{_member_name(data, node)}",
        namespace=_namespace(data, node, *scope),
        complexity=_complexity(data, clause),
        path=path,
    )


def _append_top_level(found, data, root, path, program: str) -> None:
    """Top-level statements are `<Main>$` in `Program`, with every local function inside."""

    statements = [child for child in root.children if child.type == "global_statement"]
    if not statements:
        return
    first, last = statements[0], statements[-1]
    score = 1 + sum(_complexity(data, statement) - 1 for statement in statements)
    found.append(
        (
            first.start_byte,
            Function(
                name=TOP_LEVEL_NAME,
                namespace=program,
                complexity=score,
                start_line=start_line(first),
                end_line=end_line(last),
                path=path,
                language="csharp",
                start_byte=first.start_byte,
                end_byte=last.end_byte,
            ),
        )
    )


def _literal_text(data: bytes, node) -> str | None:
    """The route in a plain, verbatim, raw, or interpolated string, without its quotes."""

    if node.type == "verbatim_string_literal":
        text = node_text(data, node)
        return text[2:-1] if text.startswith('@"') and text.endswith('"') else text
    if node.type in {"string_literal", "raw_string_literal", "interpolated_string_expression"}:
        return "".join(node_text(data, child) for child in node.children if child.type in _STRING_PARTS)
    return None


def _route_path(data: bytes, call) -> str | None:
    for value in _argument_values(call):
        text = _literal_text(data, value)
        if text is not None:
            return text
    return None


def _collect_routes(routes: list, data: bytes, call) -> None:
    verb = _route_verb(data, call)
    if verb is None:
        return
    callbacks = [value for value in _argument_values(call) if value.type in _CALLBACKS]
    if not callbacks:
        return
    route = _route_path(data, call)
    for callback in callbacks:
        routes.append((callback.start_byte, callback, verb, route))


def _append_routes(found, routes, data, scope, path) -> None:
    used: set[str] = set()
    for _start, callback, verb, route in sorted(routes, key=lambda item: item[0]):
        label = f"{verb} {route}" if route else verb
        _append(
            found,
            callback,
            name=claim_name(used, label),
            namespace=_namespace(data, callback, *scope),
            complexity=_complexity(data, callback),
            path=path,
        )


def functions_in_source(
    source: str, path: str, project_root: str | None = None
) -> list[Function]:
    data, tree = parse(source, "csharp")
    root = tree.root_node
    program = _program_namespace(path, project_root)
    # What a member's namespace is made of: the file-scoped namespace, and the key for code outside every type.
    scope = (_file_namespace(data, root), program)
    found: list[tuple[int, Function]] = []
    routes: list[tuple[int, object, str, str | None]] = []
    _append_top_level(found, data, root, path, program)
    for node in descendants(root):
        if node.type == "method_declaration":
            _append_method(found, data, node, scope, path)
        elif node.type == "accessor_declaration":
            _append_accessor(found, data, node, scope, path)
        elif node.type in _MEMBERS:
            _append_expression_bodied(found, data, node, scope, path)
        elif node.type == "invocation_expression":
            _collect_routes(routes, data, node)
    _append_routes(found, routes, data, scope, path)
    found.sort(key=lambda item: item[0])
    return [function for _, function in found]
