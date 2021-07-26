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
from abc import ABCMeta, abstractmethod
from collections import deque
from functools import reduce
from typing import Sequence, Tuple, NamedTuple, Optional, Iterable, Iterator, Union, Set, \
    FrozenSet, TypeVar, Generic

from pyramids import categorization, graphs, tokenization, traversal
from pyramids.categorization import Category
from pyramids.rules.parse_rule import ParseRule
from pyramids.tokenization import TokenSequence

__author__ = 'Aaron Hosford'
__all__ = [
    'TreeNode',
    'BuildTreeNode',
    'TreeNodeSet',
    'ParseTree',
    'Parse',
]


class PayloadInterface(metaclass=ABCMeta):
    rule: ParseRule
    tokens: Union[TokenSequence, Tuple[str, ...]]
    category: Category
    head_spelling: str

    @abstractmethod
    def is_compatible_with(self, other: 'PayloadInterface') -> bool:
        """Return whether two nodes holding this and the other payload are compatible to share a
        single node set."""
        raise NotImplementedError()


PayloadType = TypeVar('PayloadType', bound=PayloadInterface)


_ParsingPayload = NamedTuple('ParsingPayload', [('tokens', TokenSequence),
                                                ('rule', ParseRule),
                                                ('head_component_index', Optional[int]),
                                                ('category', Category),
                                                ('head_spelling', str),
                                                ('token_start_index', int),
                                                ('token_end_index', int)])


class ParsingPayload(_ParsingPayload, PayloadInterface):
    """Payload used for tree nodes at parse time."""

    def is_compatible_with(self, other: 'PayloadInterface'):
        """Return whether two nodes holding this and the other payload are compatible to share a
        single node set."""
        if not isinstance(other, ParsingPayload):
            return False
        return (other.token_start_index == self.token_start_index and
                other.token_end_index == self.token_end_index and
                other.category == self.category)

    @property
    def token_index_span(self) -> Tuple[int, int]:
        """Get the start and end token indices of the phrase covered by this parse tree node."""
        return self.token_start_index, self.token_end_index


_GenerationPayload = NamedTuple('GenerationPayload', [('rule', ParseRule),
                                                      ('category', Category),
                                                      ('head_spelling', str),
                                                      ('head_graph_index', int),
                                                      ('covered_graph_indices', FrozenSet[int])])


class GenerationPayload(_GenerationPayload, PayloadInterface):
    """Payload used for tree nodes at generation time."""

    def is_compatible_with(self, other: PayloadInterface):
        """Return whether two nodes holding this and the other payload are compatible to share a
        single node set."""
        if not isinstance(other, GenerationPayload):
            return False
        return (self.covered_graph_indices == other.covered_graph_indices and
                self.category == other.category)


class TreeUtils:
    """Utility methods for operating on trees at any time."""

    @staticmethod
    def restrict(node: 'TreeNodeInterface',
                 categories: Iterable[Category]) -> Iterator['TreeNodeInterface']:
        """Restrict a tree node to a particular category at parse time."""
        payload = node.payload
        for category in categories:
            if payload.category in category:
                yield node
                break
        else:
            if node.components:
                for component in node.components:
                    yield from TreeUtils.restrict(component, categories)

    @staticmethod
    def update_weighted_score(node: 'TreeNodeInterface', affected_child: 'TreeNodeInterface' = None,
                              recurse: bool = True) -> None:
        """
        Update the parse-time score of the tree node.

        If recurse is True (default) then propagate the score upward through all trees containing
        this node.
        """
        if node.recompute_weighted_score(affected_child) and recurse:
            for parent in node.iter_parents():
                TreeUtils.update_weighted_score(parent, node)

    @staticmethod
    def adjust_score(node: 'TreeNodeInterface', target: float) -> None:
        """Adjust a parse-time tree node's score towards the target."""
        payload = node.payload
        payload.rule.adjust_score(node, target)
        if not node.is_leaf():
            for component in node.components:
                TreeUtils.adjust_score(component, target)


