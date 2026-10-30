"""Haskell bindings and cyclomatic complexity.

Top-level bindings and class or instance methods are scored. Adjacent pattern
equations with the same name form one entry. Decisions are guarded right-hand
sides and pattern guards, ``if``, each ``case``/``\\case`` alternative,
list-comprehension boolean qualifiers, and ``&&`` / ``||``. Every additional
equation is another path. Local bindings stay inside their owning entry.
"""

from pathlib import Path

from crapper.languages.treesitter import descendants, end_line, node_text, parse, start_line
from crapper.model import Function

_DECLARATION_PARENTS = {"declarations", "class_declarations", "instance_declarations"}
_DEFINITION_NODES = {"function", "bind"}


def _operator(data: bytes, node) -> str | None:
    for child in descendants(node):
        if child.type in {"operator", "constructor_operator"}:
            return node_text(data, child)
    return None


def _definition_name(data: bytes, node) -> str | None:
    for child in node.named_children:
        if child.type == "variable":
            return node_text(data, child)
        if child.type in {"prefix_id", "infix"}:
            return _operator(data, child)
    return None


def _module_header(data: bytes, root) -> str | None:
    for child in root.named_children:
        if child.type != "header":
            continue
        for part in child.named_children:
            if part.type == "module":
                return node_text(data, part)
    return None


def _fallback_module(path: str, project_root: str | None) -> str:
    normalized = path.replace("\\", "/")
    if project_root:
        try:
            normalized = Path(path).resolve().relative_to(Path(project_root).resolve()).as_posix()
        except ValueError:
            pass
    if "/src/" in normalized:
        normalized = normalized.split("/src/", 1)[1]
    elif normalized.startswith("src/"):
        normalized = normalized[4:]
    if normalized.endswith(".hs"):
        normalized = normalized[:-3]
    return normalized.strip("/").replace("/", ".") or "Main"


def _instance_name(data: bytes, owner) -> str | None:
    head = [
        node_text(data, child)
        for child in owner.named_children
        if child.type in {"name", "type_patterns"}
    ]
    return " ".join(head) or None


def _class_name(data: bytes, owner) -> str | None:
    for child in owner.named_children:
        if child.type == "name":
            return node_text(data, child)
    return None


def _owner_namespace(data: bytes, node, module: str) -> str:
    parent = node.parent
    owner = parent.parent if parent is not None else None
    if owner is None:
        return module
    extra = None
    if parent.type == "instance_declarations":
        extra = _instance_name(data, owner)
    elif parent.type == "class_declarations":
        extra = _class_name(data, owner)
    if extra:
        return ".".join((module, extra))
    return module


def _is_definition(node) -> bool:
    return (
        node.type in _DEFINITION_NODES
        and node.parent is not None
        and node.parent.type in _DECLARATION_PARENTS
    )


def _is_logic_operator(data: bytes, node) -> bool:
    return node.type == "infix" and any(
        child.type in {"operator", "constructor_operator"}
        and node_text(data, child) in {"&&", "||"}
        for child in node.named_children
    )


def _decision_count(data: bytes, node) -> int:
    decisions = {"boolean", "pattern_guard", "conditional", "alternative"}
    return sum(
        1
        for child in descendants(node)
        if child.type in decisions or _is_logic_operator(data, child)
    )


def _local_extra_equations(data: bytes, equations: list) -> int:
    groups: dict[tuple[int, str], int] = {}
    roots = {node.id for node in equations}
    for equation in equations:
        for child in descendants(equation):
            if child.id in roots or child.type != "function":
                continue
            if child.parent is None or child.parent.type != "local_binds":
                continue
            name = _definition_name(data, child)
            if name is None:
                continue
            key = (child.parent.id, name)
            groups[key] = groups.get(key, 0) + 1
    return sum(max(0, count - 1) for count in groups.values())


def _complexity(data: bytes, equations: list) -> int:
    return (
        1
        + max(0, len(equations) - 1)
        + sum(_decision_count(data, equation) for equation in equations)
        + _local_extra_equations(data, equations)
    )


def functions_in_source(
    source: str, path: str, project_root: str | None = None
) -> list[Function]:
    data, tree = parse(source, "haskell")
    module = _module_header(data, tree.root_node) or _fallback_module(path, project_root)
    groups: dict[tuple[str, str], list] = {}
    for node in descendants(tree.root_node):
        if not _is_definition(node):
            continue
        name = _definition_name(data, node)
        if name is None:
            continue
        namespace = _owner_namespace(data, node, module)
        groups.setdefault((namespace, name), []).append(node)

    found: list[Function] = []
    for (namespace, name), equations in groups.items():
        first = equations[0]
        last = equations[-1]
        found.append(
            Function(
                name=name,
                namespace=namespace,
                complexity=_complexity(data, equations),
                start_line=start_line(first),
                end_line=end_line(last),
                path=path,
                language="haskell",
                start_byte=first.start_byte,
                end_byte=last.end_byte,
            )
        )
    return found
