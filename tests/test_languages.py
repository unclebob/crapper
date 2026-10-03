from pathlib import Path

import pytest

from crapper.language import Language
from crapper.languages import PYTHON, TYPESCRIPT, language_of
from crapper.paths import module_parts


@pytest.mark.parametrize(
    ("path", "language"),
    [
        ("src/app/core.clj", "clojure"),
        ("src/app/core.cljc", "clojure"),
        ("Widget.java", "java"),
        ("board.go", "go"),
        ("ui/view.tsx", "typescript"),
        ("src/app.js", "typescript"),
        ("src/app.mjs", "typescript"),
        ("src/app.cjs", "typescript"),
        ("src/app.jsx", "typescript"),
        ("src/lib.rs", "rust"),
        ("src/crapper/cli.py", "python"),
        ("types.d.ts", None),
        ("notes.md", None),
    ],
)
def test_a_file_belongs_to_the_language_of_its_extension(
    path: str, language: str | None
) -> None:
    found = language_of(Path(path))
    assert (found and found.name) == language


@pytest.mark.parametrize(
    ("language", "path"),
    [
        (PYTHON, "conftest.py"),
        (PYTHON, "/proj/tests/test_board.py"),
        (TYPESCRIPT, "src/app.test.js"),
        (TYPESCRIPT, "src/app.spec.mjs"),
    ],
)
def test_a_language_recognises_its_tests(language: Language, path: str) -> None:
    assert language.is_test(Path(path))


@pytest.mark.parametrize(
    ("path", "root", "expected"),
    [
        ("/proj/src/demo/app.py", "/proj", ("demo", "app")),
        ("./src/demo/app.py", ".", ("demo", "app")),
        ("/proj/src/demo/core_extra.clj", "/proj", ("demo", "core_extra")),
        ("./demo/box.ts", ".", ("demo", "box")),
        ("/app/pkg/src/demo/box.mts", "/app", ("demo", "box")),
    ],
)
def test_module_parts_drop_the_root_the_src_directory_and_the_suffix(
    path: str, root: str, expected: tuple[str, ...]
) -> None:
    assert module_parts(Path(path), Path(root)) == expected
