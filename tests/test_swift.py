import pytest

from crapper.languages.swift import functions_in_source


def entries(source, path="App/Views/Board.swift", root="/proj"):
    return [(fn.namespace, fn.name) for fn in functions_in_source(source, path, root)]


def complexity_of(body, name="choose"):
    found = {fn.name: fn.complexity for fn in functions_in_source(body, "Demo.swift", "/proj")}
    return found[name]


def test_functions_methods_initializers_and_deinitializers_are_entries():
    source = """
func place() {}

final class Board {
    init(size: Int) { self.size = size }
    init?(text: String) { return nil }
    deinit { print("bye") }
    func open() {}
    static func make() -> Board { Board(size: 1) }
}
"""
    assert entries(source) == [
        ("Board", "place"),
        ("Board", "init"),
        ("Board", "init"),
        ("Board", "deinit"),
        ("Board", "open"),
        ("Board", "make"),
    ]


def test_properties_with_a_body_are_one_entry_each():
    source = """
struct Cell {
    var size: Int
    let label = "cell"
    var area: Int {
        get { size * size }
        set { size = newValue }
    }
    var body: some View { Text(label) }
    var watched: Int = 0 {
        willSet { print(newValue) }
        didSet { print(oldValue) }
    }
    lazy var cache: [Int] = { [size] }()
    subscript(index: Int) -> Int { index }
}
"""
    assert entries(source) == [
        ("Cell", "area"),
        ("Cell", "body"),
        ("Cell", "watched"),
        ("Cell", "cache"),
        ("Cell", "subscript"),
    ]


def test_nested_functions_closures_and_protocol_requirements_are_not_entries():
    source = """
protocol Drawable {
    var size: Int { get }
    init(size: Int)
    func draw()
}

struct Shape {
    func render() {
        func local() {}
        let handler = { (x: Int) in x }
        struct Local {
            func inner() {}
        }
        handler(1)
    }
}
"""
    assert entries(source) == [("Shape", "render")]


def test_the_module_after_sources_prefixes_the_type_chain():
    source = """
func helper() {}

enum Feature {
    struct Row {
        func show() {}
    }
}

extension Feature.Row {
    func hide() {}
}

public extension View {
    func card() -> some View { self }
}
"""
    assert entries(source, "Feature/Sources/Feature/Views/Row.swift") == [
        ("Feature", "helper"),
        ("Feature.Feature.Row", "show"),
        ("Feature.Feature.Row", "hide"),
        ("Feature.View", "card"),
    ]


def test_the_module_comes_from_the_absolute_path_not_the_project_root():
    source = "struct Row {\n    func show() {}\n}\n"
    assert entries(source, "Row.swift", "/repo/iOS/UI/Sources/UI/Views") == [("UI.Row", "show")]
    assert entries(source, "/repo/iOS/UI/Sources/UI/Row.swift", "/elsewhere") == [
        ("UI.Row", "show")
    ]


def test_without_sources_the_type_chain_or_the_file_stem_is_the_namespace():
    source = "func start() {}\n\nstruct HomeView {\n    func show() {}\n}\n"
    assert entries(source, "App/Views/HomeScreen.swift") == [
        ("HomeScreen", "start"),
        ("HomeView", "show"),
    ]


def test_entries_carry_their_lines_and_language():
    source = "struct Board {\n    func run() -> Int {\n        return 1\n    }\n}\n"
    (found,) = functions_in_source(source, "Board.swift", "/proj")
    assert (found.start_line, found.end_line, found.language) == (2, 4, "swift")


def test_a_function_without_decisions_is_one():
    assert complexity_of("func choose() -> Int { 1 }\n") == 1


def test_each_decision_kind_adds_one():
    body = """
func choose(a: Int?, items: [Int]) throws -> Int {
    if a == nil { return 0 }
    guard let first = items.first else { return 1 }
    for item in items {}
    while false {}
    repeat {} while false
    do { try check() } catch {}
    let b = first > 1 && first < 5
    let c = first > 9 || first < 0
    let d = a ?? 0
    let e = d > 1 ? 1 : 2
    let f = a?.description
    let g = items.last?[0]
    return d
}
"""
    assert complexity_of(body) == 13


def test_each_comma_between_conditions_adds_one():
    body = """
func choose(a: Int?, b: Int?, c: Bool) -> Int {
    guard let a, let b, c else { return 0 }
    return a + b
}
"""
    assert complexity_of(body) == 1 + 3
    loop = """
func choose(a: Int, b: Int) {
    if a > 1, b > 1 {}
    while a > 1, b > 1 {}
}
"""
    assert complexity_of(loop) == 5


def test_switch_cases_count_once_each_and_default_adds_nothing():
    body = """
func choose(x: Shape) -> Int {
    switch x {
    case .circle, .square: return 1
    case .line: return 2
    default: return 0
    }
}
"""
    assert complexity_of(body) == 3


