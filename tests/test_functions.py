import pytest
from tree_sitter import Parser
from tree_sitter_language_pack import get_language

from crapper.language import Language
from crapper.languages import CLOJURE, GO, JAVA, PYTHON, RUST, TYPESCRIPT
from crapper.languages.treesitter import span
from crapper.model import Function, Source, Span, grouped
from support import SOURCES

type Complexities = dict[str, dict[str, int]]

BRANCHES = {
    "no-body": 1,
    "arithmetic": 1,
    "if-form": 2,
    "if-not-form": 2,
    "if-let-form": 2,
    "when-form": 2,
    "when-first-form": 2,
    "and-form": 2,
    "or-form": 2,
    "loop-form": 2,
    "discarded-form": 2,
    "cond-form": 3,
    "condp-form": 3,
    "case-form": 3,
    "cond-thread": 3,
    "some-thread-first": 3,
    "some-thread-last": 3,
    "keywords-in-a-string": 1,
    "form-in-a-string": 1,
    "keywords-in-a-comment": 1,
    "keywords-in-a-trailing-comment": 2,
    "map-literals-in-cond": 6,
    "empty-list": 1,
}


def extract(language: Language, file: str) -> list[Function]:
    root = SOURCES / language.name / file.split("/")[0]
    path = SOURCES / language.name / file
    (project,) = language.projects(root, [path])
    source = Source(home=project.home, path=path)
    return language.functions(source)


