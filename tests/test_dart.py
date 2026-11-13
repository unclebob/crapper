from pathlib import Path

from crapper.discover import is_test_file, iter_source_files, language_of
from crapper.languages.dart import functions_in_source

BOARD = """
int top(int a) {
  return a;
}

int arrow(int a) => a + 1;

class Board {
  int _size = 0;
  Board(int s) {
    _size = s;
  }
  factory Board.fromJson(Map<String, dynamic> j) {
    return Board(j['s']);
  }
  int get size => _size;
  set size(int v) {
    _size = v;
  }
  Board operator +(Board o) => Board(_size + o._size);
  static int s(int x) {
    return x;
  }
  external int ext();
}

abstract class Shape {
  void abs();
}

class P {
  factory P(int a) => P._();
  int operator [](int i) => i;
}

mixin M {
  void m() {}
}

extension E on String {
  String shout() => toUpperCase();
}

extension on int {
  int twice() => this * 2;
}

enum Color {
  red;
  String hex() => '#f00';
}
"""

SCORE = """
int f(int a, bool b, bool c, List<int> xs, int? x, String? s) {
  if (a > 0) {}
  for (var i = 0; i < 2; i++) {}
  while (b) {}
  do {} while (c);
  try {} catch (e) {}
  var t = b ? 1 : 2;
  switch (a) {
    case 1:
      break;
    case 2:
      break;
    default:
      break;
  }
  var r = switch (a) { 1 => 'a', _ => 'b' };
  var l = b && c && b;
  var o = b || c;
  var n = x ?? 0;
  var len = s?.length;
  var li = [if (b) 1, for (var z in xs) z];
  return a;
}
"""


def _package(tmp_path: Path, relative: str, source: str) -> tuple[str, str]:
    (tmp_path / "pubspec.yaml").write_text("name: demo\nenvironment:\n  sdk: ^3.0.0\n")
    file = tmp_path / relative
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(source)
    return relative, str(tmp_path)


def _rows(tmp_path: Path, relative: str, source: str) -> list[tuple[str, str]]:
    path, root = _package(tmp_path, relative, source)
    return [(f.namespace, f.name) for f in functions_in_source(source, path, root)]


def test_dart_entries_and_names(tmp_path):
    assert _rows(tmp_path, "lib/src/board.dart", BOARD) == [
        ("demo.src.board", "top"),
        ("demo.src.board", "arrow"),
        ("demo.src.board.Board", "fromJson"),
        ("demo.src.board.Board", "size"),
        ("demo.src.board.Board", "size="),
        ("demo.src.board.Board", "operator +"),
        ("demo.src.board.Board", "s"),
        ("demo.src.board.P", "P"),
        ("demo.src.board.P", "operator []"),
        ("demo.src.board.M", "m"),
        ("demo.src.board.E", "shout"),
        ("demo.src.board.extension", "twice"),
        ("demo.src.board.Color", "hex"),
    ]


def test_dart_functions_carry_language_and_path(tmp_path):
    path, root = _package(tmp_path, "lib/a.dart", "int top() => 1;\n")
    [function] = functions_in_source("int top() => 1;\n", path, root)
    assert function.language == "dart"
    assert function.path == "lib/a.dart"
    assert function.jacoco_class is None


def test_dart_local_functions_and_closures_stay_inside(tmp_path):
    source = """
int s() {
  var f = (int y) => y > 0 ? 1 : 2;
  int local() { return 1; }
  return f(1);
}
"""
    path, root = _package(tmp_path, "lib/a.dart", source)
    [function] = functions_in_source(source, path, root)
    assert (function.name, function.complexity) == ("s", 2)


def test_dart_complexity_counts_each_decision(tmp_path):
    path, root = _package(tmp_path, "lib/a.dart", SCORE)
    [function] = functions_in_source(SCORE, path, root)
    # 1 + if, for, while, do, catch, ?:, 2 case + default, 2 switch arms,
    # 2 &&, 1 ||, ??, ?., if element, for element
    assert function.complexity == 1 + 6 + 3 + 2 + 3 + 2 + 2


