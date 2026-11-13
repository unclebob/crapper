# crapper

This is a fork of [unclebob/crapper](https://github.com/unclebob/crapper) that adds F#, Kotlin, and Swift support. Thanks to Robert C. Martin for the original tool.

CRAP scores for Clojure, Java, Go, TypeScript, Rust, Python, F#, Kotlin, and Swift. One run detects the language of each source file, applies that language's complexity and coverage rules, and writes the snapshot [uml-viewer](https://github.com/unclebob/uml-viewer) already reads.

The formula is the one from [crap4clj](https://github.com/unclebob/crap4clj), [crap4java](https://github.com/unclebob/crap4java), and [crap4go](https://github.com/unclebob/crap4go):

```text
CRAP = CC² × (1 − coverage)³ + CC
```

`CC` is cyclomatic complexity. `coverage` is the fraction of the function exercised by tests. A score of 1–5 is low risk, 5–30 is worth a look, and 30+ is complex and under-tested.

## Run

```bash
./crapper
```

The first run creates `.venv` and installs the tool. From a project root it walks the tree, skips `test`, `spec`, `vendor`, `node_modules`, and `target` folders inside the project, and the iOS build and dependency folders `.build`, `Pods`, `Carthage`, and `DerivedData`, for every language (a project that itself lives in a folder named `tests` is still scored), and writes two results:

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
| Swift | `Module.Type` (`Module.Outer.Inner`; an extension as the type it extends, `[T]`, `[K: V]`, and `T?` as `Array`, `Dictionary`, and `Optional`) when the path has `Sources/<Module>/`, otherwise `Type`; a top-level function takes `Module`, or the file stem | the function or property name, `init`, `deinit`, or `subscript` |

Rename or move is a new entry. There is no identity matching across runs.

## What each language counts

Clojure follows crap4clj: `if` / `when` and their variants, `and`, `or`, `loop`, `catch`, and each clause of `cond`, `condp`, `case`, `cond->`, `cond->>`, `some->`, and `some->>`. Coverage prefers Cloverage's per-line form counts and falls back to LCOV.

Java follows crap4java: `if`, loops, `catch`, `?:`, each `switch` label, and `&&` / `||`. Constructors and methods inside anonymous classes are omitted. Coverage is JaCoCo's `INSTRUCTION` counter.

Go follows crap4go: `if`, `for`, `range`, each `switch` and `select` clause, and `&&` / `||`. Coverage is `go test -coverprofile`, which names each file by its module import path (the `module` line of the nearest `go.mod` plus the path inside that module). crapper and mutator look a file up by that name first, then by the longest matching path suffix.

TypeScript, TSX, and JavaScript (`.js`, `.jsx`, `.mjs`, `.cjs`) use the same structural decisions as Java, including `&&` inside JSX, plus `??` and `?.`. Top-level functions, class methods, and top-level arrow functions are entries. An inline Express callback — `.get`, `.post`, `.put`, `.patch`, `.delete`, `.head`, `.options`, `.all`, `.use`, and `.route(path).get(...)` — is its own entry, named `GET /users`. A second callback on that same route is `GET /users#2`. Its decisions are not also charged to the enclosing function. Other nested callbacks stay inside the enclosing function. Coverage is LCOV. When the report has branch records (`BRDA`) inside a function, the score uses those branches; a function with no branches uses line hits. A `coverage` script is used as-is. A Vitest project runs `vitest --coverage` (installing `@vitest/coverage-v8` into `node_modules` when it is missing, without editing `package.json`). Other test scripts are wrapped in `c8`.

Rust counts `if`, loops, each `match` arm, `?`, and `&&` / `||`. `mod tests` is skipped. Coverage is LCOV from `cargo llvm-cov` or `cargo tarpaulin`, run in the nearest directory that contains `Cargo.toml`. When neither tool is installed, the run installs `cargo-llvm-cov`.

Python counts `if`, `elif`, `for`, `while`, `except`, each `match` case, a comprehension filter, a conditional expression, and each `and` / `or`. Nested functions stay inside the enclosing function. Coverage is LCOV from `coverage.py`, running pytest when the project uses it and `unittest` otherwise. `coverage` and `pytest` are installed into the project's interpreter when they are missing.

F# (`.fs` and `.fsx`) counts `if`, `elif`, `for`, `while`, each arm of `match`, `function`, and `try ... with`, each `when` guard, and `&&` / `||`; `let!` and combinators such as `Option.map` add nothing. Module- and type-level functions, members, active patterns, and values bound to a lambda or an object expression are entries. Signature files (`.fsi`), `bin`, `obj`, and `*.Test` / `*.Tests` folders are skipped. Coverage is Cobertura from Microsoft Code Coverage, run per test project, with nothing to install. A `--coverage-command` for F# writes its Cobertura reports under `target/coverage/fsharp/`.

Kotlin (`.kt`) counts `if`, `for`, `while`, `do ... while`, each `when` arm except `else`, each `catch`, and each `&&`, `||`, `?:`, and `?.`. Top-level functions, extension functions, and the functions of classes, objects, companion objects, and enum values with their own body are entries; a local function, a lambda, or an anonymous object stays in the enclosing function. Constructors, `init` blocks, property accessors, and abstract functions are not entries. A file with no `package` line uses the file stem as the namespace of its top-level functions. Gradle scripts (`.kts`), `build`, `src/test`, and `src/*Test` source sets such as `src/androidTest` and `src/commonTest` are skipped. Coverage is Kover's `INSTRUCTION` counter, read like JaCoCo's: a function takes every method of its JVM class named after it, including `name-<hash>` (value-class mangling) and `name$...` (lambdas, `internal` names, default-argument bridges). Kover records no line numbers, so overloads share one percentage. Kover is a prerequisite crapper does not add: apply `id("org.jetbrains.kotlinx.kover")` in the root build file, with `kover(project(":module"))` for each module under `dependencies`, and in each module's build file. Without it the run warns with those lines and Kotlin scores 0%.

Swift (`.swift`) counts `if`, `guard`, `for`, `while`, `repeat ... while`, each `switch` case except `default`, each `catch`, each `&&`, `||`, `??`, ternary `? :`, and optional chaining `?.`, each comma between the conditions of an `if`, `guard`, or `while`, and a `where` clause on a `for`, `case`, or `catch`. So `guard let a, let b, c else` adds 3, a `case .a, .b:` adds 1, and `try?` adds nothing. Functions, initializers (`init`), `deinit`, and `subscript` with a body are entries, and so are properties with a body: a computed property (getter and setter are one entry), `willSet` / `didSet` observers, and a property initialised by a closure, each named after the property. A nested function or a closure stays in the enclosing entry, and protocol requirements are not entries. The namespace starts with the module, the folder after `Sources/` in the file's absolute path (`Feature/Sources/Feature/...` gives `Feature.FeatureViewModel`), so it does not change with the root crapper runs from; a path without `Sources/<Module>/`, such as an app target, gets the type chain alone. `Package.swift` and folders named `Tests` or `*Tests` (`CoreTests`, `AppUITests`) are skipped, also under `--changed`. The `.build`, `Pods`, `Carthage`, and `DerivedData` folders are skipped for every language, like `vendor`, so the Python, C, or JavaScript files of a package's checkouts are not scored either; a project that itself lives in such a folder is still scored, and naming one on the command line (`crapper Pods/Lib`) scores it. Coverage comes only from a `--coverage-command` (see below): crapper never starts a Swift test run itself.

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
| Swift | none: only the command you pass with `--coverage-command` | Xcode derived data in `target/coverage/swift/DerivedData/`, or `swift test` exports (`target/coverage/swift/*.json`), converted to `target/coverage/swift/lcov.info` |

A missing tool or a failed test run scores that language at 0% and still writes the snapshot. Pass `--coverage-command` to replace those defaults with one command of your own. `--no-coverage` is the run that leaves coverage and CRAP as N/A.

Swift needs that command. It runs in the project root, must remove `target/coverage/swift/` first, and must run the tests with coverage and leave what they record in that folder. For an Xcode project, keep the derived data there, for example:

```bash
crapper --coverage-command 'rm -rf target/coverage/swift && xcodebuild test -workspace App.xcworkspace -scheme App -destination "platform=iOS Simulator,name=iPhone 17" -enableCodeCoverage YES -derivedDataPath target/coverage/swift/DerivedData'
```

For a Swift package without an Xcode project, run `swift test` with coverage and copy the export it writes, whose path `swift test --show-codecov-path` prints, into the folder:

```bash
crapper --coverage-command 'rm -rf target/coverage/swift && mkdir -p target/coverage/swift && swift test --enable-code-coverage && cp "$(swift test --show-codecov-path)" target/coverage/swift/'
```

When it exits zero, crapper reads each profile under `DerivedData/Build/ProfileData/` with `xcrun llvm-cov export -format=lcov`, against the test bundles and apps in `DerivedData/Build/Products/`, so packages linked into those binaries are covered too (`xccov` reports them as empty). It writes the executable lines of the Swift files it scores to `target/coverage/swift/lcov.info`; a file in several profiles or binaries counts a line as covered when any of them covered it. Without `xcrun`, as on Linux, those inputs are skipped with a warning. Each `*.json` export in `target/coverage/swift/` is read without `xcrun`: crapper derives each line's count from the export's regions the way `llvm-cov` does and merges it into the same `lcov.info`, so a file both runs cover counts a line as covered when either covered it; a JSON file that is not a coverage export is skipped with a warning. When the command exits non-zero nothing is converted and the old `lcov.info` is removed, so Swift scores 0%, also on a following `--use-existing-coverage`. Without `--coverage-command` the run warns with an example, removes that `lcov.info`, and scores Swift 0%; the derived data stays for the command to clean. `--use-existing-coverage` reads only `lcov.info`, so an `xcodebuild` or `swift test` run by hand is not read. Because the derived data lives in that folder and the command removes it first, each run builds from scratch.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```
