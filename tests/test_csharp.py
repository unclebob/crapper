from crapper.discover import iter_source_files
from crapper.languages.csharp import functions_in_source

SCORE = """
class Sample {
    int Score(bool a, bool b, int[] values) {
        for (int i = 0; i < values.Length; i++) {
        }
        foreach (int value in values) {
        }
        while (a) {
            a = false;
        }
        do {
            b = false;
        } while (b);
        if (a && b || values.Length > 0) {
        }
        try {
            return a ? 1 : 0;
        } catch (Exception ex) {
            return 2;
        }
    }
}
"""

SWITCHES = """
class Sample {
    int Switched(int value) {
        switch (value) {
            case 1:
                if (value > 0) {
                    return 1;
                }
                return 0;
            default:
                return 2;
        }
    }

    string Arms(int n) => n switch { 0 => "zero", > 100 => "big", _ => "small" };

    int Guarded(object o) {
        switch (o) {
            case int n when n > 0: return 1;
            case string s: return 2;
            default: return 3;
        }
    }
}
"""

NULLS = """
class Sample {
    int Nulls(string? label, Box? box) {
        var text = label ?? "none";
        var n = box?.Inner?.Count;
        return (n is > 0 and < 10 or 50) ? 1 : 0;
    }

    int Filtered() {
        try {
            return 1;
        } catch (Exception ex) when (ex.Message.Length > 0) {
            return 2;
        }
    }
}
"""

MEMBERS = """
namespace Acme.Billing;

public abstract class Invoice
{
    private readonly List<int> _lines = [];
    public int Id { get; set; }
    public string Label { get; set; } = "";
    public int Count => _lines.Count;
    public int First { get { if (_lines.Count > 0) return _lines[0]; return -1; } }
    public int this[int i] { get => _lines[i]; set { if (value < 0) return; _lines[i] = value; } }
    public event EventHandler? Changed { add { } remove { } }
    public Invoice() { if (true) { } }
    ~Invoice() { }
    public static Invoice operator +(Invoice a, Invoice b) => a;
    public abstract void Render();
    public int Twice(int x) => x > 0 ? x * 2 : 0;
    public int Folded(IEnumerable<int> xs)
    {
        Func<int, bool> positive = x => x > 0 && x < 10;
        int Local(int y) { if (y > 0) return y; return -y; }
        return xs.Count(positive) + Local(1);
    }
    public interface IRender { void Draw(); int Size() => 1; }
    public record Line(int Qty) { public int Doubled() => Qty * 2; }
}
"""

NAMESPACES = """
namespace Acme.Api
{
    public class Outer
    {
        public class Inner { public void Tick() { } }
        public void Place(int x) { if (x > 0 && Ready) return; }
    }
}
class Loose { void Run() { } }
"""

TOP_LEVEL = """\
var builder = WebApplication.CreateBuilder(args);
var app = builder.Build();
if (app.Environment.IsDevelopment()) app.UseDeveloperExceptionPage();
app.MapGet("/instances", (IStore store) => store.Count > 0 ? Results.Ok() : Results.NoContent());
app.MapPost("/instances/{id}/relaunch", async (string id, IStore store) =>
{
    var inst = store.Find(id);
    if (inst is null) return Results.NotFound();
    return Results.Ok(inst);
});
app.MapGet("/instances", () => Results.Ok()).WithName("again");
app.MapMethods("/x", new[] { "HEAD" }, () => Results.Ok());
app.MapGet($"/v{1}", Handler);
app.MapDelete(@"/raw", delegate { return Results.Ok(); });
app.Run();
static IResult Handler() { if (true) return Results.Ok(); return Results.NoContent(); }
public partial class Program { static int Twice(int x) => x > 0 ? 2 * x : 0; }
"""

ROUTES_IN_A_METHOD = """
namespace Acme.Api;

public static class Endpoints
{
    public static void MapAll(this WebApplication app)
    {
        app.MapGet("/a", () => { if (true) return Results.Ok(); return Results.NoContent(); });
        if (app.Environment.IsDevelopment()) { }
    }
}
"""


def _scored(source: str, path: str = "Sample.cs"):
    return [(f.namespace, f.name, f.complexity) for f in functions_in_source(source, path)]


def test_counts_the_same_decisions_as_crap4java():
    assert _scored(SCORE) == [("Sample", "Score", 10)]


def test_each_switch_section_arm_and_guard_is_a_decision():
    assert _scored(SWITCHES) == [
        ("Sample", "Switched", 4),
        ("Sample", "Arms", 4),
        ("Sample", "Guarded", 5),
    ]


