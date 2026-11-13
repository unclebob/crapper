from pathlib import Path

from crapper import runners
from crapper.cli import run
from crapper.dart_coverage import absolute_sources, dart_command

FLUTTER_PUBSPEC = """name: app
dependencies:
  flutter:
    sdk: flutter
"""

SOURCE = "int pick(bool a) {\n  if (a) {\n    return 1;\n  }\n  return 2;\n}\n"


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_dart_command_for_flutter_and_plain_packages(tmp_path):
    app = tmp_path / "app"
    core = tmp_path / "core"
    _write(app / "pubspec.yaml", FLUTTER_PUBSPEC)
    _write(core / "pubspec.yaml", "name: core\n")
    report = tmp_path / "lcov.info"
    assert dart_command(app, report) == [
        "flutter", "test", "--coverage", "--coverage-path", str(report),
    ]
    assert dart_command(core, report) == ["dart", "test", "--coverage-path", str(report)]


def test_relative_sources_become_absolute(tmp_path):
    text = "SF:lib/a.dart\nDA:1,1\nend_of_record\nSF:/abs/x.dart\nDA:1,0\nend_of_record\n"
    assert absolute_sources(text, tmp_path) == (
        f"SF:{tmp_path / 'lib' / 'a.dart'}\nDA:1,1\nend_of_record\n"
        "SF:/abs/x.dart\nDA:1,0\nend_of_record\n"
    )


def _edn(root: Path) -> str:
    return (root / ".metrics" / "crap.edn").read_text(encoding="utf-8")


def test_two_packages_with_the_same_relative_file(tmp_path):
    for name, hits in (("one", "1"), ("two", "0")):
        package = tmp_path / "packages" / name
        _write(package / "pubspec.yaml", f"name: {name}\n")
        _write(package / "lib" / "a.dart", SOURCE)
        lines = "".join(f"DA:{line},{hits}\n" for line in (1, 2, 3, 5))
        _write(package / "coverage" / "lcov.info", f"SF:lib/a.dart\n{lines}end_of_record\n")
    assert run(["--root", str(tmp_path), "--use-existing-coverage"]) == 0
    text = _edn(tmp_path)
    one, two = text.index('"one.a"'), text.index('"two.a"')
    first, second = sorted([one, two])
    covered_first = ":coverage 100.0" in text[first:second]
    assert covered_first == (first == one)
    assert ":coverage 0.0" in text


def test_missing_flutter_warns_and_continues(tmp_path, monkeypatch, capsys):
    app = tmp_path / "app"
    _write(app / "pubspec.yaml", FLUTTER_PUBSPEC)
    file = _write(app / "lib" / "a.dart", SOURCE)
    monkeypatch.setattr(runners.shutil, "which", lambda name: None)

    def no_run(command, cwd):
        raise AssertionError(f"ran {command}")

    monkeypatch.setattr(runners, "run_shell", no_run)
    assert runners.run_coverage(tmp_path, [file], None) == 0
    assert "flutter is not on PATH" in capsys.readouterr().err


def test_dart_run_rewrites_the_report(tmp_path, monkeypatch):
    core = tmp_path / "core"
    _write(core / "pubspec.yaml", "name: core\n")
    file = _write(core / "lib" / "a.dart", SOURCE)
    monkeypatch.setattr(runners.shutil, "which", lambda name: "/bin/" + name)

    def fake_run(command, cwd):
        _write(Path(command[-1]), "SF:lib/a.dart\nDA:1,1\nend_of_record\n")
        return 0

    monkeypatch.setattr(runners, "run_shell", fake_run)
    runners.run_coverage(tmp_path, [file], None)
    report = tmp_path / "target" / "coverage" / "dart" / "core" / "lcov.info"
    assert report.read_text(encoding="utf-8").startswith(f"SF:{core.resolve() / 'lib' / 'a.dart'}\n")


def test_cli_reports_dart_functions_with_coverage(tmp_path):
    _write(tmp_path / "pubspec.yaml", "name: demo\n")
    _write(tmp_path / "lib" / "a.dart", SOURCE)
    _write(
        tmp_path / "coverage" / "lcov.info",
        "SF:lib/a.dart\nDA:1,1\nDA:2,1\nDA:3,0\nDA:5,1\nend_of_record\n",
    )
    assert run(["--root", str(tmp_path), "--use-existing-coverage"]) == 0
    text = _edn(tmp_path)
    assert '"demo.a"' in text
    assert '"pick"' in text
    assert ":complexity 2" in text
    assert ":coverage 75.0" in text


def test_fresh_report_wins_over_package_coverage(tmp_path):
    _write(tmp_path / "pubspec.yaml", "name: demo\n")
    _write(tmp_path / "lib" / "a.dart", "int f() {\n  return 1;\n}\n")
    source = (tmp_path / "lib" / "a.dart").resolve()
    _write(
        tmp_path / "target" / "coverage" / "dart" / "lcov.info",
        f"SF:{source}\nDA:1,1\nDA:2,1\nend_of_record\n",
    )
    _write(tmp_path / "coverage" / "lcov.info", "SF:lib/a.dart\nDA:1,0\nDA:2,0\nend_of_record\n")
    assert run(["--root", str(tmp_path), "--use-existing-coverage"]) == 0
    assert ":coverage 100.0" in _edn(tmp_path)


def test_missing_tool_removes_the_old_report(tmp_path, monkeypatch):
    core = tmp_path / "core"
    _write(core / "pubspec.yaml", "name: core\n")
    file = _write(core / "lib" / "a.dart", SOURCE)
    old = _write(tmp_path / "target" / "coverage" / "dart" / "core" / "lcov.info", "SF:x\nend_of_record\n")
    monkeypatch.setattr(runners.shutil, "which", lambda name: None)
    runners.run_coverage(tmp_path, [file], None)
    assert not old.exists()
