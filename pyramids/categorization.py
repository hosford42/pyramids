# -*- coding: utf-8 -*-

# TODO: Compile the extension the correct way.
# TODO: Get rid of the weird imports via renaming and then assignment.
# TODO: Have pure Python code as a fallback.
import pyximport
pyximport.install()

# noinspection PyUnresolvedReferences
from _categorization import Property as PropertyClass, Category as CategoryClass, \
    CATEGORY_WILDCARD as _CATEGORY_WILDCARD, make_property_set as _make_property_set, \
    get_all_category_names as _get_all_category_names, get_all_properties as _get_all_properties

__author__ = 'Aaron Hosford'
__all__ = [
    'Property',
    'Category',
    'CATEGORY_WILDCARD',
    'make_property_set',
    'get_all_category_names',
    'get_all_properties',
]


Property = PropertyClass
Category = CategoryClass
CATEGORY_WILDCARD = _CATEGORY_WILDCARD
make_property_set = _make_property_set
get_all_category_names = _get_all_category_names
get_all_properties = _get_all_properties
