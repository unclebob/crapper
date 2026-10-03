import shutil
import subprocess
from pathlib import Path

import pytest

from crapper.render import SNAPSHOT
from crapper.selection import select
from support import (
    FIXTURES,
    POLYGLOT,
    POLYGLOT_SOURCES,
    REPORTS,
    Crapper,
    Project,
    scores,
)

UNMEASURED = [
    "demo.Board place 3 None None",
    "demo Place 2 None None",
    "demo open 2 None None",
    "demo.core choose 2 None None",
    "demo.tool run 2 None None",
    "ui.view view 2 None None",
]
MEASURED = [
    "demo open 2 0.0 6.0",
    "demo.Board place 3 100.0 3.0",
    "demo Place 2 50.0 2.5",
    "demo.tool run 2 50.0 2.5",
    "demo.core choose 2 75.0 2.0625",
    "ui.view view 2 100.0 2.0",
]


@pytest.fixture
def polyglot(project: Project) -> Path:
    return project("polyglot")


def git(root: Path, *args: str) -> None:
    config = (
        "user.name=crapper",
        "user.email=crapper@example.com",
        "commit.gpgsign=false",
    )
    options = [option for value in config for option in ("-c", value)]
    subprocess.run(
        ["git", "-C", root, *options, *args], check=True, capture_output=True
    )


def selected(root: Path, *targets: str, changed: bool = False) -> list[Path]:
    found = select(root, targets, (), changed=changed)
    return sorted(file for project in found for file in project.files)


def test_every_language_is_scored_and_tests_are_left_out(
    polyglot: Path, crapper: Crapper
) -> None:
    outcome = crapper("--root", polyglot, "--coverage", "none")
    assert (outcome.code, outcome.err) == (0, f"Wrote {polyglot / SNAPSHOT}\n")
    assert scores(polyglot) == UNMEASURED


@pytest.mark.skipif(shutil.which("bb") is None, reason="needs babashka")
def test_the_snapshot_is_readable_by_a_clojure_reader(
    polyglot: Path, crapper: Crapper
) -> None:
    crapper("--root", polyglot, "--coverage", "none")
    reader = subprocess.run(
        ["bb", FIXTURES / "read_snapshot.clj"],
        input=(polyglot / SNAPSHOT).read_text(encoding="utf-8"),
        text=True,
        capture_output=True,
        check=True,
    )
    assert reader.stdout == "".join(f"{line}\n" for line in UNMEASURED).replace("None", "nil")  # fmt: skip


@pytest.mark.parametrize(
    ("argv", "code", "expected"),
    [
        ([], 0, MEASURED),
        (["--threshold", "6"], 0, MEASURED),
        (["--threshold", "1"], 2, MEASURED),
        (["src/demo/core.clj"], 0, MEASURED[4:5]),
        (["--threshold", "2", "src/demo/core.clj"], 2, MEASURED[4:5]),
    ],
)
def test_existing_reports_feed_the_snapshot_and_the_threshold(
    polyglot: Path, crapper: Crapper, argv: list[str], code: int, expected: list[str]
) -> None:
    assert crapper("--root", polyglot, "--coverage", "existing", *argv).code == code
    assert scores(polyglot) == expected


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["--source-root", "src"], [UNMEASURED[0], *UNMEASURED[2:]]),
        (["src"], [UNMEASURED[0], *UNMEASURED[2:]]),
        (["src/demo/core.clj", "core"], UNMEASURED[3:4]),
        (["src/demo/core.clj"], UNMEASURED[3:4]),
    ],
)
def test_targets_and_source_roots_narrow_what_is_scored(
    polyglot: Path, crapper: Crapper, argv: list[str], expected: list[str]
) -> None:
    assert crapper("--root", polyglot, "--coverage", "none", *argv).code == 0
    assert scores(polyglot) == expected


