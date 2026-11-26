"""Swift functions, methods, and cyclomatic complexity.

Decision points follow the same structural rule as the other languages:
`if`, `guard`, `for` / `while` / `repeat-while`, each `catch`, `?:`, each
`switch` case (including `default`), `&&` / `||`, `??`, and optional
chaining (`a?.b`, `a?[i]`, `a?()`).

These are not decisions. `try`, `try?`, and `try!` are not branches.
`as?`, `as!`, and `is` are not branches. A `where` clause belongs to the
case, loop, or type constraint it narrows, so it is not a second decision.
One `if` or `guard` is one decision even when it lists several conditions;
each `else if` is another `if`. `case 1, 2` is one case. `#if` is compile
time; a `&&` inside the directive is not a branch, and each runtime `if`
the grammar still parses is. `?` on an optional type (`Int?`) or a failable
`init?` is not a chain. Operators inside strings and comments are not
branches; an interpolated expression is.

A top-level function, a method, an initializer, a deinitializer, a
subscript, and a computed property or property observer are entries.
`get`, `set`, `willSet`, and `didSet` stay inside that entry. A
requirement or accessor with no statements, such as `{ get set }`, is
not an entry. A closure
bound directly with `let` or `var` is an entry, at file scope or on a type.
Any other closure stays inside the enclosing function, the way a nested
callback stays inside its function in TypeScript. A local type's methods
are their own entries and are not also charged to the enclosing function.

The namespace is the module, or `Module.Type` for a member. The module is
the SwiftPM target whose path contains the file, otherwise the directory
under `Sources/`, otherwise the nearest `.xcodeproj` or `.xcworkspace`
name, otherwise the dotted directory path with `src/` removed. Nested
types keep each owner (`Module.Outer.Inner`). An extension uses the
extended type (`Module.Box.Inner`, `Module.Array`).
"""

from __future__ import annotations

import re
from pathlib import Path

from crapper.languages.treesitter import (
    absolute_path,
    child_of_type,
    child_text,
    complexity,
    descendants,
    end_line,
    node_text,
    parse,
    start_line,
)
from crapper.runners import nearest_marker
from crapper.model import Function

_DECISIONS = {
    "if_statement",
    "guard_statement",
    "for_statement",
    "while_statement",
    "repeat_while_statement",
    "catch_block",
    "ternary_expression",
    "switch_entry",
    "conjunction_expression",
    "disjunction_expression",
    "nil_coalescing_expression",
}
# `?` is also the optional-type suffix, the ternary operator, `try?`, and `init?`.
_NOT_CHAIN = {"optional_type", "ternary_expression", "try_operator", "init_declaration", "?"}
_SKIP = {"class_declaration", "protocol_declaration"}
_FUNCTIONS = {
    "function_declaration",
    "protocol_function_declaration",
    "init_declaration",
    "deinit_declaration",
}
_CONTAINERS = _FUNCTIONS | {
    "subscript_declaration",
    "lambda_literal",
    "computed_property",
    "computed_getter",
    "computed_setter",
    "computed_modify",
    "willset_clause",
    "didset_clause",
}
_TYPES = {"class_declaration", "protocol_declaration"}
_FIXED_NAMES = {
    "init_declaration": "init",
    "deinit_declaration": "deinit",
    "subscript_declaration": "subscript",
}
_TARGET_MARKERS = (".target(", ".executableTarget(")
_FIELD = re.compile(r'{name}:\s*"([^"]+)"')


def _is_decision(node) -> bool:
    if node.type in _DECISIONS:
        return True
    if node.type != "?":
        return False
    parent = node.parent
    return parent is not None and parent.type not in _NOT_CHAIN


def _skip_nested_type(node, root_id: int):
    def skip(current) -> bool:
        if current.id == root_id:
            return False
        return current.type in _SKIP

    return skip


def _complexity_of(node) -> int:
    return complexity(node, _is_decision, _skip_nested_type(node, node.id))


def _is_nested(node) -> bool:
    current = node.parent
    while current is not None:
        if current.type in _TYPES:
            return False
        if current.type in _CONTAINERS:
            return True
        current = current.parent
    return False


def _function_name(data: bytes, node) -> str | None:
    fixed = _FIXED_NAMES.get(node.type)
    if fixed is not None:
        return fixed
    children = node.children
    for index, child in enumerate(children):
        if child.type == "func":
            return node_text(data, children[index + 1])
    return None


def _binding_name(data: bytes, node) -> str | None:
    pattern = child_of_type(node, "pattern")
    if pattern is None:
        return None
    return child_text(data, pattern, "simple_identifier")


def _has_function_body(node) -> bool:
    return child_of_type(node, "function_body") is not None


def _direct_lambda(node):
    for child in node.children:
        if child.type == "lambda_literal":
            return child
    return None


def _has_statements(node) -> bool:
    if node.type == "statements":
        return True
    return any(_has_statements(child) for child in node.children)


def _property_is_entry(node) -> bool:
    if _direct_lambda(node) is not None:
        return True
    accessor = child_of_type(node, "computed_property", "willset_didset_block")
    if accessor is None:
        return False
    return _has_statements(accessor)


def _type_identifiers(data: bytes, node) -> list[str]:
    return [node_text(data, child) for child in node.children if child.type == "type_identifier"]


def _type_name(data: bytes, node) -> str | None:
    user = child_of_type(node, "user_type")
    if user is not None:
        parts = _type_identifiers(data, user)
        if parts:
            return ".".join(parts)
    ident = child_of_type(node, "type_identifier")
    if ident is None:
        return None
    return node_text(data, ident)


def _owner_types(data: bytes, node) -> list[str]:
    names: list[str] = []
    current = node.parent
    while current is not None:
        if current.type in _TYPES:
            name = _type_name(data, current)
            if name:
                names.append(name)
        current = current.parent
    names.reverse()
    return names


