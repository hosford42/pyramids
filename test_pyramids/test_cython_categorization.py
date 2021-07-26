"""Test suite for Cython categorization code (_categorization.pyx)."""

from pyramids.categorization import Category


def test_repr_eval():
    """Ensure that alternately calling repr() and eval() on a category gets back the original
    category unchanged."""
    cat = Category("abc", ["def"], ["ghi"])
    serialized = repr(cat)
    restored = eval(serialized)  # pylint: disable=eval-used
    assert cat == restored, (cat, serialized)


if __name__ == '__main__':
    test_repr_eval()
