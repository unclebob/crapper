"""Vue Single File Component functions, handlers, hooks, and complexity.

Top-level functions, class methods, Options API handlers (`methods`, `computed`,
`watch`, `data`, `setup`, `render`, and lifecycle hooks), and top-level
Composition API hooks (`computed`, `watch`, `watchEffect` variants, and
lifecycle hooks) are entries. Decision points follow TypeScript rules without
Express route extraction, and line and byte spans stay in `.vue` coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from crapper.languages.treesitter import (
    child_of_type,
    child_text,
    claim_name,
    descendants,
    node_text,
    parse,
    parse_range,
    strip_root,
    strip_src,
)
from crapper.languages.typescript import (
    WRAPPERS,
    append_function,
    call_callee,
    extract_tree_functions,
    has_body,
    inside_function,
    literal_text,
    property_name,
    unwrap_expression,
)
from crapper.model import Function

ScriptGrammar = Literal["javascript", "typescript", "tsx"]


@dataclass(frozen=True)
class ScriptBlock:
    grammar: ScriptGrammar
    is_setup: bool
    span: object


@dataclass(frozen=True)
class _Target:
    data: bytes
    module: str
    path: str


_SCRIPT_GRAMMARS: dict[str, ScriptGrammar] = {
    "": "javascript",
    "js": "javascript",
    "jsx": "javascript",
    "mjs": "javascript",
    "cjs": "javascript",
    "javascript": "javascript",
    "ts": "typescript",
    "mts": "typescript",
    "cts": "typescript",
    "typescript": "typescript",
    "tsx": "tsx",
}
_OPTIONS_SKIP_KEYS = frozenset(
    {"props", "emits", "components", "directives", "provide", "inject"}
)
_CALLBACKS = frozenset({"arrow_function", "function_expression"})
_EFFECT_HOOKS = frozenset(
    {
        "watchEffect",
        "watchPostEffect",
        "watchSyncEffect",
        "onBeforeMount",
        "onMounted",
        "onBeforeUpdate",
        "onUpdated",
        "onBeforeUnmount",
        "onUnmounted",
        "onActivated",
        "onDeactivated",
        "onErrorCaptured",
        "onRenderTracked",
        "onRenderTriggered",
        "onServerPrefetch",
    }
)
_WATCH_SIMPLE = frozenset({"identifier", "member_expression"})
_MAX_WATCH_LABEL = 32


def _attribute_value(data: bytes, attr) -> str:
    quoted = child_of_type(attr, "quoted_attribute_value")
    if quoted is not None:
        return child_text(data, quoted, "attribute_value") or ""
    return child_text(data, attr, "attribute_value") or ""


def _start_attributes(data: bytes, start_tag) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for child in start_tag.children:
        if child.type != "attribute":
            continue
        name = child_text(data, child, "attribute_name")
        if name is not None:
            attrs[name.lower()] = _attribute_value(data, child)
    return attrs


def _script_block(data: bytes, element) -> ScriptBlock | None:
    start_tag = child_of_type(element, "start_tag")
    raw_text = child_of_type(element, "raw_text")
    if start_tag is None or raw_text is None:
        return None
    if not data[raw_text.start_byte : raw_text.end_byte].strip():
        return None
    attrs = _start_attributes(data, start_tag)
    if "src" in attrs:
        return None
    grammar = _SCRIPT_GRAMMARS.get(attrs.get("lang", "").strip().lower())
    if grammar is None:
        return None
    return ScriptBlock(grammar=grammar, is_setup="setup" in attrs, span=raw_text.range)


def extract_script_blocks(source: str) -> tuple[bytes, list[ScriptBlock]]:
    data, tree = parse(source, "vue")
    blocks: list[ScriptBlock] = []
    for child in tree.root_node.children:
        if child.type != "script_element":
            continue
        block = _script_block(data, child)
        if block is not None:
            blocks.append(block)
    return data, blocks


def _vue_namespace(path: str, source_root: str | None) -> str:
    relative = strip_src(strip_root(path.replace("\\", "/"), source_root))
    if relative.endswith(".vue"):
        relative = relative[:-4]
    return relative.replace("/", ".")


def _record(found: list, span_node, body_node, target: _Target, name: str) -> None:
    append_function(
        found,
        span_node,
        body_node,
        target.data,
        name=name,
        namespace=target.module,
        path=target.path,
        language="vue",
        include_routes=False,
    )


def _is_callable(node) -> bool:
    if node is None or node.type not in _CALLBACKS:
        return False
    return node.type == "arrow_function" or has_body(node)


def _named_children(node) -> list:
    return [child for child in node.children if child.is_named and child.type != "comment"]


def _call_args(call) -> list:
    arguments = child_of_type(call, "arguments")
    return _named_children(arguments) if arguments is not None else []


def _member_name(data: bytes, member) -> str | None:
    ident = child_of_type(member, "property_identifier", "identifier")
    if ident is not None:
        return node_text(data, ident)
    text_node = child_of_type(member, "string")
    if text_node is not None:
        return literal_text(data, text_node)
    return None


def _named_members(data: bytes, obj):
    for member in obj.children:
        if member.type not in {"method_definition", "pair"}:
            continue
        key = _member_name(data, member)
        if key is not None:
            yield member, key


def _pair_value(member, *types: str):
    if member.type != "pair":
        return None
    value = unwrap_expression(member.child_by_field_name("value"))
    if value is None or (types and value.type not in types):
        return None
    return value


def _callback_body(member):
    if member.type == "method_definition":
        return member if has_body(member) else None
    value = _pair_value(member)
    return value if _is_callable(value) else None


def _append_member_fn(found: list, target: _Target, member, name: str) -> bool:
    body = _callback_body(member)
    if body is None:
        return False
    _record(found, member, body, target, name)
    return True


def _extract_accessors(found: list, target: _Target, obj, prefix: str) -> None:
    for member, key in _named_members(target.data, obj):
        if key in {"get", "set"}:
            _append_member_fn(found, target, member, f"{prefix}.{key}")


def _extract_methods(found: list, target: _Target, obj) -> None:
    for member, key in _named_members(target.data, obj):
        _append_member_fn(found, target, member, key)


def _extract_computed_object(found: list, target: _Target, obj) -> None:
    for member, key in _named_members(target.data, obj):
        if _append_member_fn(found, target, member, key):
            continue
        value = _pair_value(member, "object")
        if value is not None:
            _extract_accessors(found, target, value, key)


def _extract_watch_handler(found: list, target: _Target, obj, name: str) -> None:
    for member, key in _named_members(target.data, obj):
        if key == "handler":
            _append_member_fn(found, target, member, name)


def _extract_watch_array(found: list, target: _Target, array, name: str) -> None:
    for child in _named_children(array):
        item = unwrap_expression(child)
        if _is_callable(item):
            _record(found, item, item, target, name)
        elif item is not None and item.type == "object":
            _extract_watch_handler(found, target, item, name)


def _extract_watch_object(found: list, target: _Target, obj) -> None:
    for member, key in _named_members(target.data, obj):
        name = f"watch({key})"
        if _append_member_fn(found, target, member, name):
            continue
        value = _pair_value(member, "object", "array")
        if value is None:
            continue
        if value.type == "object":
            _extract_watch_handler(found, target, value, name)
        else:
            _extract_watch_array(found, target, value, name)


_OPTIONS_SECTIONS = {
    "methods": _extract_methods,
    "computed": _extract_computed_object,
    "watch": _extract_watch_object,
}


def _extract_options_object(found: list, target: _Target, obj) -> None:
    for member, key in _named_members(target.data, obj):
        if key in _OPTIONS_SKIP_KEYS or _append_member_fn(found, target, member, key):
            continue
        section = _OPTIONS_SECTIONS.get(key)
        if section is None:
            continue
        value = _pair_value(member, "object")
        if value is not None:
            section(found, target, value)


_COMPONENT_CALLS = frozenset(
    {
        (None, "defineComponent"),
        ("Vue", "defineComponent"),
        ("vue", "defineComponent"),
        ("Vue", "extend"),
        ("vue", "extend"),
    }
)
_VUE_RECEIVERS = frozenset({None, "Vue", "vue"})


def _callee_parts(data: bytes, call) -> tuple[str | None, str] | None:
    callee = unwrap_expression(call_callee(call))
    if callee is None:
        return None
    if callee.type == "identifier":
        return None, node_text(data, callee)
    if callee.type != "member_expression":
        return None
    obj = unwrap_expression(callee.child_by_field_name("object"))
    prop = property_name(data, callee)
    if obj is not None and obj.type == "identifier" and prop is not None:
        return node_text(data, obj), prop
    return None


def _is_component_call(data: bytes, call) -> bool:
    parts = _callee_parts(data, call)
    return parts is not None and parts in _COMPONENT_CALLS


def _extract_component_call(found: list, target: _Target, call) -> None:
    args = _call_args(call)
    if not args:
        return
    arg = unwrap_expression(args[0])
    if arg is None:
        return
    if arg.type == "object":
        _extract_options_object(found, target, arg)
    elif _is_callable(arg):
        _record(found, arg, arg, target, "setup")


def _export_default_expr(stmt):
    seen_default = False
    for child in stmt.children:
        if child.type == "default":
            seen_default = True
        elif seen_default and child.is_named and child.type != "comment":
            return unwrap_expression(child)
    return None


def _is_anonymous_callable(node) -> bool:
    if node.type == "arrow_function":
        return True
    return node.type == "function_expression" and child_of_type(node, "identifier") is None and has_body(node)


def _extract_export_default(found: list, target: _Target, stmt) -> None:
    exported = _export_default_expr(stmt)
    if exported is None:
        return
    if exported.type == "object":
        _extract_options_object(found, target, exported)
    elif exported.type == "call_expression" and _is_component_call(target.data, exported):
        _extract_component_call(found, target, exported)
    elif _is_anonymous_callable(exported):
        _record(found, exported, exported, target, "default")


def _extract_declaration_components(found: list, target: _Target, stmt) -> None:
    for declarator in stmt.children:
        if declarator.type != "variable_declarator":
            continue
        value = unwrap_expression(declarator.child_by_field_name("value"))
        if value is not None and value.type == "call_expression" and _is_component_call(target.data, value):
            _extract_component_call(found, target, value)


def _extract_expression_component(found: list, target: _Target, stmt) -> None:
    expr = next((c for c in stmt.children if c.is_named and c.type != "comment"), None)
    value = unwrap_expression(expr)
    if value is not None and value.type == "call_expression" and _is_component_call(target.data, value):
        _extract_component_call(found, target, value)


def _extract_options(found: list, target: _Target, root) -> None:
    for stmt in root.children:
        if stmt.type == "export_statement":
            _extract_export_default(found, target, stmt)
            decl = child_of_type(stmt, "lexical_declaration")
            if decl is not None:
                _extract_declaration_components(found, target, decl)
        elif stmt.type == "lexical_declaration":
            _extract_declaration_components(found, target, stmt)
        elif stmt.type == "expression_statement":
            _extract_expression_component(found, target, stmt)


def _composition_callee(data: bytes, call) -> str | None:
    parts = _callee_parts(data, call)
    if parts is None:
        return None
    receiver, name = parts
    return name if receiver in _VUE_RECEIVERS else None


def _computed_declarator(call):
    current = call.parent
    while current is not None and current.type in WRAPPERS:
        current = current.parent
    if current is None or current.type != "variable_declarator":
        return None, None
    ident = child_of_type(current, "identifier")
    if ident is None:
        return None, None
    return current, ident


def _extract_computed_call(found: list, target: _Target, call, arg0) -> None:
    arg = unwrap_expression(arg0)
    if arg is None:
        return
    declarator, ident = _computed_declarator(call)
    name = node_text(target.data, ident) if ident is not None else "computed"
    if _is_callable(arg):
        span_node = declarator if declarator is not None else arg
        _record(found, span_node, arg, target, name)
    elif arg.type == "object":
        _extract_accessors(found, target, arg, name)


def _getter_arrow_body(expr):
    params = child_of_type(expr, "formal_parameters")
    if params is None or any(child.is_named for child in params.children):
        return None
    body = unwrap_expression(expr.child_by_field_name("body"))
    if body is None or body.type == "statement_block":
        return None
    return body


def _single_line_text(data: bytes, node) -> str | None:
    text = node_text(data, node)
    if "\n" in text or "\r" in text:
        return None
    return text


def _bounded_single_line(data: bytes, node) -> str | None:
    text = _single_line_text(data, node)
    if text is None or len(text) > _MAX_WATCH_LABEL:
        return None
    return text


def _watch_atom(data: bytes, node) -> str | None:
    expr = unwrap_expression(node)
    if expr is not None and expr.type == "arrow_function":
        expr = _getter_arrow_body(expr)
    if expr is None or expr.type not in _WATCH_SIMPLE:
        return None
    return _bounded_single_line(data, expr)


def _array_watch_label(data: bytes, array) -> str | None:
    if _single_line_text(data, array) is None:
        return None
    children = _named_children(array)
    atoms = [atom for child in children if (atom := _watch_atom(data, child)) is not None]
    if not atoms or len(atoms) != len(children):
        return None
    joined = f"[{', '.join(atoms)}]"
    return joined if len(joined) <= _MAX_WATCH_LABEL else None


def _watch_label(data: bytes, arg0) -> str | None:
    expr = unwrap_expression(arg0)
    if expr is None:
        return None
    if expr.type == "array":
        return _array_watch_label(data, expr)
    return _watch_atom(data, expr)


def _extract_watch_call(found: list, target: _Target, args: list) -> None:
    if len(args) < 2:
        return
    cb = unwrap_expression(args[1])
    if not _is_callable(cb):
        return
    label = _watch_label(target.data, args[0])
    _record(found, cb, cb, target, f"watch({label})" if label else "watch")


def _extract_effect_call(found: list, target: _Target, hook: str, arg0) -> None:
    cb = unwrap_expression(arg0)
    if _is_callable(cb):
        _record(found, cb, cb, target, hook)


def _extract_composition_call(found: list, target: _Target, call) -> None:
    callee_name = _composition_callee(target.data, call)
    if callee_name is None:
        return
    args = _call_args(call)
    if not args:
        return
    if callee_name == "computed":
        _extract_computed_call(found, target, call, args[0])
    elif callee_name == "watch":
        _extract_watch_call(found, target, args)
    elif callee_name in _EFFECT_HOOKS:
        _extract_effect_call(found, target, callee_name, args[0])


def _extract_composition(found: list, target: _Target, root) -> None:
    for node in descendants(root):
        if node.type == "call_expression" and not inside_function(node):
            _extract_composition_call(found, target, node)


def _dedupe_names(found: list[tuple[int, Function]]) -> list[Function]:
    seen_spans: set[tuple[int, int]] = set()
    used_by_ns: dict[str, set[str]] = {}
    unique: list[Function] = []
    for _start, fn in sorted(found, key=lambda item: (item[0], item[1].end_byte)):
        span = (fn.start_byte, fn.end_byte)
        if span in seen_spans:
            continue
        seen_spans.add(span)
        used = used_by_ns.setdefault(fn.namespace, set())
        chosen = claim_name(used, fn.name)
        unique.append(fn if chosen == fn.name else replace(fn, name=chosen))
    return unique


def functions_in_source(
    source: str, path: str, source_root: str | None = None
) -> list[Function]:
    data, blocks = extract_script_blocks(source)
    if not blocks:
        return []
    target = _Target(data=data, module=_vue_namespace(path, source_root), path=path)
    found: list[tuple[int, Function]] = []
    for block in blocks:
        tree = parse_range(data, block.grammar, block.span)
        found.extend(
            extract_tree_functions(
                data, tree.root_node, target.module, path, language="vue", include_routes=False
            )
        )
        _extract_options(found, target, tree.root_node)
        _extract_composition(found, target, tree.root_node)
    return _dedupe_names(found)
