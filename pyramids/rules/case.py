from pyramids.categorization import Property, Category
from pyramids.rules.leaf import LeafRule
from pyramids.properties import CASE_FREE, MIXED_CASE, TITLE_CASE, UPPER_CASE, LOWER_CASE


class CaseRule(LeafRule):

    def __init__(self, category: Category, case: Property):
        case = Property.get(case)
        assert case in (CASE_FREE, LOWER_CASE, UPPER_CASE, TITLE_CASE, MIXED_CASE)
        super().__init__(category)
        self._case = case
        self._hash = hash(self._category) ^ hash(self._case)

    @property
    def case(self) -> Property:
        return self._case

    def __hash__(self) -> int:
        return self._hash

    def __eq__(self, other: 'CaseRule') -> bool:
        if not isinstance(other, CaseRule):
            return NotImplemented
        return self is other or (self._hash == other._hash and self._category == other._category and
                                 self._case == other._case)

    def __ne__(self, other: 'CaseRule') -> bool:
        if not isinstance(other, CaseRule):
            return NotImplemented
        return not (self == other)

    def __contains__(self, token: str) -> bool:
        positive, negative = self.discover_case_properties(token)
        return self._case in positive

    def __repr__(self) -> str:
        return type(self).__name__ + repr((self.category, str(self.case)))

    def __str__(self) -> str:
        return self.case + '->' + str(self.category)
