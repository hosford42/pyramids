# TODO: There's too much stuff going on in this one file. Split it out into separate modules.

import logging
import time
from itertools import product
from sys import intern

from sortedcontainers import SortedSet

from pyramids import graphs, rules, trees, tokenization
from pyramids.model import Model
from pyramids.loader import ModelLoader
from pyramids.utils import extend_properties

__author__ = 'Aaron Hosford'
__all__ = [
    'CategoryMap',
    'ParserState',
    'ParsingAlgorithm',
    'GenerationAlgorithm',
    'Parser',
]

log = logging.getLogger(__name__)


class CategoryMap:
    """The category map tracked & used by a parser state. This data structure holds a mapping from text ranges
    to the grammatical categories and parse sub-trees associated with them. The data is structured to minimize
    query & update time during the parser's search."""

    def __init__(self):
        self._map = {}
        self._reverse_map = {}  # For fast backwards search
        self._max_end = 0
        self._size = 0
        self._ranges = set()

    def __iter__(self):
        for start in self._map:
            for category_name_id in self._map[start]:
                for category in self._map[start][category_name_id]:
                    for end in self._map[start][category_name_id][category]:
                        yield start, category, end

    @property
    def max_end(self):
        return self._max_end

    @property
    def size(self):
        return self._size

    def add(self, node):
        """Add the given parse tree node to the category map and return a
        boolean indicating whether it was something new or was already
        mapped."""

        cat = node.category
        name = cat.name
        start = node.start
        end = node.end

        if start not in self._map:
            node_set = trees.ParseTreeNodeSet(node)
            self._map[start] = {name: {cat: {end: node_set}}}
        elif name not in self._map[start]:
            node_set = trees.ParseTreeNodeSet(node)
            self._map[start][name] = {cat: {end: node_set}}
        elif cat not in self._map[start][name]:
            node_set = trees.ParseTreeNodeSet(node)
            self._map[start][name][cat] = {end: node_set}
        elif end not in self._map[start][name][cat]:
            node_set = trees.ParseTreeNodeSet(node)
            self._map[start][name][cat][end] = node_set
        elif node not in self._map[start][name][cat][end]:
            self._map[start][name][cat][end].add(node)
            return False  # No new node sets were added.
        else:
            return False  # It's already in the map

        if end not in self._reverse_map:
            self._reverse_map[end] = {name: {cat: {start: node_set}}}
        elif name not in self._reverse_map[end]:
            self._reverse_map[end][name] = {cat: {start: node_set}}
        elif cat not in self._reverse_map[end][name]:
            self._reverse_map[end][name][cat] = {start: node_set}
        elif start not in self._reverse_map[end][name][cat]:
            self._reverse_map[end][name][cat][start] = node_set

        if end > self._max_end:
            self._max_end = end

        self._size += 1
        self._ranges.add((start, end))

        return True  # It's something new

    def iter_forward_matches(self, start, categories):
        if start in self._map:
            for category in categories:
                by_name = self._map[start]
                if category.is_wildcard():
                    for category_name in by_name:
                        by_cat = by_name[category_name]
                        for mapped_category in by_cat:
                            if mapped_category in category:
                                for end in by_cat[mapped_category]:
                                    yield mapped_category, end
                elif category.name in by_name:
                    by_cat = by_name[category.name]
                    for mapped_category in by_cat:
                        if mapped_category in category:
                            for end in by_cat[mapped_category]:
                                yield mapped_category, end

    def iter_backward_matches(self, end, categories):
        if end in self._reverse_map:
            for category in categories:
                by_name = self._reverse_map[end]
                if category.is_wildcard():
                    for category_name in by_name:
                        by_cat = by_name[category_name]
                        for mapped_category in by_cat:
                            if mapped_category in category:
                                for start in by_cat[mapped_category]:
                                    yield mapped_category, start
                elif category.name in by_name:
                    by_cat = by_name[category.name]
                    for mapped_category in by_cat:
                        if mapped_category in category:
                            for start in by_cat[mapped_category]:
                                yield mapped_category, start

    def iter_node_sets(self, start, category, end):
        if (start in self._map and
                category.name in self._map[start] and
                category in self._map[start][category.name] and
                end in self._map[start][category.name][category]):
            yield self._map[start][category.name][category][end]

    def get_node_set(self, node):
        category = node.category
        name = category.name
        start = node.start
        if (start in self._map and
                name in self._map[start] and
                category in self._map[start][name] and
                node.end in self._map[start][name][category]):
            return self._map[start][name][category][node.end]
        else:
            return None

    def has_start(self, start):
        return start in self._map

    def has_end(self, end):
        return end in self._reverse_map

    def has_range(self, start, end):
        return (start, end) in self._ranges


