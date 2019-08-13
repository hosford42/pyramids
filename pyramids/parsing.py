# -*- coding: utf-8 -*-

import logging
import time
from sys import intern

from sortedcontainers import SortedSet

from pyramids import trees, tokenization
from pyramids.category_maps import CategoryMap
from pyramids.grammar import GrammarParser
from pyramids.model import Model

__author__ = 'Aaron Hosford'
__all__ = [
    'ParserState',
    'ParsingAlgorithm',
    'Parser',
]


class ParserState:
    """The state of the parser as parsing proceeds."""

    # TODO: Can we rank them by how much they improve the best parse
    #       quality for the worst token? That is, for each token that is
    #       covered, how much did the maximum parse quality for that token
    #       improve?
    @staticmethod
    def _insertion_key(node: trees.TreeNode):
        # width = node.token_end_index - node.token_start_index
        score, confidence = node.score

        # same_rule_count = 0
        # for item in self._insertion_queue:
        #     if item.rule is node.rule:
        #         same_rule_count += 1

        # no_predecessor = node.token_start_index > 0 and not self._category_map.has_range(0, node.token_start_index)
        # no_successor = (
        #   node.token_end_index < self._category_map.max_end and
        #   not self._category_map.has_range(node.token_end_index, self._category_map.max_end)
        # )

        # Always sorts smallest to largest, so make the best the smallest.
        # Using same_rule_count forces highly-recursive rules to take a
        # back seat to those that are well-behaved.
        # return -width, -score, -confidence

        # TODO: Decide what's best to use here, to maximize the odds of
        #       finding the best parse when parsing times out.
        return -score, -confidence

    def __init__(self, model):
        if not isinstance(model, Model):
            raise TypeError(model, Model)
        self._model = model
        self._tokens = []
        self._token_sequence = None
        self._category_map = CategoryMap()
        self._insertion_queue = SortedSet(key=self._insertion_key)
        self._node_set_ids = set()
        self._roots = set()

    @property
    def model(self):
        return self._model

    @property
    def tokens(self):
        if self._token_sequence is None:
            self._token_sequence = tokenization.TokenSequence(self._tokens)
        return self._token_sequence

    @property
    def category_map(self):
        return self._category_map

    @property
    def insertion_queue(self):
        return self._insertion_queue

    @property
    def any_promoted_properties(self):
        """Properties that may be promoted if any element possesses them."""
        return self._model.any_promoted_properties

    @property
    def all_promoted_properties(self):
        """Properties that may be promoted if all elements possess them."""
        return self._model.all_promoted_properties

    def has_nodes_pending(self):
        """The number of nodes still waiting to be processed."""
        return bool(self._insertion_queue)

    def add_node(self, node):
        """Add a new parse tree node to the insertion queue."""
        self._insertion_queue.add(node)

    def is_covered(self):
        """Returns a boolean indicating whether a node exists that covers
        the entire input by itself."""
        for node_set in self._roots:
            if node_set.payload.token_end_index - node_set.payload.token_start_index >= len(self._tokens):
                return True
        return False

    # TODO: Move to ParsingAlgorithm
    def add_token(self, token, start=None, end=None):
        """Add a new token to the token sequence."""
        token = intern(str(token))
        index = len(self._tokens)
        self._tokens.append((token, start, end))
        self._token_sequence = None
        covered = False
        for leaf_rule in self._model.primary_leaf_rules:
            covered |= leaf_rule(self, token, index)
        if not covered:
            for leaf_rule in self._model.secondary_leaf_rules:
                leaf_rule(self, token, index)

    # TODO: Move to ParsingAlgorithm
    def process_node(self, timeout=None, emergency=False):
        """Search for the next parse tree node in the insertion queue that
        makes an original contribution to the parse. If any is found,
        process it. Return a boolean indicating whether there are more
        nodes to process."""
        while self._insertion_queue and (timeout is None or time.time() < timeout):
            node = self._insertion_queue.pop(index=0)
            if not self._category_map.add(node):
                # Drop it and continue on to the next one. "We've already got one!"
                continue
            if not node.is_leaf():
                self._roots -= set(node.components)
            node_set = self._category_map.get_node_set(node)
            assert node_set is not None, node
            if id(node_set) not in self._node_set_ids:
                self._node_set_ids.add(id(node_set))
                # Only add to roots if the node set hasn't already been removed
                self._roots.add(node_set)
            for branch_rule in self._model.branch_rules:
                branch_rule(self, node_set, emergency)
            break
        return bool(self._insertion_queue)

    # TODO: Move to ParserAlgorithm
    def process_necessary_nodes(self, timeout=None, emergency=False):
        """Process pending nodes until they are exhausted or the entire
        input is covered by a single tree."""
        # TODO: This isn't always working. Sometimes I don't get a complete
        #       parse. I checked, and is_covered is not the problem.
        while (not self.is_covered() and self.process_node(timeout, emergency) and
               (timeout is None or time.time() < timeout)):
            pass  # The condition call does all the work.

    # TODO: Move to ParsingAlgorithm
    def process_all_nodes(self, timeout=None, emergency=False):
        """Process all pending nodes."""
        while self.process_node(timeout, emergency) and (timeout is None or time.time() < timeout):
            pass  # The condition call does all the work.

    def get_parse(self):
        """Create a tree for each node that doesn't get included as a
        component to some other one. Then it make a Parse instance with
        those trees."""
        return trees.Parse(self.tokens, [trees.ParseTree(self.tokens, node) for node in self._roots])


