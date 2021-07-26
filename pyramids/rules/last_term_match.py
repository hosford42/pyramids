from pyramids import categorization
from pyramids.rules.subtree_match import SubtreeMatchRule


# last_term()
class LastTermMatchRule(SubtreeMatchRule):

    def __str__(self):
        return str(categorization.Category('last_term', self._positive_properties,
                                           self._negative_properties))

    def __call__(self, category_list, head_index):
        return ((self._positive_properties <= category_list[-1].positive_properties) and
                not (self._negative_properties & category_list[-1].positive_properties))
