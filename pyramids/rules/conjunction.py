from typing import FrozenSet, Iterable, Tuple, Any, Optional, Sequence, Iterator, List

from pyramids import trees, categorization, parsing, model
from pyramids.categorization import CATEGORY_WILDCARD, LinkLabel, Category
from pyramids.category_maps import CategoryMap
from pyramids.properties import CONJUNCTION_PROPERTY, COMPOUND_PROPERTY, SIMPLE_PROPERTY, \
    SINGLE_PROPERTY
from pyramids.rules.branch import BranchRule
# TODO: This class is eating up more than 2/3 of the parse time, all by itself. It's broken. Rewrite
#       it.
# TODO: Define properties in the .ini that are used to indicate compound, simple, and single
#       conjunctions. These properties should be added automatically by conjunction rules unless
#       overridden in the properties of the conjunction's category.
from pyramids.rules.subtree_match import SubtreeMatchRule
from pyramids.traversal import TraversableElement


class ConjunctionRule(BranchRule):

    def __init__(self, category: Category, match_rules: Iterable[Tuple[SubtreeMatchRule]],
                 property_rules: Iterable[Tuple[FrozenSet[Tuple[Any, bool]],
                                                Tuple[SubtreeMatchRule, ...]]],
                 leadup_categories: Optional[Iterable[Category]],
                 conjunction_categories: Iterable[Category],
                 followup_categories: Iterable[Category],
                 leadup_link_types: Iterable[LinkLabel],
                 followup_link_types: Iterable[LinkLabel],
                 single: bool = False, compound: bool = True):
        super(BranchRule, self).__init__()

        # TODO: Type checking

        self._category = category

        # TODO: Do something with this... This is the list of conditions that must be met for the
        #       rule to match.
        self._match_rules = tuple(match_rules)

        # TODO: Do something with this... This is the list of conditions that must be met for
        self._property_rules = tuple(property_rules)

        self._leadup_categories = frozenset(leadup_categories or ())
        self._conjunction_categories = frozenset(conjunction_categories)
        self._followup_categories = frozenset(followup_categories)
        self._leadup_link_types = frozenset(leadup_link_types)
        self._followup_link_types = frozenset(followup_link_types)

        # Can we accept only a followup?
        self._single = bool(single) or leadup_categories is None

        # Can we accept more than 2 terms?
        self._compound = bool(compound) and leadup_categories is not None

        subcategory_sets = (self._leadup_categories, self._conjunction_categories,
                            self._followup_categories)
        self._hash = (hash(self._category) ^ hash(subcategory_sets) ^
                      hash(self._leadup_link_types) ^ hash(self._followup_link_types) ^
                      hash(self._single) ^ hash(self._compound))
        self._references = frozenset(category.name for category_set in subcategory_sets
                                     for category in category_set)
        self._has_wildcard = CATEGORY_WILDCARD in self._references
        self._all_link_types = frozenset(item[0]
                                         for item in (self._leadup_link_types |
                                                      self._followup_link_types))

    def _can_match(self, subtree_categories: Sequence[Category], head_index: int) -> bool:
        if not self._match_rules:
            return True
        for match_rules in self._match_rules:
            if all(rule(subtree_categories, head_index) for rule in match_rules):
                return True
        return False

    def _iter_forward_halves(self, category_map: CategoryMap, state: int, start: int,
                             emergency: bool) -> Iterator[List[trees.TreeNodeSet]]:
        if state == -1:  # Leadup case/exception
            for category, end in category_map.iter_forward_matches(start, self._leadup_categories,
                                                                   emergency):
                for node_set in category_map.iter_node_sets(start, category, end):
                    for tail in self._iter_forward_halves(category_map, 0, end, emergency):
                        yield [node_set] + tail
                    if self._compound:
                        for tail in self._iter_forward_halves(category_map, -1, end, emergency):
                            yield [node_set] + tail
        elif state == 0:  # Conjunction
            for category, end in category_map.iter_forward_matches(start,
                                                                   self._conjunction_categories,
                                                                   emergency):
                for node_set in category_map.iter_node_sets(start, category, end):
                    for tail in self._iter_forward_halves(category_map, 1, end, emergency):
                        yield [node_set] + tail
        elif state == 1:  # Followup case/exception
            for category, end in category_map.iter_forward_matches(start, self._followup_categories,
                                                                   emergency):
                for node_set in category_map.iter_node_sets(start, category, end):
                    yield [node_set]
        else:
            raise Exception("Unexpected state: " + repr(state))

    def _iter_backward_halves(self, category_map: CategoryMap, state: int, end: int,
                              emergency: bool) -> Iterator[List[trees.TreeNodeSet]]:
        if state == -1:  # Leadup case/exception
            for category, start in category_map.iter_backward_matches(end, self._leadup_categories,
                                                                      emergency):
                for node_set in category_map.iter_node_sets(start, category, end):
                    if self._compound:
                        for tail in self._iter_backward_halves(category_map, -1, start, emergency):
                            yield tail + [node_set]
                    yield [node_set]
        elif state == 0:  # Conjunction
            for category, start in category_map.iter_backward_matches(end,
                                                                      self._conjunction_categories,
                                                                      emergency):
                for node_set in category_map.iter_node_sets(start, category, end):
                    for tail in self._iter_backward_halves(category_map, -1, start, emergency):
                        yield tail + [node_set]
                    if self._single:
                        yield [node_set]
        else:
            # We don't need to handle followups because _find_matches will
            # never call this with that state
            raise Exception("Unexpected state: " + repr(state))

    def _find_matches(self, parser_state: 'parsing.ParserState', state: int,
                      new_node_set: trees.TreeNodeSet[trees.ParsingPayload],
                      emergency: bool) -> None:
        """Given a starting state (-1 for leadup, 0 for conjunction, 1 for followup), attempt to
        find and add all parse node sequences in the parser state that can contain the new node in
        that state."""
        # Check forward halves first, because they're less likely, and if we don't find any, we
        # won't even need to bother looking for backward halves.
        payload = new_node_set.payload
        forward_halves = list(self._iter_forward_halves(parser_state.category_map, state,
                                                        payload.token_start_index, emergency))
        if forward_halves:
            if state == -1:  # Leadup case/exception
                for forward_half in forward_halves:
                    head_offset = len(forward_half) - 2
                    subtree_categories = [subtree.payload.category for subtree in forward_half]
                    if self._can_match(subtree_categories, head_offset):
                        category = self.get_category(parser_state.model, subtree_categories,
                                                     head_offset)
                        if self.is_non_recursive(category,
                                                 forward_half[head_offset].payload.category):
                            node = trees.ParseTreeUtils.make_branch_parse_tree_node(
                                parser_state.tokens, self, head_offset, category, forward_half)
                            parser_state.add_node(node)
                if self._compound:
                    for backward_half in self._iter_backward_halves(parser_state.category_map, -1,
                                                                    payload.token_start_index,
                                                                    emergency):
                        for forward_half in forward_halves:
                            subtrees = backward_half + forward_half
                            head_offset = len(subtrees) - 2
                            subtree_categories = [subtree.payload.category for subtree in subtrees]
                            if self._can_match(subtree_categories, head_offset):
                                category = self.get_category(parser_state.model, subtree_categories,
                                                             head_offset)
                                if self.is_non_recursive(category,
                                                         subtrees[head_offset].payload.category):
                                    node = trees.ParseTreeUtils.make_branch_parse_tree_node(
                                        parser_state.tokens, self, head_offset, category, subtrees)
                                    parser_state.add_node(node)
            elif state == 0:  # Conjunction
                if self._single:
                    for forward_half in forward_halves:
                        head_offset = len(forward_half) - 2
                        subtree_categories = [subtree.payload.category for subtree in forward_half]
                        if self._can_match(subtree_categories, head_offset):
                            category = self.get_category(parser_state.model, subtree_categories,
                                                         head_offset)
                            if self.is_non_recursive(category,
                                                     forward_half[head_offset].payload.category):
                                node = trees.ParseTreeUtils.make_branch_parse_tree_node(
                                    parser_state.tokens, self, head_offset, category, forward_half)
                                parser_state.add_node(node)
                for backward_half in self._iter_backward_halves(parser_state.category_map, -1,
                                                                payload.token_start_index,
                                                                emergency):
                    for forward_half in forward_halves:
                        subtrees = backward_half + forward_half
                        head_offset = len(subtrees) - 2
                        subtree_categories = [subtree.payload.category for subtree in subtrees]
                        if self._can_match(subtree_categories, head_offset):
                            category = self.get_category(parser_state.model, subtree_categories,
                                                         head_offset)
                            if self.is_non_recursive(category,
                                                     subtrees[head_offset].payload.category):
                                node = trees.ParseTreeUtils.make_branch_parse_tree_node(
                                    parser_state.tokens, self, head_offset, category, subtrees)
                                parser_state.add_node(node)
            elif state == 1:  # Followup case/exception
                for backward_half in self._iter_backward_halves(parser_state.category_map, 0,
                                                                payload.token_start_index,
                                                                emergency):
                    for forward_half in forward_halves:
                        subtrees = backward_half + forward_half
                        head_offset = len(subtrees) - 2
                        subtree_categories = [subtree.payload.category for subtree in subtrees]
                        if self._can_match(subtree_categories, head_offset):
                            category = self.get_category(parser_state.model, subtree_categories,
                                                         head_offset)
                            if self.is_non_recursive(category,
                                                     subtrees[head_offset].payload.category):
                                node = trees.ParseTreeUtils.make_branch_parse_tree_node(
                                    parser_state.tokens, self, head_offset, category, subtrees)
                                parser_state.add_node(node)
            else:
                raise Exception("Unexpected state: " + repr(state))

    # TODO: Think about it really hard: Why does this method (or SequenceRule's) consider anything
    #       other than the final state/index? Maybe there is a good reason, but shouldn't we skip
    #       that if we're strictly appending new tokens? This may be an opportunity for an extreme
    #       speedup.
    def __call__(self, parser_state: 'parsing.ParserState', new_node_set: trees.TreeNodeSet,
                 emergency: bool = False) -> None:
        if not (self._has_wildcard or new_node_set.payload.category.name in self._references):
            return
        for state, subcategory_set in ((-1, self._leadup_categories),
                                       (0, self._conjunction_categories),
                                       (1, self._followup_categories)):
            for subcategory in subcategory_set:
                if new_node_set.payload.category in subcategory:
                    self._find_matches(parser_state, state, new_node_set, emergency)
                    break  # We only need to do it once for each state

    def __hash__(self) -> int:
        return self._hash

    def __eq__(self, other: 'ConjunctionRule') -> bool:
        if not isinstance(other, ConjunctionRule):
            return NotImplemented
        return self is other or (self._hash == other._hash and self._single == other._single and
                                 self._compound == other._compound and
                                 self._leadup_link_types == other._leadup_link_types and
                                 self._followup_link_types == other._followup_link_types and
                                 self._category == other._category and
                                 self._conjunction_categories == other._conjunction_categories and
                                 self._leadup_categories == other._leadup_categories and
                                 self._followup_categories == other._followup_categories)

    def __ne__(self, other: 'ConjunctionRule') -> bool:
        if not isinstance(other, ConjunctionRule):
            return NotImplemented
        return self is not other and not (self._hash == other._hash and
                                          self._single == other._single and
                                          self._compound == other._compound and
                                          self._leadup_link_types == other._leadup_link_types and
                                          (self._followup_link_types
                                           == other._followup_link_types) and
                                          self._category == other._category and
                                          (self._conjunction_categories
                                           == other._conjunction_categories) and
                                          self._leadup_categories == other._leadup_categories and
                                          self._followup_categories == other._followup_categories)

    def __str__(self) -> str:
        result = str(self.category) + ':'
        for rules in self._match_rules:
            result += ' [' + ' '.join(str(rule) for rule in rules) + ']'
        for properties, rules in self._property_rules:
            result += (' ' + ','.join(('' if is_positive else '-') + prop
                                      for prop, is_positive in properties) +
                       '[' + ' '.join(str(rule) for rule in rules) + ']')
        for prefix, category_set, link_types in (('+' if self._compound
                                                  else ('-' if self._single else ''),
                                                  self._leadup_categories, self._leadup_link_types),
                                                 ('*', self._conjunction_categories,
                                                  self._followup_link_types),
                                                 ('', self._followup_categories, None)):
            result += ' ' + prefix + '|'.join(sorted(str(category) for category in category_set))
            if link_types:
                for link_type, left, right in sorted(link_types):
                    result += ' '
                    if left:
                        result += '<'
                    result += link_type
                    if right:
                        result += '>'
        return result

    def __repr__(self) -> str:
        return (type(self).__name__ + "(" + repr(self.category) + ", " +
                repr(sorted(self._leadup_categories)) + ", " +
                repr(sorted(self._conjunction_categories)) + ", " +
                repr(sorted(self._followup_categories)) + ", " +
                repr(self._leadup_link_types) + ", " + repr(self._followup_link_types) + ", " +
                repr(self._single) + ", " + repr(self._compound) + ")")

    @property
    def category(self) -> Category:
        """The category (and required properties) generated by this rule."""
        return self._category

    @property
    def head_category_set(self) -> FrozenSet[Category]:
        """The category set for the head of the generated parse tree nodes."""
        return self._conjunction_categories

    @property
    def leadup_categories(self) -> FrozenSet[Category]:
        return self._leadup_categories

    @property
    def conjunction_categories(self) -> FrozenSet[Category]:
        return self._conjunction_categories

    @property
    def followup_categories(self) -> FrozenSet[Category]:
        return self._followup_categories

    @property
    def leadup_link_types(self) -> FrozenSet[LinkLabel]:
        return self._leadup_link_types

    @property
    def followup_link_types(self) -> FrozenSet[LinkLabel]:
        return self._followup_link_types

    @property
    def single(self) -> bool:
        return self._single

    @property
    def compound(self) -> bool:
        return self._compound

    @property
    def head_index(self) -> int:
        return 1

    @property
    def link_type_sets(self) -> Tuple[FrozenSet[Tuple[LinkLabel, bool, bool]],
                                      FrozenSet[Tuple[LinkLabel, bool, bool]]]:
        return (frozenset([(self._leadup_link_types, True, False)]),
                frozenset([(self._followup_link_types, False, True)]),)

    @property
    def all_link_types(self) -> FrozenSet[LinkLabel]:
        return self._all_link_types

    def get_link_types(self, parse_node: TraversableElement,
                       link_set_index: int) -> Iterable[Tuple[LinkLabel, bool, bool]]:
        # If it's the last link set interval
        if link_set_index + 2 >= len(parse_node.components):
            return self._followup_link_types
        else:
            return self._leadup_link_types

    def get_category(self, model: 'model.Model', subtree_categories: Sequence[Category],
                     head_index: int = None) -> Category:
        if head_index is None:
            # Figure out what head index to use
            head_index = len(subtree_categories) - 2
        if self.category.is_wildcard():
            category = categorization.Category(subtree_categories[-1].name,
                                               self.category.positive_properties,
                                               self.category.negative_properties)
        else:
            category = self.category

        # Start out with the intersection of shared properties for all non-
        # head subtree categories
        positive = set(subtree_categories[-1].positive_properties)
        negative = set(subtree_categories[-1].negative_properties)
        for index in range(len(subtree_categories) - 2):
            positive &= set(subtree_categories[index].positive_properties)
            negative &= set(subtree_categories[index].negative_properties)

        # Then apply the standard promotion rules
        for prop in model.any_promoted_properties:
            for subtree_category in subtree_categories:
                if prop in subtree_category.positive_properties:
                    positive.add(prop)
                    negative.discard(prop)
                    break
            if prop not in positive:
                for subtree_category in subtree_categories:
                    if prop not in subtree_category.negative_properties:
                        break
                else:
                    negative.add(prop)
        for prop in model.all_promoted_properties:
            for subtree_category in subtree_categories:
                if prop in subtree_category.negative_properties:
                    negative.add(prop)
                    positive.discard(prop)
                    break
            if prop not in negative:
                for subtree_category in subtree_categories:
                    if prop not in subtree_category.positive_properties:
                        break
                else:
                    positive.add(prop)

        # Add the standard properties
        # TODO: Load these from the .ini instead of hard-coding them.
        positive.add(CONJUNCTION_PROPERTY)
        negative.discard(CONJUNCTION_PROPERTY)
        if len(subtree_categories) > 3:
            positive.add(COMPOUND_PROPERTY)
            negative.discard(COMPOUND_PROPERTY)
            negative.add(SIMPLE_PROPERTY)
            positive.discard(SIMPLE_PROPERTY)
            negative.add(SINGLE_PROPERTY)
            positive.discard(SINGLE_PROPERTY)
        elif len(subtree_categories) < 3:
            negative.add(SIMPLE_PROPERTY)
            positive.discard(SIMPLE_PROPERTY)
            negative.add(COMPOUND_PROPERTY)
            positive.discard(COMPOUND_PROPERTY)
            positive.add(SINGLE_PROPERTY)
            negative.discard(SINGLE_PROPERTY)
        else:
            negative.add(COMPOUND_PROPERTY)
            positive.discard(COMPOUND_PROPERTY)
            positive.add(SIMPLE_PROPERTY)
            negative.discard(SIMPLE_PROPERTY)
            negative.add(SINGLE_PROPERTY)
            positive.discard(SINGLE_PROPERTY)

        # And finally, apply property rules specific to this parse rule
        for properties, property_rules in self._property_rules:
            matched = all(rule(subtree_categories, head_index) for rule in property_rules)
            for (prop, is_positive) in properties:
                if is_positive == matched:
                    positive.add(prop)
                    negative.discard(prop)
                else:
                    negative.add(prop)
                    positive.discard(prop)

        # return parser.extend_properties(category.promote_properties(positive, negative))
        return category.promote_properties(positive, negative)

    def is_non_recursive(self, result_category: Category, head_category: Category) -> bool:
        # It's *never* recursive, because we require more than one token for every conjunctive
        # phrase
        return True
