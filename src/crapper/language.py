from collections.abc import Callable, Iterable
from fnmatch import fnmatchcase
from functools import cache, partial
from pathlib import Path
from typing import Self

from crapper.coverage.formats import Lines, Report
from crapper.model import Function, Home, Model, Source, grouped

TEST_DIRS = frozenset({"test", "tests", "spec", "specs", "__tests__"})


def _matches(path: Path, globs: Iterable[str]) -> bool:
    return any(fnmatchcase(path.name, glob) for glob in globs)


class Language(Model):
    name: str
    extensions: tuple[str, ...]
    ignored: tuple[str, ...] = ()
    tests: tuple[str, ...] = ()
    skip: frozenset[str] = frozenset()
    manifests: tuple[str, ...]
    project_name: Callable[[Path], str | None] = lambda _: None
    functions: Callable[[Source], list[Function]]
    ready: Callable[[Path], bool] = lambda _: True
    measure: Callable[[Project, Path], list[Lines]]
    reports: tuple[Report, ...]

    def owns(self, path: Path) -> bool:
        return path.suffix in self.extensions and not _matches(path, self.ignored)

    def is_test(self, path: Path) -> bool:
        return not TEST_DIRS.isdisjoint(path.parts) or _matches(path, self.tests)

    def _manifest(self, root: Path, directory: Path) -> Path | None:
        return next(
            (
                manifest
                for parent in (directory, *directory.parents)
                if parent.is_relative_to(root)
                for name in self.manifests
                if (manifest := parent / name).is_file()
            ),
            None,
        )

    def projects(self, root: Path, files: Iterable[Path]) -> list[Project]:
        manifest = cache(partial(self._manifest, root))
        owned = grouped(files, lambda file: manifest(file.parent))
        found = (
            Project(
                language=self,
                home=Home(
                    root=root, directory=path.parent, name=self.project_name(path)
                )
                if path
                else Home(root=root, directory=root),
                files=tuple(members),
            )
            for path, members in owned.items()
        )
        return sorted(found, key=lambda project: project.home.directory)


class Project(Model):
    language: Language
    home: Home
    files: tuple[Path, ...]

    def measurable(self) -> Self:
        files = tuple(
            file
            for file in self.files
            if not self.language.is_test(file.relative_to(self.home.directory))
        )
        return type(self)(language=self.language, home=self.home, files=files)
