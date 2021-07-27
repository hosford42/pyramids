from functools import reduce
from typing import List, Iterator, FrozenSet, Iterable, Tuple, Set, Sequence

from pyramids import trees, categorization, parsing, model
from pyramids.categorization import CATEGORY_WILDCARD, LinkLabel, Category
from pyramids.category_maps import CategoryMap
from pyramids.rules.branch import BranchRule
from pyramids.traversal import TraversableElement


class SequenceRule(BranchRule):

    def __init__(self, category: Category, subcategory_sets: Iterable[Iterable[Category]],
                 head_index: int, link_type_sets: Iterable[Set[Tuple[LinkLabel, int, int]]]):
        super(BranchRule, self).__init__()
        self._category = category
        self._subcategory_sets = tuple(frozenset(subcategory_set)
                                       for subcategory_set in subcategory_sets)
        self._head_index = head_index
        self._link_type_sets = tuple(frozenset(link_type_set) for link_type_set in link_type_sets)
        if len(self._link_type_sets) >= len(self._subcategory_sets):
            raise ValueError("Too many link type sets.")
        self._hash = (hash(self._category) ^ hash(self._subcategory_sets) ^ hash(self._head_index) ^
                      hash(self._link_type_sets))
        self._references = frozenset(c.name for s in self._subcategory_sets for c in s)
        self._has_wildcard = CATEGORY_WILDCARD in self._references
        self._all_link_types = frozenset(reduce(lambda a, b: a | {item[0] for item in b},
                                                self._link_type_sets, set()))

    def _iter_forward_halves(self, category_map: CategoryMap, index: int, start: int,
                             emergency: bool) -> Iterator[List[trees.TreeNodeSet]]:
        # Otherwise, we can't possibly find a match since it would have to fall off the edge
        if len(self._subcategory_sets) - index <= category_map.max_end - start:
            if index < len(self._subcategory_sets):
                for category, end in \
                        category_map.iter_forward_matches(start, self._subcategory_sets[index],
                                                          emergency):
                    for tail in self._iter_forward_halves(category_map, index + 1, end, emergency):
                        for node_set in category_map.iter_node_sets(start, category, end):
                            yield [node_set] + tail
            else:
                yield []

    def _iter_backward_halves(self, category_map: CategoryMap, index: int, end: int,
                              emergency: bool) -> Iterator[List[trees.TreeNodeSet]]:
        # Otherwise, we can't possibly find a match since it would have to fall off the edge
        if index <= end:
            if index >= 0:
                for category, start in \
                        category_map.iter_backward_matches(end, self._subcategory_sets[index],
                                                           emergency):
                    for tail in self._iter_backward_halves(category_map, index - 1, start,
                                                           emergency):
                        for node_set in category_map.iter_node_sets(start, category, end):
                            yield tail + [node_set]
            else:
                yield []

    def _find_matches(self, parser_state: 'parsing.ParserState', index: int,
                      new_node_set: trees.TreeNodeSet[trees.ParsingPayload],
                      emergency: bool) -> None:
        """Given a starting index in the sequence, attempt to find and add
        all parse node sequences in the parser state that can contain the
        new node at that index."""
        # Check forward halves first, because they're less likely, and if we don't find any, we
        # won't even need to bother looking for backward halves.
        payload = new_node_set.payload
        forward_halves = list(self._iter_forward_halves(parser_state.category_map, index + 1,
                                                        payload.token_end_index, emergency))
        if forward_halves:
            for backward_half in self._iter_backward_halves(parser_state.category_map, index - 1,
                                                            payload.token_start_index, emergency):
                for forward_half in forward_halves:
                    subtrees = backward_half + [new_node_set] + forward_half
                    category = self.get_category(parser_state.model, [subtree.payload.category
                                                                      for subtree in subtrees])
                    if self.is_non_recursive(category, subtrees[self._head_index].payload.category):
                        node = trees.ParseTreeUtils.make_branch_parse_tree_node(
                            parser_state.tokens, self, self._head_index, category, subtrees)
                        parser_state.add_node(node)

    def __call__(self, parser_state: 'parsing.ParserState',
                 new_node_set: trees.TreeNodeSet, emergency: bool = False) -> None:
        if not (self._has_wildcard or new_node_set.payload.category.name in self._references):
            return
        for index, subcategory_set in enumerate(self._subcategory_sets):
            for subcategory in subcategory_set:
                if new_node_set.payload.category in subcategory:
                    self._find_matches(parser_state, index, new_node_set, emergency)
                    break

    def __hash__(self) -> int:
        return self._hash

    def __eq__(self, other: 'SequenceRule') -> bool:
        if not isinstance(other, SequenceRule):
            return NotImplemented
        return self is other or (self._hash == other._hash and
                                 self._head_index == other._head_index and
                                 self._subcategory_sets == other._subcategory_sets and
                                 self._link_type_sets == other._link_type_sets)

    def __ne__(self, other: 'SequenceRule') -> bool:
        if not isinstance(other, SequenceRule):
            return NotImplemented
        return self is not other and (self._hash != other._hash or
                                      self._head_index != other._head_index or
                                      self._subcategory_sets != other._subcategory_sets or
                                      self._link_type_sets != other._link_type_sets)

    def __str__(self) -> str:
        result = str(self.category) + ':'
        for index in range(len(self._subcategory_sets)):
            result += ' '
            if index == self._head_index:
                result += '*'
            result += '|'.join(sorted(str(category) for category in self._subcategory_sets[index]))
            if index < len(self._link_type_sets):
                for link_type, left, right in sorted(self._link_type_sets[index]):
                    result += ' '
                    if left:
                        result += '<'
                    result += link_type
                    if right:
                        result += '>'
        return result

    def __repr__(self) -> str:
        return (type(self).__name__ + "(" + repr(self.category) + ", " +
                repr([sorted(subcategory_set)
                      for subcategory_set in self.subcategory_sets]) + ", " +
                repr(self._head_index) + ", " +
                repr([sorted(link_type_set) for link_type_set in self.link_type_sets]) + ")")

    @property
    def category(self) -> Category:
        """The category (and required properties) generated by this rule."""
        return self._category

    @property
    def subcategory_sets(self) -> Tuple[FrozenSet[Category], ...]:
        """The subcategories that must appear consecutively to satisfy this rule."""
        return self._subcategory_sets

    @property
    def head_index(self) -> int:
        """The index of the head element of the sequence."""
        return self._head_index

    @property
    def link_type_sets(self) -> Tuple[FrozenSet[Tuple[LinkLabel, int, int]]]:
        """The link types & directions that are used to build the language graph."""
        return self._link_type_sets

    @property
    def head_category_set(self) -> FrozenSet[Category]:
        """The category set for the head of the generated parse tree nodes."""
        return self._subcategory_sets[self._head_index]

    @property
    def all_link_types(self) -> FrozenSet[LinkLabel]:
        return self._all_link_types

    def get_link_types(self, parse_node: TraversableElement,
                       link_set_index: int) -> Iterable[Tuple[LinkLabel, bool, bool]]:
        return self._link_type_sets[link_set_index]

    def get_category(self, model: 'model.Model',
                     subtree_categories: Sequence[Category], head_index: int = None) -> Category:
        head_category = subtree_categories[self._head_index]
        if self.category.is_wildcard():
            category = categorization.Category(head_category.name,
                                               self.category.positive_properties,
                                               self.category.negative_properties)
        else:
            category = self.category
        positive = set(head_category.positive_properties)
        negative = set(head_category.negative_properties)
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
        # return parser.extend_properties(category.promote_properties(positive, negative))
        return category.promote_properties(positive, negative)

    def is_non_recursive(self, result_category: Category, head_category: Category) -> bool:
        return (len(self.subcategory_sets) > 1 or

                # TODO: Can we make this better?
                result_category not in head_category or
                (result_category.positive_properties > head_category.positive_properties) or
                (result_category.negative_properties > head_category.negative_properties))
