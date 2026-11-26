"""Swift functions score the way a reader of the source would count branches."""

import json
from pathlib import Path

from crapper.cli import run
from crapper.coverage import SwiftFile, parse_swift_coverage
from crapper.discover import is_test_file, iter_source_files
from crapper.languages.swift import functions_in_source
from crapper.runners import llvm_cov_tool, run_coverage, swift_export_command, swift_test_binary

_FIXTURES = Path(__file__).parent / "fixtures" / "swift"
_BOX = (_FIXTURES / "Box.swift").read_text(encoding="utf-8")


def test_structural_decisions_match_the_other_languages():
    source = """
func choose(x: Int, y: Int?) -> Int {
    guard x > 0 else { return 0 }
    if x > 1 && y != nil || x < 0 { return 1 }
    for i in 0..<x { while i > 0 { break } }
    repeat { } while x > 2
    do { _ = y } catch { return 0 }
    switch x {
    case 1: return 1
    case 2: return 2
    default: return y ?? 0
    }
    return y?.hashValue ?? (x > 0 ? 1 : 0)
}
"""
    functions = functions_in_source(source, "Sources/Demo/Choose.swift", "/proj")
    assert [(fn.namespace, fn.name, fn.complexity) for fn in functions] == [
        ("Demo", "choose", 16)
    ]


def test_else_if_switch_where_and_optional_chains_follow_the_documented_rules():
    source = """
func climb(a: Bool, b: Bool) {
    if a { } else if b { }
}
func chained() -> Int { a?.b?.c() ?? d?[0] ?? e?() }
func cases(x: Int) -> Int {
    switch x {
    case let n where n > 0: return 1
    case 1, 2: return 2
    default: return 0
    }
}
func compiled(x: Bool) {
#if FOO && BAR
    return 1
#else
    if x { return }
#endif
}
"""
    functions = functions_in_source(source, "Sources/Demo/Choose.swift", "/proj")
    assert [(fn.name, fn.complexity) for fn in functions] == [
        ("climb", 3),
        ("chained", 7),
        ("cases", 4),
        ("compiled", 2),
    ]


def test_casts_tries_strings_and_comments_are_not_decisions():
    source = r"""
func casted(x: Any) -> Int { (x as? Int) ?? 0 }
func attempted() -> Int? { try? risky() }
func text() -> String { "if x && y ?? z?.a" }
func mix() -> String { "if \(a ?? b)" }
func note() -> Int {
    // if x && y ?? z?.a
    return 1
}
"""
    functions = functions_in_source(source, "Sources/Demo/Choose.swift", "/proj")
    assert [(fn.name, fn.complexity) for fn in functions] == [
        ("casted", 2),
        ("attempted", 1),
        ("text", 1),
        ("mix", 2),
        ("note", 1),
    ]


def test_types_initializers_accessors_and_closures():
    source = """
func top(n: Int) -> Int {
    let f = { (x: Int) -> Int in
        if x > 0 { return x }
        return 0
    }
    func inner() { if n > 0 { return } }
    return f(n)
}
class Box {
    init(n: Int) { if n > 0 { self.n = n } }
    func open() -> Int { n > 0 ? 1 : 0 }
    var n: Int = 0 { didSet { if n < 0 { n = 0 } } }
    var shown: Int {
        get { n > 0 ? 1 : 0 }
        set { if newValue == 0 { n = 0 } }
    }
    subscript(i: Int) -> Int { i > 0 ? 1 : 0 }
    deinit { if n == 0 { n = 1 } }
    let arrow = { (n: Int) -> Int in n > 0 ? n : 0 }
    static func == (lhs: Box, rhs: Box) -> Bool { lhs.n == rhs.n }
}
struct View { func body() -> Int { 1 } }
enum Move { func step() -> Int { 1 } }
actor Worker { func run() {} }
extension Box { func extra(flag: Bool) -> Int { flag ? 1 : 0 } }
extension Array where Element == String {
    func blank() -> Bool { isEmpty ? true : false }
}
extension Box.Inner { func more() {} }
let arrow = { (n: Int) -> Int in n > 0 ? n : 0 }
protocol P { func req() }
private func hidden() { if true { } }
"""
    functions = functions_in_source(source, "Sources/Demo/Box.swift", "/proj")
    assert [(fn.namespace, fn.name, fn.complexity) for fn in functions] == [
        ("Demo", "top", 3),
        ("Demo.Box", "init", 2),
        ("Demo.Box", "open", 2),
        ("Demo.Box", "n", 2),
        ("Demo.Box", "shown", 3),
        ("Demo.Box", "subscript", 2),
        ("Demo.Box", "deinit", 2),
        ("Demo.Box", "arrow", 2),
        ("Demo.Box", "==", 1),
        ("Demo.View", "body", 1),
        ("Demo.Move", "step", 1),
        ("Demo.Worker", "run", 1),
        ("Demo.Box", "extra", 2),
        ("Demo.Array", "blank", 2),
        ("Demo.Box.Inner", "more", 1),
        ("Demo", "arrow", 2),
        ("Demo", "hidden", 2),
    ]
    hidden = functions[-1]
    chunk = source.encode()[hidden.start_byte : hidden.end_byte].decode()
    assert chunk.startswith("private func hidden")


def test_a_nested_callback_stays_inside_its_function():
    source = """
let rows = items.map { item in item.ok ? 1 : 0 }
func make() -> Int { items.map { item in item.ok ? 1 : 0 }.count }
func outer(flag: Bool) -> Int {
    struct Inner { func go() -> Int { if true { return 1 }; return 0 } }
    if flag { return 1 }
    return 0
}
"""
    functions = functions_in_source(source, "Sources/Demo/Box.swift", "/proj")
    assert [(fn.namespace, fn.name, fn.complexity) for fn in functions] == [
        ("Demo", "make", 2),
        ("Demo", "outer", 2),
        ("Demo.Inner", "go", 2),
    ]
    make = functions[0]
    assert "map" in source.encode()[make.start_byte : make.end_byte].decode()


def test_a_requirement_without_a_body_is_not_a_function():
    source = """
protocol P {
    func req()
    var name: String { get set }
    subscript(i: Int) -> Int { get set }
    init()
}
struct S {
    var name: String { get set }
    subscript(i: Int) -> Int { i > 0 ? i : 0 }
}
class C {
    var label: String { get set }
}
"""
    functions = functions_in_source(source, "Sources/Demo/Box.swift", "/proj")
    assert [(fn.namespace, fn.name, fn.complexity) for fn in functions] == [
        ("Demo.S", "subscript", 2)
    ]


