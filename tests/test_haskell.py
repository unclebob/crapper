from crapper.languages.haskell import functions_in_source


def _by_name(source: str):
    return {function.name: function for function in functions_in_source(source, "src/Demo/Lease.hs")}


def test_groups_function_equations_and_counts_haskell_decisions():
    source = """\
module Demo.Lease where

choose True x | x > 0 && ready x = x
              | otherwise = 0
choose False x = if x < 0 || blocked x then -x else case x of
  0 -> 1
  n | n > 2 -> n
    | otherwise -> 2
"""
    choose = _by_name(source)["choose"]
    assert choose.namespace == "Demo.Lease"
    assert choose.complexity == 11
    assert (choose.start_line, choose.end_line) == (3, 8)
    assert choose.start_byte < choose.end_byte


def test_bindings_operators_and_comprehension_qualifiers_are_functions():
    source = """\
module Demo where

main = if enabled then run else pure ()
(<+>) x y = x
values = [x | x <- inputs, x > 0, odd x]
"""
    found = _by_name(source)
    assert set(found) == {"main", "<+>", "values"}
    assert found["main"].complexity == 2
    assert found["<+>"].complexity == 1
    assert found["values"].complexity == 3


def test_instance_methods_get_an_instance_namespace_and_locals_stay_nested():
    source = """\
module Demo.Lease where

instance (Monad m) => Store (Lease m) where
  reserve lease
    | active lease = 1
    | otherwise = 0

outer x = let local y
                | y > 0 = y
                | otherwise = 0
          in local x
"""
    found = functions_in_source(source, "src/Demo/Lease.hs")
    assert [(item.name, item.namespace, item.complexity) for item in found] == [
        ("reserve", "Demo.Lease.Store (Lease m)", 3),
        ("outer", "Demo.Lease", 3),
    ]


def test_path_is_the_module_fallback_when_there_is_no_header():
    found = functions_in_source("open ok = if ok then 1 else 0\n", "src/HBS2/Peer/Lease.hs")
    assert found[0].namespace == "HBS2.Peer.Lease"


def test_class_default_methods_use_the_class_namespace():
    source = """\
module Demo where
class Store a where
  reserve x = if ready x then 1 else 0
"""
    reserve = functions_in_source(source, "src/Demo.hs")[0]
    assert (reserve.name, reserve.namespace, reserve.complexity) == ("reserve", "Demo.Store", 2)


def test_infix_function_definition_uses_the_operator_name():
    found = functions_in_source("left <+> right = left\n", "Ops.hs")
    assert found[0].name == "<+>"
