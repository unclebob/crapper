import json
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
    _write(products, "FeatureTests.xctest/FeatureTests", "binary")
    _write(products, "Shop.app/Shop", "binary")
    _write(products, "Shop.app/Shop.debug.dylib", "binary")
    _write(products, "Shop.app/PlugIns/ShopTests.xctest/ShopTests", "binary")
    _write(products, "Feature.o", "object")
    return profile


def _record(path: Path | str, lines: dict[int, int]) -> str:
    """One file as `llvm-cov export -format=lcov` writes it: a DA line per executable line."""

    body = "".join(f"DA:{number},{hits}\n" for number, hits in lines.items())
    return f"SF:{path}\nFN:2,place\nFNDA:1,place\n{body}LF:{len(lines)}\nLH:0\nend_of_record\n"


def _lipo(command, archs: dict[str, str]):
    """`xcrun lipo -archs` lists each binary's slices: `archs[name]`, or one arm64 slice.

    An empty `archs[name]` is a file lipo cannot read.
    """

    if command[:2] != ["xcrun", "lipo"]:
        return None
    found = archs.get(Path(command[-1]).name, "arm64")
    if not found:
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="can't figure out the architecture")
    return subprocess.CompletedProcess(command, 0, stdout=found + "\n")


def _fake_llvm_cov(
    monkeypatch, exports: dict[Path, str], calls: list | None = None, archs: dict[str, str] | None = None
):
    """`xcrun` is on the PATH and `llvm-cov` prints `exports[profile]` for each profile."""

    def run(command, **_kwargs):
        lipo = _lipo(command, archs or {})
        if lipo is not None:
            return lipo
        if calls is not None:
            calls.append(command)
        profile = Path(command[command.index("-instr-profile") + 1])
        return subprocess.CompletedProcess(command, 0, stdout=exports[profile], stderr="")

    monkeypatch.setattr("crapper.languages.swift_coverage.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("crapper.languages.swift_coverage.subprocess.run", run)


def _converted(root: Path) -> dict:
    return {path: dict(record) for path, record in parse_lcov(lcov_path(root).read_text()).items()}


def test_only_the_executable_lines_of_the_scored_files_are_written(tmp_path, monkeypatch):
    board = _write(tmp_path, "Feature/Sources/Feature/Board.swift")
    profile = _derived_data(tmp_path)
    _fake_llvm_cov(
        monkeypatch,
        {
            profile: _record(board, {2: 3, 3: 0})
            + _record(tmp_path / "Feature/Tests/FeatureTests/BoardTests.swift", {1: 5})
            + _record("/Users/ci/checkouts/Lib/Sources/Lib/Lib.swift", {1: 5})
        },
    )
    convert(tmp_path, [board])
    assert _converted(tmp_path) == {str(board): {2: (1, 1), 3: (0, 1)}}


def test_a_file_in_two_inputs_is_covered_where_either_covers_it(tmp_path, monkeypatch):
    board = _write(tmp_path, "Feature/Sources/Feature/Board.swift")
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
    board = _write(tmp_path, "Feature/Sources/Feature/Board.swift", source)
    other = _write(tmp_path, "UI/Sources/Feature/Board.swift", source)
    profile = _derived_data(tmp_path)
    _fake_llvm_cov(monkeypatch, {profile: _record(board, {1: 2, 2: 2, 3: 0, 4: 0})})
    convert(tmp_path, [board, other])
    assert lcov_path(tmp_path).read_text().startswith(f"SF:{board}\n")
    entries = analyze_files([board, other], tmp_path, load_bundle(tmp_path))
    assert {entry.path: entry.coverage for entry in entries} == {
        "Feature/Sources/Feature/Board.swift": 50.0,
        "UI/Sources/Feature/Board.swift": 0.0,
    }


def _llvm_cov_calls(tmp_path, monkeypatch, archs: dict[str, str]) -> tuple[list, Path, Path]:
    board = _write(tmp_path, "Board.swift")
    profile = _derived_data(tmp_path)
    calls = []
    _fake_llvm_cov(monkeypatch, {profile: _record(board, {1: 1})}, calls, archs)
    convert(tmp_path, [board])
    return calls, profile, profile.parents[2] / "Products" / "Debug-iphonesimulator"


def test_llvm_cov_reads_each_profile_against_the_test_bundles_and_apps_built_beside_it(
    tmp_path, monkeypatch
):
    # llvm-cov pairs the -arch options with the binaries in order, so each
    # binary names its own; it refuses a universal binary without one.
    calls, profile, products = _llvm_cov_calls(tmp_path, monkeypatch, {})
    assert calls == [
        [
            "xcrun", "llvm-cov", "export", "-format=lcov", "-skip-functions",
            "-instr-profile", str(profile),
            str(products / "FeatureTests.xctest" / "FeatureTests"), "-arch=arm64",
            "-object", str(products / "Shop.app" / "Shop"), "-arch=arm64",
            "-object", str(products / "Shop.app" / "Shop.debug.dylib"), "-arch=arm64",
            "-object",
            str(products / "Shop.app" / "PlugIns" / "ShopTests.xctest" / "ShopTests"),
            "-arch=arm64",
        ]
    ]


def test_each_binary_names_arm64_when_it_has_that_slice_and_its_first_slice_otherwise(
    tmp_path, monkeypatch
):
    archs = {"FeatureTests": "x86_64", "Shop": "x86_64 arm64", "ShopTests": "x86_64 i386"}
    calls, _profile, _products = _llvm_cov_calls(tmp_path, monkeypatch, archs)
    assert [part for part in calls[0] if part.startswith("-arch")] == [
        "-arch=x86_64", "-arch=arm64", "-arch=arm64", "-arch=x86_64",
    ]


def test_a_universal_binary_with_one_slice_names_it(tmp_path, monkeypatch):
    # Xcode's UI test runner is a universal binary whose only slice is arm64:
    # lipo lists one architecture, as for a thin binary, and llvm-cov still
    # refuses it without -arch.
    runner = _write(tmp_path, "target/coverage/swift/DerivedData/Build/Products/Debug-iphonesimulator/"
                    "ShopUITests-Runner.app/ShopUITests-Runner", "binary")
    calls, _profile, _products = _llvm_cov_calls(tmp_path, monkeypatch, {"ShopUITests-Runner": "arm64"})
    assert calls[0][calls[0].index(str(runner)) + 1] == "-arch=arm64"


def test_a_binary_lipo_cannot_read_leaves_every_binary_without_an_arch(tmp_path, monkeypatch, capsys):
    calls, _profile, products = _llvm_cov_calls(tmp_path, monkeypatch, {"Shop.debug.dylib": ""})
    assert calls and not [part for part in calls[0] if part.startswith("-arch")]
    err = capsys.readouterr().err
    assert f"architecture of {products / 'Shop.app' / 'Shop.debug.dylib'};" in err


def test_without_xcrun_xcode_inputs_are_skipped_with_a_warning(tmp_path, monkeypatch, capsys):
    board = _write(tmp_path, "Feature/Sources/Feature/Board.swift")
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
        lipo = _lipo(command, {})
        if lipo is not None:
            return lipo
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
    _write(tmp_path, "target/coverage/swift/Shop.xcresult/Info.plist", "<plist/>\n")
    monkeypatch.setattr("crapper.languages.swift_coverage.shutil.which", lambda name: "/usr/bin/xcrun")
    convert(tmp_path, [board])
    err = capsys.readouterr().err
    assert "target/coverage/swift" in err
    assert "-derivedDataPath" in err
    assert not stale.exists()


# Segments as `swift test --enable-code-coverage` exports them for
#
#  2      public init() {}
#  4      public func label(_ score: Int) -> String {
#  5          guard score >= 0 else { return "invalid" }
#  6          if score >= 90 { return "A" } else { return "B" }
#  7      }
# 17      public func untested(_ value: Int) -> Int {
# 18          if value > 0 {
# 19              return value * 2
# 20          }
# 21          return -value
# 22      }
#
# after a test that calls `label(95)`: [line, column, count, hasCount, isRegionEntry, isGapRegion].
_GRADE_SEGMENTS = [
    [2, 19, 2, True, True, False],
    [2, 21, 0, False, False, False],
    [4, 47, 1, True, True, False],
    [5, 31, 0, True, True, False],
    [5, 51, 1, True, True, False],
    [6, 12, 1, True, True, False],
    [6, 23, 1, True, False, False],
    [6, 24, 1, True, True, False],
    [6, 38, 1, True, False, False],
    [6, 44, 0, True, True, False],
    [6, 58, 1, True, False, False],
    [7, 6, 0, False, False, False],
    [17, 47, 0, True, True, False],
    [18, 12, 0, True, True, False],
    [18, 21, 0, True, False, False],
    [18, 22, 0, True, True, False],
    [20, 10, 0, True, True, False],
    [21, 22, 0, True, False, False],
    [22, 6, 0, False, False, False],
]


def _export_file(path: Path | str, segments: list, count: int, covered: int) -> dict:
    return {
        "filename": str(path),
        "segments": segments,
        "branches": [],
        "expansions": [],
        "summary": {"lines": {"count": count, "covered": covered}},
    }


def _swift_test_export(root: Path, name: str, files: list[dict]) -> Path:
    """What `cp "$(swift test --show-codecov-path)" target/coverage/swift/` leaves."""

    export = {
        "type": "llvm.coverage.json.export",
        "version": "3.0.1",
        "data": [{"files": files, "functions": [], "totals": {}}],
    }
    return _write(root, f"target/coverage/swift/{name}", json.dumps(export))


def test_an_export_converts_each_line_as_llvm_cov_counts_it(tmp_path, monkeypatch):
    grade = _write(tmp_path, "Sources/Scratch/Grade.swift")
    entry_point = tmp_path / ".build/out/DerivedSources/test_entry_point.swift"
    _swift_test_export(
        tmp_path,
        "Scratch.json",
        [
            _export_file(grade, _GRADE_SEGMENTS, count=11, covered=5),
            _export_file(entry_point, [[1, 1, 1, True, True, False], [2, 1, 0, False, False, False]], 1, 1),
        ],
    )
    monkeypatch.setattr("crapper.languages.swift_coverage.shutil.which", lambda name: None)
    convert(tmp_path, [grade])
    converted = _converted(tmp_path)
    # Line 3 and lines 8 to 16 are not executable; lines 5 and 6 hold a covered
    # and an uncovered region and are covered; lines 17 to 22 are uncovered.
    assert converted == {
        str(grade): {
            2: (1, 1), 4: (1, 1), 5: (1, 1), 6: (1, 1), 7: (1, 1),
            17: (0, 1), 18: (0, 1), 19: (0, 1), 20: (0, 1), 21: (0, 1), 22: (0, 1),
        }
    }


def test_a_file_in_an_export_and_in_an_xcode_profile_is_covered_where_either_covers_it(
    tmp_path, monkeypatch
):
    grade = _write(tmp_path, "Sources/Scratch/Grade.swift")
    profile = _derived_data(tmp_path)
    _swift_test_export(tmp_path, "Scratch.json", [_export_file(grade, _GRADE_SEGMENTS, 11, 5)])
    _fake_llvm_cov(monkeypatch, {profile: _record(grade, {2: 0, 4: 0, 18: 3, 19: 3, 30: 0})})
    convert(tmp_path, [grade])
    assert _converted(tmp_path) == {
        str(grade): {
            2: (1, 1), 4: (1, 1), 5: (1, 1), 6: (1, 1), 7: (1, 1),
            17: (0, 1), 18: (1, 1), 19: (1, 1), 20: (0, 1), 21: (0, 1), 22: (0, 1), 30: (0, 1),
        }
    }


def test_exports_convert_without_xcrun_while_xcode_profiles_are_skipped(tmp_path, monkeypatch, capsys):
    grade = _write(tmp_path, "Sources/Scratch/Grade.swift")
    profile = _derived_data(tmp_path)
    _swift_test_export(tmp_path, "Scratch.json", [_export_file(grade, _GRADE_SEGMENTS[:2], 1, 1)])
    calls = []
    monkeypatch.setattr("crapper.languages.swift_coverage.shutil.which", lambda name: None)
    monkeypatch.setattr(
        "crapper.languages.swift_coverage.subprocess.run", lambda *args, **_kw: calls.append(args)
    )
    convert(tmp_path, [grade])
    err = capsys.readouterr().err
    assert calls == []
    assert "xcrun" in err and str(profile) in err
    assert _converted(tmp_path) == {str(grade): {2: (1, 1)}}


def test_a_json_file_that_is_not_a_coverage_export_is_skipped_with_a_warning(
    tmp_path, monkeypatch, capsys
):
    grade = _write(tmp_path, "Sources/Scratch/Grade.swift")
    resolved = _write(tmp_path, "target/coverage/swift/Package.resolved.json", '{"pins": []}')
    broken = _write(tmp_path, "target/coverage/swift/broken.json", "{not json")
    export = _swift_test_export(tmp_path, "Scratch.json", [_export_file(grade, _GRADE_SEGMENTS[:2], 1, 1)])
    monkeypatch.setattr("crapper.languages.swift_coverage.shutil.which", lambda name: None)
    convert(tmp_path, [grade])
    err = capsys.readouterr().err
    assert str(resolved) in err
    assert str(broken) in err
    assert str(export) not in err
    assert _converted(tmp_path) == {str(grade): {2: (1, 1)}}


def test_an_export_of_an_unexpected_shape_is_skipped_whole_with_a_warning(tmp_path, monkeypatch, capsys):
    grade = _write(tmp_path, "Sources/Scratch/Grade.swift")
    good = _export_file(grade, _GRADE_SEGMENTS[:2], 1, 1)
    # Each one reads a file of grade's before the part it does not expect.
    _swift_test_export(tmp_path, "nameless.json", [good, {"segments": []}])
    _swift_test_export(tmp_path, "short.json", [good, _export_file(grade, [[3, 1]], 1, 0)])
    unit = {"type": "llvm.coverage.json.export", "data": [{"files": [good]}, "not a unit"]}
    _write(tmp_path, "target/coverage/swift/unit.json", json.dumps(unit))
    _swift_test_export(tmp_path, "Scratch.json", [good])
    monkeypatch.setattr("crapper.languages.swift_coverage.shutil.which", lambda name: None)
    convert(tmp_path, [grade])
    err = capsys.readouterr().err
    for name in ("nameless.json", "short.json", "unit.json"):
        assert f"{name}: not a swift test coverage export" in err
    assert "Scratch.json" not in err
    assert lcov_path(tmp_path).read_text() == f"SF:{grade}\nDA:2,2\nend_of_record\n"
