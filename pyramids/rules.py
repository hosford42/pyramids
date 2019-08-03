from sys import intern

from pyramids import categorization, trees, scoring
from pyramids.categorization import Category, CATEGORY_WILDCARD, make_property_set, Property

__author__ = 'Aaron Hosford'
__all__ = [
    'PropertyInheritanceRule',
    'ParseRule',
    'LeafRule',
    'SetRule',
    'SuffixRule',
    'BranchRule',
    'SequenceRule',
    'SubtreeMatchRule',
    'CompoundMatchRule',
    'HeadMatchRule',
    'AnyTermMatchRule',
    'AllTermsMatchRule',
    'OneTermMatchRule',
    'LastTermMatchRule',
    'ConjunctionRule',
]


CASE_FREE = Property.get("case_free")
MIXED_CASE = Property.get("mixed_case")
TITLE_CASE = Property.get("title_case")
UPPER_CASE = Property.get("upper_case")
LOWER_CASE = Property.get("lower_case")

CONJUNCTION_PROPERTY = Property.get("conjunction")
COMPOUND_PROPERTY = Property.get("compound")
SIMPLE_PROPERTY = Property.get("simple")
SINGLE_PROPERTY = Property.get("single")


class PropertyInheritanceRule:

    def __init__(self, category, positive_additions, negative_additions):
        self._category = category
        self._positive_additions = make_property_set(positive_additions)
        self._negative_additions = make_property_set(negative_additions)

    def __call__(self, category_name, positive, negative):
        category = Category(category_name, positive, negative)
        if ((self.category.is_wildcard() or self.category.name is category.name) and
                self.category.positive_properties <= category.positive_properties and
                self.category.negative_properties <= category.negative_properties):
            return self.positive_additions, self.negative_additions
        else:
            return None

    def __str__(self):
        result = str(self.category) + ":"
        if self._positive_additions:
            result += ' ' + ' '.join(sorted(self._positive_additions))
        if self._negative_additions:
            result += ' -' + ' -'.join(sorted(self._negative_additions))
        return result

    def __repr__(self):
        return (type(self).__name__ + "(" + repr(self.category) + ", " + repr(self.positive_additions) + ", " +
                repr(self.negative_additions) + ")")

    @property
    def category(self):
        return self._category

    @property
    def positive_additions(self):
        return self._positive_additions

    @property
    def negative_additions(self):
        return self._negative_additions


class ParseRule:

    def __init__(self, default_score=None, default_accuracy=None):
        if default_score is None:
            default_score = .5
        if default_accuracy is None:
            default_accuracy = 0.001
        self._scoring_measures = {None: (default_score, default_accuracy)}

    # def __str__(self):
    #     raise NotImplementedError()

    def calculate_weighted_score(self, parse_node):
        default_score, default_weight = self._scoring_measures[None]
        total_score = default_score * default_weight
        total_weight = default_weight
        for measure in self.iter_scoring_measures(parse_node):
            if measure in self._scoring_measures:
                score, weight = self._scoring_measures[measure]
                total_score += score * weight
                total_weight += weight
        return total_score, total_weight

    def adjust_score(self, parse_node, target):
        if not 0 <= target <= 1:
            raise ValueError("Score target must be in the interval [0, 1].")
        default_score, default_weight = self._scoring_measures[None]
        error = (target - default_score) ** 2
        weight_target = 1 - error
        default_score += (target - default_score) * .1
        default_weight += (weight_target - default_weight) * .1
        self._scoring_measures[None] = (default_score, default_weight)
        for measure in self.iter_scoring_measures(parse_node):
            if measure not in self._scoring_measures:
                self._scoring_measures[measure] = self._scoring_measures[None]
            score, weight = self._scoring_measures[measure]
            error = (target - score) ** 2
            weight_target = 1 - error
            score += (target - score) * .1
            weight += (weight_target - weight) * 1
            self._scoring_measures[measure] = (score, weight)

    def get_score(self, measure):
        if measure in self._scoring_measures:
            return self._scoring_measures[measure]
        else:
            return self._scoring_measures[None]

    def set_score(self, measure, score, accuracy):
        if not isinstance(measure, scoring.ScoringMeasure):
            measure = scoring.ScoringMeasure(measure)
        score = float(score)
        accuracy = float(accuracy)
        if not 0 <= score <= 1:
            raise ValueError("Score must be in the interval [0, 1].")
        if not 0 <= accuracy <= 1:
            raise ValueError("Accuracy must be in the interval [0, 1].")
        # noinspection PyTypeChecker
        self._scoring_measures[measure] = (score, accuracy)

    def iter_all_scoring_measures(self):
        return iter(self._scoring_measures)

    def iter_scoring_measures(self, parse_node):
        raise NotImplementedError()


