# -*- coding: utf-8 -*-

"""Parse tree scoring-related functionality."""

__author__ = 'Aaron Hosford'
__all__ = [
    'ScoringFeature',
]

from typing import Union, Tuple


ScoringKey = Union[None, str, Tuple['ScoringKey', ...]]


class ScoringFeature:
    """
    Uniquely identifiable local contextual features for scoring parse trees.

    A generalized categorization of a parse tree node within its parse
    tree which acts as a key for storing/retrieving scores and their
    accuracies.
    """

    @classmethod
    def validate_key(cls, key: ScoringKey):
        if key is None:
            return
        if isinstance(key, str):
            return
        if not isinstance(key, tuple):
            raise TypeError(key)
        for item in key:
            cls.validate_key(item)

    def __init__(self, key: ScoringKey):
        self.validate_key(key)
        self._key = key
        self._hash = hash(key)

    def __hash__(self) -> int:
        return self._hash

    def __eq__(self, other: 'ScoringFeature') -> bool:
        if not isinstance(other, ScoringFeature):
            return NotImplemented
        return self._hash == other._hash and self._key == other._key

    def __ne__(self, other: 'ScoringFeature') -> bool:
        if not isinstance(other, ScoringFeature):
            return NotImplemented
        return self._hash != other._hash or self._key != other._key

    def __str__(self) -> str:
        return str(self._key)

    def __repr__(self) -> str:
        return type(self).__name__ + "(" + repr(self._key) + ")"

    @property
    def key(self) -> ScoringKey:
        """Get the unique key that distinguishes this scoring feature from others appearing in the
        same context."""
        return self._key
