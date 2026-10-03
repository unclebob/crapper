from pathlib import Path, PurePosixPath

import pytest

from crapper.analyze import _entry
from crapper.coverage import formats
from crapper.coverage.formats import Lines, Segment, source_path
from crapper.coverage.measure import existing, resolve
from crapper.language import Project
from crapper.languages import GO
from crapper.model import Function, Home, Scored, Span
from crapper.selection import select
from support import PLANS, POLYGLOT, POLYGLOT_SOURCES, REPORTS

CORE = Path("src/demo/core.clj")
PAGE = Path("demo/core.clj")
MODULES = PLANS / "go-modules"
JACOCO = POLYGLOT / "target/site/jacoco/jacoco.xml"
READ = {
    ".info": formats.LCOV.read,
    ".out": formats.GO_PROFILE.read,
    ".xml": formats.JACOCO.read,
}
LINES = {CORE: (Segment.line(3, 1, 0), Segment.line(4, 0, 1))}
FORMS = {CORE: (Segment.line(4, 3, 1),)}


def owner(file: Path, root: Path) -> Project:
    return Project(language=GO, home=Home(root=root, directory=root), files=(file,))


def measured(reports: tuple[Lines, ...], file: Path, span: Span) -> float:
    segments = resolve(reports, owner(file, Path())).get(file, ())
    function = Function(name="measured", namespace="demo", complexity=1, span=span)
    entry = _entry(function, segments)
    assert isinstance(entry, Scored)
    return entry.coverage


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("file:./src//demo/core.clj", "src/demo/core.clj"),
        ("%2E%2Fsrc%2Fcore.clj", "src/core.clj"),
    ],
)
def test_report_paths_drop_url_and_dot_prefixes(raw: str, expected: str) -> None:
    assert source_path(raw) == Path(expected)


@pytest.mark.parametrize(
    ("keys", "file", "root", "found"),
    [
        (["src/demo/core.clj"], "demo/core.clj", "", "src/demo/core.clj"),
        (["src/demo/core.clj"], "/work/src/demo/core.clj", "/work", "src/demo/core.clj"),
        (["src/demo/core.clj"], "other/core.clj", "", None),
        ([], "src/demo/core.clj", "", None),
        (["proj/src/demo/core.clj"], "src/demo/core.clj", "", "proj/src/demo/core.clj"),
        (["mod.py", "pkg/mod.py"], "/work/mod.py", "/work", "mod.py"),
        (["mod.py", "pkg/mod.py"], "/work/pkg/mod.py", "/work", "pkg/mod.py"),
        (["/ci/mod.py", "/ci/pkg/mod.py"], "/work/mod.py", "/work", "/ci/mod.py"),
    ],
)  # fmt: skip
def test_a_file_finds_its_segments_by_the_closest_matching_report_path(
    keys: list[str], file: str, root: str, found: str | None
) -> None:
    report: Lines = {
        PurePosixPath(key): (Segment.line(line, 1, 0),)
        for line, key in enumerate(keys, start=1)
    }
    expected = {Path(file): report[PurePosixPath(found)]} if found else {}
    assert resolve([report], owner(Path(file), Path(root))) == expected


@pytest.mark.parametrize(
    ("reports", "file", "span", "expected"),
    [
        ((), CORE, Span(start=3, end=5), 0.0),
        ((LINES,), Path("src/missing.clj"), Span(start=3, end=5), 0.0),
        ((LINES,), CORE, Span(start=3, end=4), 50.0),
        ((LINES,), CORE, Span(start=5, end=8), 0.0),
        ((FORMS, LINES), CORE, Span(start=3, end=5), 75.0),
    ],
)
def test_coverage_is_the_covered_share_of_the_first_report_that_has_the_file(
    reports: tuple[Lines, ...], file: Path, span: Span, expected: float
) -> None:
    assert measured(reports, file, span) == expected


@pytest.mark.parametrize(
    ("report", "file", "span", "expected"),
    [
        (REPORTS / "module.out", "board.go", Span(start=4, end=6), 100.0),
        (REPORTS / "module.out", "board.go", Span(start=8, end=9), 0.0),
        (REPORTS / "module.out", "board.go", Span(start=10, end=12), 0.0),
        (REPORTS / "module.out", "other.go", Span(start=1, end=3), 0.0),
        (REPORTS / "unrelated.out", "board.go", Span(start=4, end=6), 100.0),
        (JACOCO, "src/demo/pkg/Board.java", Span(start=4, end=5), 75.0),
        (JACOCO, "src/demo/pkg/Board.java", Span(start=9, end=9), 100.0),
        (JACOCO, "demo/Board.java", Span(start=4, end=6), 100.0),
        (JACOCO, "demo/Missing.java", Span(start=4, end=6), 0.0),
        (POLYGLOT / "target/coverage/lcov.info", "src/demo/core.clj", Span(start=3, end=4), 50.0),
        (REPORTS / "branches.info", "src/demo/app.ts", Span(start=2, end=3), 50.0),
        (REPORTS / "branches.info", "src/demo/app.ts", Span(start=6, end=7), 50.0),
    ],
)  # fmt: skip
def test_a_function_is_measured_from_a_report_on_disk(
    report: Path, file: str, span: Span, expected: float
) -> None:
    assert measured((READ[report.suffix](report),), Path(file), span) == expected


def test_cloverage_pages_count_forms_per_line() -> None:
    assert formats.CLOVERAGE.read(POLYGLOT / "target/coverage") == {
        PAGE: (
            Segment.line(1, 1, 0),
            Segment.line(2, 0, 0),
            Segment.line(3, 2, 0),
            Segment.line(4, 1, 1),
        )
    }


@pytest.mark.parametrize(
    ("report", "problem"),
    [
        ("broken.out", "invalid Go coverage block"),
        ("broken.info", "no LCOV source records"),
        ("broken.xml", "invalid JaCoCo XML"),
    ],
)
def test_a_broken_report_is_an_error(report: str, problem: str) -> None:
    with pytest.raises(ValueError, match=problem):
        READ[Path(report).suffix](REPORTS / report)


def test_a_report_path_naming_another_file_is_not_borrowed() -> None:
    (project,) = GO.projects(MODULES, [MODULES / "main.go"])
    report: Lines = {
        PurePosixPath("example.com/demo/sub/main.go"): (Segment.line(1, 1, 0),)
    }
    assert resolve([report], project) == {}


def test_go_profiles_are_keyed_by_the_files_their_modules_own() -> None:
    files = [MODULES / "main.go", MODULES / "sub/main.go", MODULES / "tools/main.go"]
    report = existing(MODULES, GO.projects(MODULES, files))
    assert sorted(report) == files
    assert [segment.covered for file in files for segment in report[file]] == [1, 0, 0]


def test_load_reads_every_report_each_language_knows() -> None:
    assert sorted(
        file.relative_to(POLYGLOT).as_posix()
        for file in existing(POLYGLOT, select(POLYGLOT, (), (), changed=False))
    ) == [source for source in POLYGLOT_SOURCES if source != "src/lib.rs"]


def test_load_on_a_tree_without_reports_measures_nothing(tmp_path: Path) -> None:
    assert not existing(tmp_path, [])
