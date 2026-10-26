from pathlib import Path

import pytest

from crapper.runners import run_coverage


@pytest.mark.parametrize("target", ["Demo.sln", "Demo.slnx", "Demo.csproj"])
def test_dotnet_test_uses_one_argument_vector_and_its_own_results(tmp_path, monkeypatch, target):
    source = tmp_path / "Box.cs"
    source.write_text("class Box {}", encoding="utf-8")
    (tmp_path / target).write_text("", encoding="utf-8")
    commands = []
    def run(command, cwd):
        commands.append((command, cwd))
        report = tmp_path / "target" / "coverage" / "csharp" / "run" / "coverage.cobertura.xml"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("<coverage/>", encoding="utf-8")
        return 0
    monkeypatch.setattr("crapper.runners.run_shell", run)
    monkeypatch.setattr("crapper.runners.shutil.which", lambda name: name)
    assert run_coverage(tmp_path, [source], None) == 0
    command, cwd = commands[0]
    assert command[:3] == ["dotnet", "test", str(tmp_path / target)]
    assert command[3:5] == ["--collect", "XPlat Code Coverage"]
    assert command[-2] == "--results-directory"
    assert command[-1] == str(tmp_path / "target" / "coverage" / "csharp")
    assert cwd == tmp_path


def test_failed_dotnet_run_cannot_reuse_stale_coverage(tmp_path, monkeypatch):
    from crapper.cli import _coverage_bundle, parse_args

    source = tmp_path / "Box.cs"
    source.write_text("class Box {}", encoding="utf-8")
    monkeypatch.setattr("crapper.cli.run_coverage", lambda *_: 1)
    monkeypatch.setattr("crapper.cli.load_bundle", lambda *_: (_ for _ in ()).throw(AssertionError("stale reports read")))
    bundle = _coverage_bundle(parse_args([]), tmp_path, [source])
    assert not bundle.cobertura


def test_ambiguous_solutions_require_an_explicit_command(tmp_path, monkeypatch, capsys):
    for name in ("A.sln", "B.slnx"):
        (tmp_path / name).write_text("", encoding="utf-8")
    source = tmp_path / "Box.cs"
    source.write_text("class Box {}", encoding="utf-8")
    monkeypatch.setattr("crapper.runners.run_shell", lambda *_: (_ for _ in ()).throw(AssertionError("must not guess")))
    assert run_coverage(tmp_path, [source], None) != 0
    assert "--coverage-command" in capsys.readouterr().err


def test_missing_dotnet_is_reported_without_installing_dependencies(tmp_path, monkeypatch, capsys):
    (tmp_path / "Demo.sln").write_text("", encoding="utf-8")
    source = tmp_path / "Box.cs"
    source.write_text("class Box {}", encoding="utf-8")
    monkeypatch.setattr("crapper.runners.shutil.which", lambda _: None)
    assert run_coverage(tmp_path, [source], None) != 0
    assert ".NET SDK" in capsys.readouterr().err


def test_no_report_is_not_success_and_unrelated_files_survive(tmp_path, monkeypatch, capsys):
    (tmp_path / "Demo.sln").write_text("", encoding="utf-8")
    source = tmp_path / "Box.cs"
    source.write_text("class Box {}", encoding="utf-8")
    report = tmp_path / "target" / "coverage" / "csharp"
    report.mkdir(parents=True)
    (report / "coverage.cobertura.xml").write_text("<coverage/>", encoding="utf-8")
    (report / "notes.txt").write_text("keep", encoding="utf-8")
    monkeypatch.setattr("crapper.runners.run_shell", lambda *_: 0)
    monkeypatch.setattr("crapper.runners.shutil.which", lambda name: name)
    assert run_coverage(tmp_path, [source], None) == 1
    assert "No C# coverage report" in capsys.readouterr().err
    assert (report / "notes.txt").read_text() == "keep"
    assert not (report / "coverage.cobertura.xml").exists()


def test_simulated_directory_link_fails_before_collection(tmp_path, monkeypatch):
    (tmp_path / "Demo.sln").write_text("", encoding="utf-8")
    source = tmp_path / "Box.cs"
    source.write_text("class Box {}", encoding="utf-8")
    report = tmp_path / "target" / "coverage" / "csharp"
    original = Path.resolve
    monkeypatch.setattr(Path, "resolve", lambda path: tmp_path / "elsewhere" if path == report else original(path))
    monkeypatch.setattr("crapper.runners.shutil.which", lambda name: name)
    monkeypatch.setattr("crapper.runners.run_shell", lambda *_: (_ for _ in ()).throw(AssertionError("linked output must not run")))
    assert run_coverage(tmp_path, [source], None) == 1


def test_simulated_file_link_is_preserved_during_collection(tmp_path, monkeypatch):
    (tmp_path / "Demo.sln").write_text("", encoding="utf-8")
    source = tmp_path / "Box.cs"
    source.write_text("class Box {}", encoding="utf-8")
    report = tmp_path / "target" / "coverage" / "csharp" / "coverage.cobertura.xml"
    report.parent.mkdir(parents=True)
    report.write_text("keep", encoding="utf-8")
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == report or original(path))
    monkeypatch.setattr("crapper.runners.shutil.which", lambda name: name)
    monkeypatch.setattr("crapper.runners.run_shell", lambda *_: 9)
    assert run_coverage(tmp_path, [source], None) == 9
    assert report.read_text() == "keep"


def test_successful_custom_command_does_not_report_failure(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("crapper.runners.run_shell", lambda *_: 0)
    assert run_coverage(tmp_path, [], "custom coverage") == 0
    assert "Reports already on disk will not be read" not in capsys.readouterr().err