def test_a_where_clause_on_a_for_a_case_or_a_catch_adds_one():
    body = """
func choose(items: [Int]) {
    for item in items where item > 0 {}
    switch items.count {
    case let n where n > 3: break
    default: break
    }
    do { try check() } catch let error as Failure where error.fatal {}
}
"""
    assert complexity_of(body) == 7


def test_if_case_counts_as_its_if():
    assert complexity_of("func choose(a: Int?) {\n    if case .some(let b) = a { print(b) }\n}\n") == 2


def test_try_question_failable_init_parameter_commas_and_optional_types_add_nothing():
    source = """
struct Board {
    init?(size: Int?, label: String, items: [Int: String]) {
        let value = try? load(size, label)
        let cast = value as? Int
        print(cast, items)
    }
}
"""
    (found,) = functions_in_source(source, "Board.swift", "/proj")
    assert found.complexity == 1


def test_closure_and_nested_function_decisions_count_in_the_outer_entry():
    body = """
func choose(items: [Int]) -> Int {
    func pick(_ x: Int) -> Int { x > 1 ? x : 0 }
    let kept = items.filter { $0 > 0 && $0 < 9 }
    return kept.isEmpty ? 0 : pick(kept[0])
}
"""
    assert complexity_of(body) == 4


def test_property_bodies_count_their_decisions():
    source = """
struct Cell {
    var label: String {
        get { size > 1 ? "big" : "small" }
        set { if newValue.isEmpty { size = 0 } }
    }
    var watched: Int = 0 {
        didSet { if oldValue != watched { refresh() } }
    }
}
"""
    found = {fn.name: fn.complexity for fn in functions_in_source(source, "Cell.swift", "/proj")}
    assert found == {"label": 3, "watched": 2}


def test_a_function_after_an_empty_tuple_argument_keeps_its_lines():
    source = """
final class Loader {
    func finish(continuation: Continuation) {
        continuation.resume(returning: (()))
        completion(.success(()))
    }

    func next() -> Int {
        if ready { return 1 }
        return 0
    }
}
"""
    found = [(fn.name, fn.start_line, fn.end_line, fn.complexity) for fn in functions_in_source(source, "Loader.swift", "/proj")]
    assert found == [("finish", 3, 6, 1), ("next", 8, 11, 2)]


def test_an_initializer_with_a_multi_line_where_clause_keeps_its_body():
    source = """
struct Paging<Data, Content> {
    init(data: Data, content: Content) where Data: RandomAccessCollection,
        Content: View {
        if data.isEmpty { print("empty") }
        self.data = data
    }

    func after() {}
}
"""
    found = [(fn.name, fn.start_line, fn.end_line, fn.complexity) for fn in functions_in_source(source, "Paging.swift", "/proj")]
    assert found == [("init", 3, 7, 2), ("after", 9, 9, 1)]


@pytest.mark.parametrize(
    "parameters",
    [
        'x: String = ")", y: String = "\\")", z: String = \"\"\"\n    )\n    \"\"\"',
        'p: String = #"C:\\"#',
        'p: String = #")"#',
        'a: Int, // the "x\n        p: String',
        'a: Int /* ")" */, p: String',
    ],
)
def test_a_parenthesis_in_a_string_or_comment_keeps_the_initializer_where_clause_blanked(parameters):
    source = f"""
struct S {{
    init<T: P, U>({parameters}) where T: P,
        U: Q {{
        if x.isEmpty {{}}
    }}
    func g() {{}}
}}
"""
    found = [(fn.namespace, fn.name, fn.complexity) for fn in functions_in_source(source, "Sources/M/S.swift", "/proj")]
    assert found == [("M.S", "init", 2), ("M.S", "g", 1)]


def test_a_where_clause_outside_an_initializer_is_left_as_written():
    source = """
extension Array where Element == Int {
    func total<T>(_ other: T) -> Int where T: Sequence, T.Element == Int {
        for item in other where item > 0 {}
        return 0
    }
}
"""
    (found,) = functions_in_source(source, "Total.swift", "/proj")
    assert (found.namespace, found.name, found.complexity) == ("Array", "total", 3)


def test_a_where_clause_after_an_initializer_call_is_left_as_written():
    source = """
extension Board {
    convenience init(items: [Int]) {
        self.init(size: items.count)
        for item in items where item > 0 {
            print(item)
        }
    }
}
"""
    (found,) = functions_in_source(source, "Board.swift", "/proj")
    assert (found.name, found.complexity) == ("init", 3)


def test_an_extension_of_a_sugared_type_takes_the_standard_library_name():
    source = """
extension [Int] {
    func total() -> Int { 0 }
}

extension [String: Int] {
    func keys() -> Int { 0 }
}

extension Int? {
    func orZero() -> Int { 0 }
}
"""
    assert entries(source, "Feature/Sources/Feature/Sugar.swift") == [
        ("Feature.Array", "total"),
        ("Feature.Dictionary", "keys"),
        ("Feature.Optional", "orZero"),
    ]