class LeafRule(ParseRule):
    """Used by Parser to identify base-level (atomic) tokens, which are the
    leaves in a parse tree."""

    def __init__(self, category):
        super().__init__()
        self._category = category

    @property
    def category(self):
        return self._category

    def __contains__(self, token):
        raise NotImplementedError()

    def __call__(self, parser_state, new_token, index):
        if new_token in self:
            positive, negative = self.discover_case_properties(new_token)
            category = self._category.promote_properties(positive, negative)
            category = parser_state.extend_properties(category)
            parser_state.add_node(trees.ParseTreeNode(parser_state.tokens, self, index, category, index))
            return True
        else:
            return False

    @classmethod
    def discover_case_properties(cls, token: str):
        token_uppered = token.upper()
        token_lowered = token.lower()
        positive = set()
        if token_uppered == token_lowered:
            positive.add(CASE_FREE)
        elif token == token_lowered:
            positive.add(LOWER_CASE)
        else:
            if token == token_uppered:
                positive.add(UPPER_CASE)
            if token == token.title():
                positive.add(TITLE_CASE)
                positive.add(MIXED_CASE)
        if not positive:
            positive.add(MIXED_CASE)
        negative = {CASE_FREE, LOWER_CASE, UPPER_CASE, TITLE_CASE, MIXED_CASE} - positive
        return positive, negative

    def iter_scoring_measures(self, parse_node):
        # CAREFUL!!! Scoring measures must be perfectly recoverable via eval(repr(measure))
        yield scoring.ScoringMeasure(tuple(parse_node.tokens[parse_node.start:parse_node.end]))
        for index in range(parse_node.start, parse_node.end):
            yield scoring.ScoringMeasure((index - parse_node.start, parse_node.tokens[index]))


class SetRule(LeafRule):

    def __init__(self, category, tokens):
        super().__init__(category)
        self._tokens = frozenset(intern(token.lower()) for token in tokens)
        self._hash = hash(self._category) ^ hash(self._tokens)

    def __hash__(self):
        return self._hash

    def __eq__(self, other):
        if not isinstance(other, SetRule):
            return NotImplemented
        return self is other or (self._hash == other._hash and self._category == other._category and
                                 self._tokens == other._tokens)

    def __ne__(self, other):
        if not isinstance(other, SetRule):
            return NotImplemented
        return not (self == other)

    def __contains__(self, token):
        return token.lower() in self._tokens

    def __repr__(self):
        return type(self).__name__ + repr((self.category, sorted(self.tokens)))

    def __str__(self):
        return str(self.category) + '.ctg'

    @property
    def tokens(self):
        return self._tokens


class SuffixRule(LeafRule):

    def __init__(self, category, suffixes, positive=True):
        super().__init__(category)
        self._suffixes = frozenset([suffix.lower() for suffix in suffixes])
        self._positive = bool(positive)
        self._hash = hash(self._category) ^ hash(self._suffixes) ^ hash(self._positive)

    def __hash__(self):
        return self._hash

    def __eq__(self, other):
        if not isinstance(other, SuffixRule):
            return NotImplemented
        return self is other or (self._hash == other._hash and self._positive == other._positive and
                                 self._category == other._category and self._suffixes == other._suffixes)

    def __ne__(self, other):
        if not isinstance(other, SuffixRule):
            return NotImplemented
        return not (self == other)

    def __contains__(self, token):
        token = token.lower()
        for suffix in self._suffixes:
            if len(token) > len(suffix) + 1 and token.endswith(suffix):
                return self._positive
        return not self._positive

    def __repr__(self):
        return (type(self).__name__ + "(" + repr(self.category) + ", " + repr(sorted(self.suffixes)) + ", " +
                repr(self.positive) + ")")

    def __str__(self):
        return str(self.category) + ': ' + '-+'[self.positive] + ' ' + ' '.join(sorted(self.suffixes))

    @property
    def suffixes(self):
        return self._suffixes

    @property
    def positive(self):
        return self._positive


