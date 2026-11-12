import subprocess
from pathlib import Path

from crapper.coverage import parse_lcov
from crapper.languages.swift_coverage import convert, lcov_path


def _write(root: Path, relative: str, text: str = "") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _derived_data(root: Path, name: str = "DerivedData", device: str = "B2F2EDFE") -> Path:
    """What `xcodebuild test -enableCodeCoverage YES -derivedDataPath ...` leaves."""

    derived = root / "target" / "coverage" / "swift" / name
    profile = _write(derived, f"Build/ProfileData/{device}/Coverage.profdata", "profile")
    products = derived / "Build" / "Products" / "Debug-iphonesimulator"
    _write(products, "PoolTests.xctest/PoolTests", "binary")
    _write(products, "Tyche.app/Tyche", "binary")
    _write(products, "Tyche.app/Tyche.debug.dylib", "binary")
    _write(products, "Tyche.app/PlugIns/TycheTests.xctest/TycheTests", "binary")
    _write(products, "Pool.o", "object")
    return profile


def _record(path: Path | str, lines: dict[int, int]) -> str:
    """One file as `llvm-cov export -format=lcov` writes it: a DA line per executable line."""

    body = "".join(f"DA:{number},{hits}\n" for number, hits in lines.items())
    return f"SF:{path}\nFN:2,place\nFNDA:1,place\n{body}LF:{len(lines)}\nLH:0\nend_of_record\n"


