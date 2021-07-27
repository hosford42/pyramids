# -*- coding: utf-8 -*-

"""
Parsing of grammar files
"""

from typing import Tuple, List, Iterable, FrozenSet, Any

from pyramids.categorization import Category, Property, LinkLabel
from pyramids.rules.conjunction import ConjunctionRule
from pyramids.rules.last_term_match import LastTermMatchRule
from pyramids.rules.one_term_match import OneTermMatchRule
from pyramids.rules.all_terms_match import AllTermsMatchRule
from pyramids.rules.any_term_match import AnyTermMatchRule
from pyramids.rules.head_match import HeadMatchRule
from pyramids.rules.compound_match import CompoundMatchRule
from pyramids.rules.sequence import SequenceRule
from pyramids.rules.subtree_match import SubtreeMatchRule
from pyramids.rules.suffix import SuffixRule
from pyramids.rules.token_set import SetRule
from pyramids.rules.property_inheritance import PropertyInheritanceRule

__all__ = [
    'GrammarSyntaxError',
    'GrammarParserError',
    'GrammarParser',
]


class GrammarParserError(Exception):
    """An error while parsing a grammar file"""

    def __init__(self, msg: str = None, filename: str = None, lineno: int = 1, offset: int = 1,
                 text: str = None):
        super().__init__(msg, (filename, lineno, offset, text))
        self.msg = msg
        self.args = (msg, (filename, lineno, offset, text))

        self.filename = filename
        self.lineno = lineno
        self.offset = offset
        self.text = text

    def __repr__(self) -> str:
        return type(self).__name__ + repr((self.msg,
                                           (self.filename, self.lineno, self.offset, self.text)))

    def set_info(self, filename: str = None, lineno: int = None, offset: int = None,
                 text: str = None) -> None:
        """Set additional information on the exception after it has been raised."""
        if filename is not None:
            self.filename = filename
        if lineno is not None:
            self.lineno = lineno
        if offset is not None:
            self.offset = offset
        if text is not None:
            self.text = text
        self.args = (self.msg, (self.filename, self.lineno, self.offset, self.text))


class GrammarSyntaxError(GrammarParserError, SyntaxError):
    """A syntax error detected in a grammar file"""

    def __init__(self, msg: str, filename: str = None, lineno: int = 1, offset: int = 1,
                 text: str = None):
        super().__init__(msg, (filename, lineno, offset, text))

    def __repr__(self) -> str:
        return super(GrammarParserError, self).__repr__()