class ParseTreeUtils:
    """Utility methods for operating on trees at parse time."""

    def __init__(self):
        raise NotImplementedError("This class is not instantiable.")

    @staticmethod
    def make_leaf_parse_tree_node(tokens: TokenSequence, rule: ParseRule, token_index: int,
                                  category: Category) -> 'TreeNode':
        """Create a leaf tree node with a parse-time payload."""
        start = token_index
        head_spelling = tokens[start]
        end = start + 1
        payload = ParsingPayload(tokens, rule, None, category, head_spelling, start, end)
        node = TreeNode(payload, None)
        TreeUtils.update_weighted_score(node)
        return node

    @staticmethod
    def make_branch_parse_tree_node(tokens: TokenSequence, rule: ParseRule, head_index: int,
                                    category: Category,
                                    components: Sequence['TreeNodeInterface[ParsingPayload]']) \
            -> 'TreeNode':
        """Create a tree node with a parse-time payload."""
        components = tuple(components)
        if not components:
            raise ValueError("At least one component must be provided for a non-leaf node.")
        start = end = components[0].payload.token_start_index
        for component in components:
            if end != component.payload.token_start_index:
                raise ValueError("Discontinuity in component coverage.")
            end = component.payload.token_end_index
        head_spelling = components[head_index].payload.head_spelling
        payload = ParsingPayload(tokens, rule, head_index, category, head_spelling, start, end)
        node = TreeNode(payload, components)
        TreeUtils.update_weighted_score(node)
        return node

    @staticmethod
    def get_head_token_start(node: 'TreeNodeInterface[ParsingPayload]') -> int:
        """Return the starting index of the head token of the phrase for this tree node."""
        payload = node.payload
        if node.is_leaf():
            return payload.token_start_index
        return ParseTreeUtils.get_head_token_start(
            node.components[payload.head_component_index].best_node
        )

    @staticmethod
    def to_str(node: 'TreeNodeInterface[ParsingPayload]', simplify: bool = False) -> str:
        """Generate a string representation of a parse-time tree node."""
        payload = node.payload
        result = payload.category.to_str(simplify) + ':'
        if node.is_leaf():
            covered_tokens = ' '.join(
                payload.tokens[payload.token_start_index:payload.token_end_index]
            )
            result += ' ' + repr(covered_tokens) + ' ' + repr(payload.token_index_span)
            if not simplify:
                result += ' [' + str(payload.rule) + ']'
        elif len(node.components) == 1 and simplify:
            result += ' ' + ParseTreeUtils.to_str(node.components[0], simplify)
        else:
            if not simplify:
                result += ' [' + str(payload.rule) + ']'
            for component in node.components:
                result += '\n    ' + ParseTreeUtils.to_str(component, simplify).replace('\n',
                                                                                        '\n    ')
        return result


class TreeNodeInterface(Generic[PayloadType], metaclass=ABCMeta):
    """Abstract interface for various types of interoperable tree nodes."""

    @property
    @abstractmethod
    def payload(self) -> PayloadType:
        """Get the payload associated with this tree node."""
        raise NotImplementedError()

    @property
    @abstractmethod
    def components(self) -> Tuple['TreeNodeInterface[PayloadType]', ...]:
        """Get the children of this tree node."""
        raise NotImplementedError()

    @property
    @abstractmethod
    def coverage(self) -> int:
        """Compute the number of unique combinatoric variations of the subtree rooted at this
        node."""
        raise NotImplementedError()

    @abstractmethod
    def iter_parents(self) -> Iterator['TreeNodeInterface[PayloadType]']:
        """Iterate over the parents of this node."""
        raise NotImplementedError()

    @abstractmethod
    def is_leaf(self) -> bool:
        """Return a boolean indicating whether this node is a leaf."""
        raise NotImplementedError()

    @abstractmethod
    def iter_leaves(self) -> Iterator['TreeNodeInterface[PayloadType]']:
        """Iterate over the leaves of the subtree rooted at this node from left to right."""
        raise NotImplementedError()

    @abstractmethod
    def add_parent(self, parent: 'TreeNodeInterface[PayloadType]') -> None:
        """Add a weak reference to a parent of this node."""
        raise NotImplementedError()

    @abstractmethod
    def has_ancestor(self, ancestor: 'TreeNodeInterface[PayloadType]') -> bool:
        """Return a boolean indicating whether the subtree rooted at the given ancestor contains
        this node."""
        raise NotImplementedError()

    @property
    @abstractmethod
    def score(self) -> Tuple[float, float]:
        raise NotImplementedError()

    @property
    @abstractmethod
    def raw_score(self) -> Tuple[int, float, float]:
        raise NotImplementedError()

    @abstractmethod
    def recompute_weighted_score(self,
                                 affected_child: 'TreeNodeInterface[PayloadType]' = None) -> bool:
        """Recompute the score of the tree node."""
        raise NotImplementedError()