class CaseRule(LeafRule):

    def __init__(self, category, case):
        case = Property.get(case)
        assert case in (CASE_FREE, LOWER_CASE, UPPER_CASE, TITLE_CASE, MIXED_CASE)
        super().__init__(category)
        self._case = case
        self._hash = hash(self._category) ^ hash(self._case)

    @property
    def case(self):
        return self._case

    def __hash__(self):
        return self._hash

    def __eq__(self, other):
        if not isinstance(other, CaseRule):
            return NotImplemented
        return self is other or (self._hash == other._hash and self._category == other._category and
                                 self._case == other._case)

    def __ne__(self, other):
        if not isinstance(other, CaseRule):
            return NotImplemented
        return not (self == other)

    def __contains__(self, token):
        positive, negative = self.discover_case_properties(token)
        return self._case in positive

    def __repr__(self):
        return type(self).__name__ + repr((self.category, str(self.case)))

    def __str__(self):
        return self.case + '->' + str(self.category)


class BranchRule(ParseRule):
    """"Used by Parser to identify higher-level (composite) structures,
    which are the branches in a parse tree."""

    def __call__(self, parser_state, new_node):
        raise NotImplementedError()

    def get_link_types(self, parse_node, link_set_index):
        raise NotImplementedError()

    def iter_scoring_measures(self, parse_node):
        # CAREFUL!!! Scoring measures must be perfectly recoverable via eval(repr(measure))

        # TODO: These are basic scoring measures. We could conceivably add
        #       much more sophisticated measures that would allow the
        #       parser to further adjust score based on finer-grained
        #       details of the parse tree node's surrounding details. For
        #       example, we could score separately based on individual
        #       properties and all combinations thereof. Preferably, we
        #       would keep an index of which ones provided the most
        #       accurate scoring contributions and only maintain scores for
        #       those particular measures, as in XCS. We could then have
        #       each rule evolve its own maximally accurate scoring
        #       measures. I have changed the call into this method below to
        #       expect it to belong to the rule instead of being in this
        #       class. This allows each rule to identify its own optimal
        #       set of scoring measures independently of the others. That
        #       makes each rule into a unique classifier system.
        yield scoring.ScoringMeasure(tuple([component.category for component in parse_node.components]))
        for index in range(len(parse_node.components)):
            yield scoring.ScoringMeasure((index, parse_node.components[index].category))
        yield scoring.ScoringMeasure(('head', parse_node.head_token))


