# -*- coding: utf-8 -*-
from itertools import product

from pyramids import graphs, trees
from pyramids.rules import leaf, conjunction
from pyramids.utils import extend_properties


class GenerationAlgorithm:

    def generate(self, model, sentence):
        assert isinstance(sentence, graphs.ParseGraph)
        return self._generate(model, sentence.root_index, sentence)

    def _generate(self, model, head_node: int, sentence):
        head_spelling = sentence[head_node][1]
        head_category = sentence[head_node][3]

        # Find the subnodes of the head node
        subnodes = sentence.get_sinks(head_node)

        # Build the subtree for each subnode
        subtrees = {sink: self._generate(model, sink, sentence) for sink in subnodes}

        # Find all leaves for the head node
        subtrees[head_node] = set()
        positive_case_properties, negative_case_properties = leaf.LeafRule.discover_case_properties(head_spelling)
        for rule in model.primary_leaf_rules:
            if head_spelling in rule:
                category = rule.category.promote_properties(positive_case_properties, negative_case_properties)
                category = extend_properties(model, category)
                if category in head_category:
                    tree = trees.BuildTreeNode(rule, category, head_spelling, head_node)
                    subtrees[head_node].add(tree)
        if not subtrees[head_node]:
            for rule in model.secondary_leaf_rules:
                if head_spelling in rule:
                    category = rule.category.promote_properties(positive_case_properties, negative_case_properties)
                    category = extend_properties(model, category)
                    if category in head_category:
                        tree = trees.BuildTreeNode(rule, category, head_spelling, head_node)
                        subtrees[head_node].add(tree)

        results = set()
        backup_results = set()
        emergency_results = set()

        # If we only have the head node, the leaves for the head node can
        # serve as results
        if len(subtrees) == 1:
            if head_node == sentence.root_index:
                for tree in subtrees[head_node]:
                    if tree.category in sentence.root_category:
                        results.add(tree)
                    else:
                        backup_results.add(tree)
            else:
                results = set(subtrees[head_node])
        else:
            results = set()

        # For each possible subtree headed by the head node, attempt to
        # iteratively expand coverage out to all subnodes via branch rules.
        # TODO: This loop only works for non-conjunction rules because it
        #       assumes the link_type_sets and head_index properties are
        #       available. Move the code into appropriate methods on the
        #       branch rule subclasses and call into them.
        # TODO: Break this up into functions so it isn't so deeply nested.
        insertion_queue = set(subtrees[head_node])
        while insertion_queue:
            head_tree = insertion_queue.pop()
            for rule in model.branch_rules:
                fits = False
                for subcategory in rule.head_category_set:
                    if head_tree.category in subcategory:
                        fits = True
                        break
                if not fits:
                    continue
                possible_components = []
                failed = False
                # TODO: AttributeError: 'ConjunctionRule' object has no
                #       attribute 'link_type_sets'
                for index in range(len(rule.link_type_sets)):
                    required_incoming = set()
                    required_outgoing = set()
                    for link_type, left, right in rule.link_type_sets[index]:
                        if (right and index < rule.head_index) or (left and index >= rule.head_index):
                            required_incoming.add(link_type)
                        if (left and index < rule.head_index) or (right and index >= rule.head_index):
                            required_outgoing.add(link_type)
                    component_candidates = self.get_component_candidates(model, head_category, head_node, index,
                                                                         required_incoming, required_outgoing, rule,
                                                                         sentence, subnodes, subtrees)
                    if not component_candidates:
                        failed = True
                        break
                    possible_components.append(component_candidates)
                if failed:
                    continue
                possible_components.insert(rule.head_index, {head_tree})
                for component_combination in product(*possible_components):
                    covered = set()
                    for component in component_combination:
                        if component.node_coverage & covered:
                            break
                        covered |= component.node_coverage
                    else:
                        category = rule.get_category(model, [component.category for component in component_combination])
                        if rule.is_non_recursive(category, head_tree.category):
                            new_tree = trees.BuildTreeNode(rule, category, head_tree.head_spelling,
                                                           head_tree.head_index, component_combination)
                            if new_tree not in results:
                                if subnodes <= new_tree.node_coverage:
                                    if new_tree.head_index != sentence.root_index or category in sentence.root_category:
                                        results.add(new_tree)
                                    else:
                                        backup_results.add(new_tree)
                                emergency_results.add(new_tree)
                                insertion_queue.add(new_tree)
        if results:
            return results
        elif backup_results:
            return backup_results
        else:
            return emergency_results

    @staticmethod
    def get_component_candidates(model, head_category, head_node, index, required_incoming, required_outgoing,
                                 rule, sentence, subnodes, subtrees):
        component_head_candidates = subnodes.copy()
        for link_type in required_incoming:
            if link_type not in model.sequence_rules_by_link_type:
                continue
            component_head_candidates &= {source for source in sentence.get_sources(head_node)
                                          if link_type in sentence.get_labels(source, head_node)}
            if not component_head_candidates:
                break
        if not component_head_candidates:
            return None
        for link_type in required_outgoing:
            if link_type not in model.sequence_rules_by_link_type:
                continue
            component_head_candidates &= {sink for sink in sentence.get_sinks(head_node)
                                          if link_type in sentence.get_labels(head_node, sink)}
            if not component_head_candidates:
                break
        if not component_head_candidates:
            return None
        component_candidates = set()
        if isinstance(rule, conjunction.ConjunctionRule):
            for candidate in component_head_candidates:
                for subtree in subtrees[candidate]:
                    if subtree.category in head_category:
                        component_candidates.add(subtree)
                        break
                else:
                    for subtree in subtrees[candidate]:
                        component_candidates.add(subtree)
                        break
        else:
            cat_names = {category.name
                         for category in rule.subcategory_sets[index if index < rule.head_index else index + 1]}
            for candidate in component_head_candidates:
                for subtree in subtrees[candidate]:
                    if subtree.category.name in cat_names:
                        good = False
                        cat_index = (index if index < rule.head_index else index + 1)
                        for category in rule.subcategory_sets[cat_index]:
                            if subtree.category in category:
                                good = True
                                break
                        if good:
                            component_candidates.add(subtree)
        return component_candidates
