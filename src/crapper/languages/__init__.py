"""Per-language function extraction."""

from crapper.languages.clojure import functions_in_source as clojure_functions
from crapper.languages.golang import functions_in_source as go_functions
from crapper.languages.java import functions_in_source as java_functions
from crapper.languages.python import functions_in_source as python_functions
from crapper.languages.rust import functions_in_source as rust_functions
from crapper.languages.typescript import functions_in_source as typescript_functions
from crapper.model import Function

_READERS = {
    "clojure": clojure_functions,
    "java": java_functions,
    "go": go_functions,
    "typescript": typescript_functions,
    "python": python_functions,
    "rust": rust_functions,
}


def functions_in_file(
    language: str, source: str, path: str, project_root: str
) -> list[Function]:
    from crapper.strategies import strategy_for

    strategy = strategy_for(language)
    if strategy is not None:
        return strategy.functions_in_source(source, path, project_root)
    reader = _READERS.get(language)
    if reader is None:
        return []
    return reader(source, path, project_root)
