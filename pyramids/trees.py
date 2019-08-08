# -*- coding: utf-8 -*-

"""
Parse tree-related classes.

Parse trees in Pyramids are represented a bit unusually. They do not
represent ordinary trees, but are rather hierarchically grouped unions of
similar trees. The structure in fact alternates between nodes and node
sets, where a node holds the actual content and structure of the tree at
that level of grouping, and a node set contains multiple parse trees having
the same token span and top-level category. This structure serves to reduce
the combinatorics inherent to the parsing process, by allowing us to treat
a whole family of sub-trees as if they were a single entity.
"""
import math
import time
import weakref
from collections import deque
from functools import reduce
from typing import Sequence, Tuple, NamedTuple, Optional, Iterable, Iterator, Union

from pyramids import categorization, graphs, tokenization, traversal
from pyramids.categorization import Category
from pyramids.rules.parse_rule import ParseRule
from pyramids.tokenization import TokenSequence

__author__ = 'Aaron Hosford'
__all__ = [
    'ParseTreeNode',
    'BuildTreeNode',
    'ParseTreeNodeSet',
    'ParseTree',
    'Parse',
]


_ParsingPayload = NamedTuple('ParsingPayload', [('tokens', TokenSequence), ('rule', ParseRule),
                                                ('head_index', int), ('category', Category), ('start', int),
                                                ('end', int)])


class ParsingPayload(_ParsingPayload):

    def get_sort_key(self):
        return self.start, self.end, self.head_index, self.category, self.rule

    @property
    def span(self) -> Tuple[int, int]:
        """Return the start and end token indices of the phrase covered by this parse tree node."""
        return self.start, self.end


