# -*- coding: utf-8 -*-
from typing import TYPE_CHECKING

from pyramids import categorization

if TYPE_CHECKING:
    from pyramids.model import Model


# TODO: Consider moving this to _categorization.pyx
def extend_properties(model: 'Model',
                      category: 'categorization.Category') -> 'categorization.Category':
    """Extend the category's properties per the inheritance rules."""
    positive = set(category.positive_properties)
    negative = set(category.negative_properties)
    more = True
    while more:
        more = False
        for rule in model.property_inheritance_rules:
            new = rule(category.name, positive, negative)
            if new:
                new_positive, new_negative = new
                new_positive -= positive
                new_negative -= negative
                if new_positive or new_negative:
                    more = True
                    positive |= new_positive
                    negative |= new_negative
    negative -= positive
    return categorization.Category(category.name, positive, negative)
