from collections import defaultdict
from collections.abc import Callable, Iterable
from functools import cached_property
from pathlib import Path, PurePosixPath
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeFloat,
    PositiveInt,
    StringConstraints,
    computed_field,
    model_validator,
)

type Percent = Annotated[float, Field(ge=0, le=100)]
type Name = Annotated[str, StringConstraints(pattern=r"^\S(.*\S)?$")]
type Namespace = Annotated[str, StringConstraints(min_length=1)]


def grouped[T, K](items: Iterable[T], key: Callable[[T], K]) -> dict[K, list[T]]:
    groups: defaultdict[K, list[T]] = defaultdict(list)
    for item in items:
        groups[key(item)].append(item)
    return dict(groups)


class Model(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")


class Span(Model):
    start: PositiveInt
    end: PositiveInt

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.end < self.start:
            raise ValueError(f"end ({self.end}) is before start ({self.start})")
        return self

    def overlaps(self, other: Self) -> bool:
        return self.start <= other.end and other.start <= self.end


class Home(Model):
    root: Path
    directory: Path
    name: str | None = None

    def qualified(self, file: Path) -> PurePosixPath | None:
        if self.name is None:
            return None
        return PurePosixPath(self.name, file.relative_to(self.directory).as_posix())


class Source(Model):
    home: Home
    path: Path


class Function(Model):
    name: Name
    namespace: Namespace
    complexity: PositiveInt
    span: Span


class Scored(Model):
    function: Function
    coverage: Percent

    @computed_field
    @cached_property
    def crap(self) -> NonNegativeFloat:
        complexity = self.function.complexity
        return complexity**2 * (1 - self.coverage / 100) ** 3 + complexity


class Unmeasured(Model):
    function: Function


type Entry = Scored | Unmeasured
