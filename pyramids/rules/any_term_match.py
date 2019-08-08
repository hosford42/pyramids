from pyramids import categorization
from pyramids.rules.subtree_match import SubtreeMatchRule


# any_term()
class AnyTermMatchRule(SubtreeMatchRule):

    def __str__(self):
        return str(categorization.Category('any_term', self._positive_properties, self._negative_properties))

    def __call__(self, category_list, head_index):
        for index in range(len(category_list)):
            if index == head_index:
                continue
            if ((self._positive_properties <= category_list[index].positive_properties) and
                    not (self._negative_properties & category_list[index].positive_properties)):
                return True
        return False
