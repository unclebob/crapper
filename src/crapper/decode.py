import json
from collections.abc import Callable
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict


class Malformed(ValueError):
    pass


def decoded[T](path: Path, decode: Callable[[str], T]) -> T:
    try:
        return decode(path.read_text(encoding="utf-8"))
    except ValueError as invalid:
        raise Malformed(f"{path}: {invalid}") from invalid


class ForeignDocument(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    @classmethod
    def read(cls, path: Path, decode: Callable[[str], object] = json.loads) -> Self:
        return decoded(path, lambda text: cls.model_validate(decode(text)))