class ParseTreeUtils:
    # TODO: Make this into a singleton or a static class, and get rid of all the scattered locations where it gets
    #       created for a single method call.

    def make_parse_tree_node(self, tokens: TokenSequence, rule: ParseRule, head_index: int, category: Category,
                             components: Optional[Sequence['ParseTreeNodeSet']] = None) -> 'ParseTreeNode':
        if components is None:
            start = head_index
            end = start + 1
        else:
            components = tuple(components)
            if not components:
                raise ValueError("At least one component must be provided for a non-leaf node.")
            start = end = components[0].start
            for component in components:
                if end != component.start:
                    raise ValueError("Discontinuity in component coverage.")
                end = component.end
            # assert start <= head_index < end, (start, head_index, end)
        payload = ParsingPayload(tokens, rule, head_index, category, start, end)
        node = ParseTreeNode(payload, components)
        self.update_node_weighted_score(node)
        return node

    def get_head_token(self, node: 'ParseTreeNode') -> str:
        payload = node.payload
        if node.is_leaf():
            return payload.tokens[payload.start]
        else:
            return self.get_head_token(node.components[payload.head_index].best_node)

    def get_head_token_start(self, node: 'ParseTreeNode') -> int:
        payload = node.payload
        if node.is_leaf():
            return payload.start
        else:
            return self.get_head_token_start(node.components[payload.head_index].best_node)

    def to_str(self, node: 'ParseTreeNode', simplify: bool = False) -> str:
        payload = node.payload
        result = payload.category.to_str(simplify) + ':'
        if node.is_leaf():
            covered_tokens = ' '.join(payload.tokens[payload.start:payload.end])
            result += ' ' + repr(covered_tokens) + ' ' + repr(payload.span)
            if not simplify:
                result += ' [' + str(payload.rule) + ']'
        elif len(node.components) == 1 and simplify:
            result += ' ' + self.to_str(node.components[0].best_node, simplify)
        else:
            if not simplify:
                result += ' [' + str(payload.rule) + ']'
            for component in node.components:
                result += '\n    ' + self.to_str(component.best_node, simplify).replace('\n', '\n    ')
        return result

    def restrict_node(self, node: 'ParseTreeNode', categories: Iterable[Category]) \
            -> Iterator[Union['ParseTreeNode', 'ParseTreeNodeSet']]:
        payload = node.payload
        for category in categories:
            if payload.category in category:
                yield node
                break
        else:
            if node.components:
                for component in node.components:
                    yield from self.restrict_node_set(component, categories)

    def restrict_node_set(self, node_set: 'ParseTreeNodeSet', categories: Iterable[Category]) \
            -> Iterator[Union['ParseTreeNode', 'ParseTreeNodeSet']]:
        for category in categories:
            if node_set.category in category:
                yield node_set
                break
        else:
            for node in node_set.iter_unique():
                yield from self.restrict_node(node, categories)

    def update_node_weighted_score(self, node: 'ParseTreeNode', recurse: bool = True) -> None:
        payload = node.payload
        total_weighted_score, total_weight = payload.rule.calculate_weighted_score(node)
        if node.is_leaf():
            depth = 1
        else:
            depth = total_weight
            for component in node.components:
                component_depth, weighted_score, weight = component.get_score_data()

                # It's already weighted, so don't multiply it
                total_weighted_score += weighted_score

                total_weight += weight
                depth += component_depth * weight
            depth /= total_weight

        node.raw_score = (depth, total_weighted_score, total_weight)
        node.score = (total_weighted_score / math.log(1 + depth, 2), total_weight)

        if recurse and node.iter_parents():
            for parent in node.iter_parents():
                self.update_node_set_weighted_score(parent)

    def adjust_node_score(self, node: 'ParseTreeNode', target: float) -> None:
        payload = node.payload
        payload.rule.adjust_score(node, target)
        if not node.is_leaf():
            for component in node.components:
                self.adjust_node_set_score(component, target)

    def update_node_set_weighted_score(self, node_set: 'ParseTreeNodeSet', affected_node=None, recurse=True):
        assert node_set.best_node is not None
        if affected_node is None or affected_node is node_set.best_node:
            best_score = None
            best_node = None
            for node in node_set.iter_unique():
                score = node.get_weighted_score()
                if best_score is None or best_score < score:
                    best_score = score
                    best_node = node
            node_set.best_node = best_node
            if recurse and node_set.has_parents():
                for parent in node_set.iter_parents():
                    self.update_node_weighted_score(parent)
        elif node_set.best_node.get_weighted_score() < affected_node.get_weighted_score():
            node_set.best_node = affected_node
            if recurse and node_set.has_parents():
                for parent in node_set.iter_parents():
                    self.update_node_weighted_score(parent)
        assert node_set.best_node is not None

    def adjust_node_set_score(self, node_set, target):
        for node in node_set.iter_unique():
            self.adjust_node_score(node, target)


