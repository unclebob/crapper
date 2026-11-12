"""Convert Swift coverage in `target/coverage/swift/` to one LCOV file.

The user's `--coverage-command` runs Xcode's tests with code coverage and its
derived data inside that folder (`-derivedDataPath
target/coverage/swift/DerivedData`). Each profile it leaves
(`Build/ProfileData/<device>/*.profdata`) is read with
`xcrun llvm-cov export -format=lcov` against the test bundles and apps built
next to it, which also holds the packages linked into them; `xccov` reports
those packages as empty. Only the lines `llvm-cov` lists, which are the
executable ones, are written, because the LCOV loader counts every line it
is given. Only the Swift files being scored are written, under their absolute
paths, so a test or third-party file cannot match a source file by suffix. A
file in several inputs, or in several binaries, is merged line by line, so a
line is covered when any of them covered it. Without `xcrun`, as on Linux,
the Xcode inputs are skipped with a warning.

A `swift test --enable-code-coverage` run instead leaves a JSON export, which
the command copies into the folder from the path `swift test
--show-codecov-path` prints. Its per-line counts are derived from each file's
segments the way `llvm-cov` derives its own LCOV lines, and merged into the
same file; exports need no `xcrun`. A JSON file that is not a coverage export
is skipped with a warning.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from crapper.discover import language_of

COVERAGE_DIR = Path("target") / "coverage" / "swift"
_PROFILES = ("Build/ProfileData/*/*.profdata", "*/Build/ProfileData/*/*.profdata")
_BINARIES = ("*/*.xctest", "*/*.app", "*/*.app/PlugIns/*.xctest")
_EXPORT_TYPE = "llvm.coverage.json.export"


def _warn(message: str) -> None:
    print(message, file=sys.stderr)


def lcov_path(root: Path) -> Path:
    return root / COVERAGE_DIR / "lcov.info"


def remove_lcov(root: Path) -> None:
    lcov_path(root).unlink(missing_ok=True)


def _scored_sources(files: list[Path]) -> dict[str, str]:
    """Each scored Swift file by its real path, mapped to the path written."""

    return {
        os.path.realpath(file): str(Path(file).resolve())
        for file in files
        if language_of(Path(file)) == "swift"
    }


def _profiles(folder: Path) -> list[Path]:
    return sorted({path for pattern in _PROFILES for path in folder.glob(pattern)})


def _bundle_binaries(bundle: Path) -> list[Path]:
    """The bundle's executable, and the `.debug.dylib` that holds an app's code in a debug build."""

    found = []
    for folder in (bundle, bundle / "Contents" / "MacOS"):
        for name in (bundle.stem, f"{bundle.stem}.debug.dylib"):
            if (folder / name).is_file():
                found.append(folder / name)
    return found


def _binaries(profile: Path) -> list[Path]:
    """Test bundles, hosted test bundles, and apps in the `Build/Products` next to the profile."""

    products = profile.parents[2] / "Products"
    bundles = sorted({path for pattern in _BINARIES for path in products.glob(pattern)})
    return [binary for bundle in bundles for binary in _bundle_binaries(bundle)]


def _export(profile: Path, binaries: list[Path]) -> str | None:
    """One `-arch` per binary picks this machine's slice of a universal binary,
    such as Xcode's UI test runner, which `llvm-cov` otherwise refuses."""

    arch = f"-arch={platform.machine()}"
    command = [
        "xcrun", "llvm-cov", "export", "-format=lcov", "-skip-functions",
        "-instr-profile", str(profile), str(binaries[0]), arch,
    ]
    for binary in binaries[1:]:
        command.extend(["-object", str(binary), arch])
    try:
        completed = subprocess.run(command, capture_output=True, text=True)
    except OSError as exc:
        _warn(f"{profile}: llvm-cov failed to start ({exc}); skipped.")
        return None
    if completed.returncode != 0:
        _warn(f"{profile}: llvm-cov exited {completed.returncode} ({completed.stderr.strip()}); skipped.")
        return None
    return completed.stdout


def _counts_for(merged: dict[str, dict[int, int]], path: str, sources: dict[str, str]) -> dict[int, int] | None:
    source = sources.get(os.path.realpath(path))
    return None if source is None else merged.setdefault(source, {})


