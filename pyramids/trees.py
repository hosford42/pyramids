# TODO: Separate data from algorithms.
"""
pyramids.trees: Parse tree-related classes.

Parse trees in Pyramids are represented a bit unusually. They do not
represent ordinary trees, but are rather hierarchically grouped unions of
similar trees. The structure in fact alternates between nodes and node
sets, where a node holds the actual content and structure of the tree at
that level of grouping, and a node set contains multiple parse trees having
the same token span and top-level category. This structure serves to reduce
the combinatorics inherent to the parsing process, by allowing us to treat
a whole family of sub-trees as if they were a single entity.
"""
from collections import deque
from functools import reduce
import math
import time

from pyramids import categorization, exceptions, graphs, tokenization
from pyramids.categorization import Property
from pyramids.graphs import ParseGraphBuilder

__author__ = 'Aaron Hosford'
__all__ = [
    'ParseTreeNode',
    'BuildTreeNode',
    'ParseTreeNodeSet',
    'ParseTree',
    'Parse',
]


class ParseTreeNode:
    """Represents a branch or leaf node in a parse tree during parsing."""

    def __init__(self, tokens, rule, head_index, category, index_or_components):
        # assert isinstance(rule, rules.ParseRule)
        assert isinstance(category, categorization.Category)

        self._tokens = tokens
        self._head_index = int(head_index)
        self._rule = rule

        self._parents = None

        if isinstance(index_or_components, int):
            self._start = index_or_components
            self._end = self._start + 1
            self._components = None
        else:
            self._components = tuple(index_or_components)
            if not self._components:
                raise ValueError("At least one component must be provided for a non-leaf node.")
            for component in self._components:
                if not isinstance(component, ParseTreeNodeSet):
                    raise TypeError(component, ParseTreeNodeSet)
                component.add_parent(self)
            self._start = self._end = self._components[0].start
            for component in self._components:
                if self._end != component.start:
                    raise ValueError("Discontinuity in component coverage.")
                self._end = component.end
        self._category = category
        self._hash = (hash(self._rule) ^ hash(self._head_index) ^ hash(self._category) ^ hash(self._start) ^
                      hash(self._end) ^ hash(self._components))
        self._score = None
        self._raw_score = None
        self.update_weighted_score()

    def __hash__(self):
        return self._hash

    def __eq__(self, other):
        if not isinstance(other, ParseTreeNode):
            return NotImplemented
        return self is other or (self._hash == other._hash and self._start == other._start and
                                 self._end == other._end and self._head_index == other._head_index and
                                 self._category == other._category and self._rule == other._rule and
                                 self._components == other._components)

    def __ne__(self, other):
        if not isinstance(other, ParseTreeNode):
            return NotImplemented
        return not (self == other)

    def __le__(self, other):
        if not isinstance(other, ParseTreeNode):
            return NotImplemented
        if self._start != other._start:
            return self._start < other._start
        if self._end != other._end:
            return self._end < other._end
        if self._head_index != other._head_index:
            return self._head_index < other._head_index
        if self._category != other._category:
            return self._category < other._category
        if self._rule != other._rule:
            return self._rule < other._rule
        return self._components <= other._components

    def __lt__(self, other):
        if not isinstance(other, ParseTreeNode):
            return NotImplemented
        if self._start != other._start:
            return self._start < other._start
        if self._end != other._end:
            return self._end < other._end
        if self._head_index != other._head_index:
            return self._head_index < other._head_index
        if self._category != other._category:
            return self._category < other._category
        if self._rule != other._rule:
            return self._rule < other._rule
        return self._components < other._components

    def __ge__(self, other):
        if not isinstance(other, ParseTreeNode):
            return NotImplemented
        return other <= self

    def __gt__(self, other):
        if not isinstance(other, ParseTreeNode):
            return NotImplemented
        return other < self

    def __repr__(self):
        # TODO: Update this
        if self.is_leaf():
            return type(self).__name__ + "(" + repr(self._rule) + ", " + repr(self.span) + ")"
        else:
            return type(self).__name__ + "(" + repr(self._rule) + ", " + repr(self.components) + ")"

    def __str__(self):
        return self.to_str()

    @property
    def tokens(self):
        return self._tokens

    @property
    def rule(self):
        return self._rule

    @property
    def head_index(self):
        return self._head_index

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
        return self.start, self.end

    @property
    def components(self):
        return self._components

    @property
    def coverage(self):
        return 1 if self.is_leaf() else reduce(lambda a, b: a * b.coverage, self.components, 1)

    @property
    def head_token(self):
        return self.tokens[self._start] if self.is_leaf() else self._components[self._head_index].head_token

    @property
    def head_token_start(self):
        return self._start if self.is_leaf() else self._components[self._head_index].best.head_token_start

    def iter_parents(self):
        if self._parents:
            yield from self._parents

    def is_leaf(self):
        return self._components is None

    def to_str(self, simplify=False):
        result = self.category.to_str(simplify) + ':'
        if self.is_leaf():
            covered_tokens = ' '.join(self.tokens[self.start:self.end])
            result += ' ' + repr(covered_tokens) + ' ' + repr(self.span)
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

    def restrict(self, categories):
        for category in categories:
            if self._category in category:
                yield self
                break
        else:
            if self._components:
                for component in self._components:
                    for restriction in component.restrict(categories):
                        yield restriction

    def get_weighted_score(self):
        return self._score

    def get_score_data(self):
        return self._raw_score

    def update_weighted_score(self, recurse=True):
        total_weighted_score, total_weight = self.rule.calculate_weighted_score(self)
        if self.is_leaf():
            depth = 1
        else:
            depth = total_weight
            for component in self.components:
                component_depth, weighted_score, weight = component.get_score_data()

                # It's already weighted, so don't multiply it
                total_weighted_score += weighted_score

                total_weight += weight
                depth += component_depth * weight
            depth /= total_weight

            # TODO: At each level, divide both values by the number of values summed. This way we have a usable
            #       confidence score between 0 and 1 that comes out at the top.
            # self._score = total_weighted_score, total_weight

        # return self._score

        self._raw_score = (depth, total_weighted_score, total_weight)
        self._score = (total_weighted_score / math.log(1 + depth, 2), total_weight)

        if recurse and self._parents:
            for parent in self._parents:
                parent.update_weighted_score()

    def adjust_score(self, target):
        self.rule.adjust_score(self, target)
        if not self.is_leaf():
            for component in self.components:
                component.adjust_score(target)
        # self._score = None
        # self.update_weighted_score()

    def iter_leaves(self):
        if self.is_leaf():
            yield self
        else:
            for component in self.components:
                yield from component.iter_leaves()

    def add_parent(self, parent):
        assert not parent.has_ancestor(self)
        if self._parents is None:
            self._parents = [parent]
        else:
            self._parents.append(parent)

    def has_ancestor(self, ancestor):
        if ancestor is self:
            return True
        if not self._parents:
            return False
        return any(parent.has_ancestor(ancestor) for parent in self._parents)

    def visit(self, handler, is_root=False):
        """Visit this node with a LanguageContentHandler."""
        # TODO: Should we let the handler know that there's a dangling
        #       needs_* or takes_* property that hasn't been satisfied at
        #       the root level?

        # Hide the return value, since it's only for internal use.
        self._visit(handler, is_root)

    def _visit(self, handler, is_root=False):
        assert isinstance(handler, graphs.LanguageContentHandler)

        if self.is_leaf():
            if is_root:
                handler.handle_root()

            handler.handle_token(self.tokens[self.start], self._category, self.head_token_start,
                                 self.tokens.spans[self.start])

            need_sources = {}
            for prop in self.category.positive_properties:
                if prop.startswith(('needs_', 'takes_')):
                    needed = Property.get(prop[6:])
                    need_sources[needed] = {self.head_token_start}
            return need_sources

        head_start = self.components[self._head_index].best.head_token_start
        handler.handle_phrase_start(self.category, head_start)

        # Visit each subtree, remembering which indices are to receive
        # which potential links.
        nodes = []
        need_sources = {}
        head_need_sources = {}
        index = 0
        for component in self.components:
            assert isinstance(component, ParseTreeNodeSet)
            component = component.best
            assert isinstance(component, ParseTreeNode)

            component_need_sources = component._visit(handler, is_root and index == self._head_index)

            nodes.append(component.head_token_start)

            for property_name in component_need_sources:
                # if (Property('needs_'+ property_name) not in
                #         self.category.positive_properties and
                #         Property('takes_'+ property_name) not in
                #         self.category.positive_properties):
                #     continue
                if property_name in need_sources:
                    need_sources[property_name] |= component_need_sources[property_name]
                else:
                    need_sources[property_name] = component_need_sources[property_name]

            if index == self._head_index:
                head_need_sources = component_need_sources
            index += 1

        # Add the links as appropriate for the rule used to build this tree
        for index in range(len(self.components) - 1):
            links = self.rule.get_link_types(self, index)

            # Skip the head node; there won't be any looping links.
            if index < self._head_index:
                left_side = nodes[index]
                right_side = head_start
            else:
                left_side = head_start
                right_side = nodes[index + 1]

            for label, left, right in links:
                if left:
                    if label.lower() in head_need_sources:
                        #     and not (Property.get('needs_' + label.lower()) in self.category.positive_properties or
                        #              Property.get('takes_' + label.lower()) in self.category.positive_properties):
                        for node in need_sources[label.lower()]:
                            handler.handle_link(node, left_side, label)
                    elif label[-3:].lower() == '_of' and label[:-3].lower() in head_need_sources:
                        for node in need_sources[label[:-3].lower()]:
                            handler.handle_link(left_side, node, label)
                    else:
                        handler.handle_link(right_side, left_side, label)

                if right:
                    if label.lower() in head_need_sources:
                        #     and not (Property.get('needs_' + label.lower()) in self.category.positive_properties or
                        #              Property.get('takes_' + label.lower()) in self.category.positive_properties):
                        for node in need_sources[label.lower()]:
                            handler.handle_link(node, right_side, label)
                    elif label[-3:].lower() == '_of' and label[:-3].lower() in head_need_sources:
                        for node in need_sources[label[:-3].lower()]:
                            handler.handle_link(right_side, node, label)
                    else:
                        handler.handle_link(left_side, right_side, label)

        handler.handle_phrase_end()

        # Figure out which nodes should get which links from outside this
        # subtree
        parent_need_sources = {}
        for prop in self.category.positive_properties:
            if prop.startswith(('needs_', 'takes_')):
                needed = Property.get(prop[6:])
                if needed in need_sources:
                    parent_need_sources[needed] = need_sources[needed]
                else:
                    parent_need_sources[needed] = {head_start}
        return parent_need_sources


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

    def __init__(self, rule, category, head_spelling, head_index,
                 components=None):
        # TODO: Type checking
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
        else:
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
            return id(self._rule) < id(other._rule)  # TODO: Bad idea???
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


