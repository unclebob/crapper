from crapper.cli import run
from crapper.languages.vue import extract_script_blocks, functions_in_source


def test_extract_script_blocks_handles_edge_tags_and_grammars():
    source = """<template><div>{{ count }}</div><script>function inTemplate() {}</script></template>
<!-- <script>function commentedOut() {}</script> -->
<script src="./external.ts"></script>
<script SRC="./UPPER.ts"></script>
<script lang="coffee">square = (x) -> x * x</script>
<script>   \n\t  </script>
<script lang="TS">
export const a = 1
</script>
<script setup lang="tsx" generic="T extends string">
const view = () => <div />
</script>
<script lang="mjs">
export function helper() { return 1 }
</script>
"""
    _data, blocks = extract_script_blocks(source)
    assert [(b.grammar, b.is_setup) for b in blocks] == [
        ("typescript", False),
        ("tsx", True),
        ("javascript", False),
    ]
    assert functions_in_source("<template><div>hi</div></template>", "src/Empty.vue", "/proj") == []


def test_script_setup_declarations_wrappers_complexity_and_tsx():
    source = """<script setup lang="ts" generic="T extends string">
export function choose(x: number): number {
  if (x > 0 && x < 10) return 1;
  for (let i = 0; i < x; i++) {
    if (i === 2) return i;
  }
  try {
    return x;
  } catch (e) {
    return 0;
  }
  return x > 0 ? 1 : 0;
}

export const wrapped = ((a?: number, b?: number) => a ?? b?.value) as ((a?: number, b?: number) => unknown);
const satisfied = ((ok: boolean) => (ok ? 1 : 0)) satisfies ((ok: boolean) => number);
const asserted = <any>((n: number) => (n ? 1 : 0));

class Helper {
  run(flag?: boolean): number {
    return flag ? 1 : 0;
  }
}

function withRoutes(pinia: any, router: any) {
  pinia.use((store: any) => {
    if (store.ready) return 1;
    return 0;
  });
  router.get("/users", (req: any) => (req.ok ? 1 : 0));
}
</script>
<script setup lang="tsx">
const jsxBranch = (ok: boolean, ready: boolean) => ok && ready && <span />;
</script>
"""
    functions = functions_in_source(source, "src/components/UserCard.vue", "/proj")
    assert [(fn.namespace, fn.name, fn.complexity, fn.language) for fn in functions] == [
        ("components.UserCard", "choose", 7, "vue"),
        ("components.UserCard", "wrapped", 3, "vue"),
        ("components.UserCard", "satisfied", 2, "vue"),
        ("components.UserCard", "asserted", 2, "vue"),
        ("components.UserCard.Helper", "run", 2, "vue"),
        ("components.UserCard", "withRoutes", 3, "vue"),
        ("components.UserCard", "jsxBranch", 3, "vue"),
    ]


def test_composition_api_computed_watch_and_lifecycle_hooks():
    source = """<script setup lang="ts">
const doubled = computed<number>(() => (count.value > 0 ? count.value * 2 : 0));
computed(() => 1);
const rw = computed({
  get: () => (a.value ? 1 : 0),
  set(v: number) {
    if (v > 0) raw.value = v;
  },
});

watch(() => props.id, (id) => {
  if (id) load(id);
});
watch([() => props.a, count], ([a, c]) => {
  if (a && c) sync();
});
watch(() => props.a + props.b, (v) => v);
watch(() => {
  return props.x;
}, (v) => v);
watch(veryLongReactiveSourceNameExceedingThirtyTwoCharacters, (v) => v);
watch([
  a,
  b,
], ([x, y]) => x);
watch(count, existingHandler);

watchEffect(() => {
  if (ready.value) run();
});
watchPostEffect(() => {});
watchSyncEffect(() => {});
onBeforeMount(() => {});
onMounted(() => {
  if (ok) init();
});
Vue.onMounted(() => {});
onBeforeUpdate(() => {});
onUpdated(() => {});
onBeforeUnmount(() => {});
onUnmounted(() => {});
onActivated(() => {});
onDeactivated(() => {});
onErrorCaptured(() => {});
onRenderTracked(() => {});
onRenderTriggered(() => {});
onServerPrefetch(async () => {});

function useCounter() {
  const local = computed(() => (n.value ? 1 : 0));
  onMounted(() => {
    if (local.value) bump();
  });
  return local;
}

fs.watch("./x", () => reload());
_.extend({}, { run: () => 1 });
other.onMounted(() => {});
</script>
"""
    functions = functions_in_source(source, "src/composables/Counter.vue", "/proj")
    assert [(fn.name, fn.complexity) for fn in functions] == [
        ("doubled", 2),
        ("computed", 1),
        ("rw.get", 2),
        ("rw.set", 2),
        ("watch(props.id)", 2),
        ("watch([props.a, count])", 3),
        ("watch", 1),
        ("watch#2", 1),
        ("watch#3", 1),
        ("watch#4", 1),
        ("watchEffect", 2),
        ("watchPostEffect", 1),
        ("watchSyncEffect", 1),
        ("onBeforeMount", 1),
        ("onMounted", 2),
        ("onMounted#2", 1),
        ("onBeforeUpdate", 1),
        ("onUpdated", 1),
        ("onBeforeUnmount", 1),
        ("onUnmounted", 1),
        ("onActivated", 1),
        ("onDeactivated", 1),
        ("onErrorCaptured", 1),
        ("onRenderTracked", 1),
        ("onRenderTriggered", 1),
        ("onServerPrefetch", 1),
        ("useCounter", 3),
    ]
    by_name = {fn.name: fn for fn in functions}
    assert by_name["rw.get"].end_line < by_name["rw.set"].start_line


