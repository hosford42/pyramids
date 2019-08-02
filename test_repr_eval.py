from pyramids.categorization import Category, Property


def test_repr_eval():
    cat = Category.get("abc", ["def"], ["ghi"])
    serialized = repr(cat)
    restored = eval(serialized)
    assert cat == restored, (cat, serialized)


if __name__ == '__main__':
    test_repr_eval()
