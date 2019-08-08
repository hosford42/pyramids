# -*- coding: utf-8 -*-

"""Parse tree scoring-related functionality."""

__author__ = 'Aaron Hosford'
__all__ = [
    'ScoringFeature',
]


class ScoringFeature:
    """
    Uniquely identifiable local contextual features for scoring parse trees.

    A generalized categorization of a parse tree node within its parse
    tree which acts as a key for storing/retrieving scores and their
    accuracies.
    """

    def __init__(self, key):
        self._key = key
        self._hash = hash(key)

    def __hash__(self):
        return self._hash

    def __eq__(self, other):
        if not isinstance(other, ScoringFeature):
            return NotImplemented
        return self._hash == other._hash and self._key == other._key

    def __ne__(self, other):
        if not isinstance(other, ScoringFeature):
            return NotImplemented
        return self._hash != other._hash or self._key != other._key

    def __str__(self) -> str:
        return str(self._key)

    def __repr__(self):
        return type(self).__name__ + "(" + repr(self._key) + ")"

    @property
    def key(self):
        """Get the unique key that distinguishes this scoring feature from others appearing in the same context."""
        return self._key