def test_null_operators_patterns_and_catch_filters_are_decisions():
    assert _scored(NULLS) == [("Sample", "Nulls", 7), ("Sample", "Filtered", 3)]


def test_members_with_a_body_are_entries_under_the_compilers_names():
    assert _scored(MEMBERS, "src/Acme/Invoice.cs") == [
        ("Acme.Billing.Invoice", "get_Count", 1),
        ("Acme.Billing.Invoice", "get_First", 2),
        ("Acme.Billing.Invoice", "get_Item", 1),
        ("Acme.Billing.Invoice", "set_Item", 2),
        ("Acme.Billing.Invoice", "add_Changed", 1),
        ("Acme.Billing.Invoice", "remove_Changed", 1),
        ("Acme.Billing.Invoice", "Twice", 2),
        ("Acme.Billing.Invoice", "Folded", 3),
        ("Acme.Billing.Invoice.IRender", "Size", 1),
        ("Acme.Billing.Invoice.Line", "Doubled", 1),
    ]


def test_block_namespaces_nested_types_and_a_type_outside_any_namespace():
    assert _scored(NAMESPACES) == [
        ("Acme.Api.Outer.Inner", "Tick", 1),
        ("Acme.Api.Outer", "Place", 3),
        ("Loose", "Run", 1),
    ]


def test_top_level_statements_are_main_and_each_endpoint_lambda_is_its_own_entry():
    found = functions_in_source(TOP_LEVEL, "Program.cs")
    assert [(f.namespace, f.name, f.complexity) for f in found] == [
        ("Program", "<Main>$", 3),
        ("Program", "GET /instances", 2),
        ("Program", "POST /instances/{id}/relaunch", 2),
        ("Program", "GET /instances#2", 1),
        ("Program", "MAP /x", 1),
        ("Program", "DELETE /raw", 1),
        ("Program", "Twice", 2),
    ]
    main = found[0]
    assert (main.start_line, main.end_line) == (1, 16)
    assert main.start_byte == 0
    assert found[1].start_line == 4


def test_top_level_statements_are_keyed_under_the_projects_root_namespace(tmp_path):
    project = tmp_path / "src" / "Host" / "Acme.Host.csproj"
    project.parent.mkdir(parents=True)
    project.write_text('<Project Sdk="Microsoft.NET.Sdk.Web" />\n', encoding="utf-8")
    source = 'var app = Build();\napp.MapGet("/a", () => 1);\npublic partial class Program { static int One() => 1; }\n'
    found = functions_in_source(source, "src/Host/Program.cs", str(tmp_path))
    assert [(f.namespace, f.name) for f in found] == [
        ("Acme.Host.Program", "<Main>$"),
        ("Acme.Host.Program", "GET /a"),
        ("Program", "One"),
    ]
    project.write_text(
        "<Project><PropertyGroup><RootNamespace>Acme.Web</RootNamespace></PropertyGroup></Project>\n",
        encoding="utf-8",
    )
    assert functions_in_source(source, "src/Host/Program.cs", str(tmp_path))[0].namespace == "Acme.Web.Program"
    # no project above the file inside the root: the bare name
    assert functions_in_source("var x = 1;\n", "Loose.cs", str(tmp_path))[0].namespace == "Program"


def test_an_endpoint_registered_inside_a_method_is_not_charged_to_that_method():
    assert _scored(ROUTES_IN_A_METHOD, "Endpoints.cs") == [
        ("Acme.Api.Endpoints", "MapAll", 2),
        ("Acme.Api.Endpoints", "GET /a", 2),
    ]


def test_keywords_in_comments_and_strings_are_not_decisions():
    source = """
    class Sample {
        int Stable() {
            string text = "if && || ? case default catch ?? ?.";
            // if && || ? case default catch
            /* if && || ? case default catch */
            return 1;
        }
    }
    """
    assert _scored(source) == [("Sample", "Stable", 1)]


def test_generated_sources_under_obj_and_test_code_are_not_walked(tmp_path):
    for relative, text in {
        "src/Host/Program.cs": "class P { void Run() { } }\n",
        "src/Host/obj/Debug/Host.AssemblyInfo.cs": "class A { }\n",
        "src/Host/ProgramTests.cs": "class T { }\n",
        "src/Host.Tests/Fixture.cs": "class F { }\n",
        "tests/Host.Tests/HostTests.cs": "class H { }\n",
    }.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    found = [path.relative_to(tmp_path).as_posix() for path in iter_source_files([tmp_path])]
    assert found == ["src/Host/Program.cs"]
