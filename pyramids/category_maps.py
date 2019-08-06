# TODO: Optimize this class. Consider moving to _categorization.pyx.

from pyramids import trees


class CategoryMap:
    """The category map tracked & used by a parser state. This data structure holds a mapping from text ranges
    to the grammatical categories and parse sub-trees associated with them. The data is structured to minimize
    query & update time during the parser's search."""

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
                    for end in self._map[start][category_name_id][category]:
                        yield start, category, end

    @property
    def max_end(self):
        return self._max_end

    @property
    def size(self):
        return self._size

    def add(self, node: trees.ParseTreeNode):
        """Add the given parse tree node to the category map and return a
        boolean indicating whether it was something new or was already
        mapped."""

        cat = node.category
        name = cat.name
        start = node.start
        end = node.end

        if start not in self._map:
            node_set = trees.ParseTreeNodeSet(node)
            self._map[start] = {name: {cat: {end: node_set}}}
        elif name not in self._map[start]:
            node_set = trees.ParseTreeNodeSet(node)
            self._map[start][name] = {cat: {end: node_set}}
        elif cat not in self._map[start][name]:
            node_set = trees.ParseTreeNodeSet(node)
            self._map[start][name][cat] = {end: node_set}
        elif end not in self._map[start][name][cat]:
            node_set = trees.ParseTreeNodeSet(node)
            self._map[start][name][cat][end] = node_set
        elif node not in self._map[start][name][cat][end]:
            self._map[start][name][cat][end].add(node)
            return False  # No new node sets were added.
        else:
            return False  # It's already in the map

        if end not in self._reverse_map:
            self._reverse_map[end] = {name: {cat: {start: node_set}}}
        elif name not in self._reverse_map[end]:
            self._reverse_map[end][name] = {cat: {start: node_set}}
        elif cat not in self._reverse_map[end][name]:
            self._reverse_map[end][name][cat] = {start: node_set}
        elif start not in self._reverse_map[end][name][cat]:
            self._reverse_map[end][name][cat][start] = node_set

        if end > self._max_end:
            self._max_end = end

        self._size += 1
        self._ranges.add((start, end))

        return True  # It's something new

    def iter_forward_matches(self, start, categories):
        if start in self._map:
            for category in categories:
                by_name = self._map[start]
                if category.is_wildcard():
                    for category_name in by_name:
                        by_cat = by_name[category_name]
                        for mapped_category in by_cat:
                            if mapped_category in category:
                                for end in by_cat[mapped_category]:
                                    yield mapped_category, end
                elif category.name in by_name:
                    by_cat = by_name[category.name]
                    for mapped_category in by_cat:
                        if mapped_category in category:
                            for end in by_cat[mapped_category]:
                                yield mapped_category, end

    def iter_backward_matches(self, end, categories):
        if end in self._reverse_map:
            for category in categories:
                by_name = self._reverse_map[end]
                if category.is_wildcard():
                    for category_name in by_name:
                        by_cat = by_name[category_name]
                        for mapped_category in by_cat:
                            if mapped_category in category:
                                for start in by_cat[mapped_category]:
                                    yield mapped_category, start
                elif category.name in by_name:
                    by_cat = by_name[category.name]
                    for mapped_category in by_cat:
                        if mapped_category in category:
                            for start in by_cat[mapped_category]:
                                yield mapped_category, start

    def iter_node_sets(self, start, category, end):
        if (start in self._map and
                category.name in self._map[start] and
                category in self._map[start][category.name] and
                end in self._map[start][category.name][category]):
            yield self._map[start][category.name][category][end]

    def get_node_set(self, node):
        category = node.category
        name = category.name
        start = node.start
        if (start in self._map and
                name in self._map[start] and
                category in self._map[start][name] and
                node.end in self._map[start][name][category]):
            return self._map[start][name][category][node.end]
        else:
            return None

    def has_start(self, start):
        return start in self._map

    def has_end(self, end):
        return end in self._reverse_map

    def has_range(self, start, end):
        return (start, end) in self._ranges