class ParseTreeNode:
    """Represents a branch or leaf node in a parse tree during parsing."""

    def __init__(self, payload: ParsingPayload, components: Optional[Tuple['ParseTreeNodeSet', ...]]):
        self._payload = payload
        self._components = components
        self._hash = (hash(self._payload) ^ hash(self._components))
        self._parents = None
        self.score = None
        self.raw_score = None

        if components:
            # This has to happen after the hash is determined, since the node will be added to the components'
            # parent sets.
            for component in self._components:
                if not isinstance(component, ParseTreeNodeSet):
                    raise TypeError(component, ParseTreeNodeSet)
                component.add_parent(self)

    def __hash__(self):
        return self._hash

    def __eq__(self, other):
        if not isinstance(other, ParseTreeNode):
            return NotImplemented
        return self is other or (self._hash == other._hash and self._payload == other._payload and
                                 self._components == other._components)

    def __ne__(self, other):
        if not isinstance(other, ParseTreeNode):
            return NotImplemented
        return not self == other

    def __le__(self, other):
        if not isinstance(other, ParseTreeNode):
            return NotImplemented
        my_sort_key = self.payload.get_sort_key()
        other_sort_key = other.payload.get_sort_key()
        if my_sort_key != other_sort_key:
            return my_sort_key < other_sort_key
        return self._components <= other._components

    def __lt__(self, other):
        if not isinstance(other, ParseTreeNode):
            return NotImplemented
        my_sort_key = self.payload.get_sort_key()
        other_sort_key = other.payload.get_sort_key()
        if my_sort_key != other_sort_key:
            return my_sort_key < other_sort_key
        return self._components < other._components

    def __ge__(self, other):
        if not isinstance(other, ParseTreeNode):
            return NotImplemented
        my_sort_key = self.payload.get_sort_key()
        other_sort_key = other.payload.get_sort_key()
        if my_sort_key != other_sort_key:
            return my_sort_key > other_sort_key
        return self._components >= other._components

    def __gt__(self, other):
        if not isinstance(other, ParseTreeNode):
            return NotImplemented
        my_sort_key = self.payload.get_sort_key()
        other_sort_key = other.payload.get_sort_key()
        if my_sort_key != other_sort_key:
            return my_sort_key > other_sort_key
        return self._components > other._components

    def __repr__(self):
        args = (self._payload, self._components)
        return '%s%r' % (type(self).__name__, args)

    # def __str__(self):
    #     return self.to_str()

    @property
    def payload(self) -> ParsingPayload:
        return self._payload

    @property
    def components(self):
        return self._components

    @property
    def coverage(self):
        # TODO: Is this a bug? It looks like it will always return 1.
        return 1 if self.is_leaf() else reduce(lambda a, b: a * b.coverage, self.components, 1)

    def iter_parents(self):
        if self._parents:
            yield from self._parents

    def is_leaf(self):
        return self._components is None

    def get_weighted_score(self):
        return self.score

    def get_score_data(self):
        return self.raw_score

    def iter_leaves(self):
        if self.is_leaf():
            yield self
        else:
            for component in self.components:
                yield from component.iter_leaves()

    def add_parent(self, parent):
        assert not parent.has_ancestor(self)
        if self._parents is None:
            self._parents = weakref.WeakSet({parent})
        else:
            self._parents.add(parent)

    def has_ancestor(self, ancestor):
        if ancestor is self:
            return True
        if not self._parents:
            return False
        return any(parent.has_ancestor(ancestor) for parent in self._parents)