class ParserState:
    """The state of the parser as parsing proceeds."""

    # TODO: Can we rank them by how much they improve the best parse
    #       quality for the worst token? That is, for each token that is
    #       covered, how much did the maximum parse quality for that token
    #       improve?
    @staticmethod
    def _insertion_key(node):
        # width = node.end - node.start
        score, confidence = node.get_weighted_score()

        # same_rule_count = 0
        # for item in self._insertion_queue:
        #     if item.rule is node.rule:
        #         same_rule_count += 1

        # no_predecessor = node.start > 0 and not self._category_map.has_range(0, node.start)
        # no_successor = (
        #   node.end < self._category_map.max_end and
        #   not self._category_map.has_range(node.end, self._category_map.max_end)
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
            if node_set.end - node_set.start >= len(self._tokens):
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
    def process_node(self, timeout=None):
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
            if id(node_set) not in self._node_set_ids:
                self._node_set_ids.add(id(node_set))
                # Only add to roots if the node set hasn't already been removed
                self._roots.add(node_set)
            for branch_rule in self._model.branch_rules:
                branch_rule(self, node_set)
            break
        return bool(self._insertion_queue)

    # TODO: Move to ParserAlgorithm
    def process_necessary_nodes(self, timeout=None):
        """Process pending nodes until they are exhausted or the entire
        input is covered by a single tree."""
        # TODO: This isn't always working. Sometimes I don't get a complete
        #       parse. I checked, and is_covered is not the problem.
        while not self.is_covered() and self.process_node() and (timeout is None or time.time() < timeout):
            pass  # The condition call does all the work.

    # TODO: Move to ParsingAlgorithm
    def process_all_nodes(self, timeout=None):
        """Process all pending nodes."""
        while self.process_node(timeout) and (timeout is None or time.time() < timeout):
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
    def parse(parser_state, text, fast=False, timeout=None):
        """Parses a piece of text, returning the results."""
        for token, start, end in parser_state.model.tokenizer.tokenize(text):
            parser_state.add_token(token, start, end)
        if fast:
            parser_state.process_necessary_nodes(timeout)
        else:
            parser_state.process_all_nodes(timeout)
        return parser_state.get_parse()

    @staticmethod
    def extract(parse, language_graph_builder):
        """Extracts a sentence network from a parse."""
        return parse.build_language_graph(language_graph_builder)

    # def _iter_combos(self, subcategory_sets, covered, trees):
    #     if not subcategory_sets:
    #         yield []
    #     else:
    #         subcategory_set = subcategory_sets[0]
    #         subcategory_sets = subcategory_sets[1:]
    #         for tree in trees:
    #             if tree.node_coverage & covered:
    #                 # Don't allow multiple occurrences of the same node.
    #                 continue
    #             satisfied = False
    #             for subcategory in subcategory_set:
    #                 # If the subtree's category matches...
    #                 if tree.category in subcategory:
    #                     satisfied = True
    #                     break
    #             if not satisfied:
    #                 continue
    #             for tail in self._iter_combos(subcategory_sets, covered | tree.node_coverage, trees):
    #                 yield [tree] + tail


