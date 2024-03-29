from typing import Iterable, FrozenSet, Sequence

from pyramids.categorization import make_property_set, Property, Category


class SubtreeMatchRule:

    def __init__(self, positive_properties: Iterable[Property],
                 negative_properties: Iterable[Property]):
        self._positive_properties = make_property_set(positive_properties)
        self._negative_properties = make_property_set(negative_properties)

    @property
    def positive_properties(self) -> FrozenSet[Property]:
        return self._positive_properties

    @property
    def negative_properties(self) -> FrozenSet[Property]:
        return self._negative_properties

    def __str__(self) -> str:
        raise NotImplementedError()

    def __repr__(self) -> str:
        return (type(self).__name__ + "(" + repr(self._positive_properties) + ", " +
                repr(self._negative_properties) + ")")

    # def __eq__(self, other):
    #     raise NotImplementedError()
    #
    # def __ne__(self, other):
    #     raise NotImplementedError()
    #
    # def __le__(self, other):
    #     raise NotImplementedError()
    #
    # def __ge__(self, other):
    #     raise NotImplementedError()
    #
    # def __lt__(self, other):
    #     raise NotImplementedError()
    #
    # def __gt__(self, other):
    #     raise NotImplementedError()

    def __call__(self, category_list: Sequence[Category], head_index: int) -> bool:
        raise NotImplementedError()
