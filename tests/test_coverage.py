from crapper.analyze import analyze_files
from crapper.coverage import (
    CoverageBundle,
    go_percent,
    load_bundle,
    parse_form_coverage,
    parse_go_profile,
    parse_jacoco_index,
    parse_lcov,
)
from crapper.model import Function


def function(**kwargs):
    defaults = dict(
        name="choose",
        namespace="demo.core",
        complexity=2,
        start_line=3,
        end_line=5,
        path="src/demo/core.clj",
        language="clojure",
        jacoco_class=None,
    )
    defaults.update(kwargs)
    return Function(**defaults)


def test_cloverage_form_counts_and_lcov_lines():
    html = '<span class="pc" title="1 out of 2 forms covered">   4&nbsp;&nbsp;(if x 1)</span>'
    assert parse_form_coverage(html) == {4: (1, 2)}
    lcov = "SF:src/demo/core.clj\nDA:3,1\nDA:4,0\nDA:9,3\nend_of_record\n"
    parsed = parse_lcov(lcov)
    bundle = CoverageBundle(lcov=parsed, form_html={"src/demo/core.clj": {4: (1, 2)}})
    # Form HTML wins over LCOV for Clojure, matching crap4clj.
    assert bundle.percent_for(function(start_line=3, end_line=5)) == 50.0


def test_lcov_percentage_when_there_is_no_html():
    lcov = parse_lcov("SF:src/demo/core.clj\nDA:3,1\nDA:4,0\nend_of_record\n")
    bundle = CoverageBundle(lcov=lcov)
    assert bundle.percent_for(function(start_line=3, end_line=4)) == 50.0
    assert bundle.percent_for(function(path="src/missing.clj")) is None


def test_lcov_branch_records_override_line_hits():
    text = "SF:src/demo/app.ts\nDA:2,1\nDA:3,1\nBRDA:3,0,0,1\nBRDA:3,0,1,-\nend_of_record\n"
    parsed = parse_lcov(text)
    assert parsed["src/demo/app.ts"][2] == (1, 1)
    assert parsed["src/demo/app.ts"].branches[3] == (1, 2)
    bundle = CoverageBundle(lcov=parsed)
    scored = function(
        path="src/demo/app.ts",
        language="typescript",
        start_line=2,
        end_line=3,
        namespace="demo.app",
    )
    assert bundle.percent_for(scored) == 50.0


def test_a_branchless_span_keeps_line_coverage():
    text = "SF:src/demo/app.ts\nDA:2,1\nDA:3,0\nBRDA:8,0,0,1\nBRDA:8,0,1,0\nend_of_record\n"
    bundle = CoverageBundle(lcov=parse_lcov(text))
    scored = function(path="src/demo/app.ts", language="typescript", start_line=2, end_line=3)
    assert bundle.percent_for(scored) == 50.0


def test_go_profile_matches_crap4go_statement_ranges():
    profile = parse_go_profile(
        "mode: set\ngithub.com/acme/demo/board.go:4.1,6.2 2 1\ngithub.com/acme/demo/board.go:8.1,9.2 1 0\n"
    )
    assert go_percent(profile, "board.go", 4, 6) == 100.0
    assert go_percent(profile, "board.go", 8, 9) == 0.0
    assert go_percent(profile, "other.go", 1, 3) is None


def test_jacoco_instruction_coverage_joins_on_class_and_method():
    xml = """<?xml version="1.0"?>
    <report>
      <package>
        <class name="demo/pkg/Board">
          <method name="place" line="4">
            <counter type="INSTRUCTION" missed="1" covered="3"/>
          </method>
        </class>
        <class name="demo/pkg/Board$Inner">
          <method name="tick" line="9">
            <counter type="INSTRUCTION" missed="0" covered="2"/>
          </method>
        </class>
      </package>
    </report>
    """
    bundle = CoverageBundle(jacoco=parse_jacoco_index(xml))
    outer = function(
        name="place",
        namespace="demo.pkg.Board",
        language="java",
        jacoco_class="demo.pkg.Board",
        start_line=4,
        path="src/demo/pkg/Board.java",
    )
    inner = function(
        name="tick",
        namespace="demo.pkg.Board.Inner",
        language="java",
        jacoco_class="demo.pkg.Board$Inner",
        start_line=9,
        path="src/demo/pkg/Board.java",
    )
    assert bundle.percent_for(outer) == 75.0
    assert bundle.percent_for(inner) == 100.0


