import pytest

from crapper.coverage import (
    CoverageBundle,
    go_percent,
    load_bundle,
    parse_form_coverage,
    parse_go_profile,
    parse_hpc_markup,
    parse_d_coverage,
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


def test_hpc_markup_counts_expressions_and_partial_booleans():
    html = """\
<span class="lineno">    4 </span><span class="istickedoff">choose ok =</span>
<span class="lineno">    5 </span><span class="istickedoff">if <span class="tickonlytrue">ok</span></span>
<span class="lineno">    7 </span><span class="istickedoff">else <span class="nottickedoff">0</span></span>
"""
    assert parse_hpc_markup(html) == {4: (1, 1), 5: (2, 3), 7: (1, 2)}


def test_d_listing_counts_executable_lines_and_keeps_the_source_path():
    listing = """\
       |module demo.board;
      3|int choose(bool ok) {
0000000|  if (ok) return 1;
      2|  return 0;
       |}
source/demo/board.d is 66% covered
"""
    assert parse_d_coverage(listing) == (
        "source/demo/board.d",
        {2: (1, 1), 3: (0, 1), 4: (1, 1)},
    )


def test_load_bundle_reads_d_coverage_listings(tmp_path):
    report = tmp_path / "target" / "coverage" / "d" / "compiler-a.lst"
    report.parent.mkdir(parents=True)
    report.write_text(
        "       |module demo.board;\n"
        "      1|int choose(bool ok) {\n"
        "0000000|  return ok ? 1 : 0;\n"
        "       |}\n"
        "source/demo/board.d is 50% covered\n",
        encoding="utf-8",
    )
    report.with_name("compiler-b.lst").write_text(
        "       |module demo.board;\n"
        "0000000|int choose(bool ok) {\n"
        "      1|  return ok ? 1 : 0;\n"
        "       |}\n"
        "source/demo/board.d is 50% covered\n",
        encoding="utf-8",
    )
    scored = function(
        path="source/demo/board.d",
        language="d",
        namespace="demo.board",
        start_line=2,
        end_line=3,
    )
    assert load_bundle(tmp_path).percent_for(scored) == 100.0


def _write_hpc(tmp_path, package, module):
    markup = (
        tmp_path
        / f"dist-newstyle/build/x/ghc/{package}/t/test/hpc/vanilla/html"
        / f"{package}-inplace/{module}.hs.html"
    )
    markup.parent.mkdir(parents=True, exist_ok=True)
    markup.write_text(
        '<span class="lineno">    4 </span><span class="istickedoff">choose ok =</span>\n'
        '<span class="lineno">    5 </span><span class="nottickedoff">0</span>\n',
        encoding="utf-8",
    )


def _haskell_function(path, namespace):
    return function(
        path=path,
        language="haskell",
        namespace=namespace,
        start_line=4,
        end_line=5,
    )


@pytest.mark.parametrize(
    "package,module,path,namespace",
    [
        ("demo", "Demo", "src/Demo.hs", "Demo"),
        (
            "hbs2-core",
            "HBS2.Storage.Inventory",
            "hbs2-core/lib/HBS2/Storage/Inventory.hs",
            "HBS2.Storage.Inventory",
        ),
        (
            "demo",
            "Demo.Store",
            "demo/lib/Demo/Store.hs",
            "Demo.Store.HasStore MemoryStore",
        ),
    ],
)
def test_load_bundle_maps_cabal_hpc_module_names(
    tmp_path, package, module, path, namespace
):
    _write_hpc(tmp_path, package, module)
    scored = _haskell_function(path, namespace)
    assert load_bundle(tmp_path).percent_for(scored) == 50.0


def test_hpc_module_lookup_uses_package_and_refuses_an_ambiguous_module(tmp_path):
    _write_hpc(tmp_path, "alpha", "Shared.Store")
    _write_hpc(tmp_path, "beta", "Shared.Store")
    owned = _haskell_function("beta/lib/Shared/Store.hs", "Shared.Store")
    ambiguous = _haskell_function("gamma/lib/Shared/Store.hs", "Shared.Store")
    bundle = load_bundle(tmp_path)
    assert bundle.percent_for(owned) == 50.0
    assert bundle.percent_for(ambiguous) is None


def test_headerless_haskell_uses_main_for_hpc_without_changing_uml_namespace(tmp_path):
    _write_hpc(tmp_path, "demo", "Main")
    scored = _haskell_function("app/Runner.hs", "app.Runner")
    scored = Function(**{**scored.__dict__, "coverage_module": "Main"})
    assert load_bundle(tmp_path).percent_for(scored) == 50.0


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
