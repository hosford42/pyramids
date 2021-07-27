from typing import Iterable, FrozenSet

from pyramids.categorization import Category
from pyramids.rules.leaf import LeafRule


class SuffixRule(LeafRule):

    def __init__(self, category: Category, suffixes: Iterable[str], positive: bool = True):
        super().__init__(category)
        self._suffixes = frozenset([suffix.lower() for suffix in suffixes])
        self._positive = bool(positive)
        self._hash = hash(self._category) ^ hash(self._suffixes) ^ hash(self._positive)

    def __hash__(self) -> int:
        return self._hash

    def __eq__(self, other: 'SuffixRule') -> bool:
        if not isinstance(other, SuffixRule):
            return NotImplemented
        return self is other or (self._hash == other._hash and self._positive == other._positive and
                                 self._category == other._category and
                                 self._suffixes == other._suffixes)

    def __ne__(self, other: 'SuffixRule') -> bool:
        if not isinstance(other, SuffixRule):
            return NotImplemented
        return not (self == other)

    def __contains__(self, token: str) -> bool:
        token = token.lower()
        for suffix in self._suffixes:
            if len(token) > len(suffix) + 1 and token.endswith(suffix):
                return self._positive
        return not self._positive

    def __repr__(self) -> str:
        return (type(self).__name__ + "(" + repr(self.category) + ", " +
                repr(sorted(self.suffixes)) + ", " + repr(self.positive) + ")")

    def __str__(self) -> str:
        return (str(self.category) + ': ' + '-+'[self.positive] + ' ' +
                ' '.join(sorted(self.suffixes)))

    @property
    def suffixes(self) -> FrozenSet[str]:
        return self._suffixes

    @property
    def positive(self) -> bool:
        return self._positive
