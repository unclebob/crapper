"""Swift functions and cyclomatic complexity.

Decision points are `if`, `guard`, `for`, `while`, `repeat ... while`, each
`switch` case except `default`, each `catch`, each `&&`, `||`, `??`, ternary
`? :`, and optional chaining `?.`, each comma between the conditions of an
`if`, `guard`, or `while`, and a `where` clause on a `for`, `case`, or
`catch`. A `case .a, .b:` counts once; `try?`, `as?`, and `init?` add nothing.
One `?` token serves all of those, and `,` also separates parameters and
patterns, so each is told apart by its parent node.

Entries are functions, initializers (`init`), `deinit`, and `subscript` with a
body, and properties with a body: computed properties (getter and setter are
one entry), `willSet`/`didSet` observers, and a property initialised by a
closure. Functions nested in another entry and closures stay in the enclosing
entry. The namespace is the module, the folder after `Sources/` in the file's
absolute path, then the chain of enclosing types; an extension counts as the
type it extends, and an extension of `[T]`, `[K: V]`, or `T?` as `Array`,
`Dictionary`, or `Optional`. Without `Sources/<Module>/` it is the type chain
alone, and a top-level function takes the module, or the file stem.
"""

import re
from pathlib import Path

from crapper.languages.treesitter import (
    absolute_path,
    child_of_type,
    complexity,
    end_line,
    node_text,
    parse,
    start_line,
)
from crapper.model import Function

# The grammar rejects the empty tuple as an argument, `.success(())`.
_EMPTY_TUPLE_ARGUMENT = "(())"
_EMPTY_TUPLE_PLACEHOLDER = "(0 )"
# An initializer's signature, up to its opening parenthesis. A call such as
# `self.init(` or `.init(` is not one.
_INIT_SIGNATURE = re.compile(r"(?<![.\w])init[?!]?\s*(?:<[^<>{}()]*>\s*)?\(")
_INIT_EFFECTS = re.compile(r"\s*(?:(?:async|rethrows|throws(?:\s*\([^()]*\))?)\s*)*")
# A `where` clause up to the body's brace, crossing no other declaration.
_INIT_WHERE = re.compile(
    r"where\b(?:(?!\b(?:func|var|let|init|subscript|typealias|associatedtype|case)\b)[^{};])*(?=\{)"
)

_TYPES = {"class_declaration", "protocol_declaration"}
_NESTING = {"lambda_literal"}
_STATEMENTS = {
    "if_statement",
    "guard_statement",
    "for_statement",
    "while_statement",
    "repeat_while_statement",
    "catch_block",
}
_CONDITION_LISTS = {"if_statement", "guard_statement", "while_statement"}
_OPERATORS = {
    "&&": "conjunction_expression",
    "||": "disjunction_expression",
    "??": "nil_coalescing_expression",
}
_QUESTION_PARENTS = {"ternary_expression", "navigation_expression", "call_expression"}
_WHERE_PARENTS = {"for_statement", "catch_block"}
_PROPERTY_BODIES = {"computed_property", "willset_didset_block"}
# The standard library type behind each sugared type an extension can name.
_SUGARED_TYPES = {"array_type": "Array", "dictionary_type": "Dictionary", "optional_type": "Optional"}


def _blank(text: str) -> str:
    return re.sub(r"[^\n]", " ", text)


def _string_end(source: str, start: int, hashes: int) -> int:
    """The index after the string literal whose opening quote is at `start`.

    A raw string, opened with `hashes` `#`s, has no escapes and ends at a quote
    followed by as many `#`s. A single-line string also ends at a newline, so
    an unmatched quote cannot run on.
    """

    quote = '"""' if source.startswith('"""', start) else '"'
    closing = quote + "#" * hashes
    index = start + len(quote)
    while index < len(source):
        if source[index] == "\\" and not hashes:
            index += 2
        elif source.startswith(closing, index):
            return index + len(closing)
        elif source[index] == "\n" and quote == '"':
            return index
        else:
            index += 1
    return index


def _skipped(source: str, index: int) -> int | None:
    """The index after the comment or string literal starting at `index`, if one does."""

    if source.startswith("//", index):
        end = source.find("\n", index)
        return len(source) if end < 0 else end
    if source.startswith("/*", index):
        end = source.find("*/", index + 2)
        return len(source) if end < 0 else end + 2
    quote = index
    while quote < len(source) and source[quote] == "#":
        quote += 1
    if quote < len(source) and source[quote] == '"':
        return _string_end(source, quote, quote - index)
    return None


def _close_paren(source: str, start: int) -> int:
    """The index after the parenthesis that closes the one before `start`,
    skipping comments and string literals such as a default argument's."""

    depth = 1
    index = start
    while index < len(source) and depth:
        skipped = _skipped(source, index)
        if skipped is not None:
            index = skipped
            continue
        if source[index] == "(":
            depth += 1
        elif source[index] == ")":
            depth -= 1
        index += 1
    return index


