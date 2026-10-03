from pathlib import Path
from typing import Final

from crapper.language import Language
from crapper.languages.clojure import CLOJURE
from crapper.languages.go import GO
from crapper.languages.java import JAVA
from crapper.languages.python import PYTHON
from crapper.languages.rust import RUST
from crapper.languages.typescript import TYPESCRIPT

LANGUAGES: Final = (CLOJURE, GO, JAVA, PYTHON, RUST, TYPESCRIPT)


def language_of(path: Path) -> Language | None:
    return next((language for language in LANGUAGES if language.owns(path)), None)