def test_swiftui_body_is_the_view_type():
    source = """
import SwiftUI
struct ContentView: View {
    var ready = true
    var body: some View {
        if ready { Text("hi") }
    }
}
"""
    functions = functions_in_source(source, "Sources/Demo/ContentView.swift", "/proj")
    assert [(fn.namespace, fn.name, fn.complexity) for fn in functions] == [
        ("Demo.ContentView", "body", 2)
    ]


def test_package_and_xcode_names_are_the_module(tmp_path):
    (tmp_path / "Package.swift").write_text(
        "\n".join(
            [
                '.target(name: "RenamedPlain", path: "lib/plain"),',
                '.target(name: "Core", path: "lib/core", dependencies: [.product(name: "X", package: "Y")]),',
                '.target(name: "Also", path: "lib/core"),',
                '.target(name: "CoreKit", path: "Sources/Renamed"),',
                '.testTarget(name: "CoreTests", dependencies: ["Core"]),',
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "App.xcodeproj").mkdir()
    (tmp_path / "Sources" / "Renamed").mkdir(parents=True)
    core = functions_in_source("public func ping() -> Int { 1 }\n", "lib/core/Ping.swift", str(tmp_path))
    assert [(fn.namespace, fn.name) for fn in core] == [("Core", "ping")]
    plain = functions_in_source("func ping() {}\n", "lib/plain/A.swift", str(tmp_path))
    assert plain[0].namespace == "RenamedPlain"
    renamed = functions_in_source("func renamed() {}\n", "Sources/Renamed/Box.swift", str(tmp_path))
    assert renamed[0].namespace == "CoreKit"
    view = functions_in_source(
        "struct ContentView { func body() -> Int { 1 } }\n",
        "App/ContentView.swift",
        str(tmp_path),
    )
    assert [(fn.namespace, fn.name) for fn in view] == [("App.ContentView", "body")]
    ui = functions_in_source("func view() -> Int { 1 }\n", "src/ui/theme.swift", "/proj")
    assert ui[0].namespace == "ui"
    flat = functions_in_source("func open() {}\n", "Sources/Box.swift", "/proj")
    assert flat[0].namespace == "Sources"
    doubled = functions_in_source("func open() {}\n", "Sources//Demo/Box.swift", "/proj")
    assert doubled[0].namespace == "Demo"
    (tmp_path / "mobile" / "IOS.xcodeproj").mkdir(parents=True)
    ios = functions_in_source(
        "struct ContentView { func body() {} }\n",
        "mobile/feature/ContentView.swift",
        str(tmp_path),
    )
    assert [(fn.namespace, fn.name) for fn in ios] == [("IOS.ContentView", "body")]


def test_a_workspace_names_the_module_when_a_project_is_beside_it(tmp_path):
    (tmp_path / "Proj.xcodeproj").mkdir()
    (tmp_path / "Work.xcworkspace").mkdir()
    functions = functions_in_source(
        "struct ContentView { func body() {} }\n",
        "App/ContentView.swift",
        str(tmp_path),
    )
    assert [(fn.namespace, fn.name) for fn in functions] == [("Work.ContentView", "body")]


def test_a_commented_target_does_not_name_the_module(tmp_path):
    (tmp_path / "Package.swift").write_text(
        "\n".join(
            [
                '// .target(name: "Stale", path: "Sources/Demo"),',
                '/* .target(name: "Blocked", path: "Sources/Demo") */',
                '.testTarget(name: "DemoTests", path: "lib/demo"),',
                '.target(name: "Demo", path: "lib/demo"),',
                '.executableTarget(name: "Tool", path: "lib/tool"),',
                '.target(name: "Weird", path: "lib/odd", cSettings: [.define("FOO", to: "a)b")]),',
                '.target(name: "Wide", path: """',
                "lib/wide",
                '"""),',
            ]
        ),
        encoding="utf-8",
    )
    demo = functions_in_source("func open() {}\n", "lib/demo/Box.swift", str(tmp_path))
    assert demo[0].namespace == "Demo"
    tool = functions_in_source("func main() {}\n", "lib/tool/Main.swift", str(tmp_path))
    assert tool[0].namespace == "Tool"
    weird = functions_in_source("func open() {}\n", "lib/odd/Box.swift", str(tmp_path))
    assert weird[0].namespace == "Weird"
    wide = functions_in_source("func open() {}\n", "lib/wide/Box.swift", str(tmp_path))
    assert wide[0].namespace == "Wide"


def test_swift_tests_and_build_products_are_not_scored(tmp_path):
    source = tmp_path / "Sources" / "Demo" / "Box.swift"
    source.parent.mkdir(parents=True)
    source.write_text("func open() {}\n", encoding="utf-8")
    for relative in (
        "Tests/DemoTests/BoxTests.swift",
        "AppTests/Board.swift",
        ".build/debug/Generated.swift",
        ".swiftpm/cache/Generated.swift",
        "DerivedData/App.swift",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("func hidden() {}\n", encoding="utf-8")
    assert is_test_file(tmp_path / "Tests" / "DemoTests" / "BoxTests.swift")
    assert is_test_file(tmp_path / "AppTests" / "Board.swift")
    assert iter_source_files([tmp_path]) == [source.resolve()]


def _swift_project(tmp_path: Path, report_name: str) -> None:
    source = tmp_path / "Sources" / "Demo" / "Box.swift"
    source.parent.mkdir(parents=True)
    source.write_text(_BOX, encoding="utf-8")
    report = tmp_path / "target" / "coverage" / "swift" / report_name
    report.parent.mkdir(parents=True)
    report.write_text((_FIXTURES / report_name).read_text(encoding="utf-8"), encoding="utf-8")


def _snapshot(tmp_path: Path) -> str:
    assert run(["--root", str(tmp_path), "--use-existing-coverage"]) == 0
    return (tmp_path / ".metrics" / "crap.edn").read_text(encoding="utf-8")


def _xccov_snapshot(tmp_path: Path, report: dict) -> str:
    _swift_project(tmp_path, "xccov.json")
    destination = tmp_path / "target" / "coverage" / "swift" / "xccov.json"
    destination.write_text(json.dumps(report), encoding="utf-8")
    return _snapshot(tmp_path)


def test_llvm_cov_regions_join_the_swift_snapshot(tmp_path):
    _swift_project(tmp_path, "llvm-cov.json")
    text = _snapshot(tmp_path)
    assert ':name "choose", :namespace "Demo", :complexity 2, :coverage 50.0, :crap 2.5' in text
    assert ':name "open", :namespace "Demo.Box", :complexity 1, :coverage 100.0, :crap 1.0' in text


def _llvm_regions(filename: str, regions: list) -> str:
    return json.dumps(
        {
            "type": "llvm.coverage.json.export",
            "data": [
                {
                    "files": [{"filename": filename}],
                    "functions": [{"filenames": [filename], "regions": regions}],
                }
            ],
        }
    )


def test_a_function_region_follows_that_functions_filenames():
    text = (_FIXTURES / "function-filenames.json").read_text(encoding="utf-8")
    files = parse_swift_coverage(text)
    place = files["/proj/Sources/Demo/Place.swift"]
    entry = files["/proj/DerivedSources/test_entry_point.swift"]
    assert place.regions == [(4, 5, 1)]
    assert entry.regions == [(1, 1, 1)]
    assert place.line_covered(4)
    assert place.line_covered(5)
    assert not place.line_covered(1)
    assert entry.line_covered(1)
    assert not entry.line_covered(4)
    assert not entry.line_covered(5)


def test_a_region_without_function_filenames_uses_the_unit_file_list():
    text = json.dumps(
        {
            "type": "llvm.coverage.json.export",
            "data": [
                {
                    "files": [
                        {"filename": "First.swift"},
                        {"filename": "Second.swift"},
                    ],
                    "functions": [
                        {"regions": [[4, 1, 5, 1, 1, 0, 0, 0]]},
                        {"filenames": [], "regions": [[1, 1, 1, 2, 1, 1, 0, 0]]},
                    ],
                }
            ],
        }
    )
    files = parse_swift_coverage(text)
    assert files["First.swift"].line_covered(4)
    assert files["First.swift"].line_covered(5)
    assert not files["First.swift"].line_covered(1)
    assert files["Second.swift"].regions == [(1, 1, 1)]
    assert files["Second.swift"].line_covered(1)
    assert not files["Second.swift"].line_covered(5)


def test_a_region_file_id_outside_the_function_filenames_is_ignored():
    text = json.dumps(
        {
            "type": "llvm.coverage.json.export",
            "data": [
                {
                    "files": [
                        {"filename": "Other.swift"},
                        {"filename": "Place.swift"},
                    ],
                    "functions": [
                        {
                            "filenames": ["Place.swift"],
                            "regions": [[4, 1, 5, 1, 1, 1, 0, 0]],
                        }
                    ],
                }
            ],
        }
    )
    files = parse_swift_coverage(text)
    assert not files["Other.swift"].line_covered(5)
    assert not files["Place.swift"].line_covered(4)
    assert not files["Place.swift"].line_covered(5)


def test_an_empty_function_filename_does_not_receive_the_region():
    text = json.dumps(
        {
            "type": "llvm.coverage.json.export",
            "data": [
                {
                    "files": [{"filename": "Place.swift"}],
                    "functions": [
                        {
                            "filenames": ["", "Place.swift"],
                            "regions": [
                                [4, 1, 5, 1, 1, 0, 0, 0],
                                [2, 1, 2, 1, 1, 1, 0, 0],
                            ],
                        }
                    ],
                }
            ],
        }
    )
    files = parse_swift_coverage(text)
    assert "" not in files
    assert files["Place.swift"].regions == [(2, 2, 1)]
    assert files["Place.swift"].line_covered(2)
    assert not files["Place.swift"].line_covered(5)


def test_a_function_filename_absent_from_the_unit_still_keeps_its_region():
    text = json.dumps(
        {
            "type": "llvm.coverage.json.export",
            "data": [
                {
                    "files": [{"filename": "Other.swift"}],
                    "functions": [
                        {
                            "filenames": ["Place.swift"],
                            "regions": [[4, 1, 5, 1, 1, 0, 0, 0]],
                        }
                    ],
                }
            ],
        }
    )
    files = parse_swift_coverage(text)
    assert files["Place.swift"].regions == [(4, 5, 1)]
    assert files["Place.swift"].line_covered(5)
    assert not files["Other.swift"].line_covered(5)


def test_a_unit_file_with_an_empty_name_is_skipped():
    text = json.dumps(
        {
            "data": [
                {
                    "files": [
                        {"filename": "", "segments": [[1, 1, 1, True, True, False]]},
                        {"filename": "Place.swift", "segments": [[2, 1, 1, True, True, False]]},
                    ],
                    "functions": [],
                }
            ]
        }
    )
    files = parse_swift_coverage(text)
    assert "" not in files
    assert files["Place.swift"].line_covered(2)


def test_a_region_records_its_end_line_and_covers_that_span():
    text = _llvm_regions(
        "Sources/Demo/Box.swift",
        [
            [4, 9, 5, 2, 1, 0, 0, 0],
            [2, 1, 2, 4, 0, 0, 0, 0],
            [4, 1, "end", 2, 1, 0, 0, 0],
        ],
    )
    record = parse_swift_coverage(text)["Sources/Demo/Box.swift"]
    assert record.regions == [(4, 5, 1), (2, 2, 0)]
    assert record.line_covered(4)
    assert record.line_covered(5)
    assert not record.line_covered(2)
    assert not record.line_covered(3)
    assert not record.line_covered(6)


def test_the_innermost_region_decides_whether_a_line_is_covered():
    nested = SwiftFile(regions=[(1, 6, 1), (4, 5, 0)])
    assert nested.line_covered(1)
    assert nested.line_covered(3)
    assert not nested.line_covered(4)
    assert not nested.line_covered(5)
    assert nested.line_covered(6)
    assert not nested.line_covered(7)

    later = SwiftFile(regions=[(4, 5, 0), (5, 6, 1)])
    assert not later.line_covered(4)
    assert later.line_covered(5)
    assert later.line_covered(6)

    same = SwiftFile(regions=[(4, 5, 0), (4, 5, 1)])
    assert not same.line_covered(4)
    assert not same.line_covered(5)


def test_a_segment_region_is_a_single_line():
    text = json.dumps(
        {
            "data": [
                {
                    "files": [
                        {
                            "filename": "Short.swift",
                            "segments": ["nope", [1, 2], [2, 5, 1, True]],
                        }
                    ],
                    "functions": [],
                }
            ]
        }
    )
    short = parse_swift_coverage(text)["Short.swift"]
    assert short.regions == [(2, 2, 1)]
    text = json.dumps(
        {
            "data": [
                {
                    "files": [
                        {
                            "filename": "Gap.swift",
                            "segments": [[2, 5, 1, True, False]],
                        }
                    ],
                    "functions": [],
                }
            ]
        }
    )
    gap = parse_swift_coverage(text)["Gap.swift"]
    assert gap.regions == []
    assert not gap.line_covered(2)
    text = (_FIXTURES / "segments.json").read_text(encoding="utf-8")
    record = parse_swift_coverage(text)["Sources/Demo/Box.swift"]
    assert (2, 2, 1) in record.regions
    assert (5, 5, 0) in record.regions
    assert record.line_covered(2)
    assert not record.line_covered(3)
    assert not record.line_covered(5)


def test_an_xccov_summary_does_not_mark_a_line_covered():
    record = SwiftFile(summaries=[(2, 1, 1)])
    assert record.line_covered(2) is False


def test_an_xccov_file_with_an_empty_name_is_skipped():
    text = json.dumps(
        {
            "files": [
                {
                    "name": "",
                    "functions": [{"lineNumber": 1, "coveredLines": 1, "executableLines": 1}],
                },
                {
                    "path": "Sources/Demo/Box.swift",
                    "functions": [{"lineNumber": 1, "coveredLines": 1, "executableLines": 2}],
                },
            ]
        }
    )
    files = parse_swift_coverage(text)
    assert "" not in files
    assert files["Sources/Demo/Box.swift"].summaries == [(1, 1, 2)]


def test_an_xccov_function_missing_either_count_is_ignored():
    text = json.dumps(
        {
            "files": [
                {
                    "path": "Place.swift",
                    "functions": [
                        {"lineNumber": 4, "coveredLines": 1},
                        {"executableLines": 1, "coveredLines": 1},
                        {"lineNumber": 2, "executableLines": 1, "coveredLines": 1},
                    ],
                }
            ]
        }
    )
    record = parse_swift_coverage(text)["Place.swift"]
    assert record.summaries == [(2, 1, 1)]


def test_a_spanning_region_still_counts_once_toward_crap(tmp_path):
    source = tmp_path / "Sources" / "Demo" / "Box.swift"
    source.parent.mkdir(parents=True)
    source.write_text(_BOX, encoding="utf-8")
    report = tmp_path / "target" / "coverage" / "swift" / "llvm-cov.json"
    report.parent.mkdir(parents=True)
    report.write_text(
        _llvm_regions(
            "Sources/Demo/Box.swift",
            [
                [2, 1, 2, 4, 0, 0, 0, 0],
                [4, 1, 5, 2, 1, 0, 0, 0],
            ],
        ),
        encoding="utf-8",
    )
    text = _snapshot(tmp_path)
    assert ':name "choose", :namespace "Demo", :complexity 2, :coverage 50.0, :crap 2.5' in text
    assert ':name "open", :namespace "Demo.Box", :complexity 1, :coverage 0.0, :crap 2.0' in text
    record = parse_swift_coverage(report.read_text(encoding="utf-8"))["Sources/Demo/Box.swift"]
    assert record.line_covered(5)
    assert not record.line_covered(2)


def test_llvm_cov_segments_are_used_when_a_function_has_no_regions(tmp_path):
    _swift_project(tmp_path, "segments.json")
    text = _snapshot(tmp_path)
    assert ':name "choose", :namespace "Demo", :complexity 2, :coverage 50.0, :crap 2.5' in text
    assert ':name "open", :namespace "Demo.Box", :complexity 1, :coverage 0.0, :crap 2.0' in text


def _plant(root: Path, relative: str, source: str = "") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def test_swift_export_uses_the_default_json_format():
    command = swift_export_command("llvm-cov", Path("DemoTests"), Path("default.profdata"))
    assert command == [
        "llvm-cov",
        "export",
        "-instr-profile=default.profdata",
        "DemoTests",
    ]


def test_a_swift_package_exports_llvm_cov_json(tmp_path, monkeypatch, capsys):
    _plant(tmp_path, "Package.swift", "// swift-tools-version: 5.9\n")
    source = _plant(tmp_path, "Sources/Demo/Box.swift", "func open() {}\n")
    profdata = tmp_path / ".build" / "debug" / "codecov" / "default.profdata"
    binary = tmp_path / ".build" / "debug" / "DemoPackageTests"
    commands = []
    exports = []

    def shell(command, cwd):
        commands.append(list(command))
        profdata.parent.mkdir(parents=True, exist_ok=True)
        profdata.write_text("prof", encoding="utf-8")
        binary.write_text("bin", encoding="utf-8")
        return 0

    def export(command, cwd, destination):
        exports.append(list(command))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("{}", encoding="utf-8")
        return 0

    monkeypatch.setattr(
        "crapper.runners.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"swift", "llvm-cov"} else None,
    )
    monkeypatch.setattr("crapper.runners.run_shell", shell)
    monkeypatch.setattr("crapper.runners.write_command_output", export)
    assert run_coverage(tmp_path, [source], None) == 0
    assert commands == [["swift", "test", "--enable-code-coverage"]]
    assert exports == [
        [
            "/usr/bin/llvm-cov",
            "export",
            f"-instr-profile={profdata}",
            str(binary),
        ]
    ]
    assert (tmp_path / "target" / "coverage" / "swift" / "llvm-cov.json").is_file()
    assert "exited" not in capsys.readouterr().err


def test_an_xcode_app_exports_an_xccov_report(tmp_path, monkeypatch):
    project = tmp_path / "App.xcodeproj"
    _plant(project, "xcshareddata/xcschemes/App.xcscheme", "<Scheme/>\n")
    source = _plant(tmp_path, "App/ContentView.swift", "func body() {}\n")
    commands = []
    exports = []

    def shell(command, cwd):
        commands.append(list(command))
        return 0

    def export(command, cwd, destination):
        exports.append(list(command))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("{}", encoding="utf-8")
        return 0

    monkeypatch.setattr(
        "crapper.runners.shutil.which",
        lambda name: "/usr/bin/xcodebuild" if name == "xcodebuild" else None,
    )
    monkeypatch.setattr("crapper.runners.run_shell", shell)
    monkeypatch.setattr("crapper.runners.write_command_output", export)
    assert run_coverage(tmp_path, [source], None) == 0
    assert len(commands) == 1
    command = commands[0]
    assert command[:8] == [
        "xcodebuild",
        "test",
        "-project",
        str(project),
        "-scheme",
        "App",
        "-enableCodeCoverage",
        "YES",
    ]
    assert command[8] == "-resultBundlePath"
    result = Path(command[9])
    assert result.name == "Test.xcresult"
    assert "target/coverage/swift" in result.as_posix()
    assert exports == [["xcrun", "xccov", "view", "--report", "--json", str(result)]]


def test_a_package_and_an_app_outside_it_are_both_measured(tmp_path, monkeypatch):
    _plant(tmp_path, "libs/Demo/Package.swift", "")
    package_source = _plant(tmp_path, "libs/Demo/Sources/Demo/Box.swift", "func open() {}\n")
    _plant(tmp_path, "App.xcodeproj/xcshareddata/xcschemes/App.xcscheme", "<Scheme/>\n")
    app_source = _plant(tmp_path, "App/ContentView.swift", "func body() {}\n")
    commands = []
    monkeypatch.setattr(
        "crapper.runners.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"swift", "xcodebuild"} else None,
    )
    monkeypatch.setattr(
        "crapper.runners.run_shell",
        lambda command, cwd: commands.append(command[0]) or 1,
    )
    run_coverage(tmp_path, [package_source, app_source], None)
    assert commands == ["swift", "xcodebuild"]


def test_a_package_is_not_also_measured_with_xcodebuild(tmp_path, monkeypatch):
    _plant(tmp_path, "Package.swift", "")
    _plant(tmp_path, "App.xcodeproj/xcshareddata/xcschemes/App.xcscheme", "<Scheme/>\n")
    source = _plant(tmp_path, "Sources/Demo/Box.swift", "func open() {}\n")
    commands = []
    monkeypatch.setattr("crapper.runners.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        "crapper.runners.run_shell",
        lambda command, cwd: commands.append(list(command)) or 1,
    )
    monkeypatch.setattr("crapper.runners.write_command_output", lambda *args: 0)
    run_coverage(tmp_path, [source], None)
    assert commands == [["swift", "test", "--enable-code-coverage"]]


def test_a_workspace_is_measured_instead_of_a_nested_project(tmp_path, monkeypatch):
    _plant(tmp_path, "App.xcworkspace/xcshareddata/xcschemes/App.xcscheme", "<Scheme/>\n")
    _plant(tmp_path, "App.xcodeproj/project.pbxproj", "")
    source = _plant(tmp_path, "App/ContentView.swift", "func body() {}\n")
    commands = []
    monkeypatch.setattr("crapper.runners.shutil.which", lambda name: "/usr/bin/xcodebuild" if name == "xcodebuild" else None)
    monkeypatch.setattr("crapper.runners.run_shell", lambda command, cwd: commands.append(list(command)) or 0)
    monkeypatch.setattr("crapper.runners.write_command_output", lambda *args: 0)
    run_coverage(tmp_path, [source], None)
    assert commands[0][2] == "-workspace"
    assert commands[0][3].endswith("App.xcworkspace")


def test_xcode_without_a_shared_scheme_does_not_build(tmp_path, monkeypatch, capsys):
    (tmp_path / "App.xcodeproj").mkdir()
    source = _plant(tmp_path, "App/ContentView.swift", "func body() {}\n")
    monkeypatch.setattr("crapper.runners.shutil.which", lambda name: "/usr/bin/xcodebuild" if name == "xcodebuild" else None)
    monkeypatch.setattr(
        "crapper.runners.run_shell",
        lambda command, cwd: (_ for _ in ()).throw(AssertionError(command)),
    )
    assert run_coverage(tmp_path, [source], None) == 0
    assert "No shared Xcode scheme" in capsys.readouterr().err


def _plant_profdata(package: Path) -> None:
    profdata = package / ".build" / "debug" / "codecov" / "default.profdata"
    profdata.parent.mkdir(parents=True, exist_ok=True)
    profdata.write_text("prof", encoding="utf-8")


def test_llvm_cov_exports_the_test_binary_not_the_dsym(tmp_path, monkeypatch):
    _plant(tmp_path, "Package.swift", "")
    source = _plant(tmp_path, "Sources/Demo/Box.swift", "func open() {}\n")
    _plant_profdata(tmp_path)
    dsym = tmp_path / ".build" / "debug" / "DemoPackageTests.dSYM" / "Contents" / "Resources" / "DWARF" / "DemoPackageTests"
    binary = tmp_path / ".build" / "debug" / "DemoPackageTests.xctest" / "Contents" / "MacOS" / "DemoPackageTests"
    dsym.parent.mkdir(parents=True)
    binary.parent.mkdir(parents=True)
    dsym.write_text("dwarf", encoding="utf-8")
    binary.write_text("bin", encoding="utf-8")
    exports = []

    def export(command, cwd, destination):
        exports.append(list(command))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("{}", encoding="utf-8")
        return 0

    monkeypatch.setattr(
        "crapper.runners.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"swift", "llvm-cov"} else None,
    )
    monkeypatch.setattr("crapper.runners.run_shell", lambda command, cwd: 0)
    monkeypatch.setattr("crapper.runners.write_command_output", export)
    assert run_coverage(tmp_path, [source], None) == 0
    assert exports[0][-1] == str(binary)


def test_a_linux_xctest_file_is_the_swift_test_binary(tmp_path, monkeypatch):
    _plant(tmp_path, "Package.swift", "")
    source = _plant(tmp_path, "Sources/Demo/Box.swift", "func open() {}\n")
    _plant_profdata(tmp_path)
    binary = tmp_path / ".build" / "x86_64-unknown-linux-gnu" / "debug" / "DemoPackageTests.xctest"
    binary.parent.mkdir(parents=True)
    binary.write_text("bin", encoding="utf-8")
    exports = []

    def export(command, cwd, destination):
        exports.append(list(command))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("{}", encoding="utf-8")
        return 0

    monkeypatch.setattr(
        "crapper.runners.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"swift", "llvm-cov"} else None,
    )
    monkeypatch.setattr("crapper.runners.run_shell", lambda command, cwd: 0)
    monkeypatch.setattr("crapper.runners.write_command_output", export)
    assert run_coverage(tmp_path, [source], None) == 0
    assert exports[0][-1] == str(binary)


def test_llvm_cov_beside_swift_is_used_when_it_is_not_on_the_path(tmp_path, monkeypatch):
    swift = tmp_path / "tool" / "swift"
    llvm = tmp_path / "tool" / "llvm-cov"
    swift.parent.mkdir()
    swift.write_text("", encoding="utf-8")
    llvm.write_text("", encoding="utf-8")
    _plant(tmp_path, "Package.swift", "")
    source = _plant(tmp_path, "Sources/Demo/Box.swift", "func open() {}\n")
    profdata = tmp_path / ".build" / "debug" / "codecov" / "default.profdata"
    binary = tmp_path / ".build" / "debug" / "DemoPackageTests"
    exports = []

    def which(name):
        if name == "swift":
            return str(swift)
        return None

    def shell(command, cwd):
        profdata.parent.mkdir(parents=True, exist_ok=True)
        profdata.write_text("prof", encoding="utf-8")
        binary.write_text("bin", encoding="utf-8")
        return 0

    def export(command, cwd, destination):
        exports.append(command[0])
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("{}", encoding="utf-8")
        return 0

    monkeypatch.setattr("crapper.runners.shutil.which", which)
    monkeypatch.setattr("crapper.runners.run_shell", shell)
    monkeypatch.setattr("crapper.runners.write_command_output", export)
    run_coverage(tmp_path, [source], None)
    assert exports == [str(llvm)]


def _program(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    return path


def _which(found: dict[str, str]):
    return lambda name: found.get(name)


def test_xcrun_finds_llvm_cov_when_it_is_not_beside_swift(tmp_path, monkeypatch):
    llvm = tmp_path / "XcodeDefault.xctoolchain" / "usr" / "bin" / "llvm-cov"
    llvm.parent.mkdir(parents=True)
    llvm.write_text("", encoding="utf-8")
    xcrun = _program(
        tmp_path / "bin" / "xcrun",
        "#!/bin/sh\n"
        'if [ "$1" = "--find" ] && [ "$2" = "llvm-cov" ]; then\n'
        f"  printf '%s\\n' '{llvm}'\n"
        "  exit 0\n"
        "fi\n"
        "exit 1\n",
    )
    swift = tmp_path / "usr" / "bin" / "swift"
    swift.parent.mkdir(parents=True)
    swift.write_text("", encoding="utf-8")
    _plant(tmp_path, "Package.swift", "")
    source = _plant(tmp_path, "Sources/Demo/Box.swift", "func open() {}\n")
    profdata = tmp_path / ".build" / "debug" / "codecov" / "default.profdata"
    _plant_profdata(tmp_path)
    binary = tmp_path / ".build" / "debug" / "DemoPackageTests"
    binary.write_text("bin", encoding="utf-8")
    exports = []

    def export(command, cwd, destination):
        exports.append(list(command))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("{}", encoding="utf-8")
        return 0

    monkeypatch.setattr(
        "crapper.runners.shutil.which",
        _which({"swift": str(swift), "xcrun": str(xcrun)}),
    )
    monkeypatch.setattr("crapper.runners.run_shell", lambda command, cwd: 0)
    monkeypatch.setattr("crapper.runners.write_command_output", export)
    assert run_coverage(tmp_path, [source], None) == 0
    assert exports == [
        [str(llvm), "export", f"-instr-profile={profdata}", str(binary)]
    ]


def test_llvm_cov_beside_swift_wins_over_xcrun(tmp_path, monkeypatch):
    swift = tmp_path / "tool" / "swift"
    sibling = tmp_path / "tool" / "llvm-cov"
    other = tmp_path / "xcode" / "llvm-cov"
    swift.parent.mkdir()
    sibling.write_text("", encoding="utf-8")
    other.parent.mkdir()
    other.write_text("", encoding="utf-8")
    xcrun = _program(
        tmp_path / "xcrun",
        f"#!/bin/sh\nprintf '%s\\n' '{other}'\n",
    )
    monkeypatch.setattr(
        "crapper.runners.shutil.which",
        _which({"swift": str(swift), "xcrun": str(xcrun)}),
    )
    assert llvm_cov_tool() == str(sibling.resolve())


def test_a_missing_or_failing_xcrun_leaves_llvm_cov_unset(tmp_path, monkeypatch):
    monkeypatch.setattr("crapper.runners.shutil.which", lambda name: None)
    assert llvm_cov_tool() is None

    broken = _program(tmp_path / "xcrun", "#!/bin/sh\nexit 1\n")
    monkeypatch.setattr(
        "crapper.runners.shutil.which",
        _which({"xcrun": str(broken)}),
    )
    assert llvm_cov_tool() is None

    blank = _program(tmp_path / "blank-xcrun", "#!/bin/sh\nexit 0\n")
    monkeypatch.setattr(
        "crapper.runners.shutil.which",
        _which({"xcrun": str(blank)}),
    )
    assert llvm_cov_tool() is None

    missing_file = _program(
        tmp_path / "missing-file-xcrun",
        "#!/bin/sh\nprintf '%s\\n' '/no/such/llvm-cov'\n",
    )
    monkeypatch.setattr(
        "crapper.runners.shutil.which",
        _which({"xcrun": str(missing_file)}),
    )
    assert llvm_cov_tool() is None

    monkeypatch.setattr(
        "crapper.runners.shutil.which",
        _which({"xcrun": str(tmp_path / "not-there")}),
    )
    assert llvm_cov_tool() is None


def _xctest_binary(package: Path, directory: str, name: str) -> Path:
    binary = package / directory / f"{name}.xctest" / "Contents" / "MacOS" / name
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text("bin", encoding="utf-8")
    return binary


def _swift_stub(path: Path) -> Path:
    return _program(
        path,
        "#!/bin/sh\n"
        'if [ "$1" = "build" ] && [ "$2" = "--show-bin-path" ]; then\n'
        '  printf "%s\\n" "$SHOW_BIN_PATH"\n'
        '  exit "${SHOW_BIN_STATUS:-0}"\n'
        "fi\n"
        "exit 1\n",
    )


def test_the_current_toolchain_test_binary_is_inside_the_xctest_bundle(tmp_path):
    binary = _xctest_binary(tmp_path, ".build/out/Products/Debug", "DemoTests")
    dsym = tmp_path / ".build/out/Products/Debug/DemoTests.dSYM/Contents/MacOS/DemoTests"
    dsym.parent.mkdir(parents=True)
    dsym.write_text("dwarf", encoding="utf-8")
    plist = binary.parents[1] / "Info.plist"
    plist.write_text("plist", encoding="utf-8")
    assert swift_test_binary(tmp_path) == binary


def test_a_linux_tests_xctest_file_is_the_test_binary(tmp_path):
    binary = tmp_path / ".build" / "debug" / "DemoTests.xctest"
    binary.parent.mkdir(parents=True)
    binary.write_text("bin", encoding="utf-8")
    assert swift_test_binary(tmp_path) == binary


def test_the_earliest_test_executable_is_chosen(tmp_path):
    first = _xctest_binary(tmp_path, ".build/out/Products/Debug", "AAATests")
    _xctest_binary(tmp_path, ".build/out/Products/Debug", "ZZZTests")
    assert swift_test_binary(tmp_path) == first


def test_a_bare_tests_file_is_not_the_test_binary(tmp_path):
    bare = tmp_path / ".build" / "debug" / "AAATests"
    bare.parent.mkdir(parents=True)
    bare.write_text("bin", encoding="utf-8")
    packaged = tmp_path / ".build" / "debug" / "DemoPackageTests"
    packaged.write_text("bin", encoding="utf-8")
    assert swift_test_binary(tmp_path) == packaged


def test_show_bin_path_is_preferred_to_another_build_product(tmp_path, monkeypatch):
    swift = _swift_stub(tmp_path / "swift")
    chosen = _xctest_binary(tmp_path, "products", "ZedTests")
    decoy = tmp_path / ".build" / "debug" / "AAAPackageTests"
    decoy.parent.mkdir(parents=True)
    decoy.write_text("bin", encoding="utf-8")
    monkeypatch.setattr("crapper.runners.shutil.which", _which({"swift": str(swift)}))
    monkeypatch.setenv("SHOW_BIN_PATH", str(tmp_path / "products"))
    monkeypatch.setenv("SHOW_BIN_STATUS", "0")
    assert swift_test_binary(tmp_path) == chosen


def test_a_relative_show_bin_path_is_inside_the_package(tmp_path, monkeypatch):
    swift = _swift_stub(tmp_path / "swift")
    chosen = _xctest_binary(tmp_path, "products", "ZedTests")
    decoy = tmp_path / ".build" / "debug" / "AAAPackageTests"
    decoy.parent.mkdir(parents=True)
    decoy.write_text("bin", encoding="utf-8")
    monkeypatch.setattr("crapper.runners.shutil.which", _which({"swift": str(swift)}))
    monkeypatch.setenv("SHOW_BIN_PATH", "products")
    monkeypatch.setenv("SHOW_BIN_STATUS", "0")
    assert swift_test_binary(tmp_path) == chosen


def test_show_bin_path_falls_back_when_it_does_not_name_a_product(tmp_path, monkeypatch):
    swift = _swift_stub(tmp_path / "swift")
    chosen = tmp_path / ".build" / "debug" / "DemoPackageTests"
    chosen.parent.mkdir(parents=True)
    chosen.write_text("bin", encoding="utf-8")
    _xctest_binary(tmp_path, "elsewhere", "AAATests")
    monkeypatch.setattr("crapper.runners.shutil.which", _which({"swift": str(swift)}))

    monkeypatch.setenv("SHOW_BIN_PATH", "")
    monkeypatch.setenv("SHOW_BIN_STATUS", "0")
    assert swift_test_binary(tmp_path) == chosen

    monkeypatch.setenv("SHOW_BIN_PATH", str(tmp_path / "elsewhere"))
    monkeypatch.setenv("SHOW_BIN_STATUS", "1")
    assert swift_test_binary(tmp_path) == chosen

    noted = tmp_path / "not-a-directory"
    noted.write_text("notes", encoding="utf-8")
    monkeypatch.setenv("SHOW_BIN_PATH", str(noted))
    monkeypatch.setenv("SHOW_BIN_STATUS", "0")
    assert swift_test_binary(tmp_path) == chosen

    empty = tmp_path / "empty-products"
    empty.mkdir()
    monkeypatch.setenv("SHOW_BIN_PATH", str(empty))
    assert swift_test_binary(tmp_path) == chosen

    monkeypatch.setattr(
        "crapper.runners.shutil.which",
        _which({"swift": str(tmp_path / "missing-swift")}),
    )
    assert swift_test_binary(tmp_path) == chosen


def test_command_output_is_the_report_file(tmp_path, monkeypatch):
    from crapper.runners import write_command_output

    def fake_run(command, cwd, stdout):
        stdout.write('{"ok": true}')

        class Completed:
            returncode = 0

        return Completed()

    monkeypatch.setattr("crapper.runners.subprocess.run", fake_run)
    destination = tmp_path / "nested" / "out.json"
    assert write_command_output(["llvm-cov"], tmp_path, destination) == 0
    assert destination.read_text(encoding="utf-8") == '{"ok": true}'
    monkeypatch.setattr(
        "crapper.runners.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("missing")),
    )
    assert write_command_output(["llvm-cov"], tmp_path, destination) == 127


def test_xcode_failure_paths_do_not_export(tmp_path, monkeypatch, capsys):
    project = tmp_path / "App.xcodeproj"
    _plant(project, "xcshareddata/xcschemes/App.xcscheme", "<Scheme/>\n")
    source = _plant(tmp_path, "App/ContentView.swift", "func body() {}\n")
    calls = []
    monkeypatch.setattr("crapper.runners.shutil.which", lambda name: None)
    monkeypatch.setattr(
        "crapper.runners.run_shell",
        lambda command, cwd: (_ for _ in ()).throw(AssertionError(command)),
    )
    run_coverage(tmp_path, [source], None)
    assert "xcodebuild is not installed" in capsys.readouterr().err

    monkeypatch.setattr("crapper.runners.shutil.which", lambda name: "/usr/bin/xcodebuild" if name == "xcodebuild" else None)
    monkeypatch.setattr("crapper.runners.run_shell", lambda command, cwd: calls.append("test") or 1)
    monkeypatch.setattr(
        "crapper.runners.write_command_output",
        lambda *args: calls.append("export") or 0,
    )
    run_coverage(tmp_path, [source], None)
    assert calls == ["test"]
    assert "Xcode coverage exited" in capsys.readouterr().err

    calls.clear()
    result = tmp_path / "target" / "coverage" / "swift" / "App.xcodeproj" / "Test.xcresult"
    result.mkdir(parents=True)
    (result / "old").write_text("stale", encoding="utf-8")
    monkeypatch.setattr("crapper.runners.run_shell", lambda command, cwd: calls.append(command) or 0)
    monkeypatch.setattr("crapper.runners.write_command_output", lambda *args: calls.append("export") or 3)
    run_coverage(tmp_path, [source], None)
    assert not (result / "old").exists()
    assert calls[-1] == "export"
    assert "xccov exited 3" in capsys.readouterr().err


def test_a_failed_swift_run_forgets_the_previous_report(tmp_path, monkeypatch):
    _plant(tmp_path, "Package.swift", "// swift-tools-version: 5.9\n")
    _swift_project(tmp_path, "llvm-cov.json")
    source = tmp_path / "Sources" / "Demo" / "Box.swift"
    monkeypatch.setattr(
        "crapper.runners.shutil.which",
        lambda name: "/usr/bin/swift" if name == "swift" else None,
    )
    monkeypatch.setattr("crapper.runners.run_shell", lambda command, cwd: 1)
    assert run_coverage(tmp_path, [source], None) == 0
    assert ':name "choose", :namespace "Demo", :complexity 2, :coverage 0.0, :crap 6.0' in _snapshot(tmp_path)


def test_a_failed_llvm_cov_export_is_not_scored(tmp_path, monkeypatch):
    _plant(tmp_path, "Package.swift", "")
    _swift_project(tmp_path, "llvm-cov.json")
    _plant_profdata(tmp_path)
    binary = tmp_path / ".build" / "debug" / "DemoPackageTests"
    binary.write_text("bin", encoding="utf-8")
    source = tmp_path / "Sources" / "Demo" / "Box.swift"

    def export(command, cwd, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text((_FIXTURES / "llvm-cov.json").read_text(encoding="utf-8"), encoding="utf-8")
        return 1

    monkeypatch.setattr(
        "crapper.runners.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"swift", "llvm-cov"} else None,
    )
    monkeypatch.setattr("crapper.runners.run_shell", lambda command, cwd: 0)
    monkeypatch.setattr("crapper.runners.write_command_output", export)
    assert run_coverage(tmp_path, [source], None) == 0
    assert ':name "choose", :namespace "Demo", :complexity 2, :coverage 0.0, :crap 6.0' in _snapshot(tmp_path)


def test_a_failed_xcode_run_forgets_the_previous_report(tmp_path, monkeypatch):
    project = tmp_path / "App.xcodeproj"
    _plant(project, "xcshareddata/xcschemes/App.xcscheme", "<Scheme/>\n")
    source = tmp_path / "Sources" / "Demo" / "Box.swift"
    source.parent.mkdir(parents=True)
    source.write_text(_BOX, encoding="utf-8")
    report = tmp_path / "target" / "coverage" / "swift" / "App.xcodeproj" / "xccov.json"
    report.parent.mkdir(parents=True)
    report.write_text((_FIXTURES / "xccov.json").read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(
        "crapper.runners.shutil.which",
        lambda name: "/usr/bin/xcodebuild" if name == "xcodebuild" else None,
    )
    monkeypatch.setattr("crapper.runners.run_shell", lambda command, cwd: 1)
    assert run_coverage(tmp_path, [source], None) == 0
    assert ':name "choose", :namespace "Demo", :complexity 2, :coverage 0.0, :crap 6.0' in _snapshot(tmp_path)


def test_swift_export_needs_the_profile_the_binary_and_llvm_cov(tmp_path, monkeypatch, capsys):
    _plant(tmp_path, "Package.swift", "")
    source = _plant(tmp_path, "Sources/Demo/Box.swift", "func open() {}\n")
    _plant_profdata(tmp_path)
    exports = []
    monkeypatch.setattr(
        "crapper.runners.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"swift", "llvm-cov"} else None,
    )
    monkeypatch.setattr("crapper.runners.run_shell", lambda command, cwd: 0)
    monkeypatch.setattr(
        "crapper.runners.write_command_output",
        lambda command, cwd, destination: exports.append(command) or 0,
    )
    assert run_coverage(tmp_path, [source], None) == 0
    assert exports == []
    assert "Swift coverage data is missing" in capsys.readouterr().err


def test_swift_without_a_toolchain_does_not_run_a_command(tmp_path, monkeypatch, capsys):
    _plant(tmp_path, "Package.swift", "")
    source = _plant(tmp_path, "Sources/Demo/Box.swift", "func open() {}\n")
    monkeypatch.setattr("crapper.runners.shutil.which", lambda name: None)
    monkeypatch.setattr("crapper.runners.run_shell", lambda command, cwd: (_ for _ in ()).throw(AssertionError(command)))
    assert run_coverage(tmp_path, [source], None) == 0
    assert "swift is not installed" in capsys.readouterr().err


def test_a_broken_swift_report_does_not_hide_a_good_one(tmp_path):
    _swift_project(tmp_path, "llvm-cov.json")
    broken = tmp_path / "target" / "coverage" / "swift" / "broken.json"
    broken.write_text("{", encoding="utf-8")
    text = _snapshot(tmp_path)
    assert ':name "choose", :namespace "Demo", :complexity 2, :coverage 50.0, :crap 2.5' in text


def test_xccov_accepts_a_target_list_and_a_bare_file(tmp_path):
    import json

    report = json.loads((_FIXTURES / "xccov.json").read_text(encoding="utf-8"))
    target = report["targets"][0]
    _swift_project(tmp_path, "xccov.json")
    destination = tmp_path / "target" / "coverage" / "swift" / "xccov.json"
    destination.write_text(json.dumps([None, target]), encoding="utf-8")
    text = _snapshot(tmp_path)
    assert ':name "choose", :namespace "Demo", :complexity 2, :coverage 50.0, :crap 2.5' in text
    report["targets"] = [None, target]
    destination.write_text(json.dumps(report), encoding="utf-8")
    assert ':coverage 50.0' in _snapshot(tmp_path)
    bare = {"files": [{"name": "Sources/Demo/Box.swift", "functions": target["files"][0]["functions"]}]}
    destination.write_text(json.dumps(bare), encoding="utf-8")
    assert ':coverage 50.0' in _snapshot(tmp_path)
    destination.write_text("null", encoding="utf-8")
    assert ':name "choose", :namespace "Demo", :complexity 2, :coverage 0.0, :crap 6.0' in _snapshot(tmp_path)


def test_an_xccov_function_without_counts_is_uncovered(tmp_path):
    import json

    _swift_project(tmp_path, "xccov.json")
    report = json.loads((_FIXTURES / "xccov.json").read_text(encoding="utf-8"))
    function = report["targets"][0]["files"][0]["functions"][0]
    function.pop("coveredLines")
    destination = tmp_path / "target" / "coverage" / "swift" / "xccov.json"
    destination.write_text(json.dumps(report), encoding="utf-8")
    assert ':name "choose", :namespace "Demo", :complexity 2, :coverage 0.0, :crap 6.0' in _snapshot(tmp_path)
    function["executableLines"] = "nope"
    destination.write_text(json.dumps(report), encoding="utf-8")
    assert ':name "choose", :namespace "Demo", :complexity 2, :coverage 0.0, :crap 6.0' in _snapshot(tmp_path)


def test_an_xccov_summary_on_the_last_line_still_scores_the_function(tmp_path):
    report = json.loads((_FIXTURES / "xccov.json").read_text(encoding="utf-8"))
    report["targets"][0]["files"][0]["functions"][1]["lineNumber"] = 11
    text = _xccov_snapshot(tmp_path, report)
    assert ':name "open", :namespace "Demo.Box", :complexity 1, :coverage 100.0, :crap 1.0' in text


def test_the_earliest_xccov_summary_inside_the_function_scores_it(tmp_path):
    report = json.loads((_FIXTURES / "xccov.json").read_text(encoding="utf-8"))
    report["targets"][0]["files"][0]["functions"] = [
        {"coveredLines": 2, "executableLines": 2, "lineNumber": 1, "name": "choose(x:)"},
        {"coveredLines": 0, "executableLines": 2, "lineNumber": 4, "name": "later"},
        {"coveredLines": 1, "executableLines": 1, "lineNumber": 9, "name": "Box.open()"},
    ]
    text = _xccov_snapshot(tmp_path, report)
    assert ':name "choose", :namespace "Demo", :complexity 2, :coverage 100.0, :crap 2.0' in text


def test_xccov_report_joins_on_the_function_line(tmp_path):
    _swift_project(tmp_path, "xccov.json")
    text = _snapshot(tmp_path)
    assert ':name "choose", :namespace "Demo", :complexity 2, :coverage 50.0, :crap 2.5' in text
    assert ':name "open", :namespace "Demo.Box", :complexity 1, :coverage 100.0, :crap 1.0' in text
