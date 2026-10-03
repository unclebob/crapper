package demo.pkg;

public class Board {
    Board() { if (true) {} }
    public void place(int x) { if (x > 0 && ready) return; }
    class Inner { void tick() { return; } }
}