class TreeNode(TreeNodeInterface[PayloadType]):
    """Represents a branch or leaf node in a parse tree during parsing."""

    def __init__(self, payload: PayloadInterface,
                 components: Optional[Tuple[TreeNodeInterface[PayloadType], ...]]):
        self._payload = payload
        self._components = components
        self._hash = (hash(self._payload) * 5) ^ (hash(self._components) * 2)
        self._parents = None
        self._score = None  # type: Optional[Tuple[float, float]]
        self._raw_score = None  # type: Optional[Tuple[int, float, float]]

        if components:
            # This has to happen after the hash is determined, since the node will be added to the
            # components' parent sets.
            for component in components:
                component.add_parent(self)

    def __hash__(self):
        return self._hash

    def __eq__(self, other):
        if not isinstance(other, TreeNode):
            return NotImplemented
        return self is other or (self._hash == other._hash and self._payload == other._payload and
                                 self._components == other._components)

    def __ne__(self, other):
        if not isinstance(other, TreeNode):
            return NotImplemented
        return not self == other

    def __repr__(self):
        args = (self._payload, self._components)
        return '%s%r' % (type(self).__name__, args)

    @property
    def payload(self) -> PayloadType:
        """Get the payload for this tree node."""
        return self._payload

    @property
    def components(self) -> Tuple[TreeNodeInterface[PayloadType], ...]:
        """Get the children of this tree node."""
        return self._components or ()

    @property
    def coverage(self) -> int:
        """Compute the number of unique combinatoric variations of the subtree rooted at this
        node."""
        return 1 if self.is_leaf() else reduce(lambda a, b: a * b.coverage, self.components, 1)

    @property
    def score(self) -> Tuple[float, float]:
        assert self._score is not None
        return self._score

    @property
    def raw_score(self) -> Tuple[int, float, float]:
        assert self._raw_score is not None
        return self._raw_score

    def iter_parents(self) -> Iterator[TreeNodeInterface[PayloadType]]:
        """Iterate over the parents of this node."""
        if self._parents:
            yield from self._parents

    def is_leaf(self) -> bool:
        """Return a boolean indicating whether this node is a leaf."""
        return self._components is None

    def iter_leaves(self) -> Iterator[TreeNodeInterface[PayloadType]]:
        """Iterate over the leaves of the subtree rooted at this node from left to right."""
        if self.is_leaf():
            yield self
        else:
            for component in self.components:
                yield from component.iter_leaves()

    def add_parent(self, parent: TreeNodeInterface[PayloadType]) -> None:
        """Add a weak reference to a parent of this node."""
        assert not parent.has_ancestor(self)
        if self._parents is None:
            self._parents = weakref.WeakSet({parent})
        else:
            self._parents.add(parent)

    def has_ancestor(self, ancestor: TreeNodeInterface[PayloadType]) -> bool:
        """Return a boolean indicating whether the subtree rooted at the given ancestor contains
        this node."""
        if ancestor is self:
            return True
        if not self._parents:
            return False
        return any(parent.has_ancestor(ancestor) for parent in self._parents)

    def recompute_weighted_score(self,
                                 affected_child: TreeNodeInterface[PayloadType] = None) -> bool:
        """
        Update the parse-time score of the tree node.

        If recurse is True (default) then propagate the score upward through all trees containing
        this node.
        """
        # TODO: Take advantage of the affected_child argument.
        total_weighted_score, total_weight = self.payload.rule.calculate_weighted_score(self)
        if self.is_leaf():
            depth = 1.0
        else:
            depth = total_weight
            for component in self.components:
                raw_score = component.raw_score
                assert raw_score is not None
                component_depth, weighted_score, weight = raw_score

                # It's already weighted, so don't multiply it
                total_weighted_score += weighted_score

                total_weight += weight
                depth += component_depth * weight
            depth /= total_weight

        self._raw_score = (depth, total_weighted_score, total_weight)
        self._score = (total_weighted_score / math.log(1 + depth, 2), total_weight)

        return True


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
    """Represents a branch or leaf node in a parse tree during reconstruction."""

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
            return (type(self).__name__ + "(" + repr(self._rule) + ", " +
                    repr(self.category) + ", " + repr(self._head_node[0]) + ", " +
                    repr(self._head_node[1]) + ")")
        return (type(self).__name__ + "(" + repr(self._rule) + ", " + repr(self.category) + ", " +
                repr(self._head_node[0]) + ", " + repr(self._head_node[1]) + ", " +
                repr(self.components) + ")")

    def __str__(self):
        return self.to_str()

    def __hash__(self):
        if self._hash is None:
            self._hash = (hash(self._rule) ^ hash(self._category) ^ hash(self._head_node) ^
                          hash(self._components))
        return self._hash

    def __eq__(self, other):
        if not isinstance(other, BuildTreeNode):
            return NotImplemented
        return (self._rule == other._rule and self._category == other._category and
                self._head_node == other._head_node and self._components == other._components)

    def __ne__(self, other):
        if not isinstance(other, BuildTreeNode):
            return NotImplemented
        return (self._rule != other._rule or self._category != other._category or
                self._head_node != other._head_node or self._components != other._components)

    @property
    def rule(self):
        return self._rule

    @property
    def category(self):
        return self._category

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


