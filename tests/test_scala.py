from pathlib import Path

from crapper.coverage import CoverageBundle, load_bundle
from crapper.discover import is_test_file, language_of
from crapper.strategies import STRATEGIES, strategy_for
from crapper.strategies.scala import (
    ScalaStrategy,
    functions_in_source,
    parse_scoverage,
    scoverage_reports,
)

SCORE = """
package demo
package board

class Board(size: Int) {
  def this() = this(8)

  def score(a: Boolean, b: Boolean, values: Seq[Int]): Int = {
    while (a) {}
    do {} while (b)
    for (v <- values if v > 0) yield v
    if (a && b || values.nonEmpty) 1 else 0
    values.headOption match {
      case Some(v) if v > 1 => v
      case _                => 0
    }
    try 1 catch { case e: Exception => 2 }
  }

  def abstractOne(): Int

  def withLambda(xs: Seq[Int]): Seq[Int] = xs.map(x => if (x > 0) x else -x)

  def outer(k: Int): Int = {
    def inner(j: Int): Int = if (j > 0) j else 0
    inner(k) + 1
  }

  object Moves {
    def legal(n: Int): Boolean = n > 0 && n < size
  }

  def +(other: Board): Board = if (other.size > size) other else this
}

trait Rules {
  def check(): Boolean = true
}
"""


def _by_name(found):
    return {f.name: f for f in found}


def test_counts_crappers_decision_points():
    found = _by_name(functions_in_source(SCORE, "src/demo/Board.scala"))
    # 1 + while + do + for + guard + if + && + || + 2 cases + guard + 1 catch case
    assert found["score"].complexity == 12


def test_function_literals_count_toward_the_enclosing_method():
    found = _by_name(functions_in_source(SCORE, "src/demo/Board.scala"))
    assert found["withLambda"].complexity == 2


def test_local_methods_are_scored_on_their_own():
    found = _by_name(functions_in_source(SCORE, "src/demo/Board.scala"))
    assert found["outer"].complexity == 1
    assert found["outer.inner"].complexity == 2


def test_namespaces_follow_packages_and_enclosing_types():
    found = _by_name(functions_in_source(SCORE, "src/demo/Board.scala"))
    assert found["score"].namespace == "demo.board.Board"
    assert found["legal"].namespace == "demo.board.Board.Moves"
    assert found["legal"].complexity == 2
    assert found["check"].namespace == "demo.board.Rules"


def test_operator_methods_are_scored():
    found = _by_name(functions_in_source(SCORE, "src/demo/Board.scala"))
    assert found["+"].complexity == 2


def test_constructors_and_abstract_methods_are_ignored():
    names = {f.name for f in functions_in_source(SCORE, "src/demo/Board.scala")}
    assert "this" not in names
    assert "abstractOne" not in names


def test_methods_carry_their_byte_span_and_language():
    found = _by_name(functions_in_source(SCORE, "src/demo/Board.scala"))
    score = found["score"]
    assert score.language == "scala"
    assert SCORE.encode()[score.start_byte : score.end_byte].startswith(b"def score")


def test_scala_is_a_registered_strategy():
    assert isinstance(strategy_for("scala"), ScalaStrategy)
    assert "scala" in STRATEGIES
    assert language_of("src/main/scala/demo/Board.scala") == "scala"


def test_scala_test_sources_are_recognized():
    assert is_test_file("src/demo/BoardSuite.scala")
    assert is_test_file("src/demo/BoardSpec.scala")
    assert not is_test_file("src/main/scala/demo/Board.scala")


SOURCE = """package demo

object Calc {
  def twice(x: Int): Int = {
    def add(y: Int): Int = y + y
    add(x)
  }

  def unused(x: Int): Int = x * 3
}
"""


