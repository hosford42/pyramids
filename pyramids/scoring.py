__author__ = 'Aaron Hosford'
__all__ = [
    'ScoringMeasure',
]


class ScoringMeasure:
    """A generalized categorization of a parse tree node within its parse
    tree which acts as a key for storing/retrieving scores and their
    accuracies. Roughly analogous to XCS (Accuracy-based Classifier System)
    rules."""

    def __init__(self, value):
        self._value = value
        self._hash = hash(value)

    def __hash__(self):
        return self._hash

    def __eq__(self, other):
        if not isinstance(other, ScoringMeasure):
            return NotImplemented
        return self._hash == other._hash and self._value == other._value

    def __ne__(self, other):
        if not isinstance(other, ScoringMeasure):
            return NotImplemented
        return self._hash != other._hash or self._value != other._value

    def __str__(self):
        return str(self._value)

    def __repr__(self):
        return type(self).__name__ + "(" + repr(self._value) + ")"

    @property
    def value(self):
        return self._value
