# -*- coding: utf-8 -*-

"""
Graph representations of parse trees
"""

from typing import NamedTuple, Sequence, Set, FrozenSet, List, Tuple, Optional, Iterator, Union

try:
    from graphviz import Digraph
except ImportError:
    Digraph = None

from pyramids.categorization import Category, LinkLabel
from pyramids.traversal import LanguageContentHandler

__author__ = 'Aaron Hosford'
__all__ = [
    'Token',
    'ParseGraph',
    'BuildGraph',
    'ParseGraphBuilder'
]


Token = NamedTuple('Token', [('index', int), ('spelling', str), ('span', Optional[Tuple[int, int]]),
                             ('category', Category)])


class ParseGraph:
    """A simple class for representing language content as a semantic graph."""

    @classmethod
    def from_json(cls, json_data) -> 'ParseGraph':
        """Constructs a ParseGraph from a JSON-serializable data structure produced by ParseGraph.to_json()."""
        from pyramids.grammar import GrammarParser
        root = json_data['roots'][-1]
        tokens = [Token(token.get('index', index), token['spelling'], token['span'],
                        GrammarParser.parse_category(token['category']))
                  for index, token in enumerate(json_data['tokens'])]
        links = [{} for _ in tokens]
        for link in json_data['links']:
            source = link['source']
            sink = link['sink']
            label = LinkLabel.get(link['label'])
            if sink in links[source]:
                links[source][sink].add(label)
            else:
                links[source] = {sink: {label}}
        phrases = [[] for _ in tokens]
        for index, phrase_stack in enumerate(json_data['phrases']):
            for phrase in phrase_stack:
                category = GrammarParser.parse_category(phrase['category'])
                phrase_links = [(link['source'], link['sink']) for link in phrase['links']]
                phrases[index].append((category, phrase_links))
        return cls(root, tokens, links, phrases)

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

    @property
    def tokens(self) -> Tuple[Token, ...]:
        return self._tokens

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

    def to_json(self):
        """Returns a JSON-serializable data structure that represents the contents of the graph."""
        return {
            'roots': [self._root],
            'tokens': [{'spelling': token.spelling, 'span': list(token.span), 'category': str(token.category),
                        'index': token.index}
                       for token in self._tokens],
            'links': [{'source': source, 'sink': sink, 'label': str(label)}
                      for source, links in enumerate(self._links)
                      for sink, labels in links.items()
                      for label in labels],
            'phrases': [[{'category': str(category), 'links': [{'source': source, 'sink': sink}
                                                               for source, sink in sorted(phrase_links)]}
                         for category, phrase_links in phrase_stack]
                        for phrase_stack in self._phrases]
        }

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

    def get_labels(self, source: int, sink: int) -> FrozenSet[str]:
        """Get the labels for all edges that originate at the given source index and terminate at the given sink
        index."""
        assert 0 <= source <= len(self._tokens)
        assert 0 <= sink <= len(self._tokens)
        return self._links[source].get(sink, frozenset())

    def _get_phrase_tokens(self, head: int, indices: Set[int]) -> None:
        """Recursively collect token indices that are part of a phrase."""
        if head not in indices:
            indices.add(head)
            for sink in self.get_sinks(head):
                self._get_phrase_tokens(sink, indices)

    def get_phrase_tokens(self, head: int = None) -> List[Token]:
        """Get the list of tokens that are part of the largest phrase with the given head index."""
        if head is None:
            return list(self._tokens)
        assert 0 <= head <= len(self._tokens)
        indices = set()
        self._get_phrase_tokens(head, indices)
        return [self._tokens[index] for index in sorted(indices)]

    def get_phrase_text(self, head: int = None) -> str:
        """Return the original text of the largest phrase headed by the token at the given index."""
        assert head is None or 0 <= head <= len(self._tokens)
        phrase = ''
        for index, spelling, span, category in self.get_phrase_tokens(head):
            start, end = span
            assert len(spelling) == end - start
            assert not phrase[start:end].strip()
            if len(phrase) < start:
                phrase += ' ' * (start - len(phrase))
            phrase = phrase[:start] + spelling + phrase[end:]

        return ' '.join(phrase.split())

    def visualize(self, gv_graph: Digraph) -> None:
        depths = {self.root_index: 0}
        while len(depths) < len(self._tokens):
            for source in list(depths):
                for sink in self.get_sinks(source):
                    if sink not in depths:
                        depths[sink] = depths[source] + 1

        by_depth = []
        for depth in range(max(depths.values()) + 1):
            indices = [index for index in depths if depths[index] == depth]
            indices.sort()
            by_depth.append(indices)

        node_labels = []
        for index, token in enumerate(self._tokens):
            node_labels.append('%s [%s]\n%s' % (token.spelling, index, token.category.name))

        for depth, indices in enumerate(by_depth):
            with gv_graph.subgraph() as subgraph:
                # if depth:
                #     subgraph.attr('node', shape='circle')
                # else:
                #     subgraph.attr('node', shape='doublecircle')
                subgraph.attr(rank='same')
                for index in indices:
                    subgraph.node(node_labels[index])

        for source in range(len(self._tokens)):
            for sink in self.get_sinks(source):
                for edge_label in sorted(str(label) for label in self.get_labels(source, sink)):
                    gv_graph.edge(node_labels[source], node_labels[sink], label=edge_label)


