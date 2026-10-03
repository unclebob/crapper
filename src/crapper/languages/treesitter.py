from collections.abc import Callable, Iterator, Sequence, Set
from functools import cache
from itertools import takewhile

from tree_sitter import Node, Parser, Query, QueryCursor
from tree_sitter_language_pack import SupportedLanguage, get_language

from crapper.model import Function, Model, Source, Span, grouped


@cache
def _query(grammar: SupportedLanguage, pattern: str) -> Query:
    return Query(get_language(grammar), pattern)


def find(grammar: SupportedLanguage, node: Node, pattern: str) -> list[Node]:
    return QueryCursor(_query(grammar, pattern)).captures(node).get("found", [])


def text(node: Node) -> str:
    assert node.text is not None
    return node.text.decode()


def span(node: Node) -> Span:
    (first_row, _), (last_row, last_column) = node.start_point, node.end_point
    return Span(
        start=first_row + 1,
        end=max(first_row + 1, last_row + 1 if last_column else last_row),
    )


def ancestors(node: Node) -> Iterator[Node]:
    while (parent := node.parent) is not None:
        yield (node := parent)


def enclosing(node: Node, kinds: Set[str]) -> list[str]:
    return [
        text(name)
        for ancestor in reversed([*ancestors(node)])
        if ancestor.type in kinds and (name := ancestor.child_by_field_name("name"))
    ]


def unscoped(_: Node) -> Sequence[str]:
    return ()


def one(_: Node) -> int:
    return 1


def named(_: Node, name: Node) -> str:
    return text(name)


def _owners(decision: Node, opaque: Set[int], sealed: Set[int]) -> Iterator[Node]:
    for ancestor in takewhile(lambda node: node.id not in opaque, ancestors(decision)):
        yield ancestor
        if ancestor.id in sealed:
            return


class Grammar(Model):
    name: SupportedLanguage
    query: str
    separator: str = "."
    module: Callable[[Source, Node], Sequence[str]]
    scope: Callable[[Node], Sequence[str] | None] = unscoped
    weight: Callable[[Node], int] = one
    label: Callable[[Node, Node], str] = named

    def functions(self, source: Source) -> list[Function]:
        parser = Parser(get_language(self.name))
        tree = parser.parse(source.path.read_bytes()).root_node
        module = self.module(source, tree)
        cursor = QueryCursor(_query(self.name, self.query))
        matches = [captured for _, captured in cursor.matches(tree)]
        opaque, sealed = (
            {node.id for captured in matches for node in captured.get(kind, ())}
            for kind in ("opaque", "sealed")
        )
        definitions = [
            (definition, name)
            for captured in matches
            for definition in captured.get("definition", ())
            for name in captured["name"]
        ]
        owners = {definition.id for definition, _ in definitions}
        decisions = grouped(
            (
                (owner.id, self.weight(decision))
                for captured in matches
                for decision in captured.get("decision", ())
                for owner in _owners(decision, opaque, sealed)
                if owner.id in owners
            ),
            lambda decision: decision[0],
        )
        return [
            Function(
                name=self.label(definition, name),
                namespace=self.separator.join((*module, *scope)),
                complexity=1
                + sum(weight for _, weight in decisions.get(definition.id, ())),
                span=span(definition),
            )
            for definition, name in definitions
            if (scope := self.scope(definition)) is not None and (module or scope)
        ]
