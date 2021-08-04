from typing import List, Tuple

from pyramids.categorization import Category
from pyramids.graphs import ParseGraph, Token
from pyramids.traversal import LanguageContentHandler


class ParseGraphBuilder(LanguageContentHandler):
    """A content handler for traversing parse trees to generate parse graphs."""

    def __init__(self):
        self._counter = 0
        self._root = None
        self._tokens = []
        self._links = []
        self._phrases = []

        self._index_map = {}
        self._graphs = []
        self._phrase_stack = []

    def get_graphs(self) -> List[ParseGraph]:
        """Get the list of graphs produced by the traversal."""
        if self._tokens:
            self.handle_tree_end()
        graphs = self._graphs
        self._graphs = []
        return graphs

    def handle_tree_end(self) -> None:
        """Called to indicate the token_end_index of a tree."""
        assert self._root is not None
        assert not self._phrase_stack

        graph = ParseGraph(self._root, self._tokens, self._links, self._phrases)

        self._graphs.append(graph)

        self._counter = 0
        self._root = None
        self._tokens.clear()
        self._links.clear()
        self._phrases.clear()
        self._index_map.clear()
        self._phrase_stack.clear()

    def handle_token(self, spelling: str, category: Category, index: int = None,
                     span: Tuple[int, int] = None) -> int:
        """Called to indicate the occurrence of a token."""
        if index is None:
            index = self._counter
            self._counter += 1
        else:
            assert index not in self._index_map
            assert not self._counter
        self._index_map[index] = len(self._tokens)
        self._tokens.append(Token(index, spelling, span, category))
        self._links.append({})
        self._phrases.append([(category, frozenset())])

        # For convenience, return the id of the token so users can know
        # which index to use for links.
        return len(self._tokens) - 1

    def handle_root(self) -> None:
        """Called to indicate that the next token is the root."""
        assert self._root is None
        self._root = len(self._tokens)

    def handle_link(self, source_index: int, sink_index: int, label: str) -> None:
        """Called to indicate the occurrence of a link between two tokens.
        Note that this will not be called until handle_token() has been
        called for both the source and sink."""
        assert source_index in self._index_map
        assert sink_index in self._index_map
        assert self._phrase_stack

        source_id = self._index_map[source_index]
        sink_id = self._index_map[sink_index]

        if sink_id in self._links[source_id]:
            self._links[source_id][sink_id].add(label)
        else:
            self._links[source_id][sink_id] = {label}

        self._phrase_stack[-1][-1].append((source_id, sink_id))

    def handle_phrase_start(self, category: Category, head_index: int = None) -> None:
        """Called to indicate the token_start_index of a phrase."""
        if head_index is None:
            head_index = self._counter
        else:
            assert head_index not in self._index_map

        self._phrase_stack.append((
            head_index,
            category,
            []  # For links
        ))

    def handle_phrase_end(self) -> None:
        """Called to indicate the token_end_index of a phrase."""
        assert self._phrase_stack

        head_start_index, category, links = self._phrase_stack.pop()

        assert head_start_index in self._index_map

        head_index = self._index_map[head_start_index]
        self._phrases[head_index].append((category, frozenset(links)))