def _report(source_path: str) -> str:
    """scoverage XML: twice's own call is invoked, add's statement is not, unused is not."""

    add_start = SOURCE.index("y + y")
    call_start = SOURCE.index("add(x)")
    unused_start = SOURCE.index("x * 3")
    statement = (
        '<statement source="{src}" start="{start}" end="{end}" '
        'invocation-count="{count}" ignored="false"></statement>'
    )
    return (
        "<scoverage><packages><package><classes><class><methods><method><statements>"
        + statement.format(src=source_path, start=add_start, end=add_start + 5, count=0)
        + statement.format(src=source_path, start=call_start, end=call_start + 6, count=3)
        + statement.format(src=source_path, start=unused_start, end=unused_start + 5, count=0)
        + statement.format(src=source_path, start=0, end=1, count=1).replace(
            'ignored="false"', 'ignored="true"'
        )
        + "</statements></method></methods></class></classes></package></packages></scoverage>"
    )


def _project(tmp_path: Path) -> Path:
    source = tmp_path / "src" / "main" / "scala" / "demo" / "Calc.scala"
    source.parent.mkdir(parents=True)
    source.write_text(SOURCE)
    report = tmp_path / "out" / "core" / "scoverage" / "xmlReport.dest" / "scoverage.xml"
    report.parent.mkdir(parents=True)
    report.write_text(_report(str(source)))
    return tmp_path


def test_parse_scoverage_skips_ignored_statements():
    statements = parse_scoverage(_report("/p/Calc.scala"))["/p/Calc.scala"]
    assert len(statements) == 3
    assert sum(hit for _, hit in statements.values()) == 1


def test_statements_sharing_a_span_each_count():
    statement = '<statement source="/p/A.scala" start="5" end="9" invocation-count="{n}" ignored="false"/>'
    statements = parse_scoverage(
        "<scoverage>" + statement.format(n=1) + statement.format(n=0) + "</scoverage>"
    )["/p/A.scala"]
    assert statements[(5, 9)] == (2, 1)


def test_the_same_statements_in_two_reports_are_not_counted_twice(tmp_path):
    project = _project(tmp_path)
    aggregate = project / "out" / "scoverage" / "xmlReportAll.dest" / "scoverage.xml"
    aggregate.parent.mkdir(parents=True)
    aggregate.write_text((project / "out" / "core" / "scoverage" / "xmlReport.dest" / "scoverage.xml").read_text())
    bundle = load_bundle(project)
    path = "src/main/scala/demo/Calc.scala"
    bundle.bind_sources([path])
    found = _by_name(functions_in_source(SOURCE, path))
    assert bundle.percent_for(found["twice"]) == 100.0
    assert bundle.percent_for(found["unused"]) == 0.0


def test_finds_mill_and_sbt_reports(tmp_path):
    project = _project(tmp_path)
    sbt = project / "target" / "scala-2.13" / "scoverage-report" / "scoverage.xml"
    sbt.parent.mkdir(parents=True)
    sbt.write_text("<scoverage/>")
    assert len(scoverage_reports(project)) == 2


def test_statements_count_for_the_innermost_method(tmp_path):
    project = _project(tmp_path)
    bundle = load_bundle(project)
    path = "src/main/scala/demo/Calc.scala"
    bundle.bind_sources([path])
    found = _by_name(functions_in_source(SOURCE, path))

    assert bundle.percent_for(found["twice"]) == 100.0
    assert bundle.percent_for(found["twice.add"]) == 0.0
    assert bundle.percent_for(found["unused"]) == 0.0


def test_a_source_the_report_does_not_mention_has_no_coverage(tmp_path):
    project = _project(tmp_path)
    bundle = load_bundle(project)
    other = functions_in_source("object Other { def f = 1 }", "src/main/scala/demo/Other.scala")
    assert bundle.percent_for(other[0]) is None


def test_no_report_means_no_scala_coverage(tmp_path):
    assert ScalaStrategy().load_coverage(tmp_path) is None
    bundle = CoverageBundle()
    found = functions_in_source(SOURCE, "src/main/scala/demo/Calc.scala")
    assert bundle.percent_for(found[0]) is None


