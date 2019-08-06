# -*- coding: utf-8 -*-

# TODO: Compile the extension the correct way.
# TODO: Get rid of the weird imports via renaming and then assignment.
# TODO: Have pure Python code as a fallback.
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
