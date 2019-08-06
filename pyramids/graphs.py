"""
Graph representations of parse trees
"""

from typing import NamedTuple, Sequence, Set, FrozenSet, Any, List, Tuple

from pyramids.categorization import Category
from pyramids.traversal import LanguageContentHandler

__author__ = 'Aaron Hosford'
__all__ = [
    'ParseGraph',
    'ParseGraphBuilder'
]


Token = NamedTuple('Token', [('index', int), ('spelling', str), ('span', Tuple[int, int]), ('category', Category)])


class ParseGraph:
    """A simple class for representing language content as a semantic graph."""

    def __init__(self, root: int, tokens: Sequence[Token], links, phrases):
        self._root = root
        self._tokens = tuple(tokens)
        self._links = tuple({sink: frozenset(labels) for sink, labels in dict(sink_map).items()}
                            for sink_map in links)
        self._phrases = tuple(tuple((category, frozenset((source, sink) for source, sink in phrase_links))
                                    for category, phrase_links in phrase_stack)
                              for phrase_stack in phrases)
        assert self._phrases and self._phrases[-1]

        self._reversed_links = tuple({source: self._links[source][sink] for source in range(len(self._tokens))
                                      if sink in self._links[source]}
                                     for sink in range(len(self._tokens)))

    @property
    def root_index(self) -> int:
        """The index of the root token."""
        return self._root

    @property
    def root_category(self) -> Category:
        """The topmost phrase category of the root token."""
        return self.get_phrase_category(self._root)

    def __str__(self) -> str:
        result = str(self.root_category) + ':'
        for index in range(len(self._tokens)):
            result += '\n  '
            if index == self._root:
                result += '*'
            result += self._tokens[index][1] + ':'
            for sink, labels in sorted(self._links[index].items()):
                labels = '|'.join(sorted(str(label) for label in labels))
                result += '\n    ' + labels + ': ' + self._tokens[sink][1]
        return result

    def __getitem__(self, index: int) -> Token:
        return self._tokens[index]

    def __len__(self) -> int:
        return len(self._tokens)

    def get_phrase_category(self, head: int) -> Category:
        """Get the phrase category of the largest phrase headed by the token at the given index."""
        assert 0 <= head <= len(self._tokens)
        return self._phrases[head][-1][0]

    def get_phrase_stack(self, head: int) -> Category:
        """Get the full phrase category stack of phrases headed by the token at the given index."""
        assert 0 <= head <= len(self._tokens)
        return self._phrases[head]

    def get_sinks(self, source: int) -> Set[int]:
        """Get the sink indices of the edges that originate at the given source index."""
        assert 0 <= source < len(self._tokens)
        return set(self._links[source])

    def get_sources(self, sink: int) -> Set[int]:
        """Get the source indices of the edges that originate at the given sink index."""
        assert 0 <= sink <= len(self._tokens)
        return set(self._reversed_links[sink])

    def get_labels(self, source: int, sink: int, default: Any = None) -> FrozenSet[str]:
        """Get the labels for all edges that originate at the given source index and terminate at the given sink
        index."""
        assert 0 <= source <= len(self._tokens)
        assert 0 <= sink <= len(self._tokens)
        return self._links[source].get(sink, default)

    def _get_phrase_tokens(self, head: int, indices: Set[int]) -> None:
        """Recursively collect token indices that are part of a phrase."""
        if head not in indices:
            indices.add(head)
            for sink in self.get_sinks(head):
                self._get_phrase_tokens(sink, indices)

    def get_phrase_tokens(self, head: int) -> List[Token]:
        """Get the list of tokens that are part of the largest phrase with the given head index."""
        assert 0 <= head <= len(self._tokens)
        indices = set()
        self._get_phrase_tokens(head, indices)
        return [self._tokens[index] for index in sorted(indices)]

    def get_phrase_text(self, head: int) -> str:
        """Return the original text of the largest phrase headed by the token at the given index."""
        assert 0 <= head <= len(self._tokens)
        phrase = ''
        for index, spelling, span, category in self.get_phrase_tokens(head):
            start, end = span
            assert len(spelling) == end - start
            assert not phrase[start:end].strip()
            if len(phrase) < start:
                phrase += ' ' * (start - len(phrase))
            phrase = phrase[:start] + spelling + phrase[end:]

        return ' '.join(phrase.split())


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
        """Called to indicate the end of a tree."""
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

    def handle_token(self, spelling: str, category: Category, index: int = None, span: Tuple[int, int] = None) -> int:
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
        """Called to indicate the start of a phrase."""
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
        """Called to indicate the end of a phrase."""
        assert self._phrase_stack

        head_start_index, category, links = self._phrase_stack.pop()

        assert head_start_index in self._index_map

        head_index = self._index_map[head_start_index]
        self._phrases[head_index].append((category, frozenset(links)))