def test_options_api_targets_and_member_shapes():
    source = """<script lang="ts">
export default defineComponent({
  name: "Card",
  props: {
    items: { type: Array, default: () => (fallback ? [1] : []) },
    mode: { validator: (v: string) => v === "a" || v === "b" },
  },
  emits: { submit: (p: any) => Boolean(p) },
  components: { Child: () => import("./Child.vue") },
  directives: { focus: { mounted() {} } },
  provide: () => ({ a: 1 }),
  inject: { b: { default: () => 2 } },
  setup() {
    const inner = computed(() => (x ? 1 : 0));
    return { inner };
  },
  data() {
    return { count: 0 };
  },
  mounted() {
    if (this.count > 0) this.save();
  },
  render: () => null,
  methods: {
    save() {
      if (this.count) return 1;
      return 0;
    },
    reset: (flag: boolean) => (flag ? 0 : 1),
  },
  computed: {
    doubled() {
      return this.count * 2;
    },
    tripled: () => 3,
    model: {
      get() {
        return this.count;
      },
      set(v: number) {
        if (v >= 0) this.count = v;
      },
    },
  },
  watch: {
    count(next: number) {
      if (next > 5) this.reset(true);
    },
    "user.name": {
      handler(val: string) {
        if (val) this.save();
      },
      deep: true,
    },
    items: [
      () => {},
      {
        handler(val: any[]) {
          if (val.length) this.save();
        },
      },
      "save",
    ],
  },
}) as any;
</script>
"""
    functions = functions_in_source(source, "src/Card.vue", "/proj")
    assert [(fn.name, fn.complexity) for fn in functions] == [
        ("setup", 2),
        ("data", 1),
        ("mounted", 2),
        ("render", 1),
        ("save", 2),
        ("reset", 2),
        ("doubled", 1),
        ("tripled", 1),
        ("model.get", 1),
        ("model.set", 2),
        ("watch(count)", 2),
        ("watch(user.name)", 2),
        ("watch(items)", 1),
        ("watch(items)#2", 2),
    ]


def test_options_api_variants_avoid_double_extraction():
    plain_export = """<script>
export default {
  data() { return { n: 1 } },
  methods: { ping() { return 1 } },
}
</script>
"""
    assert [fn.name for fn in functions_in_source(plain_export, "Plain.vue")] == ["data", "ping"]

    vue_extend = """<script>
export default (Vue.extend({
  created() { if (ok) init() },
}))
</script>
"""
    assert [(fn.name, fn.complexity) for fn in functions_in_source(vue_extend, "Ext.vue")] == [
        ("created", 2)
    ]

    const_comp = """<script lang="ts">
const Comp = defineComponent({ mounted() {} });
export const ExportedComp = Vue.extend({ updated() {} });
Vue.defineComponent({ unmounted() {} });
</script>
"""
    assert [fn.name for fn in functions_in_source(const_comp, "Const.vue")] == [
        "mounted",
        "updated",
        "unmounted",
    ]

    functional = """<script lang="ts">
export default defineComponent((props) => {
  return () => (props.ok ? 1 : 0);
});
</script>
"""
    assert [(fn.name, fn.complexity) for fn in functions_in_source(functional, "Func.vue")] == [
        ("setup", 2)
    ]

    anon_default = """<script>
export default function() { return 1 }
</script>
"""
    assert [fn.name for fn in functions_in_source(anon_default, "Anon.vue")] == ["default"]

    arrow_default = """<script>
export default () => (ok ? 1 : 0)
</script>
"""
    assert [(fn.name, fn.complexity) for fn in functions_in_source(arrow_default, "Arrow.vue")] == [
        ("default", 2)
    ]

    named_default = """<script>
export default function namedDefault() { return 1 }
</script>
"""
    assert [fn.name for fn in functions_in_source(named_default, "Named.vue")] == ["namedDefault"]

    class_default = """<script lang="ts">
export default class DefaultComp {
  open() { return 1 }
}
</script>
"""
    assert [(fn.namespace, fn.name) for fn in functions_in_source(class_default, "Cls.vue")] == [
        ("Cls.DefaultComp", "open")
    ]