def test_non_ascii_sources_map_character_offsets_to_bytes(tmp_path):
    source = 'package demo\n\nobject Å {\n  def twice(x: Int): Int = {\n    val s = "ü"\n    x + x\n  }\n}\n'
    file = tmp_path / "src" / "main" / "scala" / "demo" / "A.scala"
    file.parent.mkdir(parents=True)
    file.write_text(source)
    start = source.index("x + x")  # a character offset, as scoverage writes it
    report = tmp_path / "out" / "scoverage.xml"
    report.parent.mkdir()
    report.write_text(
        f'<scoverage><statement source="{file}" start="{start}" end="{start + 5}" '
        'invocation-count="1" ignored="false"/></scoverage>'
    )
    bundle = load_bundle(tmp_path)
    path = "src/main/scala/demo/A.scala"
    bundle.bind_sources([path])
    twice = functions_in_source(source, path)[0]
    assert twice.namespace == "demo.Å"
    assert bundle.percent_for(twice) == 100.0


def test_package_blocks_scope_their_contents():
    found = functions_in_source(
        "package a {\n  object One { def f = 1 }\n}\npackage b {\n  object Two { def g = 2 }\n}\n",
        "src/Blocks.scala",
    )
    assert {(f.namespace, f.name) for f in found} == {("a.One", "f"), ("b.Two", "g")}


def test_top_level_methods_use_the_file_name_without_a_package():
    found = functions_in_source("def main(): Unit = ()\n", "scripts/tool.scala")
    assert found[0].namespace == "tool"


class _Recorder:
    def __init__(self, code: int = 0):
        self.code = code
        self.commands: list[list[str]] = []

    def __call__(self, command, cwd):
        self.commands.append(list(command))
        return self.code


def _recording(monkeypatch, code: int = 0) -> _Recorder:
    recorder = _Recorder(code)
    monkeypatch.setattr("crapper.runners.run_shell", recorder)
    return recorder


def test_mill_runs_the_tests_then_the_module_reports(tmp_path, monkeypatch):
    (tmp_path / "build.mill").write_text("")
    (tmp_path / "mill").write_text("")
    stale = tmp_path / "out" / "core" / "scoverage" / "data.dest" / "scoverage.measurements.1"
    stale.parent.mkdir(parents=True)
    stale.write_text("1\n")
    recorder = _recording(monkeypatch)

    ScalaStrategy().run_coverage(tmp_path, [])

    assert recorder.commands == [
        ["./mill", "--ticker", "false", "__.test"],
        ["./mill", "--ticker", "false", "__.scoverage.xmlReport"],
    ]
    assert not stale.exists()


def test_mill_skips_the_report_when_the_tests_fail(tmp_path, monkeypatch, capsys):
    (tmp_path / "build.sc").write_text("")
    recorder = _recording(monkeypatch, code=1)

    ScalaStrategy().run_coverage(tmp_path, [])

    assert recorder.commands == [["mill", "--ticker", "false", "__.test"]]
    assert "Scala coverage exited 1" in capsys.readouterr().err


def test_sbt_1_uses_test(tmp_path, monkeypatch):
    (tmp_path / "build.sbt").write_text("")
    recorder = _recording(monkeypatch)

    ScalaStrategy().run_coverage(tmp_path, [])

    assert recorder.commands == [["sbt", "coverage; test; coverageReport"]]


def test_sbt_2_uses_testFull(tmp_path, monkeypatch):
    (tmp_path / "build.sbt").write_text("")
    (tmp_path / "project").mkdir()
    (tmp_path / "project" / "build.properties").write_text("sbt.version = 2.0.2\n")
    recorder = _recording(monkeypatch)

    ScalaStrategy().run_coverage(tmp_path, [])

    assert recorder.commands == [["sbt", "coverage; testFull; coverageReport"]]


def test_no_scala_build_is_reported(tmp_path, monkeypatch, capsys):
    recorder = _recording(monkeypatch)

    ScalaStrategy().run_coverage(tmp_path, [])

    assert recorder.commands == []
    assert "skipping Scala coverage" in capsys.readouterr().err


def test_the_runner_asks_each_strategy_for_its_languages(tmp_path, monkeypatch):
    from crapper.runners import _cover_strategies

    called = []
    monkeypatch.setattr(ScalaStrategy, "run_coverage", lambda self, root, files: called.append(root))
    _cover_strategies(tmp_path, [], {"java"})
    assert called == []
    _cover_strategies(tmp_path, [], {"scala"})
    assert called == [tmp_path]
