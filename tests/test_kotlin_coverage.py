from pathlib import Path

from crapper.analyze import analyze_files
from crapper.coverage import load_bundle, parse_jacoco_lines

GREETER = """package demo.app

class Greeter {
    fun greet(name: String = "x"): String {
        if (name.isEmpty()) return ""
        return listOf(name).map { it + "!" }.joinToString()
    }
    companion object {
        fun make() = Greeter()
    }
}
"""

# What JaCoCo writes for GREETER: greet$default owns line 4, the lambda class
# owns part of line 6, and the Companion class owns line 9. Only the
# sourcefile section is needed to score by line.
REPORT = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE report PUBLIC "-//JACOCO//DTD Report 1.1//EN" "report.dtd">
<report name="demo">
  <package name="demo/app">
    <class name="demo/app/Greeter" sourcefilename="Greeter.kt">
      <method name="greet" desc="()V" line="4"><counter type="INSTRUCTION" missed="0" covered="1"/></method>
    </class>
    <class name="demo/app/Greeter$Companion" sourcefilename="Greeter.kt"/>
    <sourcefile name="Greeter.kt">
      <line nr="4" mi="0" ci="3" mb="0" cb="0"/>
      <line nr="5" mi="2" ci="2" mb="1" cb="1"/>
      <line nr="6" mi="0" ci="5" mb="0" cb="0"/>
      <line nr="9" mi="3" ci="0" mb="0" cb="0"/>
      <counter type="LINE" missed="1" covered="3"/>
    </sourcefile>
  </package>
  <package name="other">
    <sourcefile name="Greeter.kt">
      <line nr="4" mi="0" ci="9" mb="0" cb="0"/>
    </sourcefile>
  </package>
</report>
"""


def project(tmp_path: Path, report_at: str = "build/reports/jacoco/test/jacocoTestReport.xml"):
    source = tmp_path / "src/main/kotlin/demo/app/Greeter.kt"
    source.parent.mkdir(parents=True)
    source.write_text(GREETER)
    report = tmp_path / report_at
    report.parent.mkdir(parents=True)
    report.write_text(REPORT)
    return source


def scores(tmp_path: Path, source: Path):
    entries = analyze_files([source], tmp_path, load_bundle(tmp_path))
    return {entry.name: entry.coverage for entry in entries}


def test_parse_keys_each_source_file_by_package_path_with_instruction_counts():
    parsed = parse_jacoco_lines(REPORT)
    assert parsed["demo/app/Greeter.kt"] == {4: (3, 3), 5: (2, 4), 6: (5, 5), 9: (0, 3)}
    assert parsed["other/Greeter.kt"] == {4: (9, 9)}


def test_function_coverage_sums_the_instructions_of_its_lines(tmp_path):
    source = project(tmp_path)
    # greet spans lines 4-7: 3 + 2 + 5 covered of 3 + 4 + 5 instructions.
    # make is on the companion object's line 9, which nothing ran.
    assert scores(tmp_path, source) == {"greet": 83.3333, "make": 0.0}


def test_the_report_of_a_gradle_subproject_is_found(tmp_path):
    root = tmp_path
    source = root / "app/src/main/kotlin/demo/app/Greeter.kt"
    source.parent.mkdir(parents=True)
    source.write_text(GREETER)
    report = root / "app/build/reports/jacoco/test/jacocoTestReport.xml"
    report.parent.mkdir(parents=True)
    report.write_text(REPORT)
    assert scores(root, source)["greet"] == 83.3333


def test_a_source_file_the_report_lacks_scores_zero(tmp_path):
    project(tmp_path)
    other = tmp_path / "src/main/kotlin/demo/app/Unseen.kt"
    other.write_text("package demo.app\nfun lonely() = 1\n")
    assert scores(tmp_path, other) == {"lonely": 0.0}


def test_a_source_file_is_never_scored_from_a_same_named_file_in_another_package(tmp_path):
    source = project(tmp_path)
    moved = tmp_path / "src/main/kotlin/zzz/Greeter.kt"
    moved.parent.mkdir(parents=True)
    moved.write_text(GREETER.replace("demo.app", "zzz"))
    assert scores(tmp_path, moved) == {"greet": 0.0, "make": 0.0}
    assert scores(tmp_path, source)["greet"] == 83.3333
