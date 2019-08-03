import pyximport
pyximport.install()

# noinspection PyUnresolvedReferences
from _categorization import Property as PropertyClass, Category as CategoryClass, \
    CATEGORY_WILDCARD as _CATEGORY_WILDCARD, make_property_set as _make_property_set

__author__ = 'Aaron Hosford'
__all__ = [
    'Property',
    'Category',
    'CATEGORY_WILDCARD',
    'make_property_set'
]


Property = PropertyClass
Category = CategoryClass
CATEGORY_WILDCARD = _CATEGORY_WILDCARD
make_property_set = _make_property_set
