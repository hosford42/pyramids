from pyramids import categorization
from pyramids.rules.subtree_match import SubtreeMatchRule


# compound()
class CompoundMatchRule(SubtreeMatchRule):

    def __str__(self):
        return str(categorization.Category('compound', self._positive_properties, self._negative_properties))

    def __call__(self, category_list, head_index):
        # Stop before the term that immediately precedes the head
        for index in range(head_index - 1):
            if ((not self._positive_properties <= category_list[index].positive_properties) or
                    (self._negative_properties & category_list[index].positive_properties)):
                return False
        return True
