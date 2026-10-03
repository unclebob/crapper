# crapper

CRAP scores for Clojure, Java, Go, TypeScript, Rust, and Python. One run detects the language of each source file, applies that language's complexity and coverage rules, and writes the snapshot [uml-viewer](https://github.com/unclebob/uml-viewer) already reads.

The formula is the one from [crap4clj](https://github.com/unclebob/crap4clj), [crap4java](https://github.com/unclebob/crap4java), and [crap4go](https://github.com/unclebob/crap4go):

```text
CRAP = CC² × (1 − coverage)³ + CC
```

`CC` is cyclomatic complexity. `coverage` is the fraction of the function exercised by tests. A score of 1–5 is low risk, 5–30 is worth a look, and 30+ is complex and under-tested.

## Run

```bash
uv tool install .
crapper
```

From a project root it walks the tree, skips `test`, `spec`, `vendor`, `node_modules`, and `target`, and writes two results:

- a table on stdout, worst score first
- `.metrics/crap.edn`, replaced on every successful analysis

```bash
crapper --coverage none                # complexity only; coverage and CRAP are N/A
crapper --coverage existing            # read reports already on disk
crapper --coverage-command 'make cov'  # run this instead of the per-language tools
crapper src/demo/core.clj src/ui       # these files and trees
crapper --changed                      # git additions and edits
crapper combat                         # path fragment, same idea as crap4clj
crapper --threshold 30                 # exit 2 when the worst score is higher
crapper uml                            # open uml-viewer on the project in a detached JVM
crapper uml --restart                  # companion only: new JVM, restore the last view
```

## Snapshot

`.metrics/crap.edn` has the same shape crap4clj writes:

```clojure
{:entries [{:name "place"
            :namespace "demo.Board"
            :complexity 3
            :coverage 75.0
            :crap 3.1}]}
```

uml-viewer groups entries by `:namespace` and joins each operation on `:name`. `nil` for `:coverage` and `:crap` is what `--coverage none` writes: the function shows as N/A in the report, sorts after the scored functions and is ignored by `--threshold`. A function the coverage report does not mention scores 0%.

| Language | `:namespace` | `:name` |
| --- | --- | --- |
| Clojure | the `ns` | the `defn` / `defn-` name |
| Java | `package.Class`, or `package.Outer.Inner` | the method name |
| Go | the package import path, or `import/path.Receiver` | the function or method name |
| TypeScript | the dotted module path, or `module.Class` | the function or method name |
| Rust | `crate::module`, or `crate::module::Type` | the function or method name |
| Python | the dotted module path, or `module.Class` | the function or method name |

Module paths for Clojure, TypeScript, and Python are relative to the directory of the nearest manifest (`deps.edn`, `package.json`, `pyproject.toml`, ...), or to the project root when there is none, so a package gets the same namespace wherever the run starts.

Rename or move is a new entry. There is no identity matching across runs.

## What each language counts

Clojure follows crap4clj's rules, read from a parse tree rather than text: `if` / `when` and their variants, `and`, `or`, `loop`, `catch`, and each clause of `cond`, `condp`, `case`, `cond->`, `cond->>`, `some->`, and `some->>`. Coverage prefers Cloverage's per-line form counts and falls back to LCOV.

Java follows crap4java: `if`, loops, `catch`, `?:`, each `switch` label, and `&&` / `||`. Constructors and methods inside anonymous classes are omitted. Coverage is JaCoCo's per-line instruction counts over the method's lines, so overloads are told apart and lambda bodies count toward the method that contains them.

Go follows crap4go: `if`, `for`, `range`, each `switch` and `select` clause, and `&&` / `||`. Coverage is `go test -coverprofile`.

TypeScript, TSX, and JavaScript (`.js`, `.jsx`, `.mjs`, `.cjs`) use the same structural decisions as Java, including `&&` inside JSX, plus `??` and `?.`. Top-level functions, class methods, and top-level arrow functions are entries. An inline Express callback — `.get`, `.post`, `.put`, `.patch`, `.delete`, `.head`, `.options`, `.all`, `.use`, and `.route(path).get(...)` — is its own entry, named `GET /users`. A second callback on that same route is `GET /users#2`. Its decisions are not also charged to the enclosing function. Other nested callbacks stay inside the enclosing function. Coverage is LCOV. When the report has branch records (`BRDA`) inside a function, the score uses those branches; a function with no branches uses line hits. A `coverage` script is used as-is. A Vitest project runs `vitest --coverage` (installing `@vitest/coverage-v8` into `node_modules` when it is missing, without editing `package.json`). Other test scripts are wrapped in `c8`.

Rust counts `if`, loops, each `match` arm, `?`, and `&&` / `||`. `mod tests` is skipped. Coverage is LCOV from `cargo llvm-cov` or `cargo tarpaulin`, run in the nearest directory that contains `Cargo.toml`. When neither tool is installed, the run installs `cargo-llvm-cov`.

Python counts `if`, `elif`, `for`, `while`, `except`, each `match` case, a comprehension filter, a conditional expression, and each `and` / `or`. Nested functions stay inside the enclosing function. Coverage is LCOV from `coverage.py`, running pytest when the project uses it and `unittest` otherwise. `coverage` and `pytest` are installed into the project's interpreter when they are missing.

## Coverage commands

By default a run measures each project with its language's command below, one project at a time. Each tool writes its report into a temporary directory that is gone when the run ends, so a run keeps no coverage reports in the project. The last column is where `--coverage existing` and `--coverage-command` look for reports you produced yourself:

| Language | Command | Existing report |
| --- | --- | --- |
| Clojure | `clj -M:cov --output ... --lcov` (needs `deps.edn` or `bb.edn`) | `target/coverage/` |
| Java | JaCoCo Maven plugin `0.8.12` in each module with `pom.xml` | `target/site/jacoco/jacoco.xml` |
| Go | `go test ./... -coverprofile=...` | `target/coverage/go/coverage.out` |
| TypeScript | `npm run coverage`, or Vitest `--coverage`, or `npx c8 ... npm test` | `coverage/lcov.info` or `target/coverage/**/lcov.info` |
| Rust | `cargo llvm-cov` or `cargo tarpaulin`, per Cargo package | `target/coverage/**/lcov.info` |
| Python | `coverage run` with pytest or unittest, then `coverage lcov` | `target/coverage/**/lcov.info` |

Two commands still write inside the project because the tool decides where: Maven writes JaCoCo's XML under the module's `target/` (the run removes the previous one first, so a broken build cannot be scored from a stale report), and a `coverage` script in `package.json` writes wherever it is configured to.

A missing tool or a failed test run scores that language at 0% and still writes the snapshot. A manifest or coverage report that cannot be read is an error: the run names the file and exits 1. A function whose lines appear in no report scores 0%. Pass `--coverage-command` to replace those defaults with one command of your own. When that command fails, every function scores 0%: reports already on disk are not read, because they may be stale.

## Adding a language

A language is one module in `src/crapper/languages/` that ends in a `Language` value (`src/crapper/language.py`): its extensions, test-file and ignored globs, the directories it should `skip`, a `functions` parser, a `measure` function that runs the coverage tool for one project in a scratch directory and returns what it wrote, optionally a `ready` check that runs once per run and stops the language when its tool cannot be had, and the `reports` that `--coverage existing` looks for. Add the value to `LANGUAGES` in `src/crapper/languages/__init__.py`. Discovery, analysis, coverage, the report and `--help` all read the registry, so nothing else changes.

## Development

```bash
uv run pytest
uv run ruff check
uv run ty check src
```
