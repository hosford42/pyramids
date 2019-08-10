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

    @classmethod
    def validate_key(cls, key):
        if key is None:
            return
        if isinstance(key, str):
            return
        assert isinstance(key, tuple), key
        for item in key:
            cls.validate_key(item)

    def __init__(self, key):
        self.validate_key(key)
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