class GenerationAlgorithm:

    def generate(self, model, sentence):
        assert isinstance(sentence, graphs.ParseGraph)
        return self._generate(model, sentence.root_index, sentence)

    def _generate(self, model, head_node, sentence):
        head_spelling = sentence[head_node][1]
        head_category = sentence[head_node][3]

        log.debug("%s %s", head_spelling, head_category.to_str(False))

        # Find the subnodes of the head node
        subnodes = sentence.get_sinks(head_node)

        # Build the subtree for each subnode
        subtrees = {sink: self._generate(model, sink, sentence) for sink in subnodes}

        # Find all leaves for the head node
        subtrees[head_node] = set()
        positive_case_properties, negative_case_properties = rules.LeafRule.discover_case_properties(head_spelling)
        for rule in model.primary_leaf_rules:
            if head_spelling in rule:
                category = rule.category.promote_properties(positive_case_properties, negative_case_properties)
                category = extend_properties(model, category)
                if category in head_category:
                    tree = trees.BuildTreeNode(rule, category, head_spelling, head_node)
                    subtrees[head_node].add(tree)
        if not subtrees[head_node]:
            for rule in model.secondary_leaf_rules:
                if head_spelling in rule:
                    category = rule.category.promote_properties(positive_case_properties, negative_case_properties)
                    category = extend_properties(model, category)
                    if category in head_category:
                        tree = trees.BuildTreeNode(rule, category, head_spelling, head_node)
                        subtrees[head_node].add(tree)

        results = set()
        backup_results = set()
        emergency_results = set()

        # If we only have the head node, the leaves for the head node can
        # serve as results
        if len(subtrees) == 1:
            if head_node == sentence.root_index:
                for tree in subtrees[head_node]:
                    if tree.category in sentence.root_category:
                        results.add(tree)
                    else:
                        backup_results.add(tree)
            else:
                results = set(subtrees[head_node])
        else:
            results = set()

        # For each possible subtree headed by the head node, attempt to
        # iteratively expand coverage out to all subnodes via branch rules.
        # TODO: This loop only works for non-conjunction rules because it
        #       assumes the link_type_sets and head_index properties are
        #       available. Move the code into appropriate methods on the
        #       branch rule subclasses and call into them.
        # TODO: Break this up into functions so it isn't so deeply nested.
        insertion_queue = set(subtrees[head_node])
        while insertion_queue:
            head_tree = insertion_queue.pop()
            for rule in model.branch_rules:
                fits = False
                for subcategory in rule.head_category_set:
                    if head_tree.category in subcategory:
                        fits = True
                        break
                if not fits:
                    continue
                possible_components = []
                failed = False
                # TODO: AttributeError: 'ConjunctionRule' object has no
                #       attribute 'link_type_sets'
                for index in range(len(rule.link_type_sets)):
                    required_incoming = set()
                    required_outgoing = set()
                    for link_type, left, right in rule.link_type_sets[index]:
                        if (right and index < rule.head_index) or (left and index >= rule.head_index):
                            required_incoming.add(link_type)
                        if (left and index < rule.head_index) or (right and index >= rule.head_index):
                            required_outgoing.add(link_type)
                    component_candidates = self.get_component_candidates(model, head_category, head_node, index,
                                                                         required_incoming, required_outgoing, rule,
                                                                         sentence, subnodes, subtrees)
                    if not component_candidates:
                        failed = True
                        break
                    possible_components.append(component_candidates)
                if failed:
                    continue
                possible_components.insert(rule.head_index, {head_tree})
                for component_combination in product(*possible_components):
                    covered = set()
                    for component in component_combination:
                        if component.node_coverage & covered:
                            break
                        covered |= component.node_coverage
                    else:
                        category = rule.get_category(model, [component.category for component in component_combination])
                        if rule.is_non_recursive(category, head_tree.category):
                            new_tree = trees.BuildTreeNode(rule, category, head_tree.head_spelling,
                                                           head_tree.head_index, component_combination)
                            if new_tree not in results:
                                if subnodes <= new_tree.node_coverage:
                                    if new_tree.head_index != sentence.root_index or category in sentence.root_category:
                                        results.add(new_tree)
                                    else:
                                        backup_results.add(new_tree)
                                emergency_results.add(new_tree)
                                insertion_queue.add(new_tree)
        if results:
            return results
        elif backup_results:
            return backup_results
        else:
            return emergency_results

    @staticmethod
    def get_component_candidates(model, head_category, head_node, index, required_incoming, required_outgoing,
                                 rule, sentence, subnodes, subtrees):
        component_head_candidates = subnodes.copy()
        for link_type in required_incoming:
            if link_type not in model.rules_by_link_type:
                continue
            component_head_candidates &= {source for source in sentence.get_sources(head_node)
                                          if link_type in sentence.get_labels(source, head_node)}
            if not component_head_candidates:
                break
        if not component_head_candidates:
            return None
        for link_type in required_outgoing:
            if link_type not in model.rules_by_link_type:
                continue
            component_head_candidates &= {sink for sink in sentence.get_sinks(head_node)
                                          if link_type in sentence.get_labels(head_node, sink)}
            if not component_head_candidates:
                break
        if not component_head_candidates:
            return None
        component_candidates = set()
        if isinstance(rule, rules.ConjunctionRule):
            for candidate in component_head_candidates:
                for subtree in subtrees[candidate]:
                    if subtree.category in head_category:
                        component_candidates.add(subtree)
                        break
                else:
                    for subtree in subtrees[candidate]:
                        component_candidates.add(subtree)
                        break
        else:
            cat_names = {category.name
                         for category in rule.subcategory_sets[index if index < rule.head_index else index + 1]}
            for candidate in component_head_candidates:
                for subtree in subtrees[candidate]:
                    if subtree.category.name in cat_names:
                        good = False
                        cat_index = (index if index < rule.head_index else index + 1)
                        for category in rule.subcategory_sets[cat_index]:
                            if subtree.category in category:
                                good = True
                                break
                        if good:
                            component_candidates.add(subtree)
        return component_candidates


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
    def parse(self, text, category=None, fast=False, timeout=None, fresh=True):
        if isinstance(category, str):
            category = ModelLoader.parse_category(category)

        if fresh or not self._parser_state:
            self.clear_state()

        result = ParsingAlgorithm.parse(self._parser_state, text, fast, timeout)

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