def _without_init_where_clauses(source: str) -> str:
    """Blank each initializer's `where` clause, keeping every byte and line."""

    pieces: list[str] = []
    done = 0
    for found in _INIT_SIGNATURE.finditer(source):
        if found.start() < done:
            continue
        after = _close_paren(source, found.end())
        effects = _INIT_EFFECTS.match(source, after)
        where = _INIT_WHERE.match(source, effects.end())
        if where is None:
            continue
        pieces.append(source[done : where.start()])
        pieces.append(_blank(where.group(0)))
        done = where.end()
    pieces.append(source[done:])
    return "".join(pieces)


def _prepared(source: str) -> str:
    """Work around two constructs the grammar rejects."""

    source = source.replace(_EMPTY_TUPLE_ARGUMENT, _EMPTY_TUPLE_PLACEHOLDER)
    return _without_init_where_clauses(source)


def _parent_type(node) -> str | None:
    return node.parent.type if node.parent is not None else None


def _is_decision(node) -> bool:
    kind = node.type
    if kind in _STATEMENTS:
        return True
    parent = _parent_type(node)
    if kind == "switch_entry":
        return child_of_type(node, "default_keyword") is None
    if kind in _OPERATORS:
        return parent == _OPERATORS[kind]
    if kind == "?":
        return parent in _QUESTION_PARENTS
    if kind == ",":
        return parent in _CONDITION_LISTS
    if kind == "where_clause":
        return parent in _WHERE_PARENTS
    if kind == "where_keyword":
        return parent == "switch_entry"
    return False


def _skip(_node) -> bool:
    return False


def _type_name(data: bytes, node) -> str | None:
    if child_of_type(node, "extension") is not None:
        extended = child_of_type(node, "user_type")
        if extended is None:
            sugared = (_SUGARED_TYPES.get(child.type) for child in node.children)
            return next((name for name in sugared if name), None)
        names = [node_text(data, part) for part in extended.children if part.type == "type_identifier"]
        return ".".join(names) or None
    ident = child_of_type(node, "type_identifier")
    return node_text(data, ident) if ident is not None else None


def _type_chain(data: bytes, node) -> list[str]:
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


def _module(path: str, project_root: str | None) -> str | None:
    """The folder after the last `Sources` folder in the file's absolute path."""

    folders = Path(absolute_path(path, project_root)).parts[:-1]
    for index in range(len(folders) - 2, -1, -1):
        if folders[index] == "Sources":
            return folders[index + 1]
    return None


def _is_closure_value(node) -> bool:
    if node.type == "lambda_literal":
        return True
    return node.type == "call_expression" and child_of_type(node, "lambda_literal") is not None


def _property_name(data: bytes, node) -> str | None:
    """The property's name when its declaration has a body."""

    has_body = any(
        child.type in _PROPERTY_BODIES or _is_closure_value(child) for child in node.children
    )
    pattern = child_of_type(node, "pattern")
    ident = child_of_type(pattern, "simple_identifier") if pattern is not None else None
    if not has_body or ident is None:
        return None
    return node_text(data, ident)


def _entry_name(data: bytes, node) -> str | None:
    kind = node.type
    if kind == "function_declaration":
        ident = child_of_type(node, "simple_identifier")
        if ident is None or child_of_type(node, "function_body") is None:
            return None
        return node_text(data, ident)
    if kind == "init_declaration":
        return "init" if child_of_type(node, "function_body") is not None else None
    if kind == "deinit_declaration":
        return "deinit" if child_of_type(node, "function_body") is not None else None
    if kind == "subscript_declaration":
        return "subscript" if child_of_type(node, "computed_property") is not None else None
    if kind == "property_declaration":
        return _property_name(data, node)
    return None


class _Reader:
    def __init__(self, data: bytes, path: str, module: str | None):
        self.data = data
        self.path = path
        self.module = module
        self.found: list[Function] = []

    def _namespace(self, chain: list[str]) -> str:
        if chain:
            return ".".join([self.module, *chain] if self.module else chain)
        return self.module or Path(self.path).stem

    def read(self, node, name: str) -> None:
        self.found.append(
            Function(
                name=name,
                namespace=self._namespace(_type_chain(self.data, node)),
                complexity=complexity(node, _is_decision, _skip),
                start_line=start_line(node),
                end_line=end_line(node),
                path=self.path,
                language="swift",
            )
        )


def functions_in_source(
    source: str, path: str, project_root: str | None = None
) -> list[Function]:
    data, tree = parse(_prepared(source), "swift")
    reader = _Reader(data, path, _module(path, project_root))
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        name = _entry_name(data, node)
        if name is not None:
            reader.read(node, name)
            continue
        if node.type in _NESTING:
            continue
        stack.extend(reversed(node.children))
    return reader.found