class ParsingAlgorithm:
    """Coordinates the search for new tokens and structures in a text using
    BaseRules and BuildRules, respectively. Stores the results in a Parse
    instance, which can be passed back in if additional input is received,
    or can be queried to determine the recognized structure(s) of the
    input."""

    @staticmethod
    def new_parser_state(model):
        """Return a new parser state, for incremental parsing."""
        return ParserState(model)

    @staticmethod
    def parse(parser_state, text, fast=False, timeout=None, emergency=False):
        """Parses a piece of text, returning the results."""
        for token, start, end in parser_state.model.tokenizer.tokenize(text):
            parser_state.add_token(token, start, end)
        if fast:
            parser_state.process_necessary_nodes(timeout, emergency)
        else:
            parser_state.process_all_nodes(timeout, emergency)
        return parser_state.get_parse()

    @staticmethod
    def extract(parse, language_graph_builder):
        """Extracts a sentence network from a parse."""
        return parse.build_language_graph(language_graph_builder)


class Parser:

    def __init__(self, model):
        self._model = model
        self._parser_state = None

    @property
    def state(self):
        return self._parser_state

    def clear_state(self):
        self._parser_state = ParsingAlgorithm.new_parser_state(self._model)

    # TODO: Fix this so it returns an empty list, rather than a list containing
    #       an empty parse, if the text could not be parsed.
    def parse(self, text, category=None, fast=False, timeout=None, fresh=True, emergency=False):
        if isinstance(category, str):
            category = GrammarParser.parse_category(category)
        else:
            category = self._model.default_restriction

        if fresh or not self._parser_state:
            self.clear_state()

        result = ParsingAlgorithm.parse(self._parser_state, text, fast, timeout, emergency)

        if timeout:
            parse_timed_out = time.time() >= timeout
        else:
            parse_timed_out = False

        if category:
            result = result.restrict(category)

        forests = [disambiguation for (disambiguation, rank) in result.get_sorted_disambiguations(None, None, timeout)]

        if forests:
            emergency_disambiguation = False
        else:
            emergency_disambiguation = True
            forests = [result.disambiguate()]

        if timeout:
            disambiguation_timed_out = time.time() > timeout
        else:
            disambiguation_timed_out = False

        return forests, emergency_disambiguation, parse_timed_out, disambiguation_timed_out
