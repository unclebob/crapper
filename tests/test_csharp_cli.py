from crapper.cli import run


def test_csharp_cli_scores_real_source_and_emits_existing_snapshot_contract(tmp_path, capsys):
    source = tmp_path / "src" / "Box.cs"
    source.parent.mkdir()
    source.write_text("namespace Demo; class Box { int Read(bool ok) { if(ok) return 1; return 0; } }", encoding="utf-8")
    report = tmp_path / "target" / "coverage" / "csharp" / "coverage.cobertura.xml"
    report.parent.mkdir(parents=True)
    report.write_text('<coverage><packages><package><classes><class filename="src/Box.cs"><lines><line number="1" hits="1" branch="true" condition-coverage="50% (1/2)"/></lines></class></classes></package></packages></coverage>', encoding="utf-8")
    assert run(["--root", str(tmp_path), "--source-root", "src", "--use-existing-coverage", "--threshold", "2"]) == 2
    snapshot = (tmp_path / ".metrics" / "crap.edn").read_text(encoding="utf-8")
    assert ':namespace "Demo.Box"' in snapshot and ':name "Read"' in snapshot
    assert ':complexity 2' in snapshot and ':coverage 50.0' in snapshot and ':crap 2.5' in snapshot
    assert "CRAP threshold exceeded" in capsys.readouterr().err
    assert run(["--root", str(tmp_path), "--source-root", "src", "--no-coverage"]) == 0
    snapshot = (tmp_path / ".metrics" / "crap.edn").read_text(encoding="utf-8")
    assert ':coverage nil' in snapshot and ':crap nil' in snapshot