def test_dart_span_starts_at_the_signature(tmp_path):
    source = """class A {
  @override
  String toString() {
    return 'a';
  }
}
"""
    path, root = _package(tmp_path, "lib/a.dart", source)
    [function] = functions_in_source(source, path, root)
    assert (function.start_line, function.end_line) == (3, 5)


def test_dart_comment_between_signature_and_body_keeps_the_entry(tmp_path):
    source = """class A {
  int size() // the size
  {
    return 1;
  }
}
"""
    path, root = _package(tmp_path, "lib/a.dart", source)
    [function] = functions_in_source(source, path, root)
    assert (function.name, function.start_line, function.end_line) == ("size", 2, 5)


def test_dart_namespace_without_lib(tmp_path):
    assert _rows(tmp_path, "bin/tool.dart", "void main() {}\n") == [("demo.bin.tool", "main")]


def test_dart_namespace_without_pubspec(tmp_path):
    source = "void main() {}\n"
    (tmp_path / "tool").mkdir()
    (tmp_path / "tool" / "run.dart").write_text(source)
    [function] = functions_in_source(source, "tool/run.dart", str(tmp_path))
    assert function.namespace == "tool.run"


def test_dart_nested_package_uses_the_nearest_pubspec(tmp_path):
    (tmp_path / "pubspec.yaml").write_text("name: workspace\n")
    package = tmp_path / "packages" / "core"
    (package / "lib").mkdir(parents=True)
    (package / "pubspec.yaml").write_text("name: 'gap_core'\n")
    (package / "lib" / "user.dart").write_text("void a() {}\n")
    [function] = functions_in_source("void a() {}\n", "packages/core/lib/user.dart", str(tmp_path))
    assert function.namespace == "gap_core.user"


def test_dart_detection(tmp_path):
    assert language_of("a.dart") == "dart"
    assert language_of("lib/a.g.dart") is None
    assert language_of("lib/a.freezed.dart") is None
    assert language_of("lib/a.mocks.dart") is None
    assert language_of("lib/a.pb.dart") is None
    assert is_test_file("lib/a_test.dart")
    assert is_test_file("integration_test/x.dart")
    assert is_test_file("test_driver/x.dart")
    for name in ("lib/a.dart", ".dart_tool/x.dart", "integration_test/y.dart", "lib/b.g.dart"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("void a() {}\n")
    assert [p.name for p in iter_source_files([tmp_path])] == ["a.dart"]


def test_dart_broken_source_does_not_raise(tmp_path):
    source = "int a() {\n  return 1 +;\n}\n\nint b() {\n  return 2;\n}\n"
    path, root = _package(tmp_path, "lib/a.dart", source)
    names = [f.name for f in functions_in_source(source, path, root)]
    assert "b" in names
    unparsable = "int a( {\n  return 1;\n}\n"
    assert isinstance(functions_in_source(unparsable, path, root), list)


def test_help_mentions_dart(capsys):
    from crapper.cli import run

    assert run(["--help"]) == 0
    text = capsys.readouterr().out
    assert "Dart (.dart)" in text
    assert "flutter test --coverage" in text
    assert "*_test.dart" in text
    assert "*.g.dart" in text


def test_dart_on_handlers_count_like_catch(tmp_path):
    source = "void f() {\n  try {} on E {} on F catch (e) {} catch (e, s) {} finally {}\n}\n"
    path, root = _package(tmp_path, "lib/a.dart", source)
    [function] = functions_in_source(source, path, root)
    assert function.complexity == 4


def test_dart_extension_type_is_a_namespace(tmp_path):
    source = "extension type Meters(int v) {\n  int twice() => v * 2;\n}\n"
    assert _rows(tmp_path, "lib/a.dart", source) == [("demo.a.Meters", "twice")]


def test_dart_test_folders_do_not_skip_other_languages(tmp_path):
    assert not is_test_file("integration_test/tool.go")
    assert is_test_file("integration_test/app.dart")
    (tmp_path / "integration_test").mkdir()
    (tmp_path / "integration_test" / "tool.go").write_text("package x\n")
    (tmp_path / "integration_test" / "app.dart").write_text("void a() {}\n")
    assert [p.name for p in iter_source_files([tmp_path])] == ["tool.go"]
