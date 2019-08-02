import pyximport
pyximport.install()

# noinspection PyUnresolvedReferences
from _categorization import Property as PropertyClass, Category as CategoryClass, \
    CATEGORY_WILDCARD as _CATEGORY_WILDCARD

__author__ = 'Aaron Hosford'
__all__ = [
    'Property',
    'Category',
    'CATEGORY_WILDCARD'
]


Property = PropertyClass
Category = CategoryClass
CATEGORY_WILDCARD = _CATEGORY_WILDCARD