# TODO: Merge ParseTreeNode and BuildTreeNode, making it possible to assign
#       a semantic net node and token index/range in the parse tree node
#       after the tree has been built. These values will be extra data that
#       isn't necessary to build the tree. During parsing, no semantic net
#       nodes will be stored in the tree node, and when the language graph
#       is built these values will be fixed. During building, no token
#       interval/index values will be stored in the tree node, and when
#       they are requested after the tree is built, they will be calculated
#       and stored.
class BuildTreeNode:
    """Represents a branch or leaf node in a parse tree during
    reconstruction."""

    def __init__(self, rule, category, head_spelling, head_index, components=None):
        self._rule = rule
        self._category = category
        self._head_node = (head_spelling, head_index)
        self._components = None if components is None else tuple(components)
        self._nodes = ((self._head_node,)
                       if components is None
                       else sum((component.nodes for component in components), ()))
        self._node_coverage = frozenset(index for spelling, index in self._nodes)
        self._tokens = tuple(spelling for spelling, index in self._nodes)
        self._hash = None

    def __repr__(self):
        if self.is_leaf():
            return (type(self).__name__ + "(" + repr(self._rule) + ", " + repr(self.category) + ", " +
                    repr(self._head_node[0]) + ", " + repr(self._head_node[1]) + ")")
        return (type(self).__name__ + "(" + repr(self._rule) + ", " + repr(self.category) + ", " +
                repr(self._head_node[0]) + ", " + repr(self._head_node[1]) + ", " + repr(self.components) + ")")

    def __str__(self):
        return self.to_str()

    def __hash__(self):
        if self._hash is None:
            self._hash = hash(self._rule) ^ hash(self._category) ^ hash(self._head_node) ^ hash(self._components)
        return self._hash

    def __eq__(self, other):
        if not isinstance(other, BuildTreeNode):
            return NotImplemented
        return (self._rule == other._rule and self._category == other._category and
                self._head_node == other._head_node and self._components == other._components)

    def __ne__(self, other):
        if not isinstance(other, BuildTreeNode):
            return NotImplemented
        return (self._rule != other._rule or self._category != other._category or self._head_node != other._head_node or
                self._components != other._components)

    def __le__(self, other):
        if not isinstance(other, BuildTreeNode):
            return NotImplemented
        if self._tokens != other._tokens:
            return self._tokens < other._tokens
        if self._rule != other._rule:
            return self._rule < other._rule
        if self._category != other._category:
            return self._category < other._category
        if self._head_node[0] != other._head_node[0]:
            return self._head_node[0] < other._head_node[0]
        return self._components <= other._components

    def __ge__(self, other):
        if not isinstance(other, BuildTreeNode):
            return NotImplemented
        return other <= self

    def __lt__(self, other):
        if not isinstance(other, BuildTreeNode):
            return NotImplemented
        if self._tokens != other._tokens:
            return self._tokens < other._tokens
        if self._rule != other._rule:
            # This will vary from one model or run to the next, but it will be consistent for a given model throughout
            # a single run. That's good enough for our purposes.
            return id(self._rule) < id(other._rule)
        if self._category != other._category:
            return self._category < other._category
        if self._head_node[0] != other._head_node[0]:
            return self._head_node[0] < other._head_node[0]
        return self._components < other._components

    def __gt__(self, other):
        if not isinstance(other, BuildTreeNode):
            return NotImplemented
        return other < self

    @property
    def rule(self):
        return self._rule

    @property
    def category(self):
        return self._category

    # @property
    # def head_node(self):
    #     return self._head_node

    @property
    def head_spelling(self):
        return self._head_node[0]

    @property
    def head_index(self):
        return self._head_node[1]

    @property
    def components(self):
        return self._components

    @property
    def nodes(self):
        return self._nodes

    @property
    def node_coverage(self):
        return self._node_coverage

    @property
    def tokens(self):
        return self._tokens

    def is_leaf(self):
        return self._components is None

    def to_str(self, simplify=False):
        result = self.category.to_str(simplify) + ':'
        if self.is_leaf():
            covered_tokens = ' '.join(self.tokens)
            result += ' ' + repr(covered_tokens)
            if not simplify:
                result += ' [' + str(self.rule) + ']'
        elif len(self.components) == 1 and simplify:
            result += ' ' + self.components[0].to_str(simplify)
        else:
            if not simplify:
                result += ' [' + str(self.rule) + ']'
            for component in self.components:
                result += '\n    ' + component.to_str(simplify).replace('\n', '\n    ')
        return result


