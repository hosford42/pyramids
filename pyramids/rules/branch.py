from abc import ABCMeta, abstractmethod
from typing import FrozenSet

from pyramids import scoring, trees
from pyramids.categorization import LinkLabel
from pyramids.rules.parse_rule import ParseRule


class BranchRule(ParseRule, metaclass=ABCMeta):
    """"Used by Parser to identify higher-level (composite) structures,
    which are the branches in a parse tree."""

    @abstractmethod
    def __call__(self, parser_state, new_node, emergency=False):
        raise NotImplementedError()

    @property
    @abstractmethod
    def all_link_types(self) -> FrozenSet[LinkLabel]:
        raise NotImplementedError()

    @abstractmethod
    def get_link_types(self, parse_node, link_set_index):
        raise NotImplementedError()

    def iter_scoring_features(self, parse_node: 'trees.TreeNode'):
        # CAREFUL!!! Scoring features must be perfectly recoverable via ast.literal_eval(repr(feature))

        # Possible Head Features: category name, property names, token spelling
        # Component Features: category name, ordering, token spelling, property names

        # We have to look not at individual features, but at specific combinations thereof which might affect
        # the quality of the parse.

        head_cat = str(parse_node.payload.category.name)
        head_token = parse_node.payload.head_spelling
        yield scoring.ScoringFeature(('head spelling', (head_cat, head_token)))
        for prop in parse_node.payload.category.positive_properties:
            yield scoring.ScoringFeature(('head properties', (head_cat, str(prop))))
        for index, component in enumerate(parse_node.components):
            component_cat = str(component.payload.category.name)
            yield scoring.ScoringFeature(('body category', (head_cat, component_cat)))
            for other_component in parse_node.components[index + 1:]:
                yield scoring.ScoringFeature(('body category sequence', (head_cat, component_cat,
                                                                         str(other_component.payload.category.name))))