def _merge_lcov(merged: dict[str, dict[int, int]], text: str, sources: dict[str, str]) -> None:
    counts: dict[int, int] | None = None
    for line in text.splitlines():
        if line.startswith("SF:"):
            counts = _counts_for(merged, line[3:], sources)
        elif line.startswith("DA:") and counts is not None:
            number, hits = line[3:].split(",")[:2]
            counts[int(number)] = counts.get(int(number), 0) + int(hits)
        elif line == "end_of_record":
            counts = None


def _line_counts(segments: list) -> dict[int, int]:
    """Each executable line's count, as `llvm-cov`'s line coverage iterator gives it.

    A segment is `[line, column, count, hasCount, isRegionEntry, isGapRegion]`.
    A line is executable when a counted region starts on it, or when the
    segment carried over from an earlier line has a count; its count is the
    highest of those. A line that starts a skipped region is not executable.
    """

    counts: dict[int, int] = {}
    if not segments:
        return counts
    by_line: dict[int, list] = {}
    for segment in segments:
        by_line.setdefault(segment[0], []).append(segment)
    wrapped = None
    for number in range(segments[0][0], segments[-1][0] + 1):
        starting = by_line.get(number, [])
        starts = [s for s in starting if s[3] and s[4] and not s[5]]
        skipped = bool(starting) and not starting[0][3] and starting[0][4]
        mapped = not skipped and (bool(wrapped and wrapped[3]) or bool(starts))
        mapped = mapped or any(s[3] and s[4] for s in starting)
        if mapped:
            counts[number] = max([wrapped[2] if wrapped else 0, *(s[2] for s in starts)])
        if starting:
            wrapped = starting[-1]
    return counts


def _merge_export(merged: dict[str, dict[int, int]], export: Path, sources: dict[str, str]) -> None:
    try:
        data = json.loads(export.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        _warn(f"{export}: not a swift test coverage export ({exc}); skipped.")
        return
    if not isinstance(data, dict) or data.get("type") != _EXPORT_TYPE:
        _warn(f"{export}: not a swift test coverage export (no type {_EXPORT_TYPE}); skipped.")
        return
    for unit in data.get("data", []):
        for file in unit.get("files", []):
            counts = _counts_for(merged, file["filename"], sources)
            if counts is None:
                continue
            for number, hits in _line_counts(file.get("segments", [])).items():
                counts[number] = counts.get(number, 0) + hits


def _lcov_text(merged: dict[str, dict[int, int]]) -> str:
    records = []
    for source in sorted(merged):
        counts = merged[source]
        lines = [f"DA:{number},{counts[number]}" for number in sorted(counts)]
        records.append("\n".join([f"SF:{source}", *lines, "end_of_record"]))
    return "\n".join(records) + "\n"


def _merge_profiles(merged: dict[str, dict[int, int]], profiles: list[Path], sources: dict[str, str]) -> None:
    if shutil.which("xcrun") is None:
        names = ", ".join(str(profile) for profile in profiles)
        _warn(f"xcrun is not installed; skipping the Xcode coverage profiles {names}.")
        return
    for profile in profiles:
        binaries = _binaries(profile)
        if not binaries:
            _warn(f"{profile}: no test bundle or app next to it; skipped.")
            continue
        text = _export(profile, binaries)
        if text is not None:
            _merge_lcov(merged, text, sources)


def convert(root: Path, files: list[Path]) -> None:
    """Replace `target/coverage/swift/lcov.info` with what the profiles and exports record."""

    folder = root / COVERAGE_DIR
    remove_lcov(root)
    profiles = _profiles(folder) if folder.is_dir() else []
    exports = sorted(folder.glob("*.json")) if folder.is_dir() else []
    if not profiles and not exports:
        _warn(
            f"No Xcode coverage profile (Build/ProfileData/*/*.profdata) and no swift test "
            f"export (*.json) in {folder}. Pass -derivedDataPath target/coverage/swift/DerivedData "
            "to xcodebuild, or copy the file swift test --show-codecov-path prints there. "
            "Swift coverage will score 0%."
        )
        return
    sources = _scored_sources(files)
    merged: dict[str, dict[int, int]] = {}
    if profiles:
        _merge_profiles(merged, profiles, sources)
    for export in exports:
        _merge_export(merged, export, sources)
    if merged:
        lcov_path(root).write_text(_lcov_text(merged), encoding="utf-8")
