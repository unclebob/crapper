class Lambda {
    Runnable r = () -> {
        class Local {
            int score() { if (true) return 1; return 0; }
        }
        return null;
    };
    int outer() { return 1; }
}