class ParseTreeNodeSet:

    def __init__(self, nodes):  # Always has to contain at least one node.
        if isinstance(nodes, ParseTreeNode):
            nodes = [nodes]
        self._unique = set()
        self._best_node = None
        self._best_score = None
        self._best_raw_score = None
        self._parents = None

        values_set = False
        for node in nodes:
            if not values_set:
                self._start = node.payload.start
                self._end = node.payload.end
                self._category = node.payload.category
                values_set = True
        if not values_set:
            raise ValueError("ParseTreeNodeSet must contain at least one node.")

        self._hash = hash(self._start) ^ hash(self._end) ^ hash(self._category)

        # This has to happen after the hash is determined, since we add the node set to the node's parent set
        for node in nodes:
            self.add(node)

        assert self._best_node is not None

    def __repr__(self):
        return type(self).__name__ + "(" + repr(self._unique) + ")"

    def __iter__(self):
        return iter(self._unique)

    def __len__(self):
        return len(self._unique)

    def __contains__(self, node):
        return node in self._unique

    def __hash__(self):
        return self._hash

    def __eq__(self, other):
        if not isinstance(other, ParseTreeNodeSet):
            return NotImplemented
        return self is other or (self._hash == other._hash and self._start == other._start and
                                 self._end == other._end and self._category == other._category)

    def __ne__(self, other):
        if not isinstance(other, ParseTreeNodeSet):
            return NotImplemented
        return not self == other

    def __le__(self, other):
        if not isinstance(other, ParseTreeNodeSet):
            return NotImplemented
        if self._start != other._start:
            return self._start < other._start
        if self._end != other._end:
            return self._end < other._end
        return self._category <= other._category

    def __ge__(self, other):
        if not isinstance(other, ParseTreeNodeSet):
            return NotImplemented
        return other <= self

    def __lt__(self, other):
        if not isinstance(other, ParseTreeNodeSet):
            return NotImplemented
        return not (self >= other)

    def __gt__(self, other):
        if not isinstance(other, ParseTreeNodeSet):
            return NotImplemented
        return not (self <= other)

    @property
    def best_node(self) -> ParseTreeNode:
        return self._best_node

    @best_node.setter
    def best_node(self, node: ParseTreeNode) -> None:
        assert node in self._unique
        self._best_node = node

    @property
    def category(self):
        return self._category

    @property
    def start(self):
        return self._start

    @property
    def end(self):
        return self._end

    @property
    def span(self):
        return self._start, self._end

    @property
    def count(self):
        return len(self._unique)

    @property
    def coverage(self):
        return sum([node.coverage for node in self._unique])

    @property
    def head_token(self):
        assert self._best_node is not None, self._unique
        return self._best_node.head_token

    def iter_unique(self):
        return iter(self._unique)

    def has_parents(self):
        return bool(self._parents)

    def iter_parents(self):
        if self._parents:
            yield from self._parents

    def is_compatible(self, node_or_set):
        return (node_or_set.start == self._start and node_or_set.end == self._end and
                node_or_set.category == self._category)

    def add(self, node):
        if not isinstance(node, ParseTreeNode):
            raise TypeError(node, ParseTreeNode)
        if not self.is_compatible(node.payload):
            raise ValueError("Node is not compatible.")
        if node in self._unique:
            return
        self._unique.add(node)
        node.add_parent(self)
        if self._best_node is None:
            self._best_node = node

    def get_weighted_score(self):
        return self._best_node.get_weighted_score() if self._best_node else None

    def get_score_data(self):
        return self._best_node.get_score_data() if self._best_node else None

    def iter_leaves(self):
        for node in self._unique:
            yield from node.iter_leaves()

    def add_parent(self, parent):
        assert not parent.has_ancestor(self)
        if self._parents is None:
            self._parents = weakref.WeakSet({parent})
        else:
            self._parents.add(parent)

    def has_ancestor(self, ancestor):
        if ancestor is self:
            return True
        if not self._parents:
            return False
        return any(parent.has_ancestor(ancestor) for parent in self._parents)


class ParseTree:
    """Represents a complete parse tree."""

    def __init__(self, tokens, root):
        if not isinstance(tokens, tokenization.TokenSequence):
            raise TypeError(tokens, tokenization.TokenSequence)
        self._tokens = tokens
        if not isinstance(root, ParseTreeNodeSet):
            raise TypeError(root, ParseTreeNodeSet)
        self._root = root

    def __repr__(self):
        return type(self).__name__ + "(" + repr(self._tokens) + ", " + repr(self._root) + ")"

    def __str__(self):
        return self.to_str()

    def __hash__(self):
        return hash(self._tokens) ^ hash(self._root)

    def __eq__(self, other):
        if not isinstance(other, ParseTree):
            return NotImplemented
        return self is other or (self._tokens == other._tokens and self._root == other._root)

    def __ne__(self, other):
        if not isinstance(other, ParseTree):
            return NotImplemented
        return not (self == other)

    def __le__(self, other):
        if not isinstance(other, ParseTree):
            return NotImplemented
        if self is other:
            return True
        if self._tokens != other._tokens:
            return self._tokens < other._tokens
        return self._root <= other._root

    def __lt__(self, other):
        if not isinstance(other, ParseTree):
            return NotImplemented
        if self is other:
            return False
        if self._tokens != other._tokens:
            return self._tokens < other._tokens
        return self._root < other._root

    def __ge__(self, other):
        if not isinstance(other, ParseTree):
            return NotImplemented
        return other <= self

    def __gt__(self, other):
        if not isinstance(other, ParseTree):
            return NotImplemented
        return other < self

    @property
    def tokens(self):
        return self._tokens

    @property
    def root(self):
        return self._root

    @property
    def category(self):
        return self._root.category

    @property
    def start(self):
        return self._root.start

    @property
    def end(self):
        return self._root.end

    @property
    def span(self):
        return self._root.span

    @property
    def coverage(self):
        return self._root.coverage

    def to_str(self, simplify=True):
        return ParseTreeUtils().to_str(self._root.best_node, simplify)

    def restrict(self, categories):
        results = set()
        for node in ParseTreeUtils().restrict_node_set(self._root, categories):
            results.add(type(self)(self._tokens, node))
        return results

    def is_ambiguous_with(self, other):
        return self.start <= other.start < self.end or other.start <= self.start < other.end

    def get_weighted_score(self):
        return self.root.get_weighted_score()

    def adjust_score(self, target):
        ParseTreeUtils().adjust_node_set_score(self.root, target)

        queue = deque(self.root.iter_leaves())
        visited = set()
        while queue:
            item = queue.popleft()
            if item in visited:
                continue
            if isinstance(item, ParseTreeNode):
                ParseTreeUtils().update_node_weighted_score(item, recurse=False)
            else:
                ParseTreeUtils().update_node_set_weighted_score(item, recurse=False)
            visited.add(item)
            queue.extend(item.iter_parents())