class SequenceRule(BranchRule):

    def __init__(self, category, subcategory_sets, head_index, link_type_sets):
        super(BranchRule, self).__init__()
        # TODO: Type checking
        self._category = category
        self._subcategory_sets = tuple(frozenset(subcategory_set) for subcategory_set in subcategory_sets)
        self._head_index = head_index
        self._link_type_sets = tuple(frozenset(link_type_set) for link_type_set in link_type_sets)
        if len(self._link_type_sets) >= len(self._subcategory_sets):
            raise ValueError("Too many link type sets.")
        self._hash = (hash(self._category) ^ hash(self._subcategory_sets) ^ hash(self._head_index) ^
                      hash(self._link_type_sets))
        self._references = frozenset(c.name for s in self._subcategory_sets for c in s)
        self._has_wildcard = CATEGORY_WILDCARD in self._references

    def _iter_forward_halves(self, category_map, index, start):
        # Otherwise, we can't possibly find a match since it would have to fall off the edge
        if len(self._subcategory_sets) - index <= category_map.max_end - start:
            if index < len(self._subcategory_sets):
                for category, end in category_map.iter_forward_matches(start, self._subcategory_sets[index]):
                    for tail in self._iter_forward_halves(category_map, index + 1, end):
                        for node_set in category_map.iter_node_sets(start, category, end):
                            yield [node_set] + tail
            else:
                yield []

    def _iter_backward_halves(self, category_map, index, end):
        # Otherwise, we can't possibly find a match since it would have to fall off the edge
        if index <= end:
            if index >= 0:
                for category, start in category_map.iter_backward_matches(end, self._subcategory_sets[index]):
                    for tail in self._iter_backward_halves(category_map, index - 1, start):
                        for node_set in category_map.iter_node_sets(start, category, end):
                            yield tail + [node_set]
            else:
                yield []

    def _find_matches(self, parser_state, index, new_node_set):
        """Given a starting index in the sequence, attempt to find and add
        all parse node sequences in the parser state that can contain the
        new node at that index."""
        # Check forward halves first, because they're less likely, and if we don't find any, we won't even need to
        # bother looking for backward halves.
        forward_halves = list(self._iter_forward_halves(parser_state.category_map, index + 1, new_node_set.end))
        if forward_halves:
            for backward_half in self._iter_backward_halves(parser_state.category_map, index - 1, new_node_set.start):
                for forward_half in forward_halves:
                    subtrees = backward_half + [new_node_set] + forward_half
                    category = self.get_category(parser_state.parser, [subtree.category for subtree in subtrees])
                    if self.is_non_recursive(category, subtrees[self._head_index].category):
                        parser_state.add_node(trees.ParseTreeNode(parser_state.tokens, self, self._head_index,
                                                                  category, subtrees))

    def __call__(self, parser_state, new_node_set):
        if not (self._has_wildcard or new_node_set.category.name in self._references):
            return
        for index, subcategory_set in enumerate(self._subcategory_sets):
            for subcategory in subcategory_set:
                if new_node_set.category in subcategory:
                    self._find_matches(parser_state, index, new_node_set)
                    break

    def __hash__(self):
        return self._hash

    def __eq__(self, other):
        if not isinstance(other, SequenceRule):
            return NotImplemented
        return self is other or (self._hash == other._hash and self._head_index == other._head_index and
                                 self._subcategory_sets == other._subcategory_sets and
                                 self._link_type_sets == other._link_type_sets)

    def __ne__(self, other):
        if not isinstance(other, SequenceRule):
            return NotImplemented
        return self is not other and (self._hash != other._hash or self._head_index != other._head_index or
                                      self._subcategory_sets != other._subcategory_sets or
                                      self._link_type_sets != other._link_type_sets)

    def __str__(self):
        result = str(self.category) + ':'
        for index in range(len(self._subcategory_sets)):
            result += ' '
            if index == self._head_index:
                result += '*'
            result += '|'.join(sorted(str(category) for category in self._subcategory_sets[index]))
            if index < len(self._link_type_sets):
                for link_type, left, right in sorted(self._link_type_sets[index]):
                    result += ' '
                    if left:
                        result += '<'
                    result += link_type
                    if right:
                        result += '>'
        return result

    def __repr__(self):
        return (type(self).__name__ + "(" + repr(self.category) + ", " +
                repr([sorted(subcategory_set) for subcategory_set in self.subcategory_sets]) + ", " +
                repr(self._head_index) + ", " +
                repr([sorted(link_type_set) for link_type_set in self.link_type_sets]) + ")")

    @property
    def category(self):
        """The category (and required properties) generated by this rule."""
        return self._category

    @property
    def subcategory_sets(self):
        """The subcategories that must appear consecutively to satisfy this rule."""
        return self._subcategory_sets

    @property
    def head_index(self):
        """The index of the head element of the sequence."""
        return self._head_index

    @property
    def link_type_sets(self):
        """The link types & directions that are used to build the language graph."""
        return self._link_type_sets

    @property
    def head_category_set(self):
        """The category set for the head of the generated parse tree nodes."""
        return self._subcategory_sets[self._head_index]

    def get_link_types(self, parse_node, link_set_index):
        return self._link_type_sets[link_set_index]

    def get_category(self, parser, subtree_categories):
        head_category = subtree_categories[self._head_index]
        if self.category.is_wildcard():
            category = categorization.Category(head_category.name, self.category.positive_properties,
                                               self.category.negative_properties)
        else:
            category = self.category
        positive = set(head_category.positive_properties)
        negative = set(head_category.negative_properties)
        for prop in parser.any_promoted_properties:
            for subtree_category in subtree_categories:
                if prop in subtree_category.positive_properties:
                    positive.add(prop)
                    negative.discard(prop)
                    break
            if prop not in positive:
                for subtree_category in subtree_categories:
                    if prop not in subtree_category.negative_properties:
                        break
                else:
                    negative.add(prop)
        for prop in parser.all_promoted_properties:
            for subtree_category in subtree_categories:
                if prop in subtree_category.negative_properties:
                    negative.add(prop)
                    positive.discard(prop)
                    break
            if prop not in negative:
                for subtree_category in subtree_categories:
                    if prop not in subtree_category.positive_properties:
                        break
                else:
                    positive.add(prop)
        # return parser.extend_properties(category.promote_properties(positive, negative))
        return category.promote_properties(positive, negative)

    def is_non_recursive(self, result_category, head_category):
        return (len(self.subcategory_sets) > 1 or

                # TODO: Can we make this better?
                result_category not in head_category or
                (result_category.positive_properties > head_category.positive_properties) or
                (result_category.negative_properties > head_category.negative_properties))