def test_jacoco_skips_methods_without_an_instruction_counter():
    xml = """<report>
      <class name="demo/pkg/Board">
        <method name="skip" line="2">
          <counter type="LINE" missed="1" covered="0"/>
        </method>
        <method name="bad" line="nope">
          <counter type="INSTRUCTION" missed="1" covered="1"/>
        </method>
        <counter type="INSTRUCTION" missed="0" covered="1"/>
      </class>
    </report>"""
    found = parse_jacoco_index(xml)
    assert list(found) == ["demo.pkg.Board#bad"]
    assert found["demo.pkg.Board#bad"][0].line == 0


def test_missing_go_profile_is_na():
    assert go_percent(None, "board.go", 1, 3) is None


def test_load_bundle_merges_each_report(tmp_path):
    lcov = tmp_path / "target" / "coverage" / "lcov.info"
    lcov.parent.mkdir(parents=True)
    lcov.write_text("SF:src/demo/core.clj\nDA:3,1\nDA:4,0\nend_of_record\n", encoding="utf-8")
    go = tmp_path / "target" / "coverage" / "go" / "coverage.out"
    go.parent.mkdir(parents=True)
    go.write_text("mode: set\nboard.go:1.1,2.2 1 1\n", encoding="utf-8")
    jacoco = tmp_path / "target" / "site" / "jacoco" / "jacoco.xml"
    jacoco.parent.mkdir(parents=True)
    jacoco.write_text(
        '<report><class name="demo/Board"><method name="place" line="4">'
        '<counter type="INSTRUCTION" missed="0" covered="1"/></method></class></report>',
        encoding="utf-8",
    )
    html = tmp_path / "target" / "coverage" / "src" / "demo" / "core.clj.html"
    html.parent.mkdir(parents=True)
    html.write_text(
        '<span title="1 out of 2 forms covered">   4&nbsp;&nbsp;(if x 1)</span>',
        encoding="utf-8",
    )
    (tmp_path / "target" / "coverage" / "index.html").write_text("<html></html>", encoding="utf-8")
    bundle = load_bundle(tmp_path)
    assert bundle.percent_for(function(start_line=3, end_line=4)) == 50.0
    assert bundle.go_profile is not None
    assert bundle.jacoco is not None


def _cobertura(filename, lines, name="Demo.Board"):
    """One Cobertura report with one class; `lines` are (number, hits, "covered/total" or None)."""

    rows = "".join(
        f'<line number="{number}" hits="{hits}" branch="{"True" if cond else "False"}"'
        + (f' condition-coverage="50% ({cond})"' if cond else "")
        + " />"
        for number, hits, cond in lines
    )
    return (
        '\ufeff<?xml version="1.0" encoding="utf-8"?>\n<coverage><packages><package name="Demo">'
        f'<classes><class name="{name}" filename="{filename}"><methods/><lines>{rows}</lines>'
        "</class></classes></package></packages></coverage>"
    )


def _write_cobertura(root, project, text):
    report = root / "target" / "coverage" / "fsharp" / project / "4f2c" / "me_host_2026.cobertura.xml"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(text, encoding="utf-8")


def _fsharp_percent(root, start_line, end_line, path="src/Board.fs"):
    scored = function(
        namespace="Demo.Board",
        start_line=start_line,
        end_line=end_line,
        path=path,
        language="fsharp",
    )
    return load_bundle(root).percent_for(scored)


def test_cobertura_condition_coverage_scores_a_function_and_line_hits_score_a_branchless_one(tmp_path):
    source = tmp_path / "src" / "Board.fs"
    _write_cobertura(
        tmp_path,
        "Board.Tests",
        _cobertura(source, [(3, 4, None), (4, 1, "1/2"), (5, 0, None), (8, 2, None), (9, 0, None)]),
    )
    assert _fsharp_percent(tmp_path, 3, 5) == 50.0
    assert _fsharp_percent(tmp_path, 8, 9) == 50.0


def test_the_same_fsharp_file_in_two_cobertura_reports_merges_in_either_load_order(tmp_path):
    reports = [
        [(3, 0, None), (4, 0, "0/2")],
        [(3, 35, None), (4, 2, "2/2")],
    ]
    for name, order in (("ab", reports), ("ba", reports[::-1])):
        root = tmp_path / name
        source = root / "src" / "Board.fs"
        _write_cobertura(root, "One.Tests", _cobertura(source, order[0]))
        _write_cobertura(root, "Two.Tests", _cobertura(source, order[1]))
        assert _fsharp_percent(root, 3, 3) == 100.0
        assert _fsharp_percent(root, 3, 4) == 100.0


