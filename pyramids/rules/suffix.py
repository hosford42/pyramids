from pyramids.rules.leaf import LeafRule


class SuffixRule(LeafRule):

    def __init__(self, category, suffixes, positive=True):
        super().__init__(category)
        self._suffixes = frozenset([suffix.lower() for suffix in suffixes])
        self._positive = bool(positive)
        self._hash = hash(self._category) ^ hash(self._suffixes) ^ hash(self._positive)

    def __hash__(self):
        return self._hash

    def __eq__(self, other):
        if not isinstance(other, SuffixRule):
            return NotImplemented
        return self is other or (self._hash == other._hash and self._positive == other._positive and
                                 self._category == other._category and
                                 self._suffixes == other._suffixes)

    def __ne__(self, other):
        if not isinstance(other, SuffixRule):
            return NotImplemented
        return not (self == other)

    def __contains__(self, token):
        token = token.lower()
        for suffix in self._suffixes:
            if len(token) > len(suffix) + 1 and token.endswith(suffix):
                return self._positive
        return not self._positive

    def __repr__(self):
        return (type(self).__name__ + "(" + repr(self.category) + ", " +
                repr(sorted(self.suffixes)) + ", " + repr(self.positive) + ")")

    def __str__(self):
        return (str(self.category) + ': ' + '-+'[self.positive] + ' ' +
                ' '.join(sorted(self.suffixes)))

    @property
    def suffixes(self):
        return self._suffixes

    @property
    def positive(self):
        return self._positive
