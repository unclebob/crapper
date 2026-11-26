from crapper.coverage import (
    CoverageBundle,
    SwiftFile,
    _go_report_paths,
    _lcov_paths,
    _lookup,
    _merge_forms,
    _merge_jacoco,
    _select_key,
    _subdirs_1_and_2,
    go_percent,
    load_bundle,
    load_form_html,
    load_go_profile,
    load_jacoco,
    load_lcov,
    load_swift,
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


def test_a_single_covered_form_is_kept():
    html = '<span title="1 out of 1 forms covered">   4&nbsp;</span>'
    assert parse_form_coverage(html) == {4: (1, 1)}


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


def test_an_untaken_branch_is_not_a_hit():
    text = "SF:src/demo/app.ts\nDA:3,1\nBRDA:3,0,0,0\nend_of_record\n"
    assert parse_lcov(text)["src/demo/app.ts"].branches[3] == (0, 1)


def test_a_branch_count_that_is_not_a_number_is_ignored():
    text = "SF:src/demo/app.ts\nDA:3,1\nBRDA:3,0,0,nope\nend_of_record\n"
    parsed = parse_lcov(text)["src/demo/app.ts"]
    assert parsed[3] == (1, 1)
    assert 3 not in parsed.branches


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
    assert "src/demo/core.clj" in bundle.form_html
    assert "index" not in bundle.form_html


def _go_module(module_dir, module_line, profile_text):
    module_dir.mkdir(parents=True, exist_ok=True)
    (module_dir / "go.mod").write_text(f"{module_line}\n\ngo 1.21\n", encoding="utf-8")
    profile = module_dir / "target" / "coverage" / "go" / "coverage.out"
    profile.parent.mkdir(parents=True)
    profile.write_text(profile_text, encoding="utf-8")


def test_go_coverage_names_a_nested_file_by_its_module_import_path(tmp_path):
    # `go test` keys a profile by import path. The module is `example.com/api`
    # but its directory is `svc`, so no suffix of `svc/calc/calc.go` names it.
    _go_module(
        tmp_path / "svc",
        "module example.com/api // the service",
        "mode: set\n"
        "example.com/api/calc/calc.go:4.2,4.11 1 1\n"
        "example.com/api/calc/calc.go:5.3,6.1 1 0\n",
    )
    bundle = load_bundle(tmp_path)
    scored = function(language="go", path="svc/calc/calc.go", start_line=3, end_line=7)
    assert bundle.percent_for(scored) == 50.0


def test_go_coverage_reads_a_quoted_module_path(tmp_path):
    _go_module(
        tmp_path / "cli",
        'module "github.com/acme/tool"',
        "mode: set\n"
        "github.com/acme/tool/main.go:1.1,2.2 1 1\n"
        "github.com/acme/tool/cmd/main.go:1.1,2.2 1 0\n",
    )
    bundle = load_bundle(tmp_path)
    assert bundle.percent_for(function(language="go", path="cli/main.go", start_line=1, end_line=2)) == 100.0
    assert bundle.percent_for(function(language="go", path="cli/cmd/main.go", start_line=1, end_line=2)) == 0.0


def test_go_coverage_falls_back_to_the_path_without_a_module_name(tmp_path):
    profile = tmp_path / "target" / "coverage" / "go" / "coverage.out"
    profile.parent.mkdir(parents=True)
    profile.write_text("mode: set\nproj/board.go:1.1,2.2 1 1\n", encoding="utf-8")
    scored = function(language="go", path="board.go", start_line=1, end_line=2)
    assert load_bundle(tmp_path).percent_for(scored) == 100.0
    (tmp_path / "go.mod").write_text("go 1.21\n", encoding="utf-8")
    assert load_bundle(tmp_path).percent_for(scored) == 100.0


def test_lcov_parses_checksum_da_and_ignores_malformed_lines():
    text = "\n".join(
        [
            "SF:src/demo/app.ts",
            "FN:1,choose",
            "DA:3,2,deadbeef",
            "DA:4,0,cafebabe",
            "DA:5",
            "DA:bad,1",
            "DA:6,1abc",
            "DA:-1,1",
            "DA:,1",
            "DA:7,",
            "BRDA:3,0,0,2,extra",
            "BRDA:3,0,1,-",
            "BRDA:4,0,0",
            "BRDA:bad,0,0,1",
            "BRDA:4,0,0,1abc",
            "BRDA:4,0,0,-1",
            "end_of_record",
        ]
    )
    parsed = parse_lcov(text)["src/demo/app.ts"]
    assert dict(parsed) == {3: (1, 1), 4: (0, 1)}
    assert parsed.branches == {3: (1, 2)}


def test_lcov_paths_and_merge_forms_prune_lcov_report_and_skip_dirs(tmp_path):
    kept_files = [
        tmp_path / "target" / "coverage" / "lcov.info",
        tmp_path / "target" / "coverage" / "ts" / "lcov.info",
        tmp_path / "coverage" / "lcov.info",
    ]
    pruned_files = [
        tmp_path / "target" / "coverage" / "lcov-report" / "lcov.info",
        tmp_path / "target" / "coverage" / "node_modules" / "lcov.info",
        tmp_path / "coverage" / "lcov-report" / "lcov.info",
        tmp_path / "coverage" / "dist" / "lcov.info",
    ]
    for path in [*kept_files, *pruned_files]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("SF:src/a.ts\nDA:1,1\nend_of_record\n", encoding="utf-8")
    assert _lcov_paths(tmp_path) == kept_files

    form_kept = tmp_path / "target" / "coverage" / "src" / "a.clj.html"
    form_kept.parent.mkdir(parents=True, exist_ok=True)
    form_kept.write_text('<span title="1 out of 2 forms covered">   4&nbsp;</span>', encoding="utf-8")
    form_kept_b = tmp_path / "target" / "coverage" / "src" / "b.clj.html"
    form_kept_b.write_text('<span title="2 out of 2 forms covered">   5&nbsp;</span>', encoding="utf-8")
    for rel in (
        "target/coverage/lcov-report/ignored.clj.html",
        "target/coverage/build/ignored.clj.html",
    ):
        ignored = tmp_path / rel
        ignored.parent.mkdir(parents=True, exist_ok=True)
        ignored.write_text('<span title="1 out of 1 forms covered">   1&nbsp;</span>', encoding="utf-8")
    assert _merge_forms(tmp_path) == {
        "src/a.clj": {4: (1, 2)},
        "src/b.clj": {5: (2, 2)},
    }
    assert _merge_forms(tmp_path / "missing") == {}


def test_subdirs_and_report_paths_prune_skip_dirs(tmp_path):
    (tmp_path / "README.md").write_text("hi", encoding="utf-8")
    for rel in (
        "svc/target/coverage/go/coverage.out",
        "apps/web/target/coverage/go/coverage.out",
        "node_modules/pkg/target/coverage/go/coverage.out",
        "svc/vendor/target/coverage/go/coverage.out",
        "a/b/c/target/coverage/go/coverage.out",
    ):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("mode: set\n", encoding="utf-8")

    assert _subdirs_1_and_2(tmp_path / "missing") == []
    assert _subdirs_1_and_2(tmp_path) == [
        tmp_path / "a",
        tmp_path / "a" / "b",
        tmp_path / "apps",
        tmp_path / "apps" / "web",
        tmp_path / "svc",
    ]
    go_paths = _go_report_paths(tmp_path)
    assert tmp_path / "svc" / "target" / "coverage" / "go" / "coverage.out" in go_paths
    assert tmp_path / "apps" / "web" / "target" / "coverage" / "go" / "coverage.out" in go_paths
    assert tmp_path / "node_modules" / "pkg" / "target" / "coverage" / "go" / "coverage.out" not in go_paths
    assert tmp_path / "svc" / "vendor" / "target" / "coverage" / "go" / "coverage.out" not in go_paths
    assert tmp_path / "a" / "b" / "c" / "target" / "coverage" / "go" / "coverage.out" not in go_paths

    for rel, method in (
        ("svc/target/site/jacoco/jacoco.xml", "svcRun"),
        ("apps/web/target/site/jacoco/jacoco.xml", "webRun"),
        ("node_modules/x/target/site/jacoco/jacoco.xml", "badNode"),
        ("svc/build/target/site/jacoco/jacoco.xml", "badBuild"),
    ):
        xml = tmp_path / rel
        xml.parent.mkdir(parents=True, exist_ok=True)
        xml.write_text(
            f'<report><class name="demo/App"><method name="{method}" line="1">'
            '<counter type="INSTRUCTION" missed="0" covered="1"/></method></class></report>',
            encoding="utf-8",
        )
    merged_jacoco = _merge_jacoco(tmp_path)
    assert "demo.App#svcRun" in merged_jacoco
    assert "demo.App#webRun" in merged_jacoco
    assert "demo.App#badNode" not in merged_jacoco
    assert "demo.App#badBuild" not in merged_jacoco


def test_public_format_loaders(tmp_path):
    assert load_lcov(tmp_path) == {}
    assert load_go_profile(tmp_path) is None
    assert load_jacoco(tmp_path) is None
    assert load_form_html(tmp_path) == {}
    assert load_swift(tmp_path) == {}

    lcov = tmp_path / "target" / "coverage" / "lcov.info"
    lcov.parent.mkdir(parents=True)
    lcov.write_text("SF:src/demo/core.clj\nDA:3,1\nend_of_record\n", encoding="utf-8")
    go = tmp_path / "coverage.out"
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
    html.write_text('<span title="1 out of 2 forms covered">   3&nbsp;</span>', encoding="utf-8")
    swift = tmp_path / "target" / "coverage" / "swift" / "llvm.json"
    swift.parent.mkdir(parents=True)
    swift.write_text(
        '{"type":"llvm.coverage.json.export","data":[{"files":[{"filename":"Box.swift",'
        '"segments":[[2,1,1,true,true,false]]}],"functions":[]}]}',
        encoding="utf-8",
    )

    bundle = load_bundle(tmp_path)
    assert load_lcov(tmp_path) == bundle.lcov
    assert load_go_profile(tmp_path) == bundle.go_profile
    assert load_jacoco(tmp_path) == bundle.jacoco
    assert load_form_html(tmp_path) == bundle.form_html
    assert load_swift(tmp_path) == bundle.swift


def test_bundle_indexed_lookup_matches_select_key_and_caches(tmp_path):
    lcov_map = {
        "file:./src/exact.py": {1: (1, 1)},
        "src/exact.py": {1: (0, 1)},
        "proj/src/fwd.py": {1: (1, 1)},
        "other/tie/dup.py": {1: (1, 1)},
        "another/tie/dup.py": {1: (0, 1)},
        "a/b/main.py": {1: (1, 1)},
        "rev.py": {1: (1, 1)},
        "": {1: (0, 1)},
    }
    swift_map = {
        "Sources/Demo/Box.swift": SwiftFile(regions=[(1, 5, 1)]),
        "Sources/Demo/Summary.swift": SwiftFile(summaries=[(1, 1, 2)]),
        "Other/Tie.swift": SwiftFile(regions=[(1, 5, 1)]),
        "Another/Tie.swift": SwiftFile(regions=[(1, 5, 0)]),
    }
    bound = ["src/exact.py", "src/fwd.py", "b/main.py", "a/b/main.py", "cmd/rev.py", ""]
    bundle = CoverageBundle(lcov=lcov_map, swift=swift_map)
    snapshot = CoverageBundle(lcov=lcov_map, swift=swift_map)
    bundle.bind_sources(bound)

    queries = [
        "src/exact.py",
        "fwd.py",
        "src/fwd.py",
        "dup.py",
        "b/main.py",
        "a/b/main.py",
        "cmd/rev.py",
        "missing.py",
        "",
    ]
    for query in queries:
        expected_key = _select_key(list(lcov_map), query, bundle.source_parts)
        expected_value = None if expected_key is None else lcov_map[expected_key]
        assert bundle._lcov_lines(query) == expected_value
        assert bundle._lcov_lines(query) == _lookup(lcov_map, query, bundle.source_parts)
        assert bundle._lcov_lines(query) == expected_value

    assert _lookup({}, "src/exact.py", []) is None

    swift_queries = [
        ("Sources/Demo/Box.swift", 100.0),
        ("Demo/Box.swift", 100.0),
        ("Sources/Demo/Summary.swift", 50.0),
        ("Tie.swift", None),
        ("Missing.swift", None),
    ]
    for path, expected in swift_queries:
        fn = function(language="swift", path=path, start_line=1, end_line=5)
        assert bundle.percent_for(fn) == expected
        assert bundle.percent_for(fn) == expected

    bundle.bind_sources(["src/exact.py", "src/fwd.py"])
    assert snapshot._lcov_lines("src/exact.py") == {1: (1, 1)}
    assert snapshot == CoverageBundle(lcov=lcov_map, swift=swift_map)
    assert repr(snapshot) == repr(CoverageBundle(lcov=lcov_map, swift=swift_map))

    direct = CoverageBundle(
        lcov=dict(lcov_map),
        source_parts=[(), ("cmd", "rev.py"), ("other", "rev.py")],
    )
    assert direct._lcov_lines("cmd/rev.py") is None
    direct.source_parts = [("cmd", "rev.py")]
    assert direct._lcov_lines("cmd/rev.py") == {1: (1, 1)}

    direct.lcov["cmd/rev.py"] = {1: (0, 1)}
    assert direct._lcov_lines("cmd/rev.py") == {1: (0, 1)}
    direct.lcov.clear()
    assert direct._lcov_lines("cmd/rev.py") is None
    direct.lcov["cmd/rev.py"] = {1: (1, 1)}
    assert direct._lcov_lines("cmd/rev.py") == {1: (1, 1)}

    _go_module(
        tmp_path / "svc",
        "module example.com/api",
        "mode: set\nexample.com/api/calc.go:1.1,2.2 1 1\n",
    )
    go_bundle = load_bundle(tmp_path)
    go_fn_1 = function(language="go", path="svc/calc.go", start_line=1, end_line=2)
    go_fn_2 = function(language="go", path="svc/calc.go", start_line=1, end_line=2)
    assert go_bundle.percent_for(go_fn_1) == 100.0
    assert go_bundle.percent_for(go_fn_2) == 100.0
    miss_go = function(language="go", path="svc/other.go", start_line=1, end_line=2)
    assert go_bundle.percent_for(miss_go) is None


def test_bundle_fast_candidate_resolution_matches_uncached_candidates(tmp_path, monkeypatch):
    existing = tmp_path / "src" / "pkg" / "live.py"
    existing.parent.mkdir(parents=True)
    existing.write_text("def f():\n    return 1\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    from crapper.coverage import _candidates

    bundle = CoverageBundle()
    cases = [
        "",
        "src/pkg/live.py",
        "./src/pkg/live.py",
        "src/missing/file.py",
        "nonexistent/nested/mod.py",
        "../outside.py",
        str(existing.resolve()),
    ]
    for source_path in cases:
        assert bundle._candidates_for(source_path) == _candidates(source_path)
        assert bundle._candidates_for(source_path) == _candidates(source_path)

    other_dir = tmp_path / "other"
    other_dir.mkdir()
    monkeypatch.chdir(other_dir)
    assert bundle._candidates_for("src/missing/file.py") == _candidates("src/missing/file.py")
