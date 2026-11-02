from crapper.languages.dlang import functions_in_source


def _by_name(source: str, path: str = "source/demo/board.d"):
    return {function.name: function for function in functions_in_source(source, path, "/proj")}


def test_d_functions_methods_namespaces_and_complexity():
    source = """\
module demo.board;

int choose(int value, bool ready, int[] values) {
  foreach (item; values) value += item;
  if (ready && value > 0) value++;
  while (value < 10) value++;
  switch (value) {
    case 1: return 1;
    case 2: return 2;
    default: break;
  }
  try { risky(); } catch (Exception error) { return 0; }
  return ready ? value : 0;
}

struct Board {
  int place(int value) { return value > 0 ? value : 0; }
  this(int value) { this.value = value; }
  int value;
}
"""
    found = _by_name(source)
    assert [(name, item.namespace, item.complexity) for name, item in found.items()] == [
        ("choose", "demo.board", 10),
        ("place", "demo.board.Board", 2),
    ]
    assert found["choose"].start_byte < found["choose"].end_byte


def test_d_skips_unittest_versions_and_keeps_nested_functions_in_the_owner():
    source = """\
module demo.board;

version (unittest) {
  int helper(int value) { return value + 1; }
}

version (Windows) {
  int platformHelper(int value) { return value + 1; }
}

int declared(int value);

int outer(int value) {
  int local(int item) { return item > 0 ? item : 0; }
  return local(value);
}
"""
    found = _by_name(source)
    assert list(found) == ["platformHelper", "outer"]
    assert found["outer"].complexity == 2


def test_d_uses_the_source_path_when_the_module_declaration_is_absent():
    found = functions_in_source("int open() { return 1; }\n", "source/demo/lease.d", "/proj")
    assert [(item.namespace, item.name) for item in found] == [("demo.lease", "open")]


def test_d_fallback_handles_absolute_src_paths_and_package_modules():
    absolute = functions_in_source(
        "int open() { return 1; }\n",
        "/proj/src/demo/lease.d",
        "/proj",
    )
    package = functions_in_source(
        "int open() { return 1; }\n",
        "source/demo/package.d",
        "/proj",
    )
    root_package = functions_in_source(
        "int open() { return 1; }\n",
        "source/package.d",
        "/proj",
    )
    detached = functions_in_source(
        "int open() { return 1; }\n",
        "/workspace/src/demo/lease.d",
    )
    assert [item.namespace for item in absolute + package + root_package + detached] == [
        "demo.lease",
        "demo",
        "app",
        "demo.lease",
    ]
