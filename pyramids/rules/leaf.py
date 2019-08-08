from pyramids import trees, scoring
from pyramids.rules.parse_rule import ParseRule
from pyramids.properties import CASE_FREE, MIXED_CASE, TITLE_CASE, UPPER_CASE, LOWER_CASE
from pyramids.utils import extend_properties


class LeafRule(ParseRule):
    """Used by Parser to identify base-level (atomic) tokens, which are the
    leaves in a parse tree."""

    def __init__(self, category):
        super().__init__()
        self._category = category

    @property
    def category(self):
        return self._category

    def __contains__(self, token):
        raise NotImplementedError()

    def __call__(self, parser_state, new_token, index):
        if new_token in self:
            positive, negative = self.discover_case_properties(new_token)
            category = self._category.promote_properties(positive, negative)
            category = extend_properties(parser_state.model, category)
            node = trees.ParseTreeUtils().make_parse_tree_node(parser_state.tokens, self, index, category)
            parser_state.add_node(node)
            return True
        else:
            return False

    @classmethod
    def discover_case_properties(cls, token: str):
        token_uppered = token.upper()
        token_lowered = token.lower()
        positive = set()
        if token_uppered == token_lowered:
            positive.add(CASE_FREE)
        elif token == token_lowered:
            positive.add(LOWER_CASE)
        else:
            if token == token_uppered:
                positive.add(UPPER_CASE)
            if token == token.title():
                positive.add(TITLE_CASE)
                positive.add(MIXED_CASE)
        if not positive:
            positive.add(MIXED_CASE)
        negative = {CASE_FREE, LOWER_CASE, UPPER_CASE, TITLE_CASE, MIXED_CASE} - positive
        return positive, negative

    def iter_scoring_features(self, parse_node):
        # CAREFUL!!! Scoring features must be perfectly recoverable via eval(repr(feature))

        head_cat = str(parse_node.payload.category.name)
        head_token = trees.ParseTreeUtils().get_head_token(parse_node)
        yield scoring.ScoringFeature(('head spelling', (head_cat, head_token)))
        for prop in parse_node.payload.category.positive_properties:
            yield scoring.ScoringFeature(('head properties', (head_cat, str(prop))))
