import shutil
from pathlib import Path

import pytest

from crapper.analyze import analyze
from crapper.languages import GO
from crapper.model import Function, Span, Unmeasured
from crapper.selection import select
from support import POLYGLOT, POLYGLOT_SOURCES

BOARD = POLYGLOT / "board.go"


@pytest.mark.parametrize(
    ("root", "expected"),
    [(".", POLYGLOT_SOURCES), ("board.go", ["board.go"]), ("missing", [])],
)
def test_sources_are_found_under_a_root_without_tests(
    root: str, expected: list[str]
) -> None:
    found = select(POLYGLOT, (root,), (), changed=False)
    assert sorted(file for project in found for file in project.files) == [
        POLYGLOT / file for file in expected
    ]


@pytest.mark.parametrize("directory", ["tests", "target"])
def test_test_and_build_directories_are_not_walked(
    tmp_path: Path, directory: str
) -> None:
    (tmp_path / directory).mkdir()
    shutil.copy(BOARD, tmp_path / directory)
    assert select(tmp_path, (), (), changed=False) == []


def test_a_file_outside_the_root_is_still_analyzed(tmp_path: Path) -> None:
    place = Function(
        name="Place", namespace="demo", complexity=2, span=Span(start=3, end=8)
    )
    assert analyze(GO.projects(tmp_path, [BOARD]), None) == [Unmeasured(function=place)]
    assert select(POLYGLOT, ("notes.md",), (), changed=False) == []
