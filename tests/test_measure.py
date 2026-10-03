import shlex
import shutil
import sys

import pytest

from support import Crapper, Project, scores


def needs(tool: str) -> pytest.MarkDecorator:
    return pytest.mark.skipif(shutil.which(tool) is None, reason=f"needs {tool}")


@pytest.mark.parametrize(
    ("plan", "expected"),
    [
        pytest.param("go-test", "example.com/demo Place 2 100.0 2.0", marks=needs("go")),
        pytest.param("tauri", "bookwriter read_text 1 100.0 1.0", marks=needs("cargo-llvm-cov")),
        pytest.param("npm-coverage", "app plan 2 100.0 2.0", marks=needs("npm")),
        pytest.param("node-test", "app plan 2 100.0 2.0", marks=needs("npm")),
        pytest.param("vitest", "book plan 2 100.0 2.0", marks=needs("npm")),
    ],
)  # fmt: skip
def test_a_project_is_measured_by_its_own_toolchain(
    project: Project, crapper: Crapper, plan: str, expected: str
) -> None:
    root = project(f"plans/{plan}")
    assert crapper("--root", root).code == 0
    assert scores(root) == [expected]


@pytest.mark.parametrize(
    ("plan", "package", "expected"),
    [
        ("pytest", ".", "demo.box choose 1 100.0 1.0"),
        ("unittest", "lib", "demo.app run 1 100.0 1.0"),
    ],
)
def test_python_is_measured_by_the_runner_its_project_uses(
    project: Project, crapper: Crapper, plan: str, package: str, expected: str
) -> None:
    root = project(f"plans/{plan}")
    python = root / package / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} "$@"\n')
    python.chmod(0o755)
    assert crapper("--root", root).code == 0
    assert scores(root) == [expected]


@pytest.mark.parametrize(
    ("plan", "expected", "reason"),
    [
        ("scriptless", "app plan 2 0.0 6.0", "No test script in"),
        ("venv", "demo.app run 1 0.0 2.0", ".venv/bin/python is not installed."),
        pytest.param("maven", "demo.Board place 1 0.0 2.0", "mvn failed in", marks=needs("mvn")),
        pytest.param("vitest-unpublished", "book plan 2 0.0 6.0", "npm failed in", marks=needs("npm")),
    ],
)  # fmt: skip
def test_a_project_its_toolchain_cannot_measure_scores_zero(
    project: Project, crapper: Crapper, plan: str, expected: str, reason: str
) -> None:
    root = project(f"plans/{plan}")
    outcome = crapper("--root", root)
    assert outcome.code == 0
    assert reason in outcome.err
    assert scores(root) == [expected]