class BuildGraph:
    """A simple class for representing language content as a semantic graph."""

    @classmethod
    def from_parse_graphs(cls, graphs: Sequence[Union[ParseGraph, 'BuildGraph']]) -> 'BuildGraph':
        graph_offset = 0
        combined_graph = BuildGraph()
        for graph in graphs:
            for token in graph.tokens:
                combined_graph.append_token(token.spelling, token.category)
            for source in range(len(graph.tokens)):
                adjusted_source = graph_offset + source
                for sink in graph.get_sinks(source):
                    adjusted_sink = graph_offset + sink
                    for label in graph.get_labels(source, sink):
                        combined_graph.add_link(adjusted_source, label, adjusted_sink)
                combined_graph.set_phrase_category(adjusted_source, graph.get_phrase_category(source))
            graph_offset += len(graph.tokens)
        return combined_graph

    @classmethod
    def from_json(cls, json_data) -> 'BuildGraph':
        """Constructs a ParseGraph from a JSON-serializable data structure produced by ParseGraph.to_json()."""
        from pyramids.grammar import GrammarParser
        result = BuildGraph()
        for token in json_data['tokens']:
            spelling = token['spelling']
            category = token.get('category')
            span = token.get('span')
            if category is not None:
                category = GrammarParser.parse_category(category)
            if span is not None:
                span = tuple(span)
            result.append_token(spelling, category, span)
        for link in json_data['links']:
            source = link['source']
            sink = link['sink']
            label = LinkLabel.get(link['label'])
            result.add_link(source, label, sink)
        for index, phrase_stack in enumerate(json_data['phrases']):
            for phrase in phrase_stack:
                category = phrase.get('category')
                if category is not None:
                    category = GrammarParser.parse_category(category)
                    result.set_phrase_category(index, category)
        return result

    def __init__(self):
        self._phrase_categories = []
        self._tokens = []
        self._links = []

    @property
    def tokens(self) -> Tuple[Token, ...]:
        return tuple(self._tokens)

    def get_annotations(self) -> List[str]:
        phrase_map = [token.spelling.replace('(', '\\(').replace(')', '\\)') for token in self._tokens]
        new = self.find_leaves()
        covered = new.copy()
        while new:
            new = {source for source, outbound in enumerate(self._links) if outbound.keys() <= covered} - covered
            covered.update(new)
            links = set()
            for source in new:
                outbound = self._links[source]
                for sink in covered & outbound.keys():
                    for label in outbound[sink]:
                        links.add((source, label, sink))
            for source, label, sink in sorted(links, key=lambda l: (abs(l[2] - l[0]), l)):
                if source < sink:
                    phrase = '%s %s> %s' % (phrase_map[source], label, phrase_map[sink])
                elif sink < source:
                    phrase = '%s <%s %s' % (phrase_map[sink], label, phrase_map[source])
                else:
                    continue
                if abs(source - sink) + 1 < len(self._tokens):
                    phrase = '(%s)' % phrase
                for index in range(min(source, sink), max(source, sink) + 1):
                    phrase_map[index] = phrase
        return ['%s: %s' % (self.get_phrase_category(index), phrase_map[index])
                for index in sorted(self.find_roots())]

    def find_roots(self) -> Set[int]:
        roots = set(range(len(self._tokens)))
        for index, outbound in enumerate(self._links):
            roots -= outbound.keys()
        return roots

    def find_leaves(self) -> Set[int]:
        return {index for index in range(len(self._tokens)) if not self._links[index]}

    def _is_forest(self, roots) -> bool:
        visited = roots
        added = list(visited)
        to_add = []
        while added:
            for source in added:
                for sink in self.get_sinks(source):
                    if sink in visited:
                        return False
                    visited.add(sink)
                    to_add.append(sink)
            added, to_add = to_add, added
            to_add.clear()
        return len(visited) == len(self._tokens)

    def is_tree(self) -> bool:
        roots = self.find_roots()
        return len(roots) == 1 and self._is_forest(roots)

    def is_forest(self) -> bool:
        return self._is_forest(self.find_roots())

    def set_phrase_category(self, index: int, category: Category) -> None:
        self._phrase_categories[index] = category

    def append_token(self, spelling: str, category: Category = None, span: Tuple[int, int] = None) -> int:
        index = len(self._tokens)
        token = Token(index, spelling, span, category)
        self._phrase_categories.append(Category('_'))
        self._tokens.append(token)
        self._links.append({})
        return index

    def clear_token_category(self, index: int):
        token = self._tokens[index]
        self._tokens[index] = Token(token.index, token.spelling, token.span, None)

    def add_link(self, source: int, label: str, sink: int) -> None:
        if not 0 <= source < len(self._tokens):
            raise IndexError(source)
        if not 0 <= sink < len(self._tokens):
            raise IndexError(sink)
        outbound = self._links[source]
        if sink in outbound:
            outbound[sink].add(LinkLabel.get(label))
        else:
            outbound[sink] = {LinkLabel.get(label)}

    def discard_link(self, source: int, label: str, sink: int) -> None:
        if not 0 <= source < len(self._tokens):
            raise IndexError(source)
        if not 0 <= sink < len(self._tokens):
            raise IndexError(sink)
        outbound = self._links[source]
        labels = outbound.get(sink)
        if labels is None:
            return
        labels.discard(LinkLabel.get(label))
        if not labels:
            del outbound[sink]

    def remove_link(self, source: int, label: str, sink: int) -> None:
        if not 0 <= source < len(self._tokens):
            raise IndexError(source)
        if not 0 <= sink < len(self._tokens):
            raise IndexError(sink)
        outbound = self._links[source]
        labels = outbound[sink]
        labels.remove(LinkLabel.get(label))
        if not labels:
            del outbound[sink]

    def has_link(self, source: int, label: str, sink: int) -> bool:
        if not 0 <= source < len(self._tokens):
            raise IndexError(source)
        if not 0 <= sink < len(self._tokens):
            raise IndexError(sink)
        outbound = self._links[source]
        return LinkLabel.get(label) in outbound.get(sink, ())

    def iter_links(self, source: int = None, label: str = None, sink: int = None) \
            -> Iterator[Tuple[int, LinkLabel, int]]:
        if not (source is None or 0 <= source < len(self._tokens)):
            raise IndexError(source)
        if not (sink is None or 0 <= sink < len(self._tokens)):
            raise IndexError(sink)
        if source is None:
            source_iterator = range(len(self._tokens))
        else:
            source_iterator = [source]
        if sink is None:
            def sink_iterator_func(sinks):
                return sinks
        else:
            def sink_iterator_func(sinks):
                return [sink] if sink in sinks else []
        if label is None:
            def label_iterator_func(labels):
                return labels
        else:
            label = LinkLabel.get(label)

            def label_iterator_func(labels):
                return [label] if label in labels else []
        for each_source in source_iterator:
            for each_sink in sink_iterator_func(self._links[each_source]):
                for each_label in label_iterator_func(self._links[each_source][each_sink]):
                    yield each_source, each_label, each_sink

    def __getitem__(self, index: int) -> Token:
        return self._tokens[index]

    def __len__(self) -> int:
        return len(self._tokens)

    def to_json(self):
        """Returns a JSON-serializable data structure that represents the contents of the graph."""
        return {
            'roots': sorted(self.find_roots()),
            'tokens': [{'spelling': token.spelling,
                        'span': list(token.span) if token.span else None,
                        'category': str(token.category) if token.category else None,
                        'index': token.index}
                       for token in self._tokens],
            'links': [{'source': source, 'sink': sink, 'label': str(label)}
                      for source, links in enumerate(self._links)
                      for sink, labels in links.items()
                      for label in labels],
            'phrases': [[{'category': str(category)}] for category in self._phrase_categories]
        }

    def get_phrase_category(self, head: int) -> Category:
        """Get the phrase category of the largest phrase headed by the token at the given index."""
        return self._phrase_categories[head]

    def get_sinks(self, source: int) -> Set[int]:
        """Get the sink indices of the edges that originate at the given source index."""
        return set(self._links[source])

    def get_sources(self, sink: int) -> Set[int]:
        """Get the source indices of the edges that originate at the given sink index."""
        sources = set()
        for index, outbound in enumerate(self._links):
            if sink in outbound:
                sources.add(index)
        return sources

    def get_labels(self, source: int, sink: int) -> FrozenSet[LinkLabel]:
        """Get the labels for all edges that originate at the given source index and terminate at the given sink
        index."""
        return self._links[source].get(sink, frozenset())

    def _get_phrase_tokens(self, head: int, indices: Set[int]) -> None:
        """Recursively collect token indices that are part of a phrase."""
        if head not in indices:
            indices.add(head)
            for sink in self.get_sinks(head):
                self._get_phrase_tokens(sink, indices)

    def get_phrase_tokens(self, head: int = None) -> List[Token]:
        """Get the list of tokens that are part of the largest phrase with the given head index."""
        if head is None:
            return list(self._tokens)
        indices = set()
        self._get_phrase_tokens(head, indices)
        return [self._tokens[index] for index in sorted(indices)]

    def visualize(self, gv_graph: Digraph) -> None:
        depths = {root_index: 0 for root_index in self.find_roots()}
        new = True
        while new:
            new = False
            for source in list(depths):
                for sink in self.get_sinks(source):
                    if sink not in depths:
                        depths[sink] = depths[source] + 1
                        new = True

        # Handle cycles, if any are present.
        if len(depths) < len(self._tokens):
            depth = max(depths.values()) + 1 if depths else 0
            for index in range(len(self._tokens)):
                if index not in depths:
                    depths[index] = depth

        by_depth = []
        for depth in range(max(depths.values()) + 1):
            indices = [index for index in depths if depths[index] == depth]
            indices.sort()
            by_depth.append(indices)

        node_labels = []
        for index, token in enumerate(self._tokens):
            if token.category is None:
                node_label = '%s [%s]' % (token.spelling, index)
            else:
                node_label = '%s [%s]\n%s' % (token.spelling, index, token.category.name)
            node_labels.append(node_label)

        for depth, indices in enumerate(by_depth):
            with gv_graph.subgraph() as subgraph:
                subgraph.attr(rank=str(depth))
                for index in indices:
                    subgraph.node(node_labels[index])

        for source in range(len(self._tokens)):
            for sink in self.get_sinks(source):
                for edge_label in sorted(str(label) for label in self.get_labels(source, sink)):
                    gv_graph.edge(node_labels[source], node_labels[sink], label=edge_label)


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
