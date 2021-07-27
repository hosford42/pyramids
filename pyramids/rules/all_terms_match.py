from typing import Sequence

from pyramids import categorization
from pyramids.categorization import Category
from pyramids.rules.subtree_match import SubtreeMatchRule


# all_terms(),
class AllTermsMatchRule(SubtreeMatchRule):

    def __str__(self) -> str:
        return str(categorization.Category('all_terms', self._positive_properties,
                                           self._negative_properties))

    def __call__(self, category_list: Sequence[Category], head_index: int) -> bool:
        for index in range(len(category_list)):
            if index == head_index:
                continue
            if (not (self._positive_properties <= category_list[index].positive_properties) or
                    (self._negative_properties & category_list[index].positive_properties)):
                return False
        return True
