# crapper

This is a fork of [unclebob/crapper](https://github.com/unclebob/crapper) that adds F# and Kotlin support. Thanks to Robert C. Martin for the original tool.

CRAP scores for Clojure, Java, Go, TypeScript, Rust, Python, F#, and Kotlin. One run detects the language of each source file, applies that language's complexity and coverage rules, and writes the snapshot [uml-viewer](https://github.com/unclebob/uml-viewer) already reads.

The formula is the one from [crap4clj](https://github.com/unclebob/crap4clj), [crap4java](https://github.com/unclebob/crap4java), and [crap4go](https://github.com/unclebob/crap4go):

```text
CRAP = CC² × (1 − coverage)³ + CC
```

`CC` is cyclomatic complexity. `coverage` is the fraction of the function exercised by tests. A score of 1–5 is low risk, 5–30 is worth a look, and 30+ is complex and under-tested.

## Run

```bash
./crapper
```

The first run creates `.venv` and installs the tool. From a project root it walks the tree, skips `test`, `spec`, `vendor`, `node_modules`, and `target`, and writes two results:

- a table on stdout, worst score first
- `.metrics/crap.edn`, replaced on every successful analysis

```bash
./crapper --no-coverage                  # complexity only; coverage is N/A
./crapper --use-existing-coverage        # read reports already on disk
./crapper src/demo/core.clj src/ui       # these files and trees
./crapper --changed                      # git additions and edits
./crapper --changed-functions            # only the functions those edits touched
./crapper combat                         # path fragment, same idea as crap4clj
./crapper --threshold 30                 # exit 2 when the worst score is higher
```

`--changed-functions` analyzes the same files as `--changed`, then intersects each function's line range with the hunks of `git diff -U0 HEAD`, and counts every line of an untracked file. The table shows only the functions that overlap a changed line, and `--threshold` judges only those. `.metrics/crap.edn` still holds every function of the changed files, so uml-viewer sees whole files. Before the first commit, every changed file counts as wholly changed. A function whose coverage dropped because only a test file changed is not detected: no line of it changed.

## Snapshot

`.metrics/crap.edn` has the same shape crap4clj writes:

```clojure
{:entries [{:name "place"
            :namespace "demo.Board"
            :complexity 3
            :coverage 75.0
            :crap 3.1}]}
```

uml-viewer groups entries by `:namespace` and joins each operation on `:name`. `nil` coverage is what `--no-coverage` writes: complexity only, and CRAP is `nil` too. A function the coverage report does not mention scores 0%.

| Language | `:namespace` | `:name` |
| --- | --- | --- |
| Clojure | the `ns` | the `defn` / `defn-` name |
| Java | `package.Class`, or `package.Outer.Inner` | the method name |
| Go | the package import path, or `import/path.Receiver` | the function or method name |
| TypeScript | the dotted module path, or `module.Class` | the function or method name |
| Rust | `crate::module`, or `crate::module::Type` | the function or method name |
| Python | the dotted module path, or `module.Class` | the function or method name |
| F# | the `namespace` and `module` path, or `Namespace.Module.Type` | the function, member, or active pattern name |
| Kotlin | the `package`, or `package.Class` (`package.Outer.Inner`, `package.Class.Companion`, `package.Enum.VALUE`) | the function name |

Rename or move is a new entry. There is no identity matching across runs.

## What each language counts

Clojure follows crap4clj: `if` / `when` and their variants, `and`, `or`, `loop`, `catch`, and each clause of `cond`, `condp`, `case`, `cond->`, `cond->>`, `some->`, and `some->>`. Coverage prefers Cloverage's per-line form counts and falls back to LCOV.

Java follows crap4java: `if`, loops, `catch`, `?:`, each `switch` label, and `&&` / `||`. Constructors and methods inside anonymous classes are omitted. Coverage is JaCoCo's `INSTRUCTION` counter.

Go follows crap4go: `if`, `for`, `range`, each `switch` and `select` clause, and `&&` / `||`. Coverage is `go test -coverprofile`.

TypeScript, TSX, and JavaScript (`.js`, `.jsx`, `.mjs`, `.cjs`) use the same structural decisions as Java, including `&&` inside JSX, plus `??` and `?.`. Top-level functions, class methods, and top-level arrow functions are entries. An inline Express callback — `.get`, `.post`, `.put`, `.patch`, `.delete`, `.head`, `.options`, `.all`, `.use`, and `.route(path).get(...)` — is its own entry, named `GET /users`. A second callback on that same route is `GET /users#2`. Its decisions are not also charged to the enclosing function. Other nested callbacks stay inside the enclosing function. Coverage is LCOV. When the report has branch records (`BRDA`) inside a function, the score uses those branches; a function with no branches uses line hits. A `coverage` script is used as-is. A Vitest project runs `vitest --coverage` (installing `@vitest/coverage-v8` into `node_modules` when it is missing, without editing `package.json`). Other test scripts are wrapped in `c8`.

Rust counts `if`, loops, each `match` arm, `?`, and `&&` / `||`. `mod tests` is skipped. Coverage is LCOV from `cargo llvm-cov` or `cargo tarpaulin`, run in the nearest directory that contains `Cargo.toml`. When neither tool is installed, the run installs `cargo-llvm-cov`.

Python counts `if`, `elif`, `for`, `while`, `except`, each `match` case, a comprehension filter, a conditional expression, and each `and` / `or`. Nested functions stay inside the enclosing function. Coverage is LCOV from `coverage.py`, running pytest when the project uses it and `unittest` otherwise. `coverage` and `pytest` are installed into the project's interpreter when they are missing.

F# (`.fs` and `.fsx`) counts `if`, `elif`, `for`, `while`, each arm of `match`, `function`, and `try ... with`, each `when` guard, and `&&` / `||`; `let!` and combinators such as `Option.map` add nothing. Module- and type-level functions, members, active patterns, and values bound to a lambda or an object expression are entries. Signature files (`.fsi`), `bin`, `obj`, and `*.Test` / `*.Tests` folders are skipped. Coverage is Cobertura from Microsoft Code Coverage, run per test project, with nothing to install. A `--coverage-command` for F# writes its Cobertura reports under `target/coverage/fsharp/`.

Kotlin (`.kt`) counts `if`, `for`, `while`, `do ... while`, each `when` arm except `else`, each `catch`, and each `&&`, `||`, `?:`, and `?.`. Top-level functions, extension functions, and the functions of classes, objects, companion objects, and enum values with their own body are entries; a local function, a lambda, or an anonymous object stays in the enclosing function. Constructors, `init` blocks, property accessors, and abstract functions are not entries. A file with no `package` line uses the file stem as the namespace of its top-level functions. Gradle scripts (`.kts`), `build`, `src/test`, and `src/*Test` source sets such as `src/androidTest` and `src/commonTest` are skipped. Coverage is Kover's `INSTRUCTION` counter, read like JaCoCo's: a function takes every method of its JVM class named after it, including `name-<hash>` (value-class mangling) and `name$...` (lambdas, `internal` names, default-argument bridges). Kover records no line numbers, so overloads share one percentage. Kover is a prerequisite crapper does not add: apply `id("org.jetbrains.kotlinx.kover")` in the root build file, with `kover(project(":module"))` for each module under `dependencies`, and in each module's build file. Without it the run warns with those lines and Kotlin scores 0%.

## Coverage commands

By default a run deletes the previous report for each language it is about to measure and regenerates it:

| Language | Command | Report |
| --- | --- | --- |
| Clojure | `clj -M:cov --lcov` (needs `deps.edn` or `bb.edn`) | `target/coverage/` |
| Java | JaCoCo Maven plugin `0.8.12` in each module with `pom.xml` | `target/site/jacoco/jacoco.xml` |
| Go | `go test ./... -coverprofile=...` | `target/coverage/go/coverage.out` |
| TypeScript | `npm run coverage`, or Vitest `--coverage`, or `npx c8 ... npm test` | `coverage/lcov.info` or `target/coverage/typescript/lcov.info` |
| Rust | `cargo llvm-cov` or `cargo tarpaulin`, per Cargo package | `target/coverage/rust/lcov.info` |
| Python | `coverage run` with pytest or unittest, then `coverage lcov` | `target/coverage/python/lcov.info` |
| F# | `dotnet test <project> --collect:"Code Coverage;Format=cobertura"`, per test project | `target/coverage/fsharp/**/*.cobertura.xml` |
| Kotlin | `./gradlew :koverXmlReport` (or `gradle`) in the directory with `settings.gradle.kts` or `settings.gradle`, when its build file applies Kover | `build/reports/kover/report.xml` |

A missing tool or a failed test run scores that language at 0% and still writes the snapshot. Pass `--coverage-command` to replace those defaults with one command of your own. `--no-coverage` is the run that leaves coverage and CRAP as N/A.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```