def _fake_llvm_cov(monkeypatch, exports: dict[Path, str], calls: list | None = None):
    """`xcrun` is on the PATH and prints `exports[profile]` for each profile."""

    def run(command, **_kwargs):
        if calls is not None:
            calls.append(command)
        profile = Path(command[command.index("-instr-profile") + 1])
        return subprocess.CompletedProcess(command, 0, stdout=exports[profile], stderr="")

    monkeypatch.setattr("crapper.languages.swift_coverage.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("crapper.languages.swift_coverage.subprocess.run", run)


def _converted(root: Path) -> dict:
    return {path: dict(record) for path, record in parse_lcov(lcov_path(root).read_text()).items()}


def test_only_the_executable_lines_of_the_scored_files_are_written(tmp_path, monkeypatch):
    board = _write(tmp_path, "Pool/Sources/Pool/Board.swift")
    profile = _derived_data(tmp_path)
    _fake_llvm_cov(
        monkeypatch,
        {
            profile: _record(board, {2: 3, 3: 0})
            + _record(tmp_path / "Pool/Tests/PoolTests/BoardTests.swift", {1: 5})
            + _record("/Users/ci/checkouts/Lib/Sources/Lib/Lib.swift", {1: 5})
        },
    )
    convert(tmp_path, [board])
    assert _converted(tmp_path) == {str(board): {2: (1, 1), 3: (0, 1)}}


def test_a_file_in_two_inputs_is_covered_where_either_covers_it(tmp_path, monkeypatch):
    board = _write(tmp_path, "Pool/Sources/Pool/Board.swift")
    first = _derived_data(tmp_path, device="IPHONE")
    second = _derived_data(tmp_path, device="IPAD")
    _fake_llvm_cov(
        monkeypatch,
        {
            first: _record(board, {2: 1, 3: 0, 4: 0}),
            # One input can list a file once per binary it is linked into.
            second: _record(board, {2: 0, 3: 2}) + _record(board, {4: 0, 5: 0}),
        },
    )
    convert(tmp_path, [board])
    assert _converted(tmp_path) == {str(board): {2: (1, 1), 3: (1, 1), 4: (0, 1), 5: (0, 1)}}


def test_absolute_paths_are_kept_and_score_the_function_they_name(tmp_path, monkeypatch):
    from crapper.analyze import analyze_files
    from crapper.coverage import load_bundle

    source = "func place(_ open: Bool) -> Int {\n    if open { return 1 }\n    return 0\n}\n"
    board = _write(tmp_path, "Pool/Sources/Pool/Board.swift", source)
    other = _write(tmp_path, "UI/Sources/Pool/Board.swift", source)
    profile = _derived_data(tmp_path)
    _fake_llvm_cov(monkeypatch, {profile: _record(board, {1: 2, 2: 2, 3: 0, 4: 0})})
    convert(tmp_path, [board, other])
    assert lcov_path(tmp_path).read_text().startswith(f"SF:{board}\n")
    entries = analyze_files([board, other], tmp_path, load_bundle(tmp_path))
    assert {entry.path: entry.coverage for entry in entries} == {
        "Pool/Sources/Pool/Board.swift": 50.0,
        "UI/Sources/Pool/Board.swift": 0.0,
    }


def test_llvm_cov_reads_each_profile_against_the_test_bundles_and_apps_built_beside_it(
    tmp_path, monkeypatch
):
    board = _write(tmp_path, "Board.swift")
    profile = _derived_data(tmp_path)
    products = profile.parents[2] / "Products" / "Debug-iphonesimulator"
    calls = []
    _fake_llvm_cov(monkeypatch, {profile: _record(board, {1: 1})}, calls)
    monkeypatch.setattr("crapper.languages.swift_coverage.platform.machine", lambda: "arm64")
    convert(tmp_path, [board])
    assert calls == [
        [
            "xcrun", "llvm-cov", "export", "-format=lcov", "-skip-functions",
            "-instr-profile", str(profile),
            str(products / "PoolTests.xctest" / "PoolTests"), "-arch=arm64",
            "-object", str(products / "Tyche.app" / "Tyche"), "-arch=arm64",
            "-object", str(products / "Tyche.app" / "Tyche.debug.dylib"), "-arch=arm64",
            "-object",
            str(products / "Tyche.app" / "PlugIns" / "TycheTests.xctest" / "TycheTests"),
            "-arch=arm64",
        ]
    ]


def test_without_xcrun_xcode_inputs_are_skipped_with_a_warning(tmp_path, monkeypatch, capsys):
    board = _write(tmp_path, "Pool/Sources/Pool/Board.swift")
    profile = _derived_data(tmp_path)
    calls = []
    monkeypatch.setattr("crapper.languages.swift_coverage.shutil.which", lambda name: None)
    monkeypatch.setattr(
        "crapper.languages.swift_coverage.subprocess.run", lambda *args, **_kw: calls.append(args)
    )
    convert(tmp_path, [board])
    err = capsys.readouterr().err
    assert calls == []
    assert "xcrun" in err
    assert str(profile) in err
    assert not lcov_path(tmp_path).exists()


def test_a_profile_llvm_cov_cannot_read_is_skipped_with_a_warning(tmp_path, monkeypatch, capsys):
    board = _write(tmp_path, "Board.swift")
    broken = _derived_data(tmp_path, device="BROKEN")
    good = _derived_data(tmp_path, device="GOOD")

    def run(command, **_kwargs):
        if str(broken) in command:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="malformed profile")
        return subprocess.CompletedProcess(command, 0, stdout=_record(board, {1: 1}), stderr="")

    monkeypatch.setattr("crapper.languages.swift_coverage.shutil.which", lambda name: "/usr/bin/xcrun")
    monkeypatch.setattr("crapper.languages.swift_coverage.subprocess.run", run)
    convert(tmp_path, [board])
    err = capsys.readouterr().err
    assert str(broken) in err
    assert "malformed profile" in err
    assert str(good) not in err
    assert _converted(tmp_path) == {str(board): {1: (1, 1)}}


def test_a_folder_without_a_profile_warns_and_writes_nothing(tmp_path, monkeypatch, capsys):
    board = _write(tmp_path, "Board.swift")
    stale = _write(tmp_path, "target/coverage/swift/lcov.info", f"SF:{board}\nDA:1,1\nend_of_record\n")
    _write(tmp_path, "target/coverage/swift/Tyche.xcresult/Info.plist", "<plist/>\n")
    monkeypatch.setattr("crapper.languages.swift_coverage.shutil.which", lambda name: "/usr/bin/xcrun")
    convert(tmp_path, [board])
    err = capsys.readouterr().err
    assert "target/coverage/swift" in err
    assert "-derivedDataPath" in err
    assert not stale.exists()
