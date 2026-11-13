"""Dart and Flutter coverage: the test command for a package, and LCOV paths.

`flutter test --coverage` writes `SF:` paths relative to the package
(`lib/a.dart`); `dart test --coverage-path` writes absolute ones. Relative
paths are made absolute, so `lib/a.dart` in two packages stays two files.
"""

import os
import re
from pathlib import Path

from crapper.discover import SKIP_DIRS

_FLUTTER_SDK = re.compile(r"^\s*sdk:\s*['\"]?flutter['\"]?\s*$", re.MULTILINE)
_SOURCE = re.compile(r"^SF:(?!/)(.+)$", re.MULTILINE)


def is_flutter(package: Path) -> bool:
    pubspec = package / "pubspec.yaml"
    text = pubspec.read_text(encoding="utf-8", errors="replace") if pubspec.is_file() else ""
    return _FLUTTER_SDK.search(text) is not None


def dart_command(package: Path, report: Path) -> list[str]:
    if is_flutter(package):
        return ["flutter", "test", "--coverage", "--coverage-path", str(report)]
    return ["dart", "test", "--coverage-path", str(report)]


def absolute_sources(text: str, package: Path) -> str:
    return _SOURCE.sub(lambda match: f"SF:{package / match.group(1)}", text)


def rewrite_report(report: Path, package: Path) -> None:
    if report.is_file():
        text = report.read_text(encoding="utf-8", errors="replace")
        report.write_text(absolute_sources(text, package.resolve()), encoding="utf-8")


def package_reports(root: Path) -> list[tuple[Path, Path]]:
    """`(package, <package>/coverage/lcov.info)` for each Dart package under `root`."""

    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in SKIP_DIRS]
        report = Path(dirpath) / "coverage" / "lcov.info"
        if "pubspec.yaml" in filenames and report.is_file():
            found.append((Path(dirpath).resolve(), report))
    return found