class SubtreeMatchRule:

    def __init__(self, positive_properties, negative_properties):
        self._positive_properties = make_property_set(positive_properties)
        self._negative_properties = make_property_set(negative_properties)

    @property
    def positive_properties(self):
        return self._positive_properties

    @property
    def negative_properties(self):
        return self._negative_properties

    def __str__(self):
        raise NotImplementedError()

    def __repr__(self):
        return (type(self).__name__ + "(" + repr(self._positive_properties) + ", " +
                repr(self._negative_properties) + ")")

    # def __eq__(self, other):
    #     raise NotImplementedError()
    #
    # def __ne__(self, other):
    #     raise NotImplementedError()
    #
    # def __le__(self, other):
    #     raise NotImplementedError()
    #
    # def __ge__(self, other):
    #     raise NotImplementedError()
    #
    # def __lt__(self, other):
    #     raise NotImplementedError()
    #
    # def __gt__(self, other):
    #     raise NotImplementedError()

    def __call__(self, category_list, head_index):
        raise NotImplementedError()


# compound()
class CompoundMatchRule(SubtreeMatchRule):

    def __str__(self):
        return str(categorization.Category('compound', self._positive_properties, self._negative_properties))

    def __call__(self, category_list, head_index):
        # Stop before the term that immediately precedes the head
        for index in range(head_index - 1):
            if ((not self._positive_properties <= category_list[index].positive_properties) or
                    (self._negative_properties & category_list[index].positive_properties)):
                return False
        return True


# head()
class HeadMatchRule(SubtreeMatchRule):

    def __str__(self):
        return str(categorization.Category('head', self._positive_properties, self._negative_properties))

    def __call__(self, category_list, head_index):
        return ((self._positive_properties <= category_list[head_index].positive_properties) and
                not (self._negative_properties & category_list[head_index].positive_properties))


# any_term()
class AnyTermMatchRule(SubtreeMatchRule):

    def __str__(self):
        return str(categorization.Category('any_term', self._positive_properties, self._negative_properties))

    def __call__(self, category_list, head_index):
        for index in range(len(category_list)):
            if index == head_index:
                continue
            if ((self._positive_properties <= category_list[index].positive_properties) and
                    not (self._negative_properties & category_list[index].positive_properties)):
                return True
        return False


# all_terms(),
class AllTermsMatchRule(SubtreeMatchRule):

    def __str__(self):
        return str(categorization.Category('all_terms', self._positive_properties, self._negative_properties))

    def __call__(self, category_list, head_index):
        for index in range(len(category_list)):
            if index == head_index:
                continue
            if (not (self._positive_properties <= category_list[index].positive_properties) or
                    (self._negative_properties & category_list[index].positive_properties)):
                return False
        return True


# one_term()
class OneTermMatchRule(SubtreeMatchRule):

    def __str__(self):
        return str(categorization.Category('one_term', self._positive_properties, self._negative_properties))

    def __call__(self, category_list, head_index):
        found = False
        for index in range(len(category_list)):
            if index == head_index:
                continue
            if ((self._positive_properties <= category_list[index].positive_properties) and
                    not (self._negative_properties & category_list[index].positive_properties)):
                if found:
                    return False
                found = True
        return found


# last_term()
class LastTermMatchRule(SubtreeMatchRule):

    def __str__(self):
        return str(categorization.Category('last_term', self._positive_properties, self._negative_properties))

    def __call__(self, category_list, head_index):
        return ((self._positive_properties <= category_list[-1].positive_properties) and
                not (self._negative_properties & category_list[-1].positive_properties))