def test_branches_on_a_line_take_the_highest_covered_count_any_report_gives(tmp_path):
    source = tmp_path / "src" / "Board.fs"
    _write_cobertura(tmp_path, "One.Tests", _cobertura(source, [(4, 1, "1/4")]))
    _write_cobertura(tmp_path, "Two.Tests", _cobertura(source, [(4, 1, "3/4")]))
    assert _fsharp_percent(tmp_path, 4, 4) == 75.0


def test_a_line_listed_under_two_classes_of_one_report_merges_like_two_reports(tmp_path):
    source = tmp_path / "src" / "Board.fs"
    first = _cobertura(source, [(3, 0, "0/2")], name="Demo.Board")
    second = _cobertura(source, [(3, 1, "1/2")], name="Demo.Board/choose@3")
    classes = first.split("<classes>")[1].split("</classes>")[0]
    _write_cobertura(tmp_path, "Board.Tests", second.replace("<classes>", "<classes>" + classes))
    assert _fsharp_percent(tmp_path, 3, 3) == 50.0


def test_a_cobertura_report_beats_an_lcov_info_for_the_same_fsharp_file(tmp_path):
    source = tmp_path / "src" / "Board.fs"
    lcov = tmp_path / "target" / "coverage" / "fsharp" / "lcov.info"
    lcov.parent.mkdir(parents=True)
    lcov.write_text("SF:src/Board.fs\nDA:3,5\nend_of_record\n", encoding="utf-8")
    _write_cobertura(tmp_path, "Board.Tests", _cobertura(source, [(3, 0, None)]))
    assert _fsharp_percent(tmp_path, 3, 3) == 0.0


def test_a_file_outside_the_project_such_as_fsharp_core_matches_no_entry(tmp_path):
    outside = "/Users/runner/work/1/s/src/fsharp/src/FSharp.Core/array.fs"
    _write_cobertura(tmp_path, "Board.Tests", _cobertura(outside, [(3, 5, None)]))
    assert _fsharp_percent(tmp_path, 3, 3, path="array.fs") is None
    assert _fsharp_percent(tmp_path, 3, 3, path="FSharp.Core/array.fs") is None


def test_a_windows_path_fsharp_core_file_in_a_report_matches_no_project_entry(tmp_path):
    outside = "D:\\a\\_work\\1\\s\\src\\FSharp.Core\\array.fs"
    _write_cobertura(tmp_path, "Board.Tests", _cobertura(outside, [(3, 5, None)]))
    assert _fsharp_percent(tmp_path, 3, 3, path="src/FSharp.Core/array.fs") is None
    assert _fsharp_percent(tmp_path, 3, 3, path="FSharp.Core/array.fs") is None


def test_an_unreadable_cobertura_report_is_skipped_with_a_warning(tmp_path, capsys):
    source = tmp_path / "src" / "Board.fs"
    _write_cobertura(tmp_path, "Broken.Tests", "<coverage><packages>")
    _write_cobertura(tmp_path, "Board.Tests", _cobertura(source, [(3, 1, None)]))
    assert _fsharp_percent(tmp_path, 3, 3) == 100.0
    assert "unreadable Cobertura report" in capsys.readouterr().err


def test_a_script_function_no_coverage_report_mentions_scores_zero(tmp_path):
    board = tmp_path / "src" / "Board.fs"
    board.parent.mkdir(parents=True)
    board.write_text("module Board\n\nlet place x = x + 1\n", encoding="utf-8")
    script = tmp_path / "build.fsx"
    script.write_text("let publish target = target\n", encoding="utf-8")
    _write_cobertura(tmp_path, "Board.Tests", _cobertura(board.resolve(), [(3, 1, None)]))
    found = analyze_files([board, script], tmp_path, load_bundle(tmp_path))
    assert sorted((entry.name, entry.coverage) for entry in found) == [
        ("place", 100.0),
        ("publish", 0.0),
    ]


def test_a_cobertura_report_with_a_non_numeric_line_attribute_is_skipped_with_a_warning(tmp_path, capsys):
    source = tmp_path / "src" / "Board.fs"
    _write_cobertura(tmp_path, "Broken.Tests", _cobertura(source, [("three", 1, None)]))
    _write_cobertura(tmp_path, "Board.Tests", _cobertura(source, [(3, 1, None)]))
    assert _fsharp_percent(tmp_path, 3, 3) == 100.0
    assert "unreadable Cobertura report" in capsys.readouterr().err


