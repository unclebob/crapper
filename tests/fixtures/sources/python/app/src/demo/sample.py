class Outer:
    class Inner:
        def tick(self, ready, ok):
            if ready and ok:
                return 1
            return 0

def factory():
    class Hidden:
        def secret(self):
            if True:
                return 1
            return 0
    return Hidden()