def test_nothing_is_written_when_no_source_is_selected(
    polyglot: Path, crapper: Crapper
) -> None:
    outcome = crapper("--root", polyglot, "--coverage", "none", "notes.md")
    assert (outcome.code, outcome.out) == (0, "No source files to analyze.\n")
    assert not (polyglot / SNAPSHOT).exists()


def test_relative_targets_resolve_under_the_root() -> None:
    assert selected(POLYGLOT, "src/demo/core.clj") == [POLYGLOT / "src/demo/core.clj"]


@pytest.mark.parametrize(
    "argv",
    [
        ["--not-an-option"],
        ["--root"],
        ["--threshold", "nope"],
        ["--coverage", "none", "--coverage-command", "true"],
    ],
    ids=" ".join,
)
def test_a_usage_error_exits_with_one(crapper: Crapper, argv: list[str]) -> None:
    assert crapper(*argv).code == 1


def test_an_unreadable_report_is_named_and_exits_with_one(
    polyglot: Path, crapper: Crapper
) -> None:
    report = polyglot / "target/coverage/go/coverage.out"
    shutil.copy(REPORTS / "broken.out", report)
    outcome = crapper("--root", polyglot, "--coverage", "existing")
    assert outcome.code == 1
    assert outcome.err.startswith(f"{report}: invalid Go coverage block")


def test_a_target_outside_the_root_is_refused(polyglot: Path, crapper: Crapper) -> None:
    root, board = polyglot / "src", polyglot / "board.go"
    outcome = crapper("--root", root, "--coverage", "none", board)
    assert (outcome.code, outcome.err) == (1, f"{board} is outside {root}\n")


def test_changed_outside_a_repository_exits_with_the_status_of_git(
    polyglot: Path, crapper: Crapper
) -> None:
    assert crapper("--root", polyglot, "--changed").code == 128


def test_help_describes_the_tool(crapper: Crapper) -> None:
    outcome = crapper("--help")
    assert outcome.code == 0
    assert "uml-viewer" in outcome.out


def test_coverage_is_run_per_language_by_default(
    polyglot: Path, crapper: Crapper
) -> None:
    outcome = crapper("--root", polyglot, "src/demo/core.clj")
    assert outcome.code == 0
    assert f"clj failed in {polyglot}." in outcome.err
    assert scores(polyglot) == ["demo.core choose 2 0.0 6.0"]


def test_a_coverage_command_runs_before_its_reports_are_read(
    project: Project, crapper: Crapper
) -> None:
    root = project("staged")
    command = "mkdir -p target/coverage && cp made.info target/coverage/lcov.info"
    assert crapper("--root", root, "--coverage-command", command).code == 0
    assert scores(root) == ["demo.core choose 2 100.0 2.0"]


def test_changed_files_follow_git_status(polyglot: Path) -> None:
    with pytest.raises(subprocess.CalledProcessError, match="status 128"):
        selected(polyglot, changed=True)
    git(polyglot, "init")
    assert selected(polyglot, changed=True) == [
        polyglot / file for file in POLYGLOT_SOURCES
    ]
    git(polyglot, "add", ".")
    git(polyglot, "commit", "-m", "everything")
    assert selected(polyglot, changed=True) == []


def test_a_tests_directory_above_the_root_does_not_hide_the_project(
    polyglot: Path,
) -> None:
    root = polyglot.rename(polyglot.with_name("tests"))
    sources = [root / file for file in POLYGLOT_SOURCES]
    assert selected(root) == sources
    git(root, "init")
    assert selected(root, changed=True) == sources


def test_only_changed_files_are_scored(polyglot: Path, crapper: Crapper) -> None:
    git(polyglot, "init")
    git(polyglot, "add", ".")
    git(polyglot, "commit", "-m", "everything")
    shutil.copy(polyglot / "src/lib.rs", polyglot / "src/extra.rs")
    outcome = crapper("--root", polyglot, "--coverage", "none", "--changed")
    assert (outcome.code, scores(polyglot)) == (0, ["demo::extra open 2 None None"])
    assert "No source files" not in outcome.out