# TODO: This class is eating up more than 2/3 of the parse time, all by itself. It's broken. Rewrite it.
# TODO: Define properties in the .ini that are used to indicate compound, simple, and single conjunctions. These
#       properties should be added automatically by conjunction rules unless overridden in the properties of the
#       conjunction's category.
class ConjunctionRule(BranchRule):

    def __init__(self, category, match_rules, property_rules, leadup_categories, conjunction_categories,
                 followup_categories, leadup_link_types, followup_link_types, single=False, compound=True):
        super(BranchRule, self).__init__()

        # TODO: Type checking

        self._category = category

        # TODO: Do something with this... This is the list of conditions that must be met for the rule to match.
        self._match_rules = tuple(match_rules)

        # TODO: Do something with this... This is the list of conditions that must be met for
        self._property_rules = tuple(property_rules)

        self._leadup_categories = frozenset(leadup_categories or ())
        self._conjunction_categories = frozenset(conjunction_categories)
        self._followup_categories = frozenset(followup_categories)
        self._leadup_link_types = frozenset(leadup_link_types)
        self._followup_link_types = frozenset(followup_link_types)

        # Can we accept only a followup?
        self._single = bool(single) or leadup_categories is None

        # Can we accept more than 2 terms?
        self._compound = bool(compound) and leadup_categories is not None

        subcategory_sets = (self._leadup_categories, self._conjunction_categories, self._followup_categories)
        self._hash = (hash(self._category) ^ hash(subcategory_sets) ^ hash(self._leadup_link_types) ^
                      hash(self._followup_link_types) ^ hash(self._single) ^ hash(self._compound))
        self._references = frozenset(category.name for category_set in subcategory_sets
                                     for category in category_set)
        self._has_wildcard = CATEGORY_WILDCARD in self._references

    def _can_match(self, subtree_categories, head_index):
        if not self._match_rules:
            return True
        for match_rules in self._match_rules:
            if all(rule(subtree_categories, head_index) for rule in match_rules):
                return True
        return False

    def _iter_forward_halves(self, category_map, state, start):
        if state == -1:  # Leadup case/exception
            for category, end in category_map.iter_forward_matches(start, self._leadup_categories):
                for node_set in category_map.iter_node_sets(start, category, end):
                    for tail in self._iter_forward_halves(category_map, 0, end):
                        yield [node_set] + tail
                    if self._compound:
                        for tail in self._iter_forward_halves(category_map, -1, end):
                            yield [node_set] + tail
        elif state == 0:  # Conjunction
            for category, end in category_map.iter_forward_matches(start, self._conjunction_categories):
                for node_set in category_map.iter_node_sets(start, category, end):
                    for tail in self._iter_forward_halves(category_map, 1, end):
                        yield [node_set] + tail
        elif state == 1:  # Followup case/exception
            for category, end in category_map.iter_forward_matches(start, self._followup_categories):
                for node_set in category_map.iter_node_sets(start, category, end):
                    yield [node_set]
        else:
            raise Exception("Unexpected state: " + repr(state))

    def _iter_backward_halves(self, category_map, state, end):
        if state == -1:  # Leadup case/exception
            for category, start in category_map.iter_backward_matches(end, self._leadup_categories):
                for node_set in category_map.iter_node_sets(start, category, end):
                    if self._compound:
                        for tail in self._iter_backward_halves(category_map, -1, start):
                            yield tail + [node_set]
                    yield [node_set]
        elif state == 0:  # Conjunction
            for category, start in category_map.iter_backward_matches(end, self._conjunction_categories):
                for node_set in category_map.iter_node_sets(start, category, end):
                    for tail in self._iter_backward_halves(category_map, -1, start):
                        yield tail + [node_set]
                    if self._single:
                        yield [node_set]
        else:
            # We don't need to handle followups because _find_matches will
            # never call this with that state
            raise Exception("Unexpected state: " + repr(state))

    def _find_matches(self, parser_state, state, new_node_set):
        """Given a starting state (-1 for leadup, 0 for conjunction, 1 for followup), attempt to find and add all parse
        node sequences in the parser state that can contain the new node in that state."""
        # Check forward halves first, because they're less likely, and if we don't find any, we won't even need to
        # bother looking for backward halves.
        forward_halves = list(self._iter_forward_halves(parser_state.category_map, state, new_node_set.start))
        if forward_halves:
            if state == -1:  # Leadup case/exception
                for forward_half in forward_halves:
                    head_offset = len(forward_half) - 2
                    subtree_categories = [subtree.category for subtree in forward_half]
                    if self._can_match(subtree_categories, head_offset):
                        category = self.get_category(parser_state.parser, subtree_categories, head_offset)
                        if self.is_non_recursive(category, forward_half[head_offset].category):
                            parser_state.add_node(trees.ParseTreeNode(parser_state.tokens, self, head_offset,
                                                                      category, forward_half))
                if self._compound:
                    for backward_half in self._iter_backward_halves(parser_state.category_map, -1, new_node_set.start):
                        for forward_half in forward_halves:
                            subtrees = backward_half + forward_half
                            head_offset = len(subtrees) - 2
                            subtree_categories = [subtree.category for subtree in subtrees]
                            if self._can_match(subtree_categories, head_offset):
                                category = self.get_category(parser_state.parser, subtree_categories, head_offset)
                                if self.is_non_recursive(category, subtrees[head_offset].category):
                                    parser_state.add_node(trees.ParseTreeNode(parser_state.tokens, self,
                                                                              head_offset, category, subtrees))
            elif state == 0:  # Conjunction
                if self._single:
                    for forward_half in forward_halves:
                        head_offset = len(forward_half) - 2
                        subtree_categories = [subtree.category for subtree in forward_half]
                        if self._can_match(subtree_categories, head_offset):
                            category = self.get_category(parser_state.parser, subtree_categories, head_offset)
                            if self.is_non_recursive(category, forward_half[head_offset].category):
                                parser_state.add_node(trees.ParseTreeNode(parser_state.tokens, self, head_offset,
                                                                          category, forward_half))
                for backward_half in self._iter_backward_halves(parser_state.category_map, -1, new_node_set.start):
                    for forward_half in forward_halves:
                        subtrees = backward_half + forward_half
                        head_offset = len(subtrees) - 2
                        subtree_categories = [subtree.category for subtree in subtrees]
                        if self._can_match(subtree_categories, head_offset):
                            category = self.get_category(parser_state.parser, subtree_categories, head_offset)
                            if self.is_non_recursive(category, subtrees[head_offset].category):
                                parser_state.add_node(trees.ParseTreeNode(parser_state.tokens, self, head_offset,
                                                                          category, subtrees))
            elif state == 1:  # Followup case/exception
                for backward_half in self._iter_backward_halves(parser_state.category_map, 0, new_node_set.start):
                    for forward_half in forward_halves:
                        subtrees = backward_half + forward_half
                        head_offset = len(subtrees) - 2
                        subtree_categories = [subtree.category for subtree in subtrees]
                        if self._can_match(subtree_categories, head_offset):
                            category = self.get_category(parser_state.parser, subtree_categories, head_offset)
                            if self.is_non_recursive(category, subtrees[head_offset].category):
                                parser_state.add_node(trees.ParseTreeNode(parser_state.tokens, self, head_offset,
                                                                          category, subtrees))
            else:
                raise Exception("Unexpected state: " + repr(state))

    # TODO: Think about it really hard: Why does this method (or SequenceRule's) consider anything other than the final
    #       state/index? Maybe there is a good reason, but shouldn't we skip that if we're strictly appending new
    #       tokens? This may be an opportunity for an extreme speedup.
    def __call__(self, parser_state, new_node_set):
        if not (self._has_wildcard or new_node_set.category.name in self._references):
            return
        for state, subcategory_set in ((-1, self._leadup_categories), (0, self._conjunction_categories),
                                       (1, self._followup_categories)):
            for subcategory in subcategory_set:
                if new_node_set.category in subcategory:
                    self._find_matches(parser_state, state, new_node_set)
                    break  # We only need to do it once for each state

    def __hash__(self):
        return self._hash

    def __eq__(self, other):
        if not isinstance(other, ConjunctionRule):
            return NotImplemented
        return self is other or (self._hash == other._hash and self._single == other._single and
                                 self._compound == other._compound and
                                 self._leadup_link_types == other._leadup_link_types and
                                 self._followup_link_types == other._followup_link_types and
                                 self._category == other._category and
                                 self._conjunction_categories == other._conjunction_categories and
                                 self._leadup_categories == other._leadup_categories and
                                 self._followup_categories == other._followup_categories)

    def __ne__(self, other):
        if not isinstance(other, ConjunctionRule):
            return NotImplemented
        return self is not other and not (self._hash == other._hash and self._single == other._single and
                                          self._compound == other._compound and
                                          self._leadup_link_types == other._leadup_link_types and
                                          self._followup_link_types == other._followup_link_types and
                                          self._category == other._category and
                                          self._conjunction_categories == other._conjunction_categories and
                                          self._leadup_categories == other._leadup_categories and
                                          self._followup_categories == other._followup_categories)

    def __str__(self):
        result = str(self.category) + ':'
        for rules in self._match_rules:
            result += ' [' + ' '.join(str(rule) for rule in rules) + ']'
        for properties, rules in self._property_rules:
            result += (' ' + ','.join(('' if is_positive else '-') + prop for prop, is_positive in properties) +
                       '[' + ' '.join(str(rule) for rule in rules) + ']')
        for prefix, category_set, link_types in (('+' if self._compound else ('-' if self._single else ''),
                                                  self._leadup_categories, self._leadup_link_types),
                                                 ('*', self._conjunction_categories, self._followup_link_types),
                                                 ('', self._followup_categories, None)):
            result += ' ' + prefix + '|'.join(sorted(str(category) for category in category_set))
            if link_types:
                for link_type, left, right in sorted(link_types):
                    result += ' '
                    if left:
                        result += '<'
                    result += link_type
                    if right:
                        result += '>'
        return result

    def __repr__(self):
        return (type(self).__name__ + "(" + repr(self.category) + ", " +
                repr([sorted(subcategory_set) for subcategory_set in self._leadup_categories]) + ", " +
                repr([sorted(subcategory_set) for subcategory_set in self._conjunction_categories]) + ", " +
                repr([sorted(subcategory_set) for subcategory_set in self._followup_categories]) + ", " +
                repr(self._leadup_link_types) + ", " + repr(self._followup_link_types) + ", " +
                repr(self._single) + ", " + repr(self._compound) + ")")

    @property
    def category(self):
        """The category (and required properties) generated by this rule."""
        return self._category

    @property
    def head_category_set(self):
        """The category set for the head of the generated parse tree nodes."""
        return self._conjunction_categories

    @property
    def leadup_categories(self):
        return self._leadup_categories

    @property
    def conjunction_categories(self):
        return self._conjunction_categories

    @property
    def followup_categories(self):
        return self._followup_categories

    @property
    def leadup_link_types(self):
        return self._leadup_link_types

    @property
    def followup_link_types(self):
        return self._followup_link_types

    @property
    def single(self):
        return self._single

    @property
    def compound(self):
        return self._compound

    @property
    def head_index(self):
        return 1

    @property
    def link_type_sets(self):
        return (frozenset([(self._leadup_link_types, True, False)]),
                frozenset([(self._followup_link_types, False, True)]),)

    def get_link_types(self, parse_node, link_set_index):
        # If it's the last link set interval
        if link_set_index + 2 >= len(parse_node.components):
            return self._followup_link_types
        else:
            return self._leadup_link_types

    # TODO: Add this to BranchRule as unimplemented
    def get_category(self, parser, subtree_categories, head_index=None):
        if head_index is None:
            # Figure out what head index to use
            head_index = len(subtree_categories) - 2
        if self.category.is_wildcard():
            category = categorization.Category(subtree_categories[-1].name, self.category.positive_properties,
                                               self.category.negative_properties)
        else:
            category = self.category

        # Start out with the intersection of shared properties for all non-
        # head subtree categories
        positive = set(subtree_categories[-1].positive_properties)
        negative = set(subtree_categories[-1].negative_properties)
        for index in range(len(subtree_categories) - 2):
            positive &= set(subtree_categories[index].positive_properties)
            negative &= set(subtree_categories[index].negative_properties)

        # Then apply the standard promotion rules
        for prop in parser.any_promoted_properties:
            for subtree_category in subtree_categories:
                if prop in subtree_category.positive_properties:
                    positive.add(prop)
                    negative.discard(prop)
                    break
            if prop not in positive:
                for subtree_category in subtree_categories:
                    if prop not in subtree_category.negative_properties:
                        break
                else:
                    negative.add(prop)
        for prop in parser.all_promoted_properties:
            for subtree_category in subtree_categories:
                if prop in subtree_category.negative_properties:
                    negative.add(prop)
                    positive.discard(prop)
                    break
            if prop not in negative:
                for subtree_category in subtree_categories:
                    if prop not in subtree_category.positive_properties:
                        break
                else:
                    positive.add(prop)

        # Add the standard properties
        # TODO: Load these from the .ini instead of hard-coding them.
        positive.add(CONJUNCTION_PROPERTY)
        negative.discard(CONJUNCTION_PROPERTY)
        if len(subtree_categories) > 3:
            positive.add(COMPOUND_PROPERTY)
            negative.discard(COMPOUND_PROPERTY)
            negative.add(SIMPLE_PROPERTY)
            positive.discard(SIMPLE_PROPERTY)
            negative.add(SINGLE_PROPERTY)
            positive.discard(SINGLE_PROPERTY)
        elif len(subtree_categories) < 3:
            negative.add(SIMPLE_PROPERTY)
            positive.discard(SIMPLE_PROPERTY)
            negative.add(COMPOUND_PROPERTY)
            positive.discard(COMPOUND_PROPERTY)
            positive.add(SINGLE_PROPERTY)
            negative.discard(SINGLE_PROPERTY)
        else:
            negative.add(COMPOUND_PROPERTY)
            positive.discard(COMPOUND_PROPERTY)
            positive.add(SIMPLE_PROPERTY)
            negative.discard(SIMPLE_PROPERTY)
            negative.add(SINGLE_PROPERTY)
            positive.discard(SINGLE_PROPERTY)

        # And finally, apply property rules specific to this parse rule
        for properties, property_rules in self._property_rules:
            matched = all(rule(subtree_categories, head_index) for rule in property_rules)
            for (prop, is_positive) in properties:
                if is_positive == matched:
                    positive.add(prop)
                    negative.discard(prop)
                else:
                    negative.add(prop)
                    positive.discard(prop)

        # return parser.extend_properties(category.promote_properties(positive, negative))
        return category.promote_properties(positive, negative)

    # noinspection PyUnusedLocal
    @staticmethod
    def is_non_recursive(result_category, head_category):
        # It's *never* recursive, because we require more than one token for every conjunctive phrase
        return True
