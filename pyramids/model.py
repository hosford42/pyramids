# -*- coding: utf-8 -*-

"""
A parser model, consisting of a set of grammar rules.
"""
from typing import FrozenSet, Optional, Iterable, Mapping, AbstractSet, Tuple, TYPE_CHECKING

from pyramids.categorization import make_property_set, Category, Property, LinkLabel
from pyramids.config import ModelConfig
from pyramids.language import Language
from pyramids.tokenization import Tokenizer
from pyramids.rules import sequence

if TYPE_CHECKING:
    from pyramids.rules import branch, leaf, property_inheritance as prop_inh

__author__ = 'Aaron Hosford'
__version__ = '1.0.0'
__all__ = [
    '__author__',
    '__version__',
    'Model',
]


class Model:
    """A parser model, consisting of a set of grammar rules."""

    def __init__(self, default_restriction: Category, top_level_properties: Iterable[Property],
                 link_types: FrozenSet[LinkLabel], primary_leaf_rules: 'Iterable[leaf.LeafRule]',
                 secondary_leaf_rules: 'Iterable[leaf.LeafRule]',
                 branch_rules: 'Iterable[branch.BranchRule]',
                 tokenizer: Tokenizer, any_promoted_properties: Iterable[Property],
                 all_promoted_properties: Iterable[Property],
                 property_inheritance_rules: 'Iterable[prop_inh.PropertyInheritanceRule]',
                 language: Language, config_info: ModelConfig = None):
        self._default_restriction = default_restriction
        self._top_level_properties = make_property_set(top_level_properties)
        self._link_types = link_types
        self._primary_leaf_rules = frozenset(primary_leaf_rules)
        self._secondary_leaf_rules = frozenset(secondary_leaf_rules)
        self._branch_rules = frozenset(branch_rules)
        self._tokenizer = tokenizer
        self._any_promoted_properties = make_property_set(any_promoted_properties)
        self._all_promoted_properties = make_property_set(all_promoted_properties)
        self._property_inheritance_rules = frozenset(property_inheritance_rules)
        self._language = language
        self._config_info = config_info
        self._sequence_rules_by_link_type = {}

        for rule in self._branch_rules:
            if not isinstance(rule, sequence.SequenceRule):
                continue
            for index in range(len(rule.link_type_sets)):
                for link_type, left, right in rule.link_type_sets[index]:
                    if link_type not in self._sequence_rules_by_link_type:
                        self._sequence_rules_by_link_type[link_type] = set()
                    self._sequence_rules_by_link_type[link_type].add((rule, index))

    @property
    def default_restriction(self) -> Category:
        """The category that should be used as the restriction for most parsing operations."""
        return self._default_restriction

    @property
    def top_level_properties(self) -> FrozenSet[Property]:
        """Properties that are of relevance at the root of the parse tree."""
        return self._top_level_properties

    @property
    def link_types(self) -> FrozenSet[LinkLabel]:
        return self._link_types

    @property
    def any_promoted_properties(self) -> FrozenSet[Property]:
        """Properties that may be promoted if any element possesses them."""
        return self._any_promoted_properties

    @property
    def all_promoted_properties(self) -> FrozenSet[Property]:
        """Properties that may be promoted if all elements possess them."""
        return self._all_promoted_properties

    @property
    def tokenizer(self) -> Tokenizer:
        """The tokenizer used by this model."""
        return self._tokenizer

    @property
    def sequence_rules_by_link_type(self) \
            -> 'Mapping[LinkLabel, AbstractSet[Tuple[sequence.SequenceRule, int]]]':
        """The sequence rules of the model, organized by link type for rapid lookup."""
        return self._sequence_rules_by_link_type

    @property
    def language(self) -> Optional[Language]:
        """Get the language this parser model is designed for, if indicated."""
        return self._language

    @property
    def config_info(self) -> ModelConfig:
        """The configuration information for this model, if any."""
        return self._config_info

    @property
    def primary_leaf_rules(self) -> 'FrozenSet[leaf.LeafRule]':
        """High-confidence rules that can generate leaf nodes in the parse tree."""
        return self._primary_leaf_rules

    @property
    def secondary_leaf_rules(self) -> 'FrozenSet[leaf.LeafRule]':
        """Lower-confidence rules that can generate leaf nodes in the parse tree."""
        return self._secondary_leaf_rules

    @property
    def branch_rules(self) -> 'FrozenSet[branch.BranchRule]':
        """Rules that can generate branch nodes in a parse tree."""
        return self._branch_rules

    @property
    def property_inheritance_rules(self) -> 'FrozenSet[prop_inh.PropertyInheritanceRule]':
        """Rules for how properties are propagated upwards through the parse tree."""
        return self._property_inheritance_rules