class GrammarParser:
    """Parsing of grammar files"""

    @staticmethod
    def parse_category(definition: str, offset: int = 1) -> Category:
        """Parse a category string, in the syntax used by grammar files."""
        definition = definition.strip()
        if '(' in definition:
            if not definition.endswith(')'):
                raise GrammarSyntaxError("Expected: ')' in category definition",
                                         offset=offset + len(definition))
            if definition.count('(') > 1:
                raise GrammarSyntaxError("Unexpected: '(' in category definition",
                                         offset=offset + definition.find("(",
                                                                         definition.find("(") + 1))
            if definition.count(')') > 1:
                raise GrammarSyntaxError("Unexpected: ')' in category definition",
                                         offset=offset + definition.find(")",
                                                                         definition.find(")") + 1))
            name, properties = definition[:-1].split('(')
            if ',' in name:
                raise GrammarSyntaxError("Unexpected: ',' in category definition",
                                         offset=offset + definition.find(","))
            if len(name.split()) > 1:
                raise GrammarSyntaxError("Unexpected: white space in category definition",
                                         offset=offset + len(name) + 1)
            properties = [prop.strip() for prop in properties.split(',')]
            for prop in properties:
                if not prop.strip():
                    if ",," in definition:
                        raise GrammarSyntaxError("Unexpected: ','",
                                                 offset=offset + definition.find(",,") + 1)
                    elif "(," in definition:
                        raise GrammarSyntaxError("Unexpected: ','",
                                                 offset=offset + definition.find("(,") + 1)
                    elif ",)" in definition:
                        raise GrammarSyntaxError("Unexpected: ')'",
                                                 offset=offset + definition.find(",)") + 1)
                    else:
                        raise GrammarSyntaxError("Unexpected: ')'",
                                                 offset=offset + definition.find("()") + 1)
            positive = [prop for prop in properties if not prop.startswith('-')]
            negative = [prop[1:] for prop in properties if prop.startswith('-')]
            for prop in negative:
                if prop.startswith('-'):
                    raise GrammarSyntaxError("Unexpected: '-'",
                                             offset=offset + definition.find('-' + prop))
                if prop in positive:
                    raise GrammarSyntaxError("Unexpected: prop is both positive and negative",
                                             offset=offset + definition.find(prop))
            return Category(name, [Property.get(n) for n in positive],
                            [Property.get(n) for n in negative])
        else:
            if ')' in definition:
                raise GrammarSyntaxError("Unexpected: ')' in category definition",
                                         offset=offset + definition.find(")"))
            if ',' in definition:
                raise GrammarSyntaxError("Unexpected: ',' in category definition",
                                         offset=offset + definition.find(","))
            if len(definition.split()) > 1:
                raise GrammarSyntaxError("Unexpected: white space in category definition",
                                         offset=offset + len(definition.split()[0]) + 1)
            if not definition:
                raise GrammarSyntaxError("Expected: category definition", offset=offset)
            return Category(definition)

    def parse_branch_rule_term(self, term: str, offset: int = 1) -> Tuple[bool, List[Category]]:
        is_head = False
        if term.startswith('*'):
            term = term[1:]
            offset += 1
            is_head = True
            if '*' in term:
                raise GrammarSyntaxError("Unexpected: '*'", offset=offset + term.find('*'))
        subcategories = []
        subcategory_definitions = term.split('|')
        for definition in subcategory_definitions:
            subcategory = self.parse_category(definition, offset=offset)
            subcategories.append(subcategory)
            offset += len(definition) + 1
        if not subcategories:
            raise GrammarSyntaxError("Expected: category", offset=offset)
        return is_head, subcategories

    @staticmethod
    def parse_branch_rule_link_type(term: str, offset: int = 1) -> Tuple[LinkLabel, bool, bool]:
        if '<' in term[1:]:
            raise GrammarSyntaxError("Unexpected: '<'",
                                     offset=offset + term.find('<', term.find('<') + 1))
        if '>' in term[:-1]:
            raise GrammarSyntaxError("Unexpected: '<'", offset=offset + term.find('>'))
        left = term.startswith('<')
        right = term.endswith('>')
        if left:
            term = term[1:]
        if right:
            term = term[:-1]
        if not term:
            raise GrammarSyntaxError("Expected: link type", offset=offset + left)
        return LinkLabel.get(term), left, right

    def parse_branch_rule(self, category: Category, definition: str,
                          offset: int = 1) -> SequenceRule:
        subcategory_sets = []
        link_types = []
        term = ''
        term_start = 0
        head_index = None
        for index in range(len(definition)):
            char = definition[index]
            if char.isspace():
                if not term:
                    continue
                if '>' in term or '<' in term:
                    if not subcategory_sets:
                        raise GrammarSyntaxError("Unexpected: link type",
                                                 offset=offset + term_start)
                    link_type, left, right = self.parse_branch_rule_link_type(term,
                                                                              offset + term_start)
                    if head_index is None:
                        if right:
                            raise GrammarSyntaxError("Unexpected: right link",
                                                     offset=offset + term_start)
                    else:
                        if left:
                            raise GrammarSyntaxError("Unexpected: left link",
                                                     offset=offset + term_start)
                    link_types[-1].add((link_type, left, right))
                else:
                    is_head, subcategories = self.parse_branch_rule_term(term,
                                                                         offset=offset + term_start)
                    if is_head:
                        if head_index is not None:
                            raise GrammarSyntaxError("Unexpected: '*'",
                                                     offset=(offset + term_start + term.find('*')))
                        head_index = len(subcategory_sets)
                    subcategory_sets.append(subcategories)
                    link_types.append(set())
                term = ''
            else:
                if not term:
                    term_start = index
                term += char
        if term:
            is_head, subcategories = self.parse_branch_rule_term(term, offset=offset + term_start)
            if is_head:
                if head_index is not None:
                    raise GrammarSyntaxError("Unexpected: '*'",
                                             offset=offset + term_start + term.find('*'))
                head_index = len(subcategory_sets)
            subcategory_sets.append(subcategories)
            link_types.append(set())
        if not subcategory_sets:
            raise GrammarSyntaxError("Expected: category", offset=offset)
        if link_types[-1]:
            raise GrammarSyntaxError("Expected: category", offset=offset + term_start + len(term))
        link_types = link_types[:-1]
        if head_index is None:
            if len(subcategory_sets) != 1:
                raise GrammarSyntaxError("Expected: '*'", offset=offset + term_start)
            head_index = 0
        return SequenceRule(category, subcategory_sets, head_index, link_types)

    def parse_grammar_definition_file(self, lines: Iterable[str],
                                      filename: str = None) -> List[SequenceRule]:
        branch_rules = []
        category = None
        sequence_found = False
        line_number = 0
        for raw_line in lines:
            line_number += 1
            try:
                line = raw_line.split('#')[0].rstrip()
                if not line:
                    continue
                if line[:1].isspace():
                    if ':' in line:
                        raise GrammarSyntaxError("Unexpected: ':'", offset=1 + line.find(':'))
                    if not category:
                        raise GrammarSyntaxError("Expected: category header",
                                                 offset=1 + line.find(line.strip()))
                    branch_rules.append(
                        self.parse_branch_rule(category, line.lstrip(),
                                               offset=1 + line.find(line.lstrip())))
                    sequence_found = True
                else:
                    if category is not None and not sequence_found:
                        raise GrammarSyntaxError("Expected: category sequence", offset=1)
                    if ':' not in line:
                        raise GrammarSyntaxError("Expected: ':'", offset=1 + len(line))
                    if line.count(':') > 1:
                        raise GrammarSyntaxError("Unexpected: ':'",
                                                 offset=1 + line.find(':', line.find(':') + 1))
                    header, sequence = line.split(':')
                    category = self.parse_category(header)
                    if sequence.strip():
                        branch_rules.append(
                            self.parse_branch_rule(category, sequence.lstrip(),
                                                   offset=1 + sequence.find(sequence.lstrip()))
                        )
                        sequence_found = True
                    else:
                        sequence_found = False
            except GrammarParserError as error:
                error.set_info(filename=filename, lineno=line_number, text=raw_line)
                raise error
            except Exception as original_exception:
                raise GrammarParserError(filename=filename,
                                         lineno=line_number, text=raw_line) from original_exception
        return branch_rules

    def parse_match_rule(self, definition: str, offset: int = 1) -> Tuple[SubtreeMatchRule, ...]:
        if not definition.startswith('['):
            raise GrammarSyntaxError("Expected: '['", offset=offset)
        if not definition.endswith(']'):
            raise GrammarSyntaxError("Expected: ']'", offset=offset + len(definition) - 1)
        generator_map = {
            'any_term': AnyTermMatchRule,
            'all_terms': AllTermsMatchRule,
            'compound': CompoundMatchRule,
            'head': HeadMatchRule,
            'one_term': OneTermMatchRule,
            'last_term': LastTermMatchRule,
        }
        rule_list = []
        for category_definition in definition[1:-1].split():
            category = self.parse_category(category_definition,
                                           offset=1 + definition.find(category_definition))
            generator = generator_map.get(str(category.name), None)
            if generator is None:
                raise GrammarSyntaxError("Unexpected: " + repr(category),
                                         offset=1 + definition.find(category_definition))
            assert callable(generator)
            rule_list.append(generator(category.positive_properties, category.negative_properties))
        if not rule_list:
            raise GrammarSyntaxError("Expected: category")
        return tuple(rule_list)

    def parse_conjunction_rule(self,
                               category: Category,
                               match_rules: List[Tuple[SubtreeMatchRule, ...]],
                               property_rules: List[Tuple[FrozenSet[Tuple[Any, bool]],
                                                    Tuple[SubtreeMatchRule, ...]]],
                               definition: str,
                               offset: int = 1) -> ConjunctionRule:
        single = False
        compound = False
        while definition[:1] in ('+', '-'):
            if definition[0] == '+':
                if compound:
                    raise GrammarSyntaxError("Unexpected: '+'", offset=offset)
                compound = True
            else:
                if single:
                    raise GrammarSyntaxError("Unexpected: '-'", offset=offset)
                single = True
            definition = definition[1:]
            offset += 1
        subcategory_sets = []
        link_types = []
        term = ''
        term_start = 0
        head_index = None
        for index in range(len(definition)):
            char = definition[index]
            if char.isspace():
                if not term:
                    continue
                if '>' in term or '<' in term:
                    if not subcategory_sets:
                        raise GrammarSyntaxError("Unexpected: link type",
                                                 offset=offset + term_start)
                    link_type, left, right = self.parse_branch_rule_link_type(term,
                                                                              offset + term_start)
                    if head_index is None:
                        if right:
                            raise GrammarSyntaxError("Unexpected: right link",
                                                     offset=offset + term_start)
                    else:
                        if left:
                            raise GrammarSyntaxError("Unexpected: left link",
                                                     offset=offset + term_start)
                    link_types[-1].add((link_type, left, right))
                else:
                    if len(subcategory_sets) >= 3:
                        raise GrammarSyntaxError("Unexpected: category",
                                                 offset=offset + term_start)
                    is_head, subcategories = self.parse_branch_rule_term(term,
                                                                         offset=offset + term_start)
                    if is_head:
                        if head_index is not None:
                            raise GrammarSyntaxError("Unexpected: '*'",
                                                     offset=offset + term_start + term.find('*'))
                        head_index = len(subcategory_sets)
                    subcategory_sets.append(subcategories)
                    link_types.append(set())
                term = ''
            else:
                if not term:
                    term_start = index
                term += char
        if term:
            if len(subcategory_sets) >= 3:
                raise GrammarSyntaxError("Unexpected: category", offset=offset + term_start)
            is_head, subcategories = self.parse_branch_rule_term(term, offset=offset + term_start)
            if is_head:
                if head_index is not None:
                    raise GrammarSyntaxError("Unexpected: '*'",
                                             offset=offset + term_start + term.find('*'))
                head_index = len(subcategory_sets)
            subcategory_sets.append(subcategories)
            link_types.append(set())
        if len(subcategory_sets) < 2:
            raise GrammarSyntaxError("Expected: category", offset=offset)
        if link_types[-1]:
            raise GrammarSyntaxError("Expected: category", offset=offset + term_start + len(term))
        link_types = link_types[:-1]
        if head_index is None:
            if len(subcategory_sets) != 1:
                raise GrammarSyntaxError("Expected: '*'", offset=offset + term_start)
            head_index = 0
        assert 2 <= len(subcategory_sets) <= 3
        if len(subcategory_sets) == 3:
            if head_index != 1:
                raise GrammarSyntaxError("Unexpected: category", offset=offset)
            leadup_cats, conjunction_cats, followup_cats = subcategory_sets
            leadup_link_types, followup_link_types = link_types
        else:
            assert len(subcategory_sets) == 2
            if head_index != 0:
                raise GrammarSyntaxError("Expected: category", offset=offset)
            leadup_cats = None
            conjunction_cats, followup_cats = subcategory_sets
            leadup_link_types = set()
            followup_link_types = link_types[0]
        return ConjunctionRule(category, match_rules, property_rules, leadup_cats, conjunction_cats,
                               followup_cats, leadup_link_types, followup_link_types, single,
                               compound)

    def parse_property_inheritance_file(self, lines: Iterable[str],
                                        filename: str = None) -> List[PropertyInheritanceRule]:
        inheritance_rules = []
        line_number = 0
        for raw_line in lines:
            try:
                line_number += 1
                line = raw_line.split('#')[0].rstrip()
                if not line:
                    continue
                if ':' not in line:
                    raise GrammarSyntaxError("Expected: ':'", offset=1 + len(line))
                if line.count(':') > 1:
                    raise GrammarSyntaxError("Unexpected: ':'",
                                             offset=1 + line.find(':', line.find(':') + 1))
                definition, additions = line.split(':')
                try:
                    category = self.parse_category(definition)
                except GrammarParserError as error:
                    error.set_info(text=line)
                    raise error
                except Exception as original_exception:
                    raise GrammarParserError(text=line) from original_exception
                additions = additions.split()
                if not additions:
                    raise GrammarSyntaxError("Expected: property", offset=1 + line.find(':') + 1)
                positive_additions = [addition for addition in additions
                                      if not addition.startswith('-')]
                negative_additions = [addition[1:] for addition in additions
                                      if addition.startswith('-')]
                # Double-negatives are not allowed
                if any(addition.startswith('-') for addition in negative_additions):
                    raise GrammarSyntaxError("Unexpected: '-'", offset=2 + line.find('--'))
                # Check that positive & negative additions don't conflict
                for addition in negative_additions:
                    if addition in positive_additions:
                        raise GrammarSyntaxError("Conflicting property signs: %s" % addition,
                                                 offset=1 + line.find(addition,
                                                                      line.find(addition) + 1))
                inheritance_rules.append(PropertyInheritanceRule(category, positive_additions,
                                                                 negative_additions))
            except GrammarParserError as error:
                if error.text is None:
                    error.set_info(text=raw_line)
                error.set_info(filename=filename, lineno=line_number)
                raise error
        return inheritance_rules

    def parse_conjunctions_file(self, lines: Iterable[str],
                                filename: str = None) -> List[ConjunctionRule]:
        """Load a conjunction grammar file, returning the conjunction rules parsed from it."""
        branch_rules = []
        category = None
        match_rules = []
        match_rules_closed = False
        property_rules = []
        property_rules_closed = False
        sequence_found = False
        line_number = 0
        for raw_line in lines:
            line_number += 1
            try:
                line = raw_line.split('#')[0].rstrip()
                if not line:
                    continue
                if line[:1].isspace():
                    if ':' in line:
                        raise GrammarSyntaxError("Unexpected: ':'", offset=1 + line.find(':'))
                    if not category:
                        raise GrammarSyntaxError("Expected: category header",
                                                 offset=1 + line.find(line.strip()))
                    if line.endswith(']') and '[' in line:
                        if line.lstrip().startswith('['):
                            if match_rules_closed:
                                raise GrammarSyntaxError("Unexpected: matching rule",
                                                         offset=1 + line.find('['))
                            match_rules.append(
                                self.parse_match_rule(line.lstrip(),
                                                      offset=1 + line.find(line.lstrip()))
                            )
                        else:
                            if property_rules_closed:
                                raise GrammarSyntaxError("Unexpected: property rule",
                                                         offset=1 + len(line) - len(line.lstrip()))
                            match_rules_closed = True
                            left_bracket_index = line.index('[')
                            property_names = line[:left_bracket_index].strip().split(',')
                            properties = set()
                            for property_name in property_names:
                                if property_name.startswith('-'):
                                    properties.add((Property.get(property_name[1:]), False))
                                else:
                                    properties.add((Property.get(property_name), True))
                            line_remainder = line[left_bracket_index:]
                            property_rules.append(
                                (frozenset(properties),
                                 self.parse_match_rule(
                                     line_remainder.lstrip(),
                                     offset=1 + line.find(line_remainder.strip()))
                                 ))
                    else:
                        match_rules_closed = True
                        property_rules_closed = True
                        if '[' in line:
                            raise GrammarSyntaxError("Unexpected: '['", offset=1 + line.find('['))
                        if ']' in line:
                            raise GrammarSyntaxError("Unexpected: ']'", offset=1 + line.find(']'))
                        branch_rules.append(
                            self.parse_conjunction_rule(category, match_rules, property_rules,
                                                        line.lstrip(),
                                                        offset=1 + line.find(line.lstrip()))
                        )
                        sequence_found = True
                else:
                    if category is not None and not sequence_found:
                        raise GrammarSyntaxError("Expected: category sequence", offset=1)
                    if ':' not in line:
                        raise GrammarSyntaxError("Expected: ':'", offset=1 + len(line))
                    if line.count(':') > 1:
                        raise GrammarSyntaxError("Unexpected: ':'",
                                                 offset=1 + line.find(':', line.find(':') + 1))
                    header, sequence = line.split(':')
                    category = self.parse_category(header)
                    match_rules = []
                    match_rules_closed = False
                    property_rules = []
                    property_rules_closed = False
                    if sequence.strip():
                        branch_rules.append(
                            self.parse_conjunction_rule(
                                category, match_rules, property_rules, sequence.lstrip(),
                                offset=1 + sequence.find(sequence.lstrip())
                            )
                        )
                        sequence_found = True
                    else:
                        sequence_found = False
            except GrammarParserError as error:
                error.set_info(filename=filename, lineno=line_number, text=raw_line)
                raise error
            except Exception as original_exception:
                raise GrammarParserError(filename=filename, lineno=line_number,
                                         text=raw_line) from original_exception
        return branch_rules

    def parse_suffix_file(self, lines: Iterable[str], filename: str = None) -> List[SuffixRule]:
        """Load a suffix grammar file, returning the suffix rules parsed from it."""
        leaf_rules = []
        line_number = 0
        for raw_line in lines:
            try:
                line_number += 1
                line = raw_line.split('#')[0].rstrip()
                if not line:
                    continue
                if ':' not in line:
                    raise GrammarSyntaxError("Expected: ':'", offset=1 + len(line))
                if line.count(':') > 1:
                    raise GrammarSyntaxError("Unexpected: ':'",
                                             offset=1 + line.find(':', line.find(':') + 1))
                definition, suffixes = line.split(':')
                category = self.parse_category(definition)
                suffixes = suffixes.split()
                if not suffixes or suffixes[0] not in ('+', '-'):
                    raise GrammarSyntaxError("Expected: '+' or '-'", offset=1 + line.find(':') + 1)
                positive = suffixes.pop(0) == '+'
                suffixes = frozenset(suffixes)
                if not suffixes:
                    suffixes = frozenset([''])
                leaf_rules.append(SuffixRule(category, suffixes, positive))
            except GrammarParserError as error:
                error.set_info(filename=filename, lineno=line_number, text=raw_line)
                raise error
            except Exception as original_exception:
                raise GrammarParserError(filename=filename, lineno=line_number,
                                         text=raw_line) from original_exception
        return leaf_rules

    def parse_special_words_file(self, lines: Iterable[str], filename: str = None) -> List[SetRule]:
        """Load a special words grammar file, returning the set rules parsed from it."""
        leaf_rules = []
        line_number = 0
        for raw_line in lines:
            try:
                line_number += 1
                line = raw_line.split('#')[0].rstrip()
                if not line:
                    continue
                if ':' not in line:
                    raise GrammarSyntaxError("Expected: ':'", offset=1 + len(line))
                pieces = line.split(':')
                definition = pieces.pop(0)
                token_str = ':'.join(pieces)
                category = self.parse_category(definition)
                token_set = frozenset(token_str.split())
                leaf_rules.append(SetRule(category, token_set))
            except GrammarParserError as error:
                error.set_info(filename=filename, lineno=line_number, text=raw_line)
                raise error
            except Exception as original_exception:
                raise GrammarParserError(filename=filename, lineno=line_number,
                                         text=raw_line) from original_exception
        return leaf_rules