def test_dual_script_blocks_preserve_order_and_disambiguate_collisions():
    source = """<script lang="ts">
export function helper() { return 1 }
</script>
<script setup lang="ts">
function helper() { return 2 }
onMounted(() => {});
onMounted(() => {});
</script>
"""
    functions = functions_in_source(source, "src/Dual.vue", "/proj")
    assert [(fn.name, fn.start_line) for fn in functions] == [
        ("helper", 2),
        ("helper#2", 5),
        ("onMounted", 6),
        ("onMounted#2", 7),
    ]


def test_byte_and_line_spans_with_bom_crlf_multibyte_and_inline_script():
    source = (
        "\ufeff<template><div>你好🎉</div></template>\r\n"
        "<script setup lang=\"ts\">function greet() {\r\n"
        "  return \"你好🚀\"\r\n"
        "}</script>\r\n"
    )
    raw_bytes = source.encode("utf-8")
    functions = functions_in_source(source, "src/Greet.vue", "/proj")
    assert len(functions) == 1
    fn = functions[0]
    assert (fn.start_line, fn.end_line) == (2, 4)
    assert raw_bytes[fn.start_byte : fn.end_byte].decode("utf-8") == (
        "function greet() {\r\n  return \"你好🚀\"\r\n}"
    )


def test_vue_lcov_end_to_end_with_line_and_branch_records(tmp_path):
    vue = tmp_path / "src" / "Card.vue"
    vue.parent.mkdir(parents=True)
    vue.write_text(
        "<template><div /></template>\n"
        "<script setup lang=\"ts\">\n"
        "function decide(flag: boolean) {\n"
        "  if (flag) return 1;\n"
        "  return 0;\n"
        "}\n"
        "const plain = () => 42;\n"
        "</script>\n",
        encoding="utf-8",
    )
    lcov = tmp_path / "coverage" / "lcov.info"
    lcov.parent.mkdir(parents=True)
    lcov.write_text(
        "SF:src/Card.vue\n"
        "DA:3,1\n"
        "DA:4,1\n"
        "DA:5,0\n"
        "DA:7,1\n"
        "BRDA:4,0,0,1\n"
        "BRDA:4,0,1,0\n"
        "end_of_record\n",
        encoding="utf-8",
    )
    assert run(["--root", str(tmp_path), "--use-existing-coverage"]) == 0
    edn = (tmp_path / ".metrics" / "crap.edn").read_text(encoding="utf-8")
    assert ':namespace "Card"' in edn
    assert ':name "decide"' in edn
    assert ':coverage 50.0' in edn
    assert ':name "plain"' in edn
    assert ':coverage 100.0' in edn


def test_vue_edge_callees_options_and_composition_guards():
    source = """<script src="./external.ts">const ignored = 1;</script>
<script lang="ts">
const dynKey = "dynamic";
export default defineComponent({
  [dynKey]: () => 1,
  methods: "invalid",
  computed: {
    raw: 123,
  },
  watch: {
    tag: "onTagChange",
    bad: 123,
    arr: [() => 1, 99],
  },
});

defineComponent();
defineComponent(123);
export default existingComponent;

const { value } = computed(() => 1);
const wrappedComp = (computed(() => 2));
const rwExtra = computed({
  get: () => 1,
  extra: () => 2,
});
computed(existingFn);
computed();
watch();
watch(count);
watch([a, () => b + c], (v) => v);
watch((x) => x, (v) => v);
onMounted(existingFn);
onMounted();
getHook()(() => {});
app.vue.watch(x, () => {});
</script>
"""
    functions = functions_in_source(source, "src/Edges.vue", "/proj")
    assert [(fn.name, fn.complexity) for fn in functions] == [
        ("watch(arr)", 1),
        ("computed", 1),
        ("wrappedComp", 1),
        ("rwExtra.get", 1),
        ("watch", 1),
        ("watch#2", 1),
    ]
    assert functions_in_source("", "src/Empty.vue", "/proj") == []

