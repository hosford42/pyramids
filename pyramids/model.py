# -*- coding: utf-8 -*-

"""
A parser model, consisting of a set of grammar rules.
"""
import pyramids.rules.sequence
from pyramids import rules
from pyramids.config import ModelConfig
from pyramids.categorization import make_property_set

__author__ = 'Aaron Hosford'
__version__ = '1.0.0'
__all__ = [
    '__author__',
    '__version__',
    'Model',
]


class Model:
    """A parser model, consisting of a set of grammar rules."""

    def __init__(self, primary_leaf_rules, secondary_leaf_rules, branch_rules, tokenizer, any_promoted_properties,
                 all_promoted_properties, property_inheritance_rules, config_info=None):
        self._primary_leaf_rules = frozenset(primary_leaf_rules)
        self._secondary_leaf_rules = frozenset(secondary_leaf_rules)
        self._branch_rules = frozenset(branch_rules)
        self._tokenizer = tokenizer
        self._any_promoted_properties = make_property_set(any_promoted_properties)
        self._all_promoted_properties = make_property_set(all_promoted_properties)
        self._property_inheritance_rules = frozenset(property_inheritance_rules)
        self._config_info = config_info
        self._sequence_rules_by_link_type = {}

        for rule in self._branch_rules:
            if not isinstance(rule, pyramids.rules.sequence.SequenceRule):
                continue
            for index in range(len(rule.link_type_sets)):
                for link_type, left, right in rule.link_type_sets[index]:
                    if link_type not in self._sequence_rules_by_link_type:
                        self._sequence_rules_by_link_type[link_type] = set()
                    self._sequence_rules_by_link_type[link_type].add((rule, index))

    @property
    def any_promoted_properties(self):
        """Properties that may be promoted if any element possesses them."""
        return self._any_promoted_properties

    @property
    def all_promoted_properties(self):
        """Properties that may be promoted if all elements possess them."""
        return self._all_promoted_properties

    @property
    def tokenizer(self):
        """The tokenizer used by this model."""
        return self._tokenizer

    @property
    def sequence_rules_by_link_type(self):
        """The sequence rules of the model, organized by link type for rapid lookup."""
        return self._sequence_rules_by_link_type

    @property
    def config_info(self) -> ModelConfig:
        """The configuration information for this model, if any."""
        return self._config_info

    @property
    def primary_leaf_rules(self):
        """High-confidence rules that can generate leaf nodes in the parse tree."""
        return self._primary_leaf_rules

    @property
    def secondary_leaf_rules(self):
        """Lower-confidence rules that can generate leaf nodes in the parse tree."""
        return self._secondary_leaf_rules

    @property
    def branch_rules(self):
        """Rules that can generate branch nodes in a parse tree."""
        return self._branch_rules

    @property
    def property_inheritance_rules(self):
        """Rules for how properties are propagated upwards through the parse tree."""
        return self._property_inheritance_rules
