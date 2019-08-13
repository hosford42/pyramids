# -*- coding: utf-8 -*-

from pyramids import trees
from pyramids.categorization import Category


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
        for start, category_name_map in self._map.items():
            for category_name, category_map in category_name_map.items():
                for category, end_map in category_map.items():
                    for end in end_map:
                        yield start, category, end

    @property
    def max_end(self):
        return self._max_end

    @property
    def size(self):
        return self._size

    def add(self, node: trees.TreeNode[trees.ParsingPayload]):
        """Add the given parse tree node to the category map and return a
        boolean indicating whether it was something new or was already
        mapped."""

        cat = node.payload.category
        name = cat.name
        start = node.payload.token_start_index
        end = node.payload.token_end_index

        category_name_map = self._map.get(start)
        if category_name_map is None:
            node_set = trees.TreeNodeSet(node)
            self._map[start] = {name: {cat: {end: node_set}}}
        else:
            category_map = category_name_map.get(name)
            if category_map is None:
                node_set = trees.TreeNodeSet(node)
                category_name_map[name] = {cat: {end: node_set}}
            else:
                end_map = category_map.get(cat)
                if end_map is None:
                    node_set = trees.TreeNodeSet(node)
                    category_map[cat] = {end: node_set}
                else:
                    node_set = end_map.get(end)
                    if node_set is None:
                        node_set = trees.TreeNodeSet(node)
                        end_map[end] = node_set
                    else:
                        # No new node sets were added, so we don't need to do anything else.
                        node_set.add(node)
                        trees.TreeUtils.update_weighted_score(node_set, node)
                        return False

        category_name_map = self._reverse_map.get(end)
        if category_name_map is None:
            self._reverse_map[end] = {name: {cat: {start: node_set}}}
        else:
            category_map = category_name_map.get(name)
            if category_map is None:
                category_name_map[name] = {cat: {start: node_set}}
            else:
                start_map = category_map.get(cat)
                if start_map is None:
                    category_map[cat] = {start: node_set}
                else:
                    start_map[start] = node_set

        if end > self._max_end:
            self._max_end = end

        self._size += 1
        self._ranges.add((start, end))

        trees.TreeUtils.update_weighted_score(node_set, node)

        return True  # It's something new

    def iter_forward_matches(self, start, categories, emergency=False):
        category_name_map = self._map.get(start)
        if category_name_map is None:
            return
        for category in categories:
            if category.is_wildcard():
                for category_name, category_map in category_name_map.items():
                    for mapped_category, end_map in category_map.items():
                        if emergency or mapped_category in category:
                            for end in end_map:
                                yield mapped_category, end
            else:
                category_map = category_name_map.get(category.name)
                if category_map is not None:
                    for mapped_category, end_map in category_map.items():
                        if emergency or mapped_category in category:
                            for end in end_map:
                                yield mapped_category, end

    def iter_backward_matches(self, end, categories, emergency=False):
        category_name_map = self._reverse_map.get(end)
        if category_name_map is None:
            return
        for category in categories:
            if category.is_wildcard():
                for category_name, category_map in category_name_map.items():
                    for mapped_category, start_map in category_map.items():
                        if emergency or mapped_category in category:
                            for start in start_map:
                                yield mapped_category, start
            else:
                category_map = category_name_map.get(category.name)
                if category_map is not None:
                    for mapped_category, start_map in category_map.items():
                        if emergency or mapped_category in category:
                            for start in start_map:
                                yield mapped_category, start

    # TODO: Why does this even exist? Either convert it to a simple getter, or make it match wildcards like its name
    #       seems to imply. For now, I've changed it to return a sequence instead of working as a generator, which
    #       doesn't break anything and should improve performance slightly.
    def iter_node_sets(self, start: int, category: Category, end: int):
        assert not category.is_wildcard()
        category_name_map = self._map.get(start)
        if category_name_map is None:
            return ()
        category_map = category_name_map.get(category.name)
        if category_map is None:
            return ()
        end_map = category_map.get(category)
        if end_map is None:
            return ()
        node_set = end_map.get(end)
        if node_set is None:
            return ()
        return node_set,

    def get_node_set(self, node: trees.TreeNode[trees.ParsingPayload]):
        category_name_map = self._map.get(node.payload.token_start_index)
        if category_name_map is None:
            return None
        category_map = category_name_map.get(node.payload.category.name)
        if category_map is None:
            return None
        end_map = category_map.get(node.payload.category)
        if end_map is None:
            return None
        return end_map.get(node.payload.token_end_index)

    def has_start(self, start):
        return start in self._map

    def has_end(self, end):
        return end in self._reverse_map

    def has_range(self, start, end):
        return (start, end) in self._ranges
