from pyramids import scoring, trees
from pyramids.rules.parse_rule import ParseRule


class BranchRule(ParseRule):
    """"Used by Parser to identify higher-level (composite) structures,
    which are the branches in a parse tree."""

    def __call__(self, parser_state, new_node):
        raise NotImplementedError()

    def get_link_types(self, parse_node, link_set_index):
        raise NotImplementedError()

    def iter_scoring_features(self, parse_node: trees.ParseTreeNode):
        # CAREFUL!!! Scoring features must be perfectly recoverable via eval(repr(feature))

        # Possible Head Features: category name, property names, token spelling
        # Component Features: category name, ordering, token spelling, property names

        # We have to look not at individual features, but at specific combinations thereof which might affect
        # the quality of the parse.

        head_cat = str(parse_node.payload.category.name)
        head_token = trees.ParseTreeUtils.get_head_token(parse_node)
        yield scoring.ScoringFeature(('head spelling', (head_cat, head_token)))
        for prop in parse_node.payload.category.positive_properties:
            yield scoring.ScoringFeature(('head properties', (head_cat, str(prop))))
        for index, component in enumerate(parse_node.components):
            component_cat = str(component.payload.category.name)
            yield scoring.ScoringFeature(('body category', (head_cat, component_cat)))
            for other_component in parse_node.components[index + 1:]:
                yield scoring.ScoringFeature(('body category sequence', (head_cat, component_cat,
                                                                         str(other_component.payload.category.name))))