@pytest.mark.parametrize(
    ("language", "file", "expected"),
    [
        (CLOJURE, "app/src/demo/core.clj", {"demo.core": {"choose": 2, "hidden": 1}}),
        (CLOJURE, "app/src/demo/branches.clj", {"demo.branches": BRANCHES}),
        (CLOJURE, "app/src/demo/definitions.clj", {"demo.definitions": {"alpha": 2, "omega": 1}}),
        (CLOJURE, "app/src/demo/literals.clj", {"demo.literals": {"foo": 1}}),
        (CLOJURE, "app/src/demo/character_set.clj", {"demo.character-set": {"foo": 1}}),
        (CLOJURE, "app/src/demo/unterminated_line.clj", {"demo.unterminated-line": {"foo": 1}}),
        (CLOJURE, "app/src/demo/core_extra.clj", {"demo.core-extra": {"foo": 1}}),
        (CLOJURE, "app/src/demo/shared.cljc", {"demo.shared": {"foo": 1}}),
        (CLOJURE, "app/pkg/src/demo/task.bb", {"demo.task": {"foo": 1}}),
        (CLOJURE, "app/truncated/escape.clj", {}),
        (CLOJURE, "app/truncated/character.clj", {}),
        (CLOJURE, "app/truncated/comment.clj", {}),
        (CLOJURE, "app/truncated/string.clj", {}),
        (GO, "bare/sample.go", {"sample": {"Branchy": 5}}),
        (GO, "bare/widget.go", {"sample.Widget": {"Run": 3}, "sample": {"Simple": 1}}),
        (GO, "bare/declarations.go", {"p": {"Real": 1}}),
        (GO, "bare/orphan.go", {}),
        (GO, "module/board.go", {"github.com/acme/demo": {"Place": 1}}),
        (GO, "module/internal/game/board.go", {"github.com/acme/demo/internal/game.Board": {"Place": 3}}),
        (JAVA, "app/Score.java", {"Score": {"score": 10}}),
        (JAVA, "app/Nested.java", {"Nested": {"nested": 13, "switched": 4}}),
        (JAVA, "app/Anonymous.java", {"Anonymous": {"outer": 1}}),
        (JAVA, "app/Lambda.java", {"Lambda": {"outer": 1}}),
        (JAVA, "app/Literals.java", {"Literals": {"stable": 1}}),
        (JAVA, "app/demo/pkg/Board.java", {"demo.pkg.Board": {"place": 3}, "demo.pkg.Board.Inner": {"tick": 1}}),
        (PYTHON, "app/src/demo/box.py", {"demo.box": {"choose": 14, "outer": 2, "load": 2}, "demo.box.Box": {"open": 2, "shut": 2}}),
        (PYTHON, "app/src/demo/sample.py", {"demo.sample.Outer.Inner": {"tick": 3}, "demo.sample": {"factory": 1}, "demo.sample.Hidden": {"secret": 2}}),
        (PYTHON, "app/src/demo/__init__.py", {"demo": {"literal": 1}}),
        (PYTHON, "app/src/demo/app.py", {"demo.app": {"f": 1}}),
        (PYTHON, "app/src/app.py", {"app": {"choose": 1}}),
        (PYTHON, "app/pkg/src/demo/__init__.py", {"demo": {"f": 1}}),
        (PYTHON, "app/__init__.py", {"__init__": {"f": 1}}),
        (RUST, "crate/src/lib.rs", {"demo_game": {"choose": 6, "outer": 2}, "demo_game::Sample": {"run": 2, "draw": 1}}),
        (RUST, "crate/src/shapes.rs", {"demo_game::shapes": {"draw": 1, "sides": 1}, "demo_game::shapes::Vec": {"sides": 1}}),
        (RUST, "crate/src/game/mod.rs", {"demo_game::game": {"open": 1}}),
        (RUST, "crate/src/game/board.rs", {"demo_game::game::board": {"place": 2}}),
        (RUST, "crate/src/bin/tool.rs", {"tool": {"main_ok": 1}}),
        (RUST, "crate/notes.rs", {"demo_game::notes": {"bare": 1}}),
        (RUST, "loose/loose.rs", {"crate::loose": {"loose": 1}}),
        (TYPESCRIPT, "app/src/demo/box.ts", {"demo.box": {"choose": 7, "arrow": 2, "outer": 2}, "demo.box.Box": {"open": 2}}),
        (TYPESCRIPT, "app/src/demo/declarations.ts", {"demo.declarations": {"arrow": 1}}),
        (TYPESCRIPT, "app/src/demo/object.ts", {}),
        (TYPESCRIPT, "app/src/demo/computed.ts", {}),
        (TYPESCRIPT, "app/pkg/src/demo/box.mts", {"demo.box": {"choose": 1}}),
        (TYPESCRIPT, "app/src/ui/view.tsx", {"ui.view": {"View": 3}}),
        (TYPESCRIPT, "app/src/demo/operators.ts", {"demo.operators": {"choose": 7, "text": 1}}),
        (TYPESCRIPT, "app/src/demo/routes.ts", {"demo.routes": {"mount": 2, "GET /users": 2, "POST /users": 2, "USE": 1, "GET /items": 1, "POST /items": 1, "GET /health": 2, "GET /users#2": 1, "GET /users#3": 2, "DELETE /users/${id}": 1}}),
        (TYPESCRIPT, "app/src/demo/callback.ts", {"demo.callback": {"outer": 2}}),
        (TYPESCRIPT, "app/src/demo/app.mjs", {"demo.app": {"choose": 7, "GET /users": 2}}),
        (TYPESCRIPT, "app/src/demo/app.js", {"demo.app": {"choose": 7, "GET /users": 2}}),
    ],
)  # fmt: skip
def test_functions_are_scored_under_their_namespace(
    language: Language, file: str, expected: Complexities
) -> None:
    found = extract(language, file)
    scored = {
        namespace: {function.name: function.complexity for function in group}
        for namespace, group in grouped(
            found, lambda function: function.namespace
        ).items()
    }
    assert scored == expected
    assert sum(map(len, expected.values())) == len(found)


@pytest.mark.parametrize(
    ("file", "expected"),
    [
        ("app/src/demo/core.clj", [Span(start=3, end=4), Span(start=6, end=7)]),
        ("app/src/demo/unterminated_line.clj", [Span(start=1, end=3)]),
    ],
)
def test_functions_span_their_definitions(file: str, expected: list[Span]) -> None:
    assert [function.span for function in extract(CLOJURE, file)] == expected


def test_a_span_ends_on_the_last_line_before_a_trailing_newline() -> None:
    source = (SOURCES / "python/app/src/app.py").read_bytes()
    root = Parser(get_language("python")).parse(source).root_node
    assert span(root) == Span(start=1, end=2)
