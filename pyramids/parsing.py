import logging
import time
from sys import intern

from pyramids import (categorization, graphs, parserules, parsetrees,
                      tokenization, utility)

# These are used during pickle reconstruction. Do not remove them.
from pyramids.scoring import ScoringMeasure
from pyramids.categorization import Category, Property


__author__ = 'Aaron Hosford'
__all__ = [
    'CategoryMap',
    'ParserState',
    'Parser',
]

log = logging.getLogger(__name__)


class CategoryMap:
    """The category map tracked & used by a parser state."""

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
                    for end in \
                            self._map[start][category_name_id][category]:
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
        name_id = id(cat.name)
        start = node.start
        end = node.end

        if start not in self._map:
            node_set = parsetrees.ParseTreeNodeSet(node)
            self._map[start] = {name_id: {cat: {end: node_set}}}
        elif name_id not in self._map[start]:
            node_set = parsetrees.ParseTreeNodeSet(node)
            self._map[start][name_id] = {cat: {end: node_set}}
        elif cat not in self._map[start][name_id]:
            node_set = parsetrees.ParseTreeNodeSet(node)
            self._map[start][name_id][cat] = {end: node_set}
        elif end not in self._map[start][name_id][cat]:
            node_set = parsetrees.ParseTreeNodeSet(node)
            self._map[start][name_id][cat][end] = node_set
        elif node not in self._map[start][name_id][cat][end]:
            self._map[start][name_id][cat][end].add(node)
            return False  # No new node sets were added.
        else:
            return False  # It's already in the map

        if end not in self._reverse_map:
            self._reverse_map[end] = {name_id: {cat: {start: node_set}}}
        elif name_id not in self._reverse_map[end]:
            self._reverse_map[end][name_id] = {cat: {start: node_set}}
        elif cat not in self._reverse_map[end][name_id]:
            self._reverse_map[end][name_id][cat] = {start: node_set}
        elif start not in self._reverse_map[end][name_id][cat]:
            self._reverse_map[end][name_id][cat][start] = node_set

        if end > self._max_end:
            self._max_end = end

        self._size += 1
        self._ranges.add((start, end))

        return True  # It's something new

    def iter_forward_matches(self, start, categories):
        if start in self._map:
            for category in categories:
                by_name_id = self._map[start]
                if category.name == '_':
                    for category_name_id in by_name_id:
                        by_cat = by_name_id[category_name_id]
                        for mapped_category in by_cat:
                            if mapped_category in category:
                                for end in by_cat[mapped_category]:
                                    yield mapped_category, end
                elif id(category.name) in by_name_id:
                    by_cat = by_name_id[id(category.name)]
                    for mapped_category in by_cat:
                        if mapped_category in category:
                            for end in by_cat[mapped_category]:
                                yield mapped_category, end

    def iter_backward_matches(self, end, categories):
        if end in self._reverse_map:
            for category in categories:
                by_name_id = self._reverse_map[end]
                if category.name == '_':
                    for category_name_id in by_name_id:
                        by_cat = by_name_id[category_name_id]
                        for mapped_category in by_cat:
                            if mapped_category in category:
                                for start in by_cat[mapped_category]:
                                    yield mapped_category, start
                elif id(category.name) in by_name_id:
                    by_cat = by_name_id[id(category.name)]
                    for mapped_category in by_cat:
                        if mapped_category in category:
                            for start in by_cat[mapped_category]:
                                yield mapped_category, start

    def iter_node_sets(self, start, category, end):
        if (start in self._map and
                id(category.name) in self._map[start] and
                category in self._map[start][id(category.name)] and
                end in self._map[start][id(category.name)][category]):
            yield self._map[start][id(category.name)][category][end]

    def get_node_set(self, node):
        category = node.category
        name_id = id(category.name)
        start = node.start
        if (start in self._map and
                name_id in self._map[start] and
                category in self._map[start][name_id] and
                node.end in self._map[start][name_id][category]):
            return self._map[start][name_id][category][node.end]
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
    def _insertion_key(self, node):
        # width = node.end - node.start
        score, confidence = node.get_weighted_score()

        same_rule_count = 0
        for item in self._insertion_queue:
            if item.rule is node.rule:
                same_rule_count += 1

        # no_predecessor = node.start > 0 and \
        #     not self._category_map.has_range(0, node.start)
        # no_successor = node.end < self._category_map.max_end and \
        #     not self._category_map.has_range(
        #         node.end,
        #         self._category_map.max_end
        #     )

        # Always sorts smallest to largest, so make the best the smallest.
        # Using same_rule_count forces highly-recursive rules to take a
        # back seat to those that are well-behaved.
        # return -width, -score, -confidence

        # TODO: Decide what's best to use here, to maximize the odds of
        #       finding the best parse when parsing times out.
        return same_rule_count - score, -confidence

    def __init__(self, parser):
        if not isinstance(parser, Parser):
            raise TypeError(parser, Parser)
        self._parser = parser
        self._tokens = []
        self._token_sequence = None
        self._category_map = CategoryMap()
        self._insertion_queue = utility.PrioritySet(
            key=self._insertion_key
        )
        self._node_set_ids = set()
        self._roots = set()

    @property
    def parser(self):
        return self._parser

    @property
    def tokens(self):
        if self._token_sequence is None:
            self._token_sequence = tokenization.TokenSequence(
                self._tokens
            )
        return self._token_sequence

    @property
    def category_map(self):
        return self._category_map

    @property
    def insertion_queue(self):
        return self._insertion_queue

    @property
    def any_promoted_properties(self):
        """Properties that may be promoted if any element possesses them.
        """
        return self._parser.any_promoted_properties

    @property
    def all_promoted_properties(self):
        """Properties that may be promoted if all elements possess them."""
        return self._parser.all_promoted_properties

    def extend_properties(self, category):
        """Extend the category's properties per the inheritance rules."""
        return self._parser.extend_properties(category)

    def has_nodes_pending(self):
        """The number of nodes still waiting to be processed."""
        return bool(self._insertion_queue)

    def add_node(self, node):
        """Add a new parse tree node to the insertion queue."""
        self._insertion_queue.push(node)

    def add_token(self, token, start=None, end=None):
        """Add a new token to the token sequence."""
        token = intern(str(token))
        index = len(self._tokens)
        self._tokens.append((token, start, end))
        self._token_sequence = None
        covered = False
        for leaf_rule in self._parser.primary_leaf_rules:
            covered |= leaf_rule(self, token, index)
        if not covered:
            for leaf_rule in self._parser.secondary_leaf_rules:
                leaf_rule(self, token, index)

    def process_node(self, timeout=None):
        """Search for the next parse tree node in the insertion queue that
        makes an original contribution to the parse. If any is found,
        process it. Return a boolean indicating whether there are more
        nodes to process."""
        while (self._insertion_queue and
               (timeout is None or time.time() < timeout)):
            node = self._insertion_queue.pop()
            if not self._category_map.add(node):
                # Drop it and continue on to the next one. "We've already
                # got one!"
                continue
            if not node.is_leaf():
                self._roots -= set(node.components)
            node_set = self._category_map.get_node_set(node)
            if id(node_set) not in self._node_set_ids:
                self._node_set_ids.add(id(node_set))
                # Only add to roots if the node set hasn't already been
                # removed
                self._roots.add(node_set)
            for branch_rule in self._parser.branch_rules:
                branch_rule(self, node_set)
            break
        return bool(self._insertion_queue)

    def is_covered(self):
        """Returns a boolean indicating whether a node exists that covers
        the entire input by itself."""
        for node_set in self._roots:
            if node_set.end - node_set.start >= len(self._tokens):
                return True
        return False

    def process_necessary_nodes(self, timeout=None):
        """Process pending nodes until they are exhausted or the entire
        input is covered by a single tree."""
        # TODO: This isn't always working. Sometimes I don't get a complete
        #       parse. I checked, and is_covered is not the problem.
        while (not self.is_covered() and
               self.process_node() and
               (timeout is None or time.time() < timeout)):
            pass  # The condition call does all the work.

    def process_all_nodes(self, timeout=None):
        """Process all pending nodes."""
        while self.process_node(timeout) and (
                timeout is None or time.time() < timeout):
            pass  # The condition call does all the work.

    def get_parse(self):
        """Create a tree for each node that doesn't get included as a
        component to some other one. Then it make a Parse instance with
        those trees."""
        return parsetrees.Parse(
            self.tokens,
            [parsetrees.ParseTree(self.tokens, node)
             for node in self._roots]
        )


