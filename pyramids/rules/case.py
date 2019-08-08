from pyramids.categorization import Property
from pyramids.rules.leaf import LeafRule
from pyramids.properties import CASE_FREE, MIXED_CASE, TITLE_CASE, UPPER_CASE, LOWER_CASE


class CaseRule(LeafRule):

    def __init__(self, category, case):
        case = Property.get(case)
        assert case in (CASE_FREE, LOWER_CASE, UPPER_CASE, TITLE_CASE, MIXED_CASE)
        super().__init__(category)
        self._case = case
        self._hash = hash(self._category) ^ hash(self._case)

    @property
    def case(self):
        return self._case

    def __hash__(self):
        return self._hash

    def __eq__(self, other):
        if not isinstance(other, CaseRule):
            return NotImplemented
        return self is other or (self._hash == other._hash and self._category == other._category and
                                 self._case == other._case)

    def __ne__(self, other):
        if not isinstance(other, CaseRule):
            return NotImplemented
        return not (self == other)

    def __contains__(self, token):
        positive, negative = self.discover_case_properties(token)
        return self._case in positive

    def __repr__(self):
        return type(self).__name__ + repr((self.category, str(self.case)))

    def __str__(self):
        return self.case + '->' + str(self.category)