class TreeNodeSet(TreeNodeInterface[PayloadType]):
    """A set of tree nodes that cover the same phrase with the same category."""

    def __init__(self, nodes: Union[TreeNodeInterface[PayloadType],
                                    Iterable[TreeNodeInterface[PayloadType]]]):
        self._nodes = set()  # type: Set[TreeNodeInterface[PayloadType]]
        self._parents = weakref.WeakSet()

        if isinstance(nodes, TreeNodeInterface):
            first_node = nodes
            self._best_node = first_node
            self.add(first_node)
        else:
            node_iterator = iter(nodes)
            try:
                first_node = next(node_iterator)
            except StopIteration:
                raise ValueError("ParseTreeNodeSet must contain at least one node.")
            self._best_node = first_node  # type: TreeNodeInterface

            self.add(first_node)
            for node in node_iterator:
                self.add(node)

    def __repr__(self):
        return type(self).__name__ + "(" + repr(self._nodes) + ")"

    def __iter__(self):
        return iter(self._nodes)

    def __len__(self):
        return len(self._nodes)

    def __contains__(self, node):
        return node in self._nodes

    @property
    def best_node(self) -> TreeNodeInterface[PayloadType]:
        """Get the node in this node set with the highest score."""
        return self._best_node

    @best_node.setter
    def best_node(self, node: TreeNodeInterface[PayloadType]) -> None:
        """Get the node in this node set with the highest score."""
        assert node in self._nodes
        self._best_node = node

    @property
    def payload(self) -> PayloadType:
        """Get the payload of the node in this set with the highest score."""
        return self._best_node.payload

    @property
    def coverage(self):
        """Compute the number of unique combinatoric variations of the subtree rooted at this node
        set."""
        return sum(node.coverage for node in self._nodes)

    @property
    def components(self) -> Tuple[TreeNodeInterface[PayloadType], ...]:
        """Get the children of this tree node."""
        return self._best_node.components

    @property
    def score(self) -> Tuple[float, float]:
        return self._best_node.score

    @property
    def raw_score(self) -> Tuple[int, float, float]:
        return self._best_node.raw_score

    def recompute_weighted_score(self,
                                 affected_child: 'TreeNodeInterface[PayloadType]' = None) -> bool:
        """
        Update the parse-time score of the tree node set.

        If an affected_node is provided, the update is performed in a more efficient way that
        assumes that the affected_node is the only member of the node set whose score changed.

        If recurse is True (default) then propagate the score upward through all trees containing
        this node set.
        """
        if affected_child is None or affected_child is self._best_node:
            self._best_node = max(self._nodes, key=lambda n: n.score)
            return True
        elif self._best_node.score < affected_child.score:
            self._best_node = affected_child
            return True
        return False

    def is_leaf(self):
        """Return a boolean indicating whether this node is a leaf."""
        return self._best_node.is_leaf()

    def has_parents(self) -> bool:
        """Return a boolean indicating whether this node set has any parents."""
        return bool(self._parents)

    def iter_parents(self) -> Iterator[TreeNodeInterface[PayloadType]]:
        """Iterate over the parents of this node set."""
        if self._parents:
            yield from self._parents

    def add(self, node: TreeNodeInterface[PayloadType]) -> None:
        """Add a new node to this node set."""
        if isinstance(node, TreeNodeSet):
            for member in node:
                self.add(member)
        else:
            if (self._best_node is not None and
                    not self._best_node.payload.is_compatible_with(node.payload)):
                raise ValueError("Node is not compatible.")
            self._nodes.add(node)
            node.add_parent(self)
            if self._best_node is None:
                self._best_node = node

    def iter_leaves(self):
        """Iterate over the leaves of the subtree rooted at this node from left to right."""
        for node in self._nodes:
            yield from node.iter_leaves()

    def add_parent(self, parent):
        """Add a weak reference to a parent of this node."""
        assert not parent.has_ancestor(self)
        self._parents.add(parent)

    def has_ancestor(self, ancestor: TreeNodeInterface[PayloadType]):
        """Return a boolean indicating whether the subtree rooted at the given ancestor contains
        this node."""
        if ancestor is self:
            return True
        if not self._parents:
            return False
        return any(parent.has_ancestor(ancestor) for parent in self._parents)


