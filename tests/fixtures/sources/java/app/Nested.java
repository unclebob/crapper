class Nested {
    int nested(boolean a, boolean b, int[] values) {
        for (int i = 0; i < values.length; i++) {
            if (a) {
            }
        }
        for (int value : values) {
            if (b) {
            }
        }
        while (a) {
            if (b) {
            }
            a = false;
        }
        do {
            if (a) {
            }
            b = false;
        } while (b);
        try {
            return a ? (b ? 1 : 0) : 2;
        } catch (RuntimeException ex) {
            if (values.length > 0) {
                return values[0];
            }
            return 3;
        }
    }

    int switched(int value) {
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
}