class Parser:
    """Coordinates the search for new tokens and structures in a text using
    BaseRules and BuildRules, respectively. Stores the results in a Parse
    instance, which can be passed back in if additional input is received,
    or can be queried to determine the recognized structure(s) of the
    input."""

    def __init__(self, primary_leaf_rules, secondary_leaf_rules,
                 branch_rules, tokenizer, any_promoted_properties,
                 all_promoted_properties, property_inheritance_rules,
                 config_info=None):
        self._primary_leaf_rules = frozenset(primary_leaf_rules)
        self._secondary_leaf_rules = frozenset(secondary_leaf_rules)
        self._branch_rules = frozenset(branch_rules)
        self._tokenizer = tokenizer
        self._any_promoted_properties = frozenset(any_promoted_properties)
        self._all_promoted_properties = frozenset(all_promoted_properties)
        self._property_inheritance_rules = frozenset(
            property_inheritance_rules)
        self._config_info = config_info
        self._score_file_path = None
        self._scoring_measures_path = None
        self._rules_by_link_type = {}

        # TODO: Right now this only works for SequenceRules, not
        #       ConjunctionRules, hence the conditional thrown in here.
        for rule in self._branch_rules:
            if not isinstance(rule, parserules.SequenceRule):
                continue
            for index in range(len(rule.link_type_sets)):
                for link_type, left, right in rule.link_type_sets[index]:
                    if link_type not in self._rules_by_link_type:
                        self._rules_by_link_type[link_type] = set()
                    self._rules_by_link_type[link_type].add((rule, index))

    @property
    def primary_leaf_rules(self):
        return self._primary_leaf_rules

    @property
    def secondary_leaf_rules(self):
        return self._secondary_leaf_rules

    @property
    def branch_rules(self):
        return self._branch_rules

    @property
    def tokenizer(self):
        return self._tokenizer

    @property
    def any_promoted_properties(self):
        """Properties that may be promoted if any element possesses them.
        """
        return self._any_promoted_properties

    @property
    def all_promoted_properties(self):
        """Properties that may be promoted if all elements possess them."""
        return self._all_promoted_properties

    @property
    def config_info(self):
        """The configuration information for this parser, if any."""
        return self._config_info

    @property
    def scoring_measures_path(self):
        """The most recently loaded or saved scoring measures file path."""
        return self._scoring_measures_path

    def extend_properties(self, category):
        """Extend the category's properties per the inheritance rules."""
        positive = set(category.positive_properties)
        negative = set(category.negative_properties)
        more = True
        while more:
            more = False
            for rule in self._property_inheritance_rules:
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
        return categorization.Category(
            category.name,
            positive,
            negative
        )

    def new_parser_state(self):
        """Return a new parser state, for incremental parsing."""
        return ParserState(self)

    def parse(self, text, parser_state=None, fast=False, timeout=None):
        """Parses a piece of text, returning the results."""
        if parser_state is None:
            parser_state = self.new_parser_state()
        for token, start, end in self.tokenizer.tokenize(text):
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

    def _iter_combos(self, subcategory_sets, covered, trees):
        if not subcategory_sets:
            yield []
        else:
            subcategory_set = subcategory_sets[0]
            subcategory_sets = subcategory_sets[1:]
            for tree in trees:
                if tree.node_coverage & covered:
                    # Don't allow multiple occurrences of the same node.
                    continue
                satisfied = False
                for subcategory in subcategory_set:
                    # If the subtree's category matches...
                    if tree.category in subcategory:
                        satisfied = True
                        break
                if not satisfied:
                    continue
                for tail in self._iter_combos(
                        subcategory_sets,
                        covered | tree.node_coverage,
                        trees):
                    yield [tree] + tail

    def generate(self, sentence):
        assert isinstance(sentence, graphs.ParseGraph)
        return self._generate(
            sentence.root_index,
            sentence
        )

    def _generate(self, head_node, sentence):
        head_spelling = sentence[head_node][1]
        head_category = sentence[head_node][3]

        log.debug("%s %s", head_spelling, head_category.to_str(False))

        # Find the subnodes of the head node
        subnodes = sentence.get_sinks(head_node)

        # Build the subtree for each subnode
        subtrees = {sink: self._generate(sink, sentence)
                    for sink in subnodes}

        # Find all leaves for the head node
        subtrees[head_node] = set()
        positive_case_properties, negative_case_properties = \
            parserules.LeafRule.discover_case_properties(head_spelling)
        for rule in self._primary_leaf_rules:
            if head_spelling in rule:
                category = rule.category.promote_properties(
                    positive_case_properties,
                    negative_case_properties
                )
                category = self.extend_properties(category)
                if category in head_category:
                    tree = parsetrees.BuildTreeNode(
                        rule,
                        category,
                        head_spelling,
                        head_node
                    )
                    subtrees[head_node].add(tree)
        if not subtrees[head_node]:
            for rule in self._secondary_leaf_rules:
                if head_spelling in rule:
                    category = rule.category.promote_properties(
                        positive_case_properties,
                        negative_case_properties
                    )
                    category = self.extend_properties(category)
                    if category in head_category:
                        tree = parsetrees.BuildTreeNode(
                            rule,
                            category,
                            head_spelling,
                            head_node
                        )
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
            for rule in self._branch_rules:
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
                    for link_type, left, right in \
                            rule.link_type_sets[index]:
                        if ((right and index < rule.head_index) or
                                (left and index >= rule.head_index)):
                            required_incoming.add(link_type)
                        if ((left and index < rule.head_index) or
                                (right and index >= rule.head_index)):
                            required_outgoing.add(link_type)
                    component_head_candidates = subnodes.copy()
                    for link_type in required_incoming:
                        if link_type not in self._rules_by_link_type:
                            continue
                        component_head_candidates &= {
                            source
                            for source in sentence.get_sources(head_node)
                            if link_type in sentence.get_labels(source,
                                                                head_node)
                        }
                        if not component_head_candidates:
                            break
                    if not component_head_candidates:
                        failed = True
                        break
                    for link_type in required_outgoing:
                        if link_type not in self._rules_by_link_type:
                            continue
                        component_head_candidates &= {
                            sink
                            for sink in sentence.get_sinks(head_node)
                            if link_type in sentence.get_labels(head_node,
                                                                sink)
                        }
                        if not component_head_candidates:
                            break
                    if not component_head_candidates:
                        failed = True
                        break
                    component_candidates = set()
                    cat_name_ids = {
                        id(category.name)
                        for category in rule.subcategory_sets[
                            index if index < rule.head_index else index + 1
                        ]
                    }
                    for candidate in component_head_candidates:
                        for subtree in subtrees[candidate]:
                            if id(subtree.category.name) in cat_name_ids:
                                good = False
                                cat_index = (
                                    index
                                    if index < rule.head_index
                                    else index + 1
                                )
                                for category in \
                                        rule.subcategory_sets[cat_index]:
                                    if subtree.category in category:
                                        good = True
                                        break
                                if good:
                                    component_candidates.add(subtree)
                    if not component_candidates:
                        failed = True
                        break
                    possible_components.append(component_candidates)
                if failed:
                    continue
                possible_components.insert(rule.head_index, {head_tree})
                for component_combination in \
                        utility.iter_combinations(
                            possible_components):
                    covered = set()
                    for component in component_combination:
                        if component.node_coverage & covered:
                            break
                        covered |= component.node_coverage
                    else:
                        category = rule.get_category(
                            self,
                            [component.category
                             for component in component_combination]
                        )
                        if rule.is_non_recursive(
                                category,
                                head_tree.category):
                            new_tree = parsetrees.BuildTreeNode(
                                rule,
                                category,
                                head_tree.head_spelling,
                                head_tree.head_index,
                                component_combination
                            )
                            if new_tree not in results:
                                if subnodes <= new_tree.node_coverage:
                                    if ((new_tree.head_index !=
                                            sentence.root_index) or
                                            category in
                                            sentence.root_category):
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

    def load_scoring_measures(self, path=None):
        if path is None:
            if self._scoring_measures_path is None:
                raise ValueError("No path provided!")
            path = self._scoring_measures_path
        else:
            self._scoring_measures_path = path
        scores = {}
        with open(path, 'r') as save_file:
            for line in save_file:
                rule_str, measure_str, score_str, accuracy_str = \
                    line.strip().split('\t')
                if rule_str not in scores:
                    scores[rule_str] = set()
                scores[rule_str].add(
                    (
                        eval(measure_str),
                        float(score_str),
                        float(accuracy_str)
                    )
                )
            for rule in (self._primary_leaf_rules |
                         self._secondary_leaf_rules |
                         self._branch_rules):
                rule_str = repr(str(rule))
                if rule_str not in scores:
                    continue
                for measure, score, accuracy in scores[rule_str]:
                    rule.set_score(measure, score, accuracy)

    def save_scoring_measures(self, path=None):
        if path is None:
            if self._scoring_measures_path is None:
                raise ValueError("No path provided!")
            path = self._scoring_measures_path
        else:
            self._scoring_measures_path = path
        with open(path, 'w') as save_file:
            for rule in sorted(self._primary_leaf_rules |
                               self._secondary_leaf_rules |
                               self._branch_rules, key=str):
                for measure in rule.iter_all_scoring_measures():
                    score, accuracy = rule.get_score(measure)
                    save_file.write(
                        '\t'.join(
                            repr(item)
                            for item in (str(rule),
                                         measure,
                                         score,
                                         accuracy))
                        + '\n'
                    )
