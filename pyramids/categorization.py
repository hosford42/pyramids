# -*- coding: utf-8 -*-

# TODO: Compile the extension the correct way.
# TODO: Get rid of the weird imports via renaming and then assignment.
# TODO: Have pure Python code as a fallback.
import pyximport
pyximport.install()

# noinspection PyUnresolvedReferences
from _categorization import Property as _Property, Category as _Category, \
    CATEGORY_WILDCARD as _CATEGORY_WILDCARD, make_property_set as _make_property_set, \
    get_all_category_names as _get_all_category_names, get_all_properties as _get_all_properties, \
    LinkLabel as _LinkLabel, get_all_link_labels as _get_all_link_labels, \
    CategoryName as _CategoryName


__author__ = 'Aaron Hosford'
__all__ = [
    'Property',
    'Category',
    'LinkLabel',
    'CATEGORY_WILDCARD',
    'make_property_set',
    'get_all_category_names',
    'get_all_properties',
    'get_all_link_labels',
]


Property = _Property
Category = _Category
LinkLabel = _LinkLabel
CATEGORY_WILDCARD = _CATEGORY_WILDCARD
make_property_set = _make_property_set
get_all_category_names = _get_all_category_names
get_all_properties = _get_all_properties
get_all_link_labels = _get_all_link_labels
