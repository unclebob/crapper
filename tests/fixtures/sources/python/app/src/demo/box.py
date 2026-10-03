def choose(x, ready):
    if x > 0 and x < 10:
        return 1
    elif x == 0 or ready:
        return 0
    for i in xs:
        if i == 2:
            return i
    while ready:
        break
    try:
        return x
    except ValueError:
        return 0
    except KeyError:
        return -1
    match x:
        case 1:
            return 1
        case 2 | 3:
            return 2
        case _:
            return 0
    return x if x > 0 else 0

class Box:
    def open(self, flag=False):
        return 1 if flag else 0

    @staticmethod
    def shut(self):
        xs = [n for n in range(3) if n]
        return xs

def outer():
    def inner(n):
        if n:
            return 1
        return 0
    return inner(1)

async def load():
    if True:
        return 1