def _namespace(module: str, data: bytes, node) -> str:
    owners = _owner_types(data, node)
    if not owners:
        return module
    if not module:
        return ".".join(owners)
    return f"{module}.{'.'.join(owners)}"


def _make(node, name: str, namespace: str, path: str) -> Function:
    return Function(
        name=name,
        namespace=namespace,
        complexity=_complexity_of(node),
        start_line=start_line(node),
        end_line=end_line(node),
        path=path,
        language="swift",
        start_byte=node.start_byte,
        end_byte=node.end_byte,
    )


def _record_function(data: bytes, node, module: str, path: str) -> Function | None:
    if not _has_function_body(node) or _is_nested(node):
        return None
    name = _function_name(data, node)
    if name is None:
        return None
    return _make(node, name, _namespace(module, data, node), path)


def _record_subscript(data: bytes, node, module: str, path: str) -> Function | None:
    if _is_nested(node) or not _has_statements(node):
        return None
    return _make(node, "subscript", _namespace(module, data, node), path)


def _record_property(data: bytes, node, module: str, path: str) -> Function | None:
    if _is_nested(node) or not _property_is_entry(node):
        return None
    name = _binding_name(data, node)
    if name is None:
        return None
    return _make(node, name, _namespace(module, data, node), path)


def _recorded(data: bytes, node, module: str, path: str) -> Function | None:
    if node.type in _FUNCTIONS:
        return _record_function(data, node, module, path)
    if node.type == "subscript_declaration":
        return _record_subscript(data, node, module, path)
    if node.type == "property_declaration":
        return _record_property(data, node, module, path)
    return None


def _parts(path: str) -> list[str]:
    return [part for part in path.replace("\\", "/").split("/") if part and part != "."]


def _sources_name(parts: list[str]) -> str | None:
    if "Sources" not in parts:
        return None
    index = parts.index("Sources")
    if index + 1 >= len(parts) - 1:
        return None
    return parts[index + 1]


def _directory_module(path: str, project_root: str | None) -> str:
    sources = _sources_name(_parts(path))
    if sources:
        return sources
    dirs = _parts(path)[:-1]
    if dirs[:1] == ["src"]:
        dirs = dirs[1:]
    if dirs:
        return ".".join(dirs)
    if project_root:
        return Path(project_root).name
    return Path(path).stem


def _balanced(text: str, open_at: int) -> str:
    depth = 0
    for index in range(open_at, len(text)):
        depth += _paren_delta(text[index])
        if depth == 0:
            return text[open_at : index + 1]
    return ""


def _paren_delta(char: str) -> int:
    if char == "(":
        return 1
    if char == ")":
        return -1
    return 0


def _target_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    for marker in _TARGET_MARKERS:
        start = 0
        while True:
            index = text.find(marker, start)
            if index < 0:
                break
            blocks.append(_balanced(text, index + len(marker) - 1))
            start = index + len(marker)
    return blocks


def _field(block: str, name: str) -> str | None:
    match = _FIELD.pattern
    found = re.search(match.format(name=name), block)
    if found is None:
        return None
    return found.group(1)


def _package_targets(text: str) -> list[tuple[str, str | None]]:
    found = []
    for block in _target_blocks(text):
        if not block.endswith(")"):
            continue
        name = _field(block, "name")
        if name:
            found.append((name, _field(block, "path")))
    return found


def _inside(file: Path, root: Path) -> bool:
    try:
        file.relative_to(root)
    except ValueError:
        return False
    return True


def _best_target(package_dir: Path, file: Path, targets: list[tuple[str, str | None]]) -> str | None:
    found = []
    resolved = file.resolve()
    for index, (name, explicit) in enumerate(targets):
        if not explicit:
            continue
        if not _inside(resolved, (package_dir / explicit).resolve()):
            continue
        found.append((len(Path(explicit).parts), -index, name))
    if not found:
        return None
    return max(found)[2]


def _target_for(package_dir: Path, file: Path) -> str | None:
    manifest = package_dir / "Package.swift"
    if not manifest.is_file():
        return None
    text = manifest.read_text(encoding="utf-8", errors="replace")
    return _best_target(package_dir, file, _package_targets(text))


def _project_name(directory: Path) -> str | None:
    for pattern in ("*.xcodeproj", "*.xcworkspace"):
        matches = sorted(directory.glob(pattern))
        if matches:
            return matches[0].stem
    return None


def _xcode_name(start: Path, stop: Path) -> str | None:
    current = start if start.is_dir() else start.parent
    stop = stop.resolve()
    while True:
        name = _project_name(current)
        if name:
            return name
        if current == stop or current.parent == current:
            return None
        current = current.parent


def _module_from_disk(path: str, project_root: str) -> str | None:
    file_path = Path(absolute_path(path, project_root))
    stop = Path(project_root).resolve()
    package = nearest_marker(file_path, "Package.swift", stop)
    if package is not None:
        target = _target_for(package, file_path)
        if target:
            return target
    if _sources_name(_parts(path)):
        return _sources_name(_parts(path))
    return _xcode_name(file_path, stop)


def _module_name(path: str, project_root: str | None) -> str:
    if project_root:
        found = _module_from_disk(path, project_root)
        if found:
            return found
    return _directory_module(path, project_root)


def functions_in_source(
    source: str, path: str, source_root: str | None = None
) -> list[Function]:
    data, tree = parse(source, "swift")
    module = _module_name(path, source_root)
    found: list[Function] = []
    for node in descendants(tree.root_node):
        recorded = _recorded(data, node, module, path)
        if recorded is not None:
            found.append(recorded)
    return found
