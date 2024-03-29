from typing import Iterable, Optional, Tuple, FrozenSet

from pyramids.categorization import make_property_set, Category, Property


class PropertyInheritanceRule:

    def __init__(self, category: Category, positive_additions: Iterable[Property],
                 negative_additions: Iterable[Property]):
        self._category = category
        self._positive_additions = make_property_set(positive_additions)
        self._negative_additions = make_property_set(negative_additions)

    def __call__(self, category_name: str, positive: Iterable[Property],
                 negative: Iterable[Property]) -> Optional[Tuple[FrozenSet[Property],
                                                                 FrozenSet[Property]]]:
        category = Category(category_name, positive, negative)
        if ((self.category.is_wildcard() or self.category.name is category.name) and
                self.category.positive_properties <= category.positive_properties and
                self.category.negative_properties <= category.negative_properties):
            return self.positive_additions, self.negative_additions
        else:
            return None

    def __str__(self) -> str:
        result = str(self.category) + ":"
        if self._positive_additions:
            result += ' ' + ' '.join(sorted(self._positive_additions))
        if self._negative_additions:
            result += ' -' + ' -'.join(sorted(self._negative_additions))
        return result

    def __repr__(self) -> str:
        return (type(self).__name__ + "(" + repr(self.category) + ", " +
                repr(self.positive_additions) + ", " + repr(self.negative_additions) + ")")

    @property
    def category(self) -> Category:
        return self._category

    @property
    def positive_additions(self) -> FrozenSet[Property]:
        return self._positive_additions

    @property
    def negative_additions(self) -> FrozenSet[Property]:
        return self._negative_additions
