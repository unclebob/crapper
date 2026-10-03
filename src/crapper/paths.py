from collections.abc import Collection
from pathlib import Path


def has_file(directory: Path, names: Collection[str]) -> bool:
    return any((directory / name).is_file() for name in names)


def module_parts(path: Path, root: Path) -> tuple[str, ...]:
    *package, stem = path.relative_to(root).with_suffix("").parts
    return (
        (*package[package.index("src") + 1 :], stem)
        if "src" in package
        else (*package, stem)
    )
