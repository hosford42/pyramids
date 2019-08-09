from pyramids import categorization
from pyramids.rules.subtree_match import SubtreeMatchRule


# head()
class HeadMatchRule(SubtreeMatchRule):

    def __str__(self):
        return str(categorization.Category('head', self._positive_properties, self._negative_properties))

    def __call__(self, category_list, head_index):
        return ((self._positive_properties <= category_list[head_index].positive_properties) and
                not (self._negative_properties & category_list[head_index].positive_properties))