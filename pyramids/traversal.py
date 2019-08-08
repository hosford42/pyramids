# -*- coding: utf-8 -*-

from typing import Tuple

from pyramids.categorization import Property, Category
from pyramids import trees


class LanguageContentHandler:
    """A content handler for natural language, in the style of the
    ContentHandler class of the xml.sax module."""

    def handle_tree_end(self) -> None:
        """Called to indicate the end of a tree."""

    def handle_token(self, spelling: str, category: Category, index: int = None, span: Tuple[int, int] = None) -> None:
        """Called to indicate the occurrence of a token."""

    def handle_root(self) -> None:
        """Called to indicate that the next token is the root."""

    def handle_link(self, source_start_index: int, sink_start_index: int, label: str) -> None:
        """Called to indicate the occurrence of a link between two tokens.
        Note that this will not be called until handle_token() has been
        called for both the source and sink."""

    def handle_phrase_start(self, category: Category, head_start_index: int = None) -> None:
        """Called to indicate the start of a phrase."""

    def handle_phrase_end(self) -> None:
        """Called to indicate the end of a phrase."""


class DepthFirstTraverser:

    def traverse(self, element, handler, is_root=False):
        """Visit this node with a LanguageContentHandler."""
        # TODO: Should we let the handler know that there's a dangling
        #       needs_* or takes_* property that hasn't been satisfied at
        #       the root level?

        if isinstance(element, trees.Parse):
            scores = {tree: tree.get_weighted_score() for tree in element.parse_trees}

            for tree in sorted(element.parse_trees,
                               key=lambda tree: (tree.start, -tree.end, -scores[tree][0], -scores[tree][1])):
                self.traverse(tree, handler)
                handler.handle_tree_end()
        elif isinstance(element, trees.ParseTree):
            # TODO: Make sure the return value is empty. If not, it's a bad
            #       parse tree. This case should be detected when the Parse
            #       instance is created, and bad trees should automatically be
            #       filtered out then, so we should *never* get a need source
            #       here.
            self.traverse(element.root, handler, True)
        elif isinstance(element, trees.ParseTreeNodeSet):
            self.traverse(element.best_node, handler, is_root)
        else:
            assert isinstance(element, trees.ParseTreeNode)
            # Hide the return value, since it's only for internal use.
            self._traverse(element, handler, is_root)

    # TODO: Break this method up into comprehensible chunks.
    def _traverse(self, element, handler: LanguageContentHandler, is_root=False):
        assert isinstance(element, trees.ParseTreeNode)
        payload = element.payload
        assert isinstance(payload, trees.ParsingPayload)
        if element.is_leaf():
            if is_root:
                handler.handle_root()

            head_token_start = trees.ParseTreeUtils().get_head_token_start(element)
            handler.handle_token(payload.tokens[payload.start], payload.category, head_token_start,
                                 payload.tokens.spans[payload.start])

            need_sources = {}
            for prop in payload.category.positive_properties:
                if prop.startswith(('needs_', 'takes_')):
                    needed = Property.get(prop[6:])
                    need_sources[needed] = {head_token_start}
            return need_sources

        head_start = trees.ParseTreeUtils().get_head_token_start(element)
        handler.handle_phrase_start(payload.category, head_start)

        # Visit each subtree, remembering which indices are to receive
        # which potential links.
        nodes = []
        need_sources = {}
        head_need_sources = {}
        index = 0
        for component in element.components:
            assert isinstance(component, trees.ParseTreeNodeSet)
            component = component.best_node
            assert isinstance(component, trees.ParseTreeNode)

            component_need_sources = self._traverse(component, handler, is_root and index == payload.head_index)

            head_token_start = trees.ParseTreeUtils().get_head_token_start(component)
            nodes.append(head_token_start)

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

            if index == payload.head_index:
                head_need_sources = component_need_sources
            index += 1

        # Add the links as appropriate for the rule used to build this tree
        for index in range(len(element.components) - 1):
            links = payload.rule.get_link_types(element, index)

            # Skip the head node; there won't be any looping links.
            if index < payload.head_index:
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

        # Figure out which nodes should get which links from outside this subtree
        parent_need_sources = {}
        for prop in payload.category.positive_properties:
            if prop.startswith(('needs_', 'takes_')):
                needed = Property.get(prop[6:])
                if needed in need_sources:
                    parent_need_sources[needed] = need_sources[needed]
                else:
                    parent_need_sources[needed] = {head_start}
        return parent_need_sources
