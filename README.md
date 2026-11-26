# crapper

CRAP scores for Clojure, Java, Go, TypeScript, Rust, Python, and Swift. One run detects the language of each source file, applies that language's complexity and coverage rules, and writes the snapshot [uml-viewer](https://github.com/unclebob/uml-viewer) already reads.

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
./crapper combat                         # path fragment, same idea as crap4clj
./crapper --threshold 30                 # exit 2 when the worst score is higher
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

uml-viewer groups entries by `:namespace` and joins each operation on `:name`. `nil` coverage is what `--no-coverage` writes: complexity only, and CRAP is `nil` too. A function the coverage report does not mention scores 0%.

| Language | `:namespace` | `:name` |
| --- | --- | --- |
| Clojure | the `ns` | the `defn` / `defn-` name |
| Java | `package.Class`, or `package.Outer.Inner` | the method name |
| Go | the package import path, or `import/path.Receiver` | the function or method name |
| TypeScript | the dotted module path, or `module.Class` | the function or method name |
| Rust | `crate::module`, or `crate::module::Type` | the function or method name |
| Python | the dotted module path, or `module.Class` | the function or method name |
| Swift | the module, or `Module.Type` | the function, method, initializer, subscript, or property |

Rename or move is a new entry. There is no identity matching across runs.

## What each language counts

Clojure follows crap4clj: `if` / `when` and their variants, `and`, `or`, `loop`, `catch`, and each clause of `cond`, `condp`, `case`, `cond->`, `cond->>`, `some->`, and `some->>`. Coverage prefers Cloverage's per-line form counts and falls back to LCOV.

Java follows crap4java: `if`, loops, `catch`, `?:`, each `switch` label, and `&&` / `||`. Constructors and methods inside anonymous classes are omitted. Coverage is JaCoCo's `INSTRUCTION` counter.

Go follows crap4go: `if`, `for`, `range`, each `switch` and `select` clause, and `&&` / `||`. Coverage is `go test -coverprofile`, which names each file by its module import path (the `module` line of the nearest `go.mod` plus the path inside that module). crapper and mutator look a file up by that name first, then by the longest matching path suffix.

TypeScript, TSX, and JavaScript (`.js`, `.jsx`, `.mjs`, `.cjs`) use the same structural decisions as Java, including `&&` inside JSX, plus `??` and `?.`. Top-level functions, class methods, and top-level arrow functions are entries. An inline Express callback — `.get`, `.post`, `.put`, `.patch`, `.delete`, `.head`, `.options`, `.all`, `.use`, and `.route(path).get(...)` — is its own entry, named `GET /users`. A second callback on that same route is `GET /users#2`. Its decisions are not also charged to the enclosing function. Other nested callbacks stay inside the enclosing function. Coverage is LCOV. When the report has branch records (`BRDA`) inside a function, the score uses those branches; a function with no branches uses line hits. A `coverage` script is used as-is. A Vitest project runs `vitest --coverage` (installing `@vitest/coverage-v8` into `node_modules` when it is missing, without editing `package.json`). Other test scripts are wrapped in `c8`.

Rust counts `if`, loops, each `match` arm, `?`, and `&&` / `||`. `mod tests` is skipped. Coverage is LCOV from `cargo llvm-cov` or `cargo tarpaulin`, run in the nearest directory that contains `Cargo.toml`. When neither tool is installed, the run installs `cargo-llvm-cov`.

Python counts `if`, `elif`, `for`, `while`, `except`, each `match` case, a comprehension filter, a conditional expression, and each `and` / `or`. Nested functions stay inside the enclosing function. Coverage is LCOV from `coverage.py`, running pytest when the project uses it and `unittest` otherwise. `coverage` and `pytest` are installed into the project's interpreter when they are missing.

Swift counts `if` (each `else if` is another `if`), `guard`, `for`, `while`, `repeat-while`, each `catch`, `?:`, each `switch` case including `default`, `&&`, `||`, `??`, and optional chaining (`a?.b`, `a?[i]`, `a?()`). These are not decisions: `try` / `try?` / `try!`, `as?` / `as!` / `is`, a `where` clause, `#if`, and the `?` on an optional type (`Int?`) or a failable `init?`. One `if` or `guard` is one decision even when it lists several conditions. `case 1, 2` is one case. Operators inside a string or a comment are not decisions; an interpolated expression is. `#if` does not hide the branches the grammar still parses.

Entries are top-level functions, methods on classes, structs, enums, actors, extensions, and protocols, initializers, deinitializers, subscripts, computed properties, and property observers. A requirement or accessor with no statements, such as `{ get set }`, is not an entry. `get`, `set`, `willSet`, and `didSet` stay inside the property. A closure stored directly in a `let` or `var` is an entry. Any other closure stays inside the enclosing function, the same way a nested callback stays inside its function in TypeScript. A type declared inside a function keeps its own methods, and those methods are not also charged to the outer function.

The namespace is the module, or `Module.Type` for a member (`Module.Outer.Inner` for a nested type, `Module.Array` for an extension). The module is the SwiftPM target whose path contains the file, otherwise the directory under `Sources/`, otherwise the nearest `.xcodeproj` or `.xcworkspace` name, otherwise the dotted directory path with `src/` removed. uml-viewer groups on that namespace and joins `:name`. mutator uses the same function list, including each entry's byte span, so a nested closure's mutations belong to the enclosing function.

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
| Swift | `swift test --enable-code-coverage`, then `llvm-cov export -format=json`; or `xcodebuild test -enableCodeCoverage YES` and `xcrun xccov view --report --json` | `target/coverage/swift/**/*.json` |

A missing tool or a failed test run scores that language at 0% and still writes the snapshot. Pass `--coverage-command` to replace those defaults with one command of your own. `--no-coverage` is the run that leaves coverage and CRAP as N/A.

Swift coverage is region coverage. llvm-cov code regions count; branch, gap, skipped, and expansion regions do not. A report with no function regions uses segments that carry a count. An xccov report joins a function on `lineNumber` and uses `coveredLines` / `executableLines`. A path in the report may be absolute; the file is matched by suffix, as the other languages are.

## Swift coverage on a Mac

iOS coverage is produced by Xcode on a Mac. crapper runs the commands below when `swift` or `xcodebuild` is on the path. To score a report that was produced on another machine, put the JSON under `target/coverage/swift/` and pass `--use-existing-coverage`.

Swift package:

```bash
swift test --enable-code-coverage
bin="$(dirname "$(command -v swift)")/llvm-cov"
profdata="$(find .build -path '*/codecov/default.profdata' -print -quit)"
binary="$(find .build -type f -name '*PackageTests' -print -quit)"
mkdir -p target/coverage/swift
"$bin" export -format=json -instr-profile="$profdata" "$binary" \
  > target/coverage/swift/llvm-cov.json
```

Xcode, including an iOS app. The scheme has to be shared (`xcshareddata/xcschemes`). Use `-workspace App.xcworkspace` when the app has a workspace.

```bash
xcodebuild test -project App.xcodeproj -scheme App \
  -enableCodeCoverage YES \
  -resultBundlePath target/coverage/swift/Test.xcresult
xcrun xccov view --report --json target/coverage/swift/Test.xcresult \
  > target/coverage/swift/xccov.json
```

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```
