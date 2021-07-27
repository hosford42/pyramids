from typing import Sequence

from pyramids import categorization
from pyramids.categorization import Category
from pyramids.rules.subtree_match import SubtreeMatchRule


# last_term()
class LastTermMatchRule(SubtreeMatchRule):

    def __str__(self) -> str:
        return str(categorization.Category('last_term', self._positive_properties,
                                           self._negative_properties))

    def __call__(self, category_list: Sequence[Category], head_index: int) -> bool:
        return ((self._positive_properties <= category_list[-1].positive_properties) and
                not (self._negative_properties & category_list[-1].positive_properties))
