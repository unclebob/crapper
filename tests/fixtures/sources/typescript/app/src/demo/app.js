export function choose(a, b, c) {
  return a ?? b?.c ?? c?.() ?? c?.[0];
}
app.get("/users", (req, res) => req.id ?? 0);
