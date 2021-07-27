import os
from sys import intern
from typing import Iterable, FrozenSet, Optional

from pyramids.categorization import Category
from pyramids.rules.leaf import LeafRule
from pyramids.word_sets import WordSetUtils


class SetRule(LeafRule):

    @classmethod
    def from_word_set(cls, file_path: str, verbose: bool = False) -> 'SetRule':
        """Load a word set and return it as a set rule."""
        from pyramids.grammar import GrammarSyntaxError, GrammarParser
        folder, filename = os.path.split(file_path)
        category_definition = os.path.splitext(filename)[0]
        try:
            category = GrammarParser.parse_category(category_definition)
        except GrammarSyntaxError as error:
            raise IOError("Badly named word set file: " + file_path) from error
        if verbose:
            print("Loading category", str(category), "from", file_path, "...")
        return SetRule(category, WordSetUtils.load_word_set(file_path), _word_set_path=file_path)

    def __init__(self, category: Category, tokens: Iterable[str], *, _word_set_path: str = None):
        super().__init__(category)
        self._tokens = frozenset(intern(token.lower()) for token in tokens)
        self._hash = hash(self._category) ^ hash(self._tokens)
        self._word_set_path = _word_set_path

    def __hash__(self) -> int:
        return self._hash

    def __eq__(self, other: 'SetRule') -> bool:
        if not isinstance(other, SetRule):
            return NotImplemented
        return self is other or (self._hash == other._hash and self._category == other._category and
                                 self._tokens == other._tokens)

    def __ne__(self, other: 'SetRule') -> bool:
        if not isinstance(other, SetRule):
            return NotImplemented
        return not (self == other)

    def __contains__(self, token: str) -> bool:
        return token.lower() in self._tokens

    def __repr__(self) -> str:
        if self._word_set_path is None:
            if len(self.tokens) > 10:
                return '<%s: %s>' % (type(self).__name__, str(self))
            else:
                return type(self).__name__ + repr((self.category, sorted(self.tokens)))
        else:
            return '%s.from_word_set(%r)' % (type(self).__name__, self.word_set_path,)

    def __str__(self) -> str:
        return str(self.category) + '.ctg'

    @property
    def tokens(self) -> FrozenSet[str]:
        return self._tokens

    @property
    def word_set_path(self) -> Optional[str]:
        return self._word_set_path
