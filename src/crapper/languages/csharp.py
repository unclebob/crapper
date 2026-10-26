"""C# executable bodies and McCabe complexity, without requiring a .NET SDK.

Nested local functions and lambdas are separate entries and own their decisions.
Namespaces follow C# namespaces/types, including file-scoped namespaces and records.
Compiler-generated auto accessors and primary constructors have no source body.
"""

from crapper.languages.treesitter import child_of_type, end_line, node_text, parse, start_line
from crapper.model import Function

_TYPES = {"class_declaration", "struct_declaration", "interface_declaration", "record_declaration"}
_EXECUTABLES = {
    "method_declaration", "constructor_declaration", "destructor_declaration",
    "operator_declaration", "conversion_operator_declaration", "accessor_declaration",
    "local_function_statement", "lambda_expression", "anonymous_method_expression",
}
_DECISIONS = {
    "if_statement", "for_statement", "foreach_statement", "while_statement",
    "do_statement", "catch_clause", "catch_filter_clause", "when_clause",
    "conditional_expression", "conditional_access_expression",
}


def _body(node):
    if node.type in _EXECUTABLES:
        return node.child_by_field_name("body") or child_of_type(node, "block", "arrow_expression_clause")
    if node.type in {"property_declaration", "indexer_declaration"}:
        return child_of_type(node, "arrow_expression_clause")
    return None


def _field_text(data, node, field):
    child = node.child_by_field_name(field)
    return node_text(data, child) if child is not None else ""


def _constructor_label(data, node):
    static = any(node_text(data, child) == "static" for child in node.children if child.type == "modifier")
    return ".cctor" if static else ".ctor"


def _operator_label(data, node):
    value = _field_text(data, node, "operator") or _field_text(data, node, "type")
    checked = "checked " if any(child.type == "checked" for child in node.children) else ""
    return "operator " + checked + value


def _accessor_label(data, node):
    keyword = next((child.type for child in node.children if child.type in {"get", "set", "init", "add", "remove"}), "accessor")
    owner = node.parent.parent
    return keyword + "_" + (_field_text(data, owner, "name") or "this[]")


def _anonymous_label(_data, node):
    return f"lambda@{start_line(node)}:{node.start_point[1]}"


def _property_label(data, node):
    return "get_" + (_field_text(data, node, "name") or "this[]")


def _label(data, node):
    labels = {
        "constructor_declaration": _constructor_label,
        "destructor_declaration": lambda _data, _node: ".dtor",
        "operator_declaration": _operator_label,
        "conversion_operator_declaration": _operator_label,
        "lambda_expression": _anonymous_label,
        "anonymous_method_expression": _anonymous_label,
        "accessor_declaration": _accessor_label,
        "property_declaration": _property_label,
        "indexer_declaration": _property_label,
    }
    label = labels.get(node.type)
    return label(data, node) if label else _field_text(data, node, "name")


def _identity(data, node, file_namespace):
    namespaces, types, executables = [], [], []
    current = node
    while current is not None:
        if current.type == "namespace_declaration":
            namespaces.append(_field_text(data, current, "name"))
        if current.type in _TYPES:
            types.append(_field_text(data, current, "name"))
        if current == node or current.type in _EXECUTABLES:
            executables.append(_label(data, current))
        current = current.parent
    prefix = ([file_namespace] if file_namespace else []) + list(reversed(namespaces))
    namespace = ".".join(prefix + list(reversed(types))) or "Program"
    return namespace, ".".join(reversed(executables))


def _decision(node):
    if node.type in _DECISIONS:
        return True
    if node.type == "switch_expression_arm":
        return not any(child.type == "discard" for child in node.children)
    if node.type == "switch_section":
        return any(child.type == "case" for child in node.children)
    if node.type in {"binary_expression", "assignment_expression"}:
        return any(child.type in {"&&", "||", "??", "??="} for child in node.children)
    return node.type in {"and_pattern", "or_pattern"}


def _complexity(body):
    score = 1
    stack = [body]
    while stack:
        node = stack.pop()
        if node.type in _EXECUTABLES or node.type in _TYPES:
            continue
        if _decision(node):
            score += 1
        stack.extend(reversed(node.children))
    return score


def _member_complexity(node, body):
    initializer = child_of_type(node, "constructor_initializer")
    initial_decisions = _complexity(initializer) - 1 if initializer is not None else 0
    return _complexity(body) + initial_decisions


def functions_in_source(source: str, path: str, project_root: str | None = None) -> list[Function]:
    del project_root
    data, tree = parse(source, "csharp")
    if tree.root_node.has_error:
        raise ValueError(f"C# syntax could not be parsed: {path}")
    scoped = child_of_type(tree.root_node, "file_scoped_namespace_declaration")
    file_namespace = _field_text(data, scoped, "name") if scoped is not None else ""
    found = []
    globals_ = [node for node in tree.root_node.children if node.type == "global_statement"]
    if globals_:
        found.append(Function(
            name="<Main>$", namespace="Program", complexity=1 + sum(_complexity(node) - 1 for node in globals_),
            start_line=start_line(globals_[0]), end_line=end_line(globals_[-1]), path=path,
            language="csharp", start_byte=globals_[0].start_byte, end_byte=globals_[-1].end_byte,
        ))
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        body = _body(node)
        if body is not None:
            namespace, name = _identity(data, node, file_namespace)
            found.append(Function(
                name=name, namespace=namespace, complexity=_member_complexity(node, body),
                start_line=start_line(node), end_line=end_line(node), path=path,
                language="csharp", start_byte=node.start_byte, end_byte=node.end_byte,
            ))
        stack.extend(reversed(node.children))
    return found