# TODO: Each of these really represents a group of parses having the same
#       root form. In Parse, when we get a list of ranked parses, we're
#       ignoring all the other parses that have the same root form. While
#       this *usually* means we see all the parses we actually care to see,
#       sometimes there is an alternate parse with the same root form which
#       actually has a higher rank than the best representatives of other
#       forms. When this happens, we want to see this alternate form, but
#       we don't get to. Create a method in Parse (along with helper
#       methods here) to allow the caller to essentially treat the Parse as
#       a priority queue for the best parses, so that we can iterate over
#       *all* complete parses in order of score and not just those that are
#       the best for each root form, but without forcing the caller to wait
#       for every single complete parse to be calculated up front. That is,
#       we should iteratively expand the parse set just enough to find the
#       next best parse and yield it immediately, keeping track of where we
#       are in case the client isn't satisfied.
#
#       Now that I think about it, the best way to implement this is
#       literally with a priority queue. We create an iterator for each
#       top-level parse set, which iterates over each alternative parse
#       with the same root form, and we get the first parse from each one.
#       We then rank each iterator by the quality of the parse we got from
#       it. We take the best one & yield its parse, then grab another parse
#       from it and re-rank the iterator by the new parse, putting it back
#       into the priority queue. If no more parses are available from one
#       of the iterators, we don't add it back to the priority queue. When
#       the priority queue is empty, we return from the method. Probably
#       what's going to happen is each of these iterators is actually going
#       to use a recursive call back into the same method for each child of
#       the root node, putting the pieces together to create the next best
#       alternate parse.
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
                self._start = node.start
                self._end = node.end
                self._category = node.category
                values_set = True
            self.add(node)
        if not values_set:
            raise ValueError("ParseTreeNodeSet must contain at least one node.")

        self._hash = hash(self._start) ^ hash(self._end) ^ hash(self._category)

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

    def __str__(self):
        return self.to_str()

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
    def best(self):
        return self._best_node

    @property
    def coverage(self):
        return sum([node.coverage for node in self._unique])

    @property
    def head_token(self):
        assert self._best_node is not None, self._unique
        return self._best_node.head_token

    def iter_parents(self):
        if self._parents:
            yield from self._parents

    def is_compatible(self, node_or_set):
        if not isinstance(node_or_set, (ParseTreeNode, ParseTreeNodeSet)):
            raise TypeError(node_or_set, (ParseTreeNode, ParseTreeNodeSet))
        return (node_or_set.start == self._start and node_or_set.end == self._end and
                node_or_set.category == self._category)

    def add(self, node):
        if not isinstance(node, ParseTreeNode):
            raise TypeError(node, ParseTreeNode)
        if not self.is_compatible(node):
            raise ValueError("Node is not compatible.")
        if node in self._unique:
            return
        self._unique.add(node)
        node.add_parent(self)
        if self._best_node is None:
            self._best_node = node
        self.update_weighted_score(node)

    def get_weighted_score(self):
        return self._best_node.get_weighted_score() if self._best_node else None

    def get_score_data(self):
        return self._best_node.get_score_data() if self._best_node else None

    def update_weighted_score(self, affected_node=None, recurse=True):
        assert self._best_node is not None
        if affected_node is None or affected_node is self._best_node:
            best_score = None
            best_node = None
            for node in self._unique:
                score = node.get_weighted_score()
                if best_score is None or best_score < score:
                    best_score = score
                    best_node = node
            self._best_node = best_node
            if recurse and self._parents:
                for parent in self._parents:
                    parent.update_weighted_score()
        elif self._best_node.get_weighted_score() < affected_node.get_weighted_score():
            self._best_node = affected_node
            if recurse and self._parents:
                for parent in self._parents:
                    parent.update_weighted_score()
        assert self._best_node is not None

    def adjust_score(self, target):
        for node in self._unique:
            node.adjust_score(target)
        # if self._parents:
        #     for parent in self._parents:
        #         parent.update_weighted_score()

    def iter_leaves(self):
        for node in self._unique:
            yield from node.iter_leaves()

    def add_parent(self, parent):
        assert not parent.has_ancestor(self)
        if self._parents is None:
            self._parents = [parent]
        else:
            self._parents.append(parent)

    def has_ancestor(self, ancestor):
        if ancestor is self:
            return True
        if not self._parents:
            return False
        return any(parent.has_ancestor(ancestor) for parent in self._parents)

    def to_str(self, simplify=False):
        return self._best_node.to_str(simplify)

    def restrict(self, categories):
        for category in categories:
            if self._category in category:
                yield self
                break
        else:
            for node in self._unique:
                for restriction in node.restrict(categories):
                    yield restriction

    def visit(self, handler, is_root=False):
        self._best_node.visit(handler, is_root)


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
        return self._root.to_str(simplify)

    def restrict(self, categories):
        results = set()
        for node in self._root.restrict(categories):
            results.add(type(self)(self._tokens, node))
        return results

    def is_ambiguous_with(self, other):
        return self.start <= other.start < self.end or other.start <= self.start < other.end

    def get_weighted_score(self):
        return self.root.get_weighted_score()

    def adjust_score(self, target):
        self.root.adjust_score(target)

        queue = deque(self.root.iter_leaves())
        visited = set()
        while queue:
            item = queue.popleft()
            if item in visited:
                continue
            item.update_weighted_score(recurse=False)
            visited.add(item)
            queue.extend(item.iter_parents())

    def visit(self, handler):
        # TODO: Make sure the return value is empty. If not, it's a bad
        #       parse tree. This case should be detected when the Parse
        #       instance is created, and bad trees should automatically be
        #       filtered out then, so we should *never* get a need source
        #       here.
        self.root.visit(handler, True)


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
            raise exceptions.Timeout()
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
        except exceptions.Timeout:
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

    def visit(self, handler):
        scores = {tree: tree.get_weighted_score() for tree in self._parse_trees}

        for tree in sorted(self._parse_trees,
                           key=lambda tree: (tree.start, -tree.end, -scores[tree][0], -scores[tree][1])):
            tree.visit(handler)
            handler.handle_tree_end()

    def get_parse_graphs(self):
        assert not self.is_ambiguous()
        graph_builder = ParseGraphBuilder()
        self.visit(graph_builder)
        return graph_builder.get_graphs()
