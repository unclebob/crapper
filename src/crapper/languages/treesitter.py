"""Shared tree-sitter helpers for Java, Go, TypeScript, Rust, Python, and Swift."""

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=None)
def parser_for(language: str):
    from tree_sitter_language_pack import download, get_parser

    download([language])
    return get_parser(language)


def parse(source: str, language: str):
    data = source.encode("utf-8")
    tree = parser_for(language).parse(data)
    return data, tree


def node_text(data: bytes, node) -> str:
    return data[node.start_byte : node.end_byte].decode("utf-8")


def start_line(node) -> int:
    return node.start_point[0] + 1


def end_line(node) -> int:
    row, col = node.end_point
    if col == 0:
        return max(start_line(node), row)
    return row + 1


def child_of_type(node, *types: str):
    for child in node.children:
        if child.type in types:
            return child
    return None


def child_text(data: bytes, node, *types: str) -> str | None:
    ident = child_of_type(node, *types)
    if ident is None:
        return None
    return node_text(data, ident)


def strip_root(relative: str, source_root: str | None) -> str:
    root = (source_root or "").replace("\\", "/").rstrip("/")
    if root and root != "." and relative.startswith(root + "/"):
        return relative[len(root) + 1 :]
    if relative.startswith("./"):
        return relative[2:]
    return relative


def strip_src(relative: str) -> str:
    if relative.startswith("src/"):
        return relative[4:]
    if "/src/" in relative:
        return relative.split("/src/", 1)[1]
    return relative


def ancestor_names(data: bytes, node, kind: str, *name_types: str) -> list[str]:
    names: list[str] = []
    current = node.parent
    while current is not None:
        if current.type == kind:
            ident = child_of_type(current, *name_types)
            if ident is not None:
                names.append(node_text(data, ident))
        current = current.parent
    names.reverse()
    return names


def descendants(node):
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.children))


def absolute_path(path: str, project_root: str | None) -> str:
    file_path = Path(path)
    if file_path.is_absolute():
        return str(file_path)
    if project_root:
        return str((Path(project_root) / file_path).resolve())
    return str(file_path.resolve())


def complexity(node, is_decision, skip) -> int:
    """McCabe complexity of `node`: 1 plus each decision in the subtree.

    The walk is a stack, not recursion. A generated expression can be deeper
    than Python's call limit.
    """

    score = 1
    stack = [node]
    while stack:
        current = stack.pop()
        if skip(current):
            continue
        if is_decision(current):
            score += 1
        stack.extend(reversed(current.children))
    return score


def binary_logic(node) -> bool:
    return node.type == "binary_expression" and any(
        child.type in {"&&", "||"} for child in node.children
    )
