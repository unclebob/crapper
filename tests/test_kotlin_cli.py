from pathlib import Path

import pytest

from crapper.cli import run
from crapper.runners import run_coverage

SOURCE = "package demo\n\nfun pick(a: Boolean): Int {\n    return if (a) 1 else 2\n}\n"
REPORT = (
    '<report><package name="demo"><sourcefile name="Pick.kt">'
    '<line nr="3" mi="0" ci="1"/><line nr="4" mi="0" ci="3"/>'
    "</sourcefile></package></report>"
)


@pytest.fixture
def real_coverage(monkeypatch):
    """The suite-wide conftest stubs coverage out; these tests need the real runner."""

    monkeypatch.setattr("crapper.cli.run_coverage", run_coverage)


def project(tmp_path: Path) -> None:
    source = tmp_path / "src/main/kotlin/demo/Pick.kt"
    source.parent.mkdir(parents=True)
    source.write_text(SOURCE)
    (tmp_path / "settings.gradle.kts").write_text("rootProject.name = \"demo\"\n")
    report = tmp_path / "build/reports/jacoco/test/jacocoTestReport.xml"
    report.parent.mkdir(parents=True)
    report.write_text(REPORT)


def snapshot(tmp_path: Path) -> str:
    return (tmp_path / ".metrics" / "crap.edn").read_text(encoding="utf-8")


def test_existing_gradle_report_feeds_the_kotlin_snapshot(tmp_path):
    project(tmp_path)
    assert run(["--root", str(tmp_path), "--use-existing-coverage"]) == 0
    text = snapshot(tmp_path)
    assert ':name "pick"' in text and ':namespace "demo.PickKt"' in text
    assert ":complexity 2" in text and ":coverage 100.0" in text and ":crap 2.0" in text


def test_no_coverage_leaves_kotlin_coverage_and_crap_nil(tmp_path):
    project(tmp_path)
    assert run(["--root", str(tmp_path), "--no-coverage"]) == 0
    assert ":coverage nil" in snapshot(tmp_path) and ":crap nil" in snapshot(tmp_path)


def test_a_failed_custom_command_scores_kotlin_at_zero_and_still_writes(tmp_path, real_coverage):
    project(tmp_path)
    assert run(["--root", str(tmp_path), "--coverage-command", "exit 3"]) == 0
    assert ":coverage 0.0" in snapshot(tmp_path) and ":crap 6.0" in snapshot(tmp_path)


def test_a_custom_command_replaces_gradle(tmp_path, real_coverage):
    project(tmp_path)
    marker = tmp_path / "ran"
    assert run(["--root", str(tmp_path), "--coverage-command", f"touch {marker}"]) == 0
    assert marker.exists() and ":coverage 100.0" in snapshot(tmp_path)


def test_a_missing_gradle_scores_zero_and_still_writes(tmp_path, monkeypatch, real_coverage):
    project(tmp_path)
    monkeypatch.setattr("crapper.runners.shutil.which", lambda name: None)
    assert run(["--root", str(tmp_path)]) == 0
    assert ":coverage 0.0" in snapshot(tmp_path)