class ParseTree:
    """Represents a complete parse tree."""

    def __init__(self, tokens: tokenization.TokenSequence, root: TreeNodeSet[ParsingPayload]):
        self._tokens = tokens
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

    @property
    def tokens(self) -> tokenization.TokenSequence:
        return self._tokens

    @property
    def root(self) -> TreeNodeSet:
        return self._root

    @property
    def category(self) -> Category:
        return self._root.best_node.payload.category

    @property
    def token_start_index(self) -> int:
        return self._root.best_node.payload.token_start_index

    @property
    def token_end_index(self) -> int:
        return self._root.best_node.payload.token_end_index

    @property
    def coverage(self) -> int:
        return self._root.coverage

    def to_str(self, simplify=True) -> str:
        return ParseTreeUtils.to_str(self._root.best_node, simplify)

    def restrict(self, categories):
        results = set()
        for node in TreeUtils.restrict(self._root, categories):
            results.add(type(self)(self._tokens, node))
        return results

    def is_ambiguous_with(self, other):
        return (self.token_start_index <= other.token_start_index < self.token_end_index or
                other.token_start_index <= self.token_start_index < other.token_end_index)

    def get_weighted_score(self):
        return self.root.score

    def adjust_score(self, target):
        TreeUtils.adjust_score(self.root, target)

        queue = deque(self.root.iter_leaves())
        visited = set()
        while queue:
            item = queue.popleft()
            if item in visited:
                continue
            TreeUtils.update_weighted_score(item, recurse=False)
            visited.add(item)
            queue.extend(item.iter_parents())


class Parse:
    # TODO: Should this be renamed to Forest?
    # TODO: Make sure the docstrings are up to date.
    """A finished parse. Stores the state of the parse during Parser's
    operation as a separate, first class object. Because a sentence can
    potentially be parsed in many different ways, also represents the
    collection of ParseTrees which apply to the input after parsing is
    complete."""

    def __init__(self, tokens, parse_trees: Iterable[ParseTree]):
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
        return self is other or (self._tokens == other._tokens and
                                 self._parse_trees == other._parse_trees)

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
        """Compute the number of unique combinatoric variations of the trees in this forest."""
        return reduce(lambda a, b: a * b, (tree.coverage for tree in self._parse_trees), 1)

    def to_str(self, simplify=True):
        return '\n'.join(tree.to_str(simplify) for tree in self._parse_trees)

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
                if tree.token_start_index == index:
                    if nearest_end is None or tree.token_end_index < nearest_end:
                        nearest_end = tree.token_end_index
                    for tail in self._iter_disambiguation_tails(tree.token_end_index, max_index,
                                                                gaps, pieces - 1, timeout):
                        yield [tree] + tail
            if nearest_end is None:
                if gaps > 0:
                    for tail in self._iter_disambiguation_tails(index + 1, max_index, gaps - 1,
                                                                pieces, timeout):
                        yield tail
            else:
                for overlap_index in range(index + 1, nearest_end):
                    for tail in self._iter_disambiguation_tails(overlap_index, nearest_end, gaps,
                                                                pieces, timeout):
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
                    for tail in self._iter_disambiguation_tails(0, len(self._tokens), gaps, pieces,
                                                                timeout):
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

    def get_ranked_disambiguations(self, gaps=None, pieces=None, timeout=None):
        ranks = {}
        for disambiguation in self.get_disambiguations(gaps, pieces, timeout):
            ranks[disambiguation] = disambiguation.get_rank()
        return ranks

    def get_sorted_disambiguations(self, gaps=None, pieces=None, timeout=None):
        ranks = self.get_ranked_disambiguations(gaps, pieces, timeout)
        return [(disambiguation, ranks[disambiguation])
                for disambiguation in sorted(ranks, key=ranks.get)]

    def iter_gaps(self):
        gap_start = None
        index = -1
        for index in range(len(self._tokens)):
            for tree in self._parse_trees:
                if tree.token_start_index <= index < tree.token_end_index:
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
            width = tree.token_end_index - tree.token_start_index
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