def _kover(classes):
    """A Kover XML report: `classes` maps `pkg/Class` to (method, missed, covered) rows, no lines."""

    body = "".join(
        f'<class name="{name}" sourcefilename="Board.kt">'
        + "".join(
            f'<method name="{method}" desc="()V">'
            f'<counter type="INSTRUCTION" missed="{missed}" covered="{covered}"/></method>'
            for method, missed, covered in methods
        )
        + "</class>"
        for name, methods in classes.items()
    )
    return f'<?xml version="1.0" ?><report name="Kover"><package name="demo">{body}</package></report>'


def _write_kover(root, folder, classes):
    report = root / folder / "build" / "reports" / "kover" / "report.xml"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(_kover(classes), encoding="utf-8")


def _kotlin_scores(root, source, path="app/src/main/kotlin/demo/Board.kt"):
    file = root / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(source, encoding="utf-8")
    found = analyze_files([file], root, load_bundle(root))
    return [(entry.namespace, entry.name, entry.coverage) for entry in found]


_BOARD_KT = """package demo

fun place(x: Int): Int {
    return x
}

class Board {
    fun tick(): Int {
        return 1
    }

    fun show(a: Int) {
    }

    fun show(a: String) {
    }

    fun clear() {
    }
}
"""


def test_a_kotlin_function_sums_every_report_method_named_after_it_in_its_jvm_class(tmp_path):
    _write_kover(
        tmp_path,
        ".",
        {
            "demo/BoardKt": [("place", 1, 3)],
            "demo/Board": [
                ("tick-Xk2a9", 4, 0),
                ("tick$lambda$0", 0, 2),
                ("tick$default", 0, 2),
                ("ticker", 0, 100),
                ("show", 1, 1),
                ("show", 0, 2),
            ],
        },
    )
    scores = sorted(_kotlin_scores(tmp_path, _BOARD_KT))
    assert scores == [
        ("demo", "place", 75.0),
        ("demo.Board", "clear", 0.0),
        ("demo.Board", "show", 75.0),
        ("demo.Board", "show", 75.0),
        ("demo.Board", "tick", 50.0),
    ]


def test_a_kotlin_function_whose_class_is_absent_from_the_report_scores_zero(tmp_path):
    _write_kover(tmp_path, ".", {"demo/Other": [("place", 0, 5), ("tick", 0, 5)]})
    scores = {name: coverage for _namespace, name, coverage in _kotlin_scores(tmp_path, _BOARD_KT)}
    assert scores == {"place": 0.0, "tick": 0.0, "show": 0.0, "clear": 0.0}


def test_kover_reports_at_the_root_and_two_levels_down_merge_with_jacoco(tmp_path):
    _write_kover(tmp_path, ".", {"demo/BoardKt": [("place", 0, 4)]})
    _write_kover(tmp_path, "app", {"demo/Board": [("tick", 1, 1)]})
    _write_kover(tmp_path, "data/pool", {"demo/Board": [("clear", 3, 1)]})
    jacoco = tmp_path / "target" / "site" / "jacoco" / "jacoco.xml"
    jacoco.parent.mkdir(parents=True)
    jacoco.write_text(
        '<report><class name="demo/Legacy"><method name="run" line="3">'
        '<counter type="INSTRUCTION" missed="0" covered="2"/></method></class></report>',
        encoding="utf-8",
    )
    legacy = tmp_path / "src" / "demo" / "Legacy.java"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("package demo;\nclass Legacy {\n  void run() { }\n}\n", encoding="utf-8")
    board = tmp_path / "app" / "src" / "main" / "kotlin" / "demo" / "Board.kt"
    board.parent.mkdir(parents=True)
    board.write_text(_BOARD_KT, encoding="utf-8")
    found = analyze_files([board, legacy], tmp_path, load_bundle(tmp_path))
    scores = {(entry.namespace, entry.name): entry.coverage for entry in found}
    assert scores[("demo", "place")] == 100.0
    assert scores[("demo.Board", "tick")] == 50.0
    assert scores[("demo.Board", "clear")] == 25.0
    assert scores[("demo.Legacy", "run")] == 100.0


def test_an_interface_default_function_scores_from_the_interface_not_its_default_impls_bridge(tmp_path):
    # Kotlin 2 compiles the body into the interface and leaves a two-instruction
    # bridge in `$DefaultImpls`, as tyche's report shows for `SavedBet.scoreOrNull`.
    _write_kover(
        tmp_path,
        ".",
        {"demo/Saved": [("scoreOrNull", 0, 15)], "demo/Saved$DefaultImpls": [("scoreOrNull", 2, 0)]},
    )
    source = "package demo\n\ninterface Saved {\n    fun scoreOrNull(): Int? {\n        return null\n    }\n}\n"
    assert _kotlin_scores(tmp_path, source) == [("demo.Saved", "scoreOrNull", 100.0)]