class Parse:
    # TODO: Make sure the docstrings are up to date.
    """A finished parse. Stores the state of the parse during Parser's
    operation as a separate, first class object. Because a sentence can
    potentially be parsed in many different ways, also represents the
    collection of ParseTrees which apply to the input after parsing is
    complete."""

    def __init__(self, tokens, parse_trees):
        self._tokens = tokens
        self._parse_trees = frozenset(parse_trees)
        self._hash = None
        self._score = None
        self.update_weighted_score()

    def __hash__(self):
        if self._hash is None:
            self._hash = hash(self._tokens) ^ hash(self._parse_trees)
        return self._hash

    def __eq__(self, other):
        if not isinstance(other, Parse):
            return NotImplemented
        return self is other or (self._tokens == other._tokens and self._parse_trees == other._parse_trees)

    def __ne__(self, other):
        if not isinstance(other, Parse):
            return NotImplemented
        return not (self == other)

    def __str__(self):
        return self.to_str()

    def __repr__(self):
        return type(self).__name__ + "(" + repr(self._tokens) + ", " + repr(self._parse_trees) + ")"

    @property
    def tokens(self):
        return self._tokens

    @property
    def parse_trees(self):
        return self._parse_trees

    @property
    def coverage(self):
        return sum(tree.coverage for tree in self._parse_trees)

    def to_str(self, simplify=True):
        return '\n'.join(tree.to_str(simplify) for tree in sorted(self._parse_trees))

    def get_rank(self):
        score, weight = self.get_weighted_score()
        return self.total_gap_size(), len(self.parse_trees), -score, -weight

    def get_weighted_score(self):
        return self._score

    def adjust_score(self, target):
        for tree in self._parse_trees:
            tree.adjust_score(target)
        self.update_weighted_score()

    def update_weighted_score(self):
        total_weighted_score = 0.0
        total_weight = 0.0
        for tree in self._parse_trees:
            weighted_score, weight = tree.get_weighted_score()
            total_weighted_score += weighted_score
            total_weight += weight
        self._score = ((total_weighted_score / total_weight if total_weight else 0.0), total_weight)

    def restrict(self, categories):
        if isinstance(categories, categorization.Category):
            categories = [categories]
        trees = []
        for tree in self._parse_trees:
            for restricted in tree.restrict(categories):
                trees.append(restricted)
        return type(self)(self._tokens, trees)

    def iter_ambiguities(self):
        covered = set()
        for tree1 in self._parse_trees:
            covered.add(tree1)
            for tree2 in self._parse_trees:
                if tree2 in covered:
                    continue
                if tree1.is_ambiguous_with(tree2):
                    yield tree1, tree2

    def is_ambiguous(self):
        for _ in self.iter_ambiguities():
            return True
        return False

    def disambiguate(self):
        if len(self._parse_trees) <= 1:
            return self
        scores = {}
        for tree in self._parse_trees:
            scores[tree] = tree.get_weighted_score()
        trees = []
        for tree in sorted(scores, key=scores.get, reverse=True):
            for other_tree in trees:
                if tree.is_ambiguous_with(other_tree):
                    break
            else:
                trees.append(tree)
        return type(self)(self._tokens, trees)

    def _iter_disambiguation_tails(self, index, max_index, gaps, pieces,
                                   timeout):
        if timeout is not None and time.time() >= timeout:
            raise TimeoutError()
        if index >= len(self._tokens):
            if not gaps and not pieces:
                yield []
        elif index < max_index and pieces > 0:
            nearest_end = None
            for tree in self._parse_trees:
                if tree.start == index:
                    if nearest_end is None or tree.end < nearest_end:
                        nearest_end = tree.end
                    for tail in self._iter_disambiguation_tails(tree.end, max_index, gaps, pieces - 1, timeout):
                        yield [tree] + tail
            if nearest_end is None:
                if gaps > 0:
                    for tail in self._iter_disambiguation_tails(index + 1, max_index, gaps - 1, pieces, timeout):
                        yield tail
            else:
                for overlap_index in range(index + 1, nearest_end):
                    for tail in self._iter_disambiguation_tails(overlap_index, nearest_end, gaps, pieces, timeout):
                        yield tail

    # TODO: This fails if we have a partial parse in the *middle* of the
    #       string, surrounded by gaps.
    def iter_disambiguations(self, gaps=None, pieces=None, timeout=None):
        if gaps is None:
            gaps_seq = range(self.total_gap_size(), len(self._tokens) + 1)
        else:
            gaps_seq = [gaps] if gaps >= self.total_gap_size() else []
        if pieces is None:
            pieces_seq = range(self.min_disambiguation_size(), len(self._tokens) + 1)
        else:
            pieces_seq = [pieces] if pieces >= self.min_disambiguation_size() else []
        try:
            success = False
            for gaps in gaps_seq:
                for pieces in pieces_seq:
                    for tail in self._iter_disambiguation_tails(0, len(self._tokens), gaps, pieces, timeout):
                        yield type(self)(self._tokens, tail)
                        success = True
                    if success:
                        break
                if success:
                    break
        except TimeoutError:
            # Don't do anything; we just want to exit early if this
            # happens.
            pass

    def get_disambiguations(self, gaps=None, pieces=None, timeout=None):
        return set(self.iter_disambiguations(gaps, pieces, timeout))

    def get_ranked_disambiguations(self, gaps=None, pieces=None,
                                   timeout=None):
        ranks = {}
        for disambiguation in self.get_disambiguations(gaps, pieces, timeout):
            ranks[disambiguation] = disambiguation.get_rank()
        return ranks

    def get_sorted_disambiguations(self, gaps=None, pieces=None, timeout=None):
        ranks = self.get_ranked_disambiguations(gaps, pieces, timeout)
        return [(disambiguation, ranks[disambiguation]) for disambiguation in sorted(ranks, key=ranks.get)]

    def iter_gaps(self):
        gap_start = None
        index = -1
        for index in range(len(self._tokens)):
            for tree in self._parse_trees:
                if tree.start <= index < tree.end:
                    if gap_start is not None:
                        yield gap_start, index
                        gap_start = None
                    break
            else:
                if gap_start is None:
                    gap_start = index
        if gap_start is not None:
            yield gap_start, index + 1

    def has_gaps(self):
        for _ in self.iter_gaps():
            return True
        return False

    def total_gap_size(self):
        size = 0
        for start, end in self.iter_gaps():
            size += end - start
        return size

    def max_tree_width(self):
        max_width = 0
        for tree in self._parse_trees:
            width = tree.end - tree.start
            if max_width is None or width > max_width:
                max_width = width
        return max_width

    def min_disambiguation_size(self):
        max_width = self.max_tree_width()
        if not max_width:
            return 0
        return int(math.floor(len(self._tokens) / float(max_width)))

    def get_parse_graphs(self):
        assert not self.is_ambiguous()
        traverser = traversal.DepthFirstTraverser()
        graph_builder = graphs.ParseGraphBuilder()
        traverser.traverse(self, graph_builder)
        return graph_builder.get_graphs()
