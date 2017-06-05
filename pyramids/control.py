import bisect
import cmd
import configparser
import os
import time
import traceback
import warnings

try:
    import cProfile as profile
except ImportError:
    import profile

try:
    import pyramids_categories
except ImportError:
    pyramids_categories = None
    warnings.warn("The pyramids_categories package was not found. "
                  "The pre-compiled category files will not be available.")

from pyramids import (benchmarking, categorization, exceptions, graphs,
                      parsing, parserules, tokenization)


__author__ = 'Aaron Hosford'
__all__ = [
    'ParserConfigInfo',
    'ParserLoader',
    'ParserCmd',
]


class ParserConfigInfo:

    def __init__(self, config_file_path, defaults=None):
        if not os.path.isfile(config_file_path):
            raise FileNotFoundError(config_file_path)

        self._config_file_path = config_file_path

        data_folder = os.path.dirname(config_file_path)

        if pyramids_categories:
            default_word_sets_folder = os.path.dirname(pyramids_categories.__file__)
        else:
            default_word_sets_folder = 'word_sets'

        if defaults is None:
            self._defaults = {}
        else:
            self._defaults = dict(defaults)
        for option, value in (('Tokenizer Type', 'standard'),
                              ('Discard Spaces', '1'),
                              ('Word Sets Folder',
                               default_word_sets_folder)):
            if option not in self._defaults:
                self._defaults[option] = value

        config_parser = configparser.ConfigParser(self._defaults)
        config_parser.read(self._config_file_path)

        # Tokenizer
        self._tokenizer_type = config_parser.get('Tokenizer', 'Tokenizer Type').strip()
        self._discard_spaces = config_parser.getboolean('Tokenizer', 'Discard Spaces')

        # Properties
        self._any_promoted_properties = frozenset(
            categorization.Property(prop.strip())
            for prop in config_parser.get('Properties', 'Any-Promoted Properties').split(';')
            if prop.strip()
        )
        self._all_promoted_properties = frozenset(
            categorization.Property(prop.strip())
            for prop in config_parser.get('Properties', 'All-Promoted Properties').split(';')
            if prop.strip()
        )
        self._property_inheritance_files = tuple(
            os.path.join(data_folder, path.strip())
            for path in config_parser.get('Properties', 'Property Inheritance File').split(';')
            if path.strip()
        )

        # Grammar
        self._grammar_definition_files = tuple(
            os.path.join(data_folder, path.strip())
            for path in config_parser.get('Grammar', 'Grammar Definition File').split(';')
            if path.strip()
        )
        self._conjunction_files = tuple(
            os.path.join(data_folder, path.strip())
            for path in config_parser.get('Grammar', 'Conjunctions File').split(';')
            if path.strip()
        )
        self._word_sets_folders = tuple(
            os.path.join(data_folder, path.strip())
            for path in config_parser.get('Grammar', 'Word Sets Folder').split(';')
            if path.strip()
        )
        self._suffix_files = tuple(
            os.path.join(data_folder, path.strip())
            for path in config_parser.get('Grammar', 'Suffix File').split(';')
            if path.strip()
        )
        self._special_words_files = tuple(
            os.path.join(data_folder, path.strip())
            for path in config_parser.get('Grammar', 'Special Words File').split(';')
            if path.strip()
        )
        self._name_cases = frozenset(
            prop_name.strip()
            for prop_name in config_parser.get('Grammar', 'Name Cases').split(';')
            if prop_name.strip()
        )

        # Scoring
        self._scoring_measures_file = os.path.join(
            data_folder,
            config_parser.get('Scoring', 'Scoring Measures File')
        )

        # Benchmarking
        self._benchmark_file = os.path.join(
            data_folder,
            config_parser.get('Benchmarking', 'Benchmark File')
        )

    @property
    def config_file_path(self):
        return self._config_file_path

    def get_defaults(self):
        if self._defaults is None:
            return None
        return self._defaults.copy()

    @property
    def tokenizer_type(self):
        return self._tokenizer_type

    @property
    def discard_spaces(self):
        return self._discard_spaces

    @property
    def any_promoted_properties(self):
        return self._any_promoted_properties

    @property
    def all_promoted_properties(self):
        return self._all_promoted_properties

    @property
    def property_inheritance_files(self):
        return self._property_inheritance_files

    @property
    def grammar_definition_files(self):
        return self._grammar_definition_files

    @property
    def conjunction_files(self):
        return self._conjunction_files

    @property
    def word_sets_folders(self):
        return self._word_sets_folders

    @property
    def suffix_files(self):
        return self._suffix_files

    @property
    def special_words_files(self):
        return self._special_words_files

    @property
    def scoring_measures_file(self):
        return self._scoring_measures_file

    @property
    def benchmark_file(self):
        return self._benchmark_file

    @property
    def name_cases(self):
        return self._name_cases


class ParserLoader:

    def __init__(self, verbose=False):
        self.verbose = bool(verbose)

    @staticmethod
    def parse_category(definition, offset=1):
        definition = definition.strip()
        if '(' in definition:
            if not definition.endswith(')'):
                raise exceptions.GrammarSyntaxError(
                    "Expected: ')' in category definition",
                    offset=offset + len(definition)
                )
            if definition.count('(') > 1:
                raise exceptions.GrammarSyntaxError(
                    "Unexpected: '(' in category definition",
                    offset=offset + definition.find(
                        "(",
                        definition.find("(") + 1
                    )
                )
            if definition.count(')') > 1:
                raise exceptions.GrammarSyntaxError(
                    "Unexpected: ')' in category definition",
                    offset=offset + definition.find(
                        ")",
                        definition.find(")") + 1
                    )
                )
            name, properties = definition[:-1].split('(')
            if ',' in name:
                raise exceptions.GrammarSyntaxError(
                    "Unexpected: ',' in category definition",
                    offset=offset + definition.find(",")
                )
            if len(name.split()) > 1:
                raise exceptions.GrammarSyntaxError(
                    "Unexpected: white space in category definition",
                    offset=offset + len(name) + 1
                )
            properties = [
                prop.strip()
                for prop in properties.split(',')
            ]
            for prop in properties:
                if not prop.strip():
                    if ",," in definition:
                        raise exceptions.GrammarSyntaxError(
                            "Unexpected: ','",
                            offset=offset + definition.find(",,") + 1
                        )
                    elif "(," in definition:
                        raise exceptions.GrammarSyntaxError(
                            "Unexpected: ','",
                            offset=offset + definition.find("(,") + 1
                        )
                    elif ",)" in definition:
                        raise exceptions.GrammarSyntaxError(
                            "Unexpected: ')'",
                            offset=offset + definition.find(",)") + 1
                        )
                    else:
                        raise exceptions.GrammarSyntaxError(
                            "Unexpected: ')'",
                            offset=offset + definition.find("()") + 1
                        )
            positive = [
                prop
                for prop in properties
                if not prop.startswith('-')
            ]
            negative = [
                prop[1:]
                for prop in properties
                if prop.startswith('-')
            ]
            for prop in negative:
                if prop.startswith('-'):
                    raise exceptions.GrammarSyntaxError(
                        "Unexpected: '-'",
                        offset=offset + definition.find('-' + prop)
                    )
                if prop in positive:
                    raise exceptions.GrammarSyntaxError(
                        "Unexpected: prop is both positive and negative",
                        offset=offset + definition.find(prop)
                    )
            return categorization.Category(
                name,
                [categorization.Property(name) for name in positive],
                [categorization.Property(name) for name in negative]
            )
        else:
            if ')' in definition:
                raise exceptions.GrammarSyntaxError(
                    "Unexpected: ')' in category definition",
                    offset=offset + definition.find(")")
                )
            if ',' in definition:
                raise exceptions.GrammarSyntaxError(
                    "Unexpected: ',' in category definition",
                    offset=offset + definition.find(",")
                )
            if len(definition.split()) > 1:
                raise exceptions.GrammarSyntaxError(
                    "Unexpected: white space in category definition",
                    offset=offset + len(definition.split()[0]) + 1
                )
            if not definition:
                raise exceptions.GrammarSyntaxError(
                    "Expected: category definition",
                    offset=offset
                )
            return categorization.Category(definition)

    def parse_branch_rule_term(self, term, offset=1):
        is_head = False
        if term.startswith('*'):
            term = term[1:]
            offset += 1
            is_head = True
            if '*' in term:
                raise exceptions.GrammarSyntaxError(
                    "Unexpected: '*'",
                    offset=offset + term.find('*')
                )
        subcategories = []
        subcategory_definitions = term.split('|')
        for definition in subcategory_definitions:
            subcategory = self.parse_category(definition, offset=offset)
            subcategories.append(subcategory)
            offset += len(definition) + 1
        if not subcategories:
            raise exceptions.GrammarSyntaxError(
                "Expected: category",
                offset=offset
            )
        return is_head, subcategories

    @staticmethod
    def parse_branch_rule_link_type(term, offset=1):
        if '<' in term[1:]:
            raise exceptions.GrammarSyntaxError(
                "Unexpected: '<'",
                offset=offset + term.find('<', term.find('<') + 1)
            )
        if '>' in term[:-1]:
            raise exceptions.GrammarSyntaxError(
                "Unexpected: '<'",
                offset=offset + term.find('>')
            )
        left = term.startswith('<')
        right = term.endswith('>')
        if left:
            term = term[1:]
        if right:
            term = term[:-1]
        if not term:
            raise exceptions.GrammarSyntaxError(
                "Expected: link type",
                offset=offset + left
            )
        return term, left, right

    def parse_branch_rule(self, category, definition, offset=1):
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
                        raise exceptions.GrammarSyntaxError(
                            "Unexpected: link type",
                            offset=offset + term_start
                        )
                    link_type, left, right = \
                        self.parse_branch_rule_link_type(
                            term,
                            offset + term_start
                        )
                    if head_index is None:
                        if right:
                            raise exceptions.GrammarSyntaxError(
                                "Unexpected: right link",
                                offset=offset + term_start
                            )
                    else:
                        if left:
                            raise exceptions.GrammarSyntaxError(
                                "Unexpected: left link",
                                offset=offset + term_start
                            )
                    link_types[-1].add((link_type, left, right))
                else:
                    is_head, subcategories = self.parse_branch_rule_term(
                        term,
                        offset=offset + term_start
                    )
                    if is_head:
                        if head_index is not None:
                            raise exceptions.GrammarSyntaxError(
                                "Unexpected: '*'",
                                offset=(offset +
                                        term_start +
                                        term.find('*'))
                            )
                        head_index = len(subcategory_sets)
                    subcategory_sets.append(subcategories)
                    link_types.append(set())
                term = ''
            else:
                if not term:
                    term_start = index
                term += char
        if term:
            is_head, subcategories = self.parse_branch_rule_term(
                term,
                offset=offset + term_start
            )
            if is_head:
                if head_index is not None:
                    raise exceptions.GrammarSyntaxError(
                        "Unexpected: '*'",
                        offset=offset + term_start + term.find('*')
                    )
                head_index = len(subcategory_sets)
            subcategory_sets.append(subcategories)
            link_types.append(set())
        if not subcategory_sets:
            raise exceptions.GrammarSyntaxError(
                "Expected: category",
                offset=offset
            )
        if link_types[-1]:
            raise exceptions.GrammarSyntaxError(
                "Expected: category",
                offset=offset + term_start + len(term)
            )
        link_types = link_types[:-1]
        if head_index is None:
            if len(subcategory_sets) != 1:
                raise exceptions.GrammarSyntaxError(
                    "Expected: '*'",
                    offset=offset + term_start
                )
            head_index = 0
        return parserules.SequenceRule(
            category,
            subcategory_sets,
            head_index,
            link_types
        )

    def parse_grammar_definition_file(self, path):
        branch_rules = []
        category = None
        sequence_found = False
        line_number = 0
        with open(path) as grammar_file:
            for raw_line in grammar_file:
                line_number += 1
                try:
                    line = raw_line.split('#')[0].rstrip()
                    if not line:
                        continue
                    if line[:1].isspace():
                        if ':' in line:
                            raise exceptions.GrammarSyntaxError(
                                "Unexpected: ':'",
                                offset=1 + line.find(':')
                            )
                        if not category:
                            raise exceptions.GrammarSyntaxError(
                                "Expected: category header",
                                offset=1 + line.find(line.strip())
                            )
                        branch_rules.append(
                            self.parse_branch_rule(
                                category,
                                line.lstrip(),
                                offset=1 + line.find(line.lstrip())
                            )
                        )
                        sequence_found = True
                    else:
                        if category is not None and not sequence_found:
                            raise exceptions.GrammarSyntaxError(
                                "Expected: category sequence",
                                offset=1
                            )
                        if ':' not in line:
                            raise exceptions.GrammarSyntaxError(
                                "Expected: ':'",
                                offset=1 + len(line)
                            )
                        if line.count(':') > 1:
                            raise exceptions.GrammarSyntaxError(
                                "Unexpected: ':'",
                                offset=1 + line.find(':', line.find(':') + 1)
                            )
                        header, sequence = line.split(':')
                        category = self.parse_category(header)
                        if sequence.strip():
                            branch_rules.append(
                                self.parse_branch_rule(
                                    category,
                                    sequence.lstrip(),
                                    offset=1 + sequence.find(sequence.lstrip())
                                )
                            )
                            sequence_found = True
                        else:
                            sequence_found = False
                except exceptions.GrammarParserError as error:
                    error.set_info(path, line_number, None, raw_line)
                    raise error
                except Exception as original_exception:
                    raise exceptions.GrammarParserError(
                        None,
                        path,
                        line_number,
                        None,
                        raw_line
                    ) from original_exception
        return branch_rules

    def parse_match_rule(self, definition, offset=1):
        if not definition.startswith('['):
            raise exceptions.GrammarSyntaxError(
                "Expected: '['",
                offset
            )
        if not definition.endswith(']'):
            raise exceptions.GrammarSyntaxError(
                "Expected: ']'",
                offset + len(definition) - 1
            )
        generator_map = {
            'any_term': parserules.AnyTermMatchRule,
            'all_terms': parserules.AllTermsMatchRule,
            'compound': parserules.CompoundMatchRule,
            'head': parserules.HeadMatchRule,
            'one_term': parserules.OneTermMatchRule,
            'last_term': parserules.LastTermMatchRule,
        }
        rule_list = []
        for category_definition in definition[1:-1].split():
            category = self.parse_category(
                category_definition,
                offset=1 + definition.find(category_definition)
            )
            generator = generator_map.get(category.name, None)
            if generator is None:
                raise exceptions.GrammarSyntaxError(
                    "Unexpected: " + repr(category),
                    offset=1 + definition.find(category_definition)
                )
            else:
                assert callable(generator)
                rule_list.append(
                    generator(
                        category.positive_properties,
                        category.negative_properties
                    )
                )
        if not rule_list:
            raise exceptions.GrammarSyntaxError(
                "Expected: category"
            )
        return tuple(rule_list)

    def parse_conjunction_rule(self, category, match_rules, property_rules,
                               definition, offset=1):
        single = False
        compound = False
        while definition[:1] in ('+', '-'):
            if definition[0] == '+':
                if compound:
                    raise exceptions.GrammarSyntaxError(
                        "Unexpected: '+'",
                        offset=offset
                    )
                compound = True
            else:
                if single:
                    raise exceptions.GrammarSyntaxError(
                        "Unexpected: '-'",
                        offset=offset
                    )
                single = True
            definition = definition[1:]
            offset += 1
        # TODO: While functional, this is a copy/paste from parse_branch_
        #       rule. Modify it to fit conjunctions more cleanly, or
        #       combine the two methods.
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
                        raise exceptions.GrammarSyntaxError(
                            "Unexpected: link type",
                            offset=offset + term_start
                        )
                    link_type, left, right = \
                        self.parse_branch_rule_link_type(
                            term,
                            offset + term_start
                        )
                    if head_index is None:
                        if right:
                            raise exceptions.GrammarSyntaxError(
                                "Unexpected: right link",
                                offset=offset + term_start
                            )
                    else:
                        if left:
                            raise exceptions.GrammarSyntaxError(
                                "Unexpected: left link",
                                offset=offset + term_start
                            )
                    link_types[-1].add((link_type, left, right))
                else:
                    is_head, subcategories = self.parse_branch_rule_term(
                        term,
                        offset=offset + term_start
                    )
                    if is_head:
                        if head_index is not None:
                            raise exceptions.GrammarSyntaxError(
                                "Unexpected: '*'",
                                offset=offset + term_start + term.find('*')
                            )
                        head_index = len(subcategory_sets)
                    subcategory_sets.append(subcategories)
                    link_types.append(set())
                term = ''
            else:
                if not term:
                    term_start = index
                term += char
        if term:
            is_head, subcategories = self.parse_branch_rule_term(
                term,
                offset=offset + term_start
            )
            if is_head:
                if head_index is not None:
                    raise exceptions.GrammarSyntaxError(
                        "Unexpected: '*'",
                        offset=offset + term_start + term.find('*')
                    )
                head_index = len(subcategory_sets)
            subcategory_sets.append(subcategories)
            link_types.append(set())
        if not subcategory_sets:
            raise exceptions.GrammarSyntaxError(
                "Expected: category",
                offset=offset
            )
        if link_types[-1]:
            raise exceptions.GrammarSyntaxError(
                "Expected: category",
                offset=offset + term_start + len(term)
            )
        link_types = link_types[:-1]
        if head_index is None:
            if len(subcategory_sets) != 1:
                raise exceptions.GrammarSyntaxError(
                    "Expected: '*'",
                    offset=offset + term_start
                )
            head_index = 0
        # TODO: Specify offsets for these errors.
        if len(subcategory_sets) > 3:
            raise exceptions.GrammarSyntaxError(
                "Unexpected: category"
            )
        elif len(subcategory_sets) < 2:
            raise exceptions.GrammarSyntaxError(
                "Expected: category"
            )
        elif len(subcategory_sets) == 3:
            if head_index != 1:
                raise exceptions.GrammarSyntaxError(
                    "Unexpected: category"
                )
            leadup_cats, conjunction_cats, followup_cats = subcategory_sets
            leadup_link_types, followup_link_types = link_types
        else:  # if len(subcategory_sets) == 2:
            if head_index != 0:
                raise exceptions.GrammarSyntaxError(
                    "Expected: category"
                )
            leadup_cats = None
            conjunction_cats, followup_cats = subcategory_sets
            # TODO: While these are sets, ConjunctionRule expects
            #       individual links. Modify ConjunctionRule to expect sets
            leadup_link_types = set()

            followup_link_types = link_types[0]
        return parserules.ConjunctionRule(
            category,
            match_rules,
            property_rules,
            leadup_cats,
            conjunction_cats,
            followup_cats,
            leadup_link_types,
            followup_link_types,
            single,
            compound
        )

    def parse_conjunctions_file(self, path):
        branch_rules = []
        category = None
        match_rules = []
        match_rules_closed = False
        property_rules = []
        property_rules_closed = False
        sequence_found = False
        line_number = 0
        with open(path) as conjunctions_file:
            for raw_line in conjunctions_file:
                line_number += 1
                try:
                    line = raw_line.split('#')[0].rstrip()
                    if not line:
                        continue
                    if line[:1].isspace():
                        if ':' in line:
                            raise exceptions.GrammarSyntaxError(
                                "Unexpected: ':'",
                                offset=1 + line.find(':')
                            )
                        if not category:
                            raise exceptions.GrammarSyntaxError(
                                "Expected: category header",
                                offset=1 + line.find(line.strip())
                            )
                        if line.endswith(']') and '[' in line:
                            if line.lstrip().startswith('['):
                                if match_rules_closed:
                                    raise exceptions.GrammarSyntaxError(
                                        "Unexpected: matching rule"
                                        # TODO: offset?
                                    )
                                match_rules.append(
                                    self.parse_match_rule(
                                        line.lstrip(),
                                        offset=1 + line.find(line.lstrip())
                                    )
                                )
                            else:
                                if property_rules_closed:
                                    raise exceptions.GrammarSyntaxError(
                                        "Unexpected: property rule"
                                        # TODO: offset?
                                    )
                                match_rules_closed = True
                                left_bracket_index = line.index('[')
                                property_names = \
                                    line[:left_bracket_index].strip().split(
                                        ','
                                    )
                                properties = set()
                                for property_name in property_names:
                                    if property_name.startswith('-'):
                                        properties.add(
                                            (
                                                categorization.Property(
                                                    property_name[1:]
                                                ),
                                                False
                                            )
                                        )
                                    else:
                                        properties.add(
                                            (
                                                categorization.Property(
                                                    property_name
                                                ),
                                                True
                                            )
                                        )
                                line_remainder = line[left_bracket_index:]
                                property_rules.append(
                                    (
                                        frozenset(properties),
                                        self.parse_match_rule(
                                            line_remainder.lstrip(),
                                            offset=1 + line.find(
                                                line_remainder.strip()
                                            )
                                        )
                                    )
                                )
                        else:
                            match_rules_closed = True
                            property_rules_closed = True
                            if '[' in line:
                                raise exceptions.GrammarSyntaxError(
                                    "Unexpected: '['",
                                    offset=1 + line.find('[')
                                )
                            if ']' in line:
                                raise exceptions.GrammarSyntaxError(
                                    "Unexpected: ']'",
                                    offset=1 + line.find(']')
                                )
                            branch_rules.append(
                                self.parse_conjunction_rule(
                                    category,
                                    match_rules,
                                    property_rules,
                                    line.lstrip(),
                                    offset=1 + line.find(line.lstrip())
                                )
                            )
                            sequence_found = True
                    else:
                        if category is not None and not sequence_found:
                            raise exceptions.GrammarSyntaxError(
                                "Expected: category sequence",
                                offset=1
                            )
                        if ':' not in line:
                            raise exceptions.GrammarSyntaxError(
                                "Expected: ':'",
                                offset=1 + len(line)
                            )
                        if line.count(':') > 1:
                            raise exceptions.GrammarSyntaxError(
                                "Unexpected: ':'",
                                offset=1 + line.find(':', line.find(':') + 1)
                            )
                        header, sequence = line.split(':')
                        category = self.parse_category(header)
                        match_rules = []
                        match_rules_closed = False
                        property_rules = []
                        property_rules_closed = False
                        if sequence.strip():
                            branch_rules.append(
                                self.parse_conjunction_rule(
                                    category,
                                    match_rules,
                                    property_rules,
                                    sequence.lstrip(),
                                    offset=1 + sequence.find(
                                        sequence.lstrip()
                                    )
                                )
                            )
                            sequence_found = True
                        else:
                            sequence_found = False
                except exceptions.GrammarParserError as error:
                    error.set_info(path, line_number, None, raw_line)
                    raise error
                except Exception as original_exception:
                    raise exceptions.GrammarParserError(
                        None,
                        path,
                        line_number,
                        None,
                        raw_line
                    ) from original_exception
        return branch_rules

    def parse_suffix_file(self, path):
        leaf_rules = []
        line_number = 0
        with open(path) as suffix_file:
            for raw_line in suffix_file:
                try:
                    line_number += 1
                    line = raw_line.split('#')[0].rstrip()
                    if not line:
                        continue
                    if ':' not in line:
                        raise exceptions.GrammarSyntaxError(
                            "Expected: ':'",
                            filename=path,
                            lineno=line_number,
                            offset=1 + len(line),
                            text=raw_line
                        )
                    if line.count(':') > 1:
                        raise exceptions.GrammarSyntaxError(
                            "Unexpected: ':'",
                            filename=path,
                            lineno=line_number,
                            offset=1 + line.find(
                                ':',
                                line.find(':') + 1
                            ),
                            text=raw_line
                        )
                    definition, suffixes = line.split(':')
                    try:
                        category = self.parse_category(definition)
                    except exceptions.GrammarParserError as error:
                        error.set_info(path, line_number, None, line)
                        raise error
                    except Exception as original_exception:
                        raise exceptions.GrammarParserError(
                            None,
                            path,
                            line_number,
                            None,
                            line
                        ) from original_exception
                    suffixes = suffixes.split()
                    if not suffixes or suffixes[0] not in ('+', '-'):
                        raise exceptions.GrammarSyntaxError(
                            "Expected: '+' or '-'",
                            filename=path,
                            lineno=line_number,
                            offset=1 + line.find(':') + 1, text=raw_line
                        )
                    positive = suffixes.pop(0) == '+'
                    suffixes = frozenset(suffixes)
                    if not suffixes:
                        suffixes = frozenset([''])
                    leaf_rules.append(
                        parserules.SuffixRule(category, suffixes, positive)
                    )
                except exceptions.GrammarParserError as error:
                    error.set_info(path, line_number, text=raw_line)
                    raise error
                except Exception as original_exception:
                    raise exceptions.GrammarParserError(
                        None,
                        path,
                        line_number,
                        None,
                        raw_line
                    ) from original_exception
        return leaf_rules

    def parse_special_words_file(self, path):
        leaf_rules = []
        line_number = 0
        with open(path) as word_file:
            for raw_line in word_file:
                try:
                    line_number += 1
                    line = raw_line.split('#')[0].rstrip()
                    if not line:
                        continue
                    if ':' not in line:
                        raise exceptions.GrammarSyntaxError(
                            "Expected: ':'",
                            filename=path,
                            lineno=line_number,
                            offset=1 + len(line),
                            text=raw_line
                        )
                    line = line.split(':')
                    definition = line.pop(0)
                    token_str = ':'.join(line)
                    try:
                        category = self.parse_category(definition)
                    except exceptions.GrammarParserError as error:
                        error.set_info(path, line_number, None, line)
                        raise error
                    except Exception as original_exception:
                        raise exceptions.GrammarParserError(
                            None,
                            path,
                            line_number,
                            None,
                            line
                        ) from original_exception
                    token_set = frozenset(token_str.split())
                    leaf_rules.append(parserules.SetRule(category, token_set))
                except exceptions.GrammarParserError as error:
                    error.set_info(path, line_number, text=raw_line)
                    raise error
                except Exception as original_exception:
                    raise exceptions.GrammarParserError(
                        None,
                        path,
                        line_number,
                        None,
                        raw_line
                    ) from original_exception
        return leaf_rules

    def load_word_set(self, file_path):
        folder, filename = os.path.split(file_path)
        category_definition = os.path.splitext(filename)[0]
        try:
            category = self.parse_category(category_definition)
        except exceptions.GrammarSyntaxError:
            raise IOError("Badly named word set file: " + file_path)
        if self.verbose:
            print(
                "Loading category",
                str(category),
                "from",
                file_path,
                "..."
            )
        with open(file_path) as token_file:
            token_set = token_file.read().split()
        return parserules.SetRule(category, token_set)

    def load_word_sets_folder(self, folder):
        # TODO: Should this do a directory walk instead?
        leaf_rules = []
        for filename in os.listdir(folder):
            filepath = os.path.join(folder, filename)
            if os.path.splitext(filename)[-1].lower() == '.ctg':
                leaf_rules.append(self.load_word_set(filepath))
            elif self.verbose:
                print("Skipping file " + filepath + "...")
        return leaf_rules

    # TODO: Write a parser for a file that defines property inheritance;
    #       essentially, if a category of a given name has a given property
    #       (or combination thereof) it also has such-and-such other
    #       properties. Then remove all rules that just do this from the
    #       grammar file and make them a syntax error. The most important
    #       thing here is that we eliminate the 1000s of different ways a
    #       single node can end up with the same properties just from
    #       adding them in a different order. These property inheritance
    #       rules should be applied to every node before it is added to the
    #       category map. To ensure conflicts don't cause issues due to
    #       variation in the order the inheritance rules are applied,
    #       strict rules will have to be enforced on the order the rules
    #       are applied. The simplest, most obvious answer is to apply them
    #       in the order they appear in the file. It may be more
    #       appropriate to sort them according to some rule, however. It
    #       may also be appropriate to restrict them, as well. For example,
    #       only allowing reference to a negative property in the
    #       conditions if it is a property that cannot be added as a
    #       result. (The *_ending properties are a good example; they can
    #       be supplied only by a leaf rule or promotion. They will never
    #       be added by a property inheritance rule because they are really
    #       properties of the token, not logical properties.) Now that I
    #       think about it, the only time a negative property should be
    #       accessible as a condition in property inheritance is if it can
    #       only apply to leaves. Properties should be divided into those
    #       that belong to leaves, and those that also belong to branches.
    #       Leaf-only properties can be referenced as negatives in the
    #       property inheritance, but branch properties cannot.
    #
    #       I've rethought it again: negative properties can be conditions,
    #       but not effects. Positive and negative properties are not
    #       resolved via cancellation until all inheritance rules have
    #       finished firing; this lets every rule get a chance to fire
    #       without the issue of things disappearing before it can due to
    #       other rules' actions. When all have fired and nothing new can
    #       be added, positive properties overrule negative ones.

    def load_property_inheritance_file(self, path):
        inheritance_rules = []
        line_number = 0
        with open(path) as inheritance_file:
            for raw_line in inheritance_file:
                try:
                    line_number += 1
                    line = raw_line.split('#')[0].rstrip()
                    if not line:
                        continue
                    if ':' not in line:
                        raise exceptions.GrammarSyntaxError(
                            "Expected: ':'",
                            filename=path,
                            lineno=line_number,
                            offset=1 + len(line),
                            text=raw_line
                        )
                    if line.count(':') > 1:
                        raise exceptions.GrammarSyntaxError(
                            "Unexpected: ':'",
                            filename=path,
                            lineno=line_number,
                            offset=1 + line.find(':', line.find(':') + 1),
                            text=raw_line
                        )
                    definition, additions = line.split(':')
                    try:
                        category = self.parse_category(definition)
                    except exceptions.GrammarParserError as error:
                        error.set_info(path, line_number, None, line)
                        raise error
                    except Exception as original_exception:
                        raise exceptions.GrammarParserError(
                            None,
                            path,
                            line_number,
                            None,
                            line
                        ) from original_exception
                    additions = additions.split()
                    if not additions:
                        raise exceptions.GrammarSyntaxError(
                            "Expected: property",
                            filename=path,
                            lineno=line_number,
                            offset=1 + line.find(':') + 1,
                            text=raw_line
                        )
                    positive_additions = [
                        addition
                        for addition in additions
                        if not addition.startswith('-')
                    ]
                    negative_additions = [
                        addition[1:]
                        for addition in additions
                        if addition.startswith('-')
                    ]
                    # TODO: Check negative additions for a double '-'
                    # TODO: Check that positive & negative additions don't
                    #       conflict
                    inheritance_rules.append(
                        parserules.PropertyInheritanceRule(
                            category,
                            positive_additions,
                            negative_additions
                        )
                    )
                except exceptions.GrammarParserError as error:
                    exceptions.GrammarSyntaxError.set_info(
                        path,
                        line_number,
                        text=raw_line
                    )
                    raise error
                except Exception as original_exception:
                    raise exceptions.GrammarParserError(
                        None,
                        path,
                        line_number,
                        None,
                        raw_line
                    ) from original_exception
        return inheritance_rules

    def load_parser(self, config_info):
        if self.verbose:
            print("Loading parser from", config_info.config_file_path, "...")

        # Tokenizer
        if config_info.tokenizer_type.lower() != 'standard':
            raise ValueError("Tokenizer type not supported: " + config_info.tokenizer_type)
        tokenizer = tokenization.StandardTokenizer(config_info.discard_spaces)

        # Properties
        property_inheritance_rules = []
        for path in config_info.property_inheritance_files:
            property_inheritance_rules.extend(self.load_property_inheritance_file(path))

        # Grammar
        branch_rules = []
        primary_leaf_rules = []
        secondary_leaf_rules = []
        for path in config_info.grammar_definition_files:
            branch_rules.extend(self.parse_grammar_definition_file(path))
        for path in config_info.conjunction_files:
            branch_rules.extend(self.parse_conjunctions_file(path))
        for folder in config_info.word_sets_folders:
            primary_leaf_rules.extend(self.load_word_sets_folder(folder))
        for path in config_info.suffix_files:
            secondary_leaf_rules.extend(self.parse_suffix_file(path))
        for path in config_info.special_words_files:
            primary_leaf_rules.extend(self.parse_special_words_file(path))
        for case in config_info.name_cases:
            secondary_leaf_rules.append(parserules.CaseRule(categorization.Category('name'), case))

        parser = parsing.Parser(
            primary_leaf_rules,
            secondary_leaf_rules,
            branch_rules,
            tokenizer,
            config_info.any_promoted_properties,
            config_info.all_promoted_properties,
            property_inheritance_rules,
            config_info
        )

        # Scoring
        if self.verbose:
            print("Loading scoring measures from", config_info.scoring_measures_file + "...")
        if os.path.isfile(config_info.scoring_measures_file):
            parser.load_scoring_measures(config_info.scoring_measures_file)
        else:
            parser.save_scoring_measures(config_info.scoring_measures_file)

        if self.verbose:
            print("Done loading parser from", config_info.config_file_path + ".")

        return parser

    def standardize_word_set_file(self, filepath):
        with open(filepath) as word_set_file:
            original_data = word_set_file.read()
        data = '\n'.join(sorted(set(original_data.split())))
        if data != original_data:
            with open(filepath, 'w') as word_set_file:
                word_set_file.write(data)
        folder = os.path.dirname(filepath)
        filename = os.path.basename(filepath)
        category = self.parse_category(os.path.splitext(filename)[0])
        if str(category) + '.ctg' != filename:
            os.rename(
                filepath,
                os.path.join(folder, str(category) + '.ctg')
            )

    def standardize_word_sets_folder(self, folder):
        for filename in os.listdir(folder):
            filepath = os.path.join(folder, filename)
            if filepath.endswith('.ctg'):
                self.standardize_word_set_file(filepath)

    def standardize_parser(self, config_info):
        for folder in config_info.word_sets_folders:
            self.standardize_word_sets_folder(folder)

    def get_word_set_categories(self, config_info):
        categories = set()
        for folder_path in config_info.word_sets_folders:
            for filename in os.listdir(folder_path):
                if not filename.lower().endswith('.ctg'):
                    continue
                category = self.parse_category(filename[:-4])
                categories.add(category)
        return categories

    def find_word_set_path(self, config_info, category):
        for folder_path in config_info.word_sets_folders:
            for filename in os.listdir(folder_path):
                if not filename.lower().endswith('.ctg'):
                    continue
                file_category = self.parse_category(filename[:-4])
                if file_category == category:
                    return os.path.join(folder_path, filename)
        for folder_path in config_info.word_sets_folders:
            return os.path.join(folder_path, str(category) + '.ctg')
        raise IOError("Could not find a word sets folder.")

    def add_words(self, config_info, category, words):
        path = self.find_word_set_path(config_info, category)
        if os.path.isfile(path):
            with open(path) as word_set_file:
                known_words = word_set_file.read().split()
            known_words.sort()
        else:
            known_words = []
        added = set()
        for w in words:
            w = w.lower()
            index = bisect.bisect_left(known_words, w)
            if index < len(known_words) and known_words[index] == w:
                continue
            added.add(w)
            known_words.insert(index, w)
        with open(path, 'w') as word_set_file:
            word_set_file.write('\n'.join(known_words))
        return added

    def remove_words(self, config_info, category, words):
        path = self.find_word_set_path(config_info, category)
        if not os.path.isfile(path):
            return set()
        with open(path) as word_set_file:
            known_words = word_set_file.read().split()
        known_words.sort()
        removed = set()
        for w in words:
            w = w.lower()
            index = bisect.bisect_left(known_words, w)
            if index < len(known_words) and known_words[index] == w:
                removed.add(w)
                del known_words[index]
        with open(path, 'w') as word_set_file:
            word_set_file.write('\n'.join(known_words))
        return removed


# TODO: Some code from this class is duplicated in __init__.py
class ParserCmd(cmd.Cmd):

    def __init__(self):
        cmd.Cmd.__init__(self)
        self.prompt = '% '
        self._simple = True
        self._show_broken = False
        self._parser_loader = ParserLoader()
        self._parser = None
        self._parser_state = None
        self._parses = []
        self._whole_parses = 0
        self._parse_index = 0
        self._fast = False
        self._timeout_interval = 5
        self._benchmark_path = None
        self._benchmark = None
        self._benchmark_dirty = False
        self._benchmark_emergency_disambiguations = 0
        self._benchmark_parse_timeouts = 0
        self._benchmark_disambiguation_timeouts = 0
        self._benchmark_time = 0.0
        self._benchmark_tests_completed = 0
        self._benchmark_update_time = time.time()
        self._last_input_text = None
        self.do_load()

    @property
    def parser_loader(self):
        return self._parser_loader

    @property
    def parser(self):
        return self._parser

    @property
    def max_parse_index(self):
        if self._show_broken:
            return len(self._parses) - 1 if self._parses else 0
        else:
            return self._whole_parses - 1 if self._whole_parses else 0

    @property
    def parses_available(self):
        if self._show_broken:
            return bool(self._parses)
        else:
            return bool(self._whole_parses)

    @property
    def last_input_text(self):
        return self._last_input_text

    def onecmd(self, line):
        try:
            return cmd.Cmd.onecmd(self, line)
        except:
            traceback.print_exc()

    def precmd(self, line):
        # Preprocesses command lines before they are executed.
        line = line.strip()
        if not line:
            return line
        command = line.split()[0]
        if command == '+':
            return 'good' + line[1:]
        if command == '-':
            return 'bad' + line[1:]
        if command == '++':
            return 'best' + line[2:]
        if command == '--':
            return 'worst' + line[2:]
        return line

    def postcmd(self, stop, line):
        # Postprocesses command results before they are passed back to the
        # command interpreter.
        print('')  # Print a blank line for clarity
        return stop

    def emptyline(self):
        # Called when the user just hits enter with no input.
        return self.do_next()

    def default(self, line):
        # Called when the command is unrecognized. By default, we assume
        # it's a parse request.
        return self.do_parse(line)

    @staticmethod
    def do_shell(line):
        # Called when the command starts with "!".
        try:
            print(eval(line))
        except SyntaxError:
            exec(line)

    def do_quit(self, line):
        """Save scoring measures and exit the parser debugger."""
        if line:
            print("'quit' command does not accept arguments.")
            return
        self.do_save()  # Save what we're doing first.
        return True  # Indicate we're ready to stop.

    def do_exit(self, line):
        """Alias for quit."""
        if line:
            print("'exit' command does not accept arguments.")
            return
        return self.do_quit(line)

    def do_bye(self, line):
        """Alias for quit."""
        if line:
            print("'bye' command does not accept arguments.")
            return
        return self.do_quit(line)

    def do_done(self, line):
        """Alias for quit."""
        if line:
            print("'done' command does not accept arguments.")
            return
        return self.do_quit(line)

    @staticmethod
    def do_cls(line):
        """Clears the screen."""
        os.system('cls')

    def do_standardize(self, line):
        """Standardizes the parser's files."""
        if not line:
            if self._parser and self._parser.config_info:
                config_info = self._parser.config_info
            else:
                config_info = ParserConfigInfo(
                    os.path.abspath('pyramids.ini'))
        else:
            config_info = ParserConfigInfo(line)
        self._parser_loader.standardize_parser(config_info)

    def do_short(self, line):
        """Causes parses to be printed in short form instead of long form.
        """
        if line:
            print("'short' command does not accept arguments.")
            return
        self._simple = True
        print("Parses will now be printed in short form.")

    def do_broken(self, line):
        """Causes parses that have more pieces or gaps than necessary to be
        listed."""
        if line:
            print("'broken' command does not accept arguments.")
            return
        self._show_broken = True
        print(
            "Parses with more pieces or gaps than necessary will now be "
            "listed."
        )

    def do_whole(self, line):
        """Causes only parses that have no more pieces or gaps than
        necessary to be listed."""
        if line:
            print("'whole' command does not accept arguments.")
            return
        self._show_broken = False
        self._parse_index = min(self._parse_index, self.max_parse_index)
        print(
            "Only parses with no more pieces or gaps than necessary will "
            "now be listed."
        )

    def do_long(self, line):
        """Causes parses to be printed in long form instead of short form.
        """
        if line:
            print("'long' command does not accept arguments.")
            return
        self._simple = False
        print("Parses will now be printed in long form.")

    def do_fast(self, line):
        """Causes parsing to stop as soon as a single parse is found."""
        if line:
            print("'fast' command does not accept arguments.")
            return
        self._fast = True
        print("Parsing will now stop as soon as a single parse is found.")

    def do_complete(self, line):
        """Causes parsing to continue until all parses have been
        identified."""
        if line:
            print("'complete' command does not accept arguments.")
            return
        self._fast = False
        print(
            "Parsing will now continue until all parses have been "
            "identified."
        )

    def do_load(self, line=''):
        """Save scoring measures and load a parser from the given
        configuration file."""
        self.do_save()
        if not line:
            line = os.path.abspath('data/pyramids.ini')
            if not os.path.isfile(line):
                line = os.path.join(
                    os.path.dirname(__file__),
                    'data/pyramids.ini'
                )
        if not os.path.isfile(line):
            print("The pyramids.ini file could not be found.")
            return
        config_info = ParserConfigInfo(line)
        self._parser = self._parser_loader.load_parser(config_info)
        self._benchmark = (
            benchmarking.Benchmark.load(
                config_info.benchmark_file
            ) 
            if os.path.isfile(config_info.benchmark_file) 
            else benchmarking.Benchmark()
        )
        self._benchmark_dirty = False

    def do_reload(self, line=''):
        """Save scoring measures and reload the last configuration file
        provided."""
        if line:
            print("'reload' command does not accept arguments.")
            return
        self.do_save()
        self.do_load(
            self._parser.config_info.config_file_path
            if self._parser and self._parser.config_info
            else ''
        )

    def do_save(self, line=''):
        """Save scoring measures."""
        if line:
            print("'save' command does not accept arguments.")
            return
        if self._parser is not None:
            self._parser.save_scoring_measures()
            if self._benchmark_dirty:
                self._benchmark.save(
                    self._parser.config_info.benchmark_file)
                self._benchmark_dirty = False

    def do_discard(self, line=''):
        """Discard scoring measures."""
        if line:
            print("'discard' command does not accept arguments.")
            return
        self._parser.load_scoring_measures()

        config_info = self._parser.config_info
        if os.path.isfile(config_info.benchmark_file):
            self._benchmark = \
                benchmarking.Benchmark.load(
                    config_info.benchmark_file
                )
        else:
            self._benchmark = benchmarking.Benchmark()

        self._benchmark_dirty = False

    def do_compare(self, line):
        """Compare two categories to determine if either contains the
        other."""
        definitions = [definition for definition in line.split() if
                       definition]
        if len(definitions) == 0:
            print("Nothing to compare.")
            return
        if len(definitions) == 1:
            print("Nothing to compare with.")
            return
        categories = set()
        for definition in definitions:
            categories.add(
                self._parser_loader.parse_category(
                    definition,
                    offset=line.find(definition) + 1
                )
            )
        categories = sorted(categories, key=lambda category: str(category))
        for category1 in categories:
            for category2 in categories:
                if category1 is not category2:
                    contains_phrase = [
                        " does not contain ",
                        " contains "
                    ][category2 in category1]
                    print(
                        str(category1) +
                        contains_phrase +
                        str(category2)
                    )

    def do_timeout(self, line):
        """Set (or display) the timeout duration for parsing."""
        if not line:
            print(
                "Parsing timeout duration is currently " +
                str(self._timeout_interval) + " seconds"
            )
            return
        try:
            try:
                # Only bother with this because an integer looks prettier
                # when printed.
                self._timeout_interval = int(line)
            except ValueError:
                self._timeout_interval = float(line)
        except ValueError:
            print("Timeout duration could not be set to this value.")
        else:
            print(
                "Set parsing timeout duration to " +
                str(self._timeout_interval) + " seconds."
            )

    def _do_parse(self, line, timeout, new_parser_state=True,
                  restriction_category=None, fast=None):
        if fast is None:
            fast = self._fast
        if new_parser_state:
            self._parser_state = self._parser.new_parser_state()
        parse = self._parser.parse(line, self._parser_state, fast, timeout)
        parse_timed_out = time.time() >= timeout
        emergency_disambiguation = False
        if restriction_category:
            parse = parse.restrict(restriction_category)
        self._parses = [
            disambiguation
            for (disambiguation, rank) in parse.get_sorted_disambiguations(
                None,
                None,
                timeout
            )
        ]
        if not self._parses:
            emergency_disambiguation = True
            self._parses = [parse.disambiguate()]
        disambiguation_timed_out = time.time() >= timeout
        self._whole_parses = len([
            disambiguation
            for disambiguation in self._parses
            if ((len(disambiguation.parse_trees) ==
                 len(self._parses[0].parse_trees)) and
                (disambiguation.total_gap_size() ==
                 self._parses[0].total_gap_size()))
        ])
        self._parse_index = 0
        self._last_input_text = line
        return (
            emergency_disambiguation,
            parse_timed_out,
            disambiguation_timed_out
        )

    def _handle_parse(self, line, new_parser_state=True,
                      restriction_category=None, fast=None):
        """Handles parsing on behalf of do_parse, do_as, and do_extend."""
        if not line:
            print("Nothing to parse.")
            return
        start_time = time.time()
        timeout = start_time + self._timeout_interval
        emergency_disambig, parse_timed_out, disambig_timed_out = \
            self._do_parse(
                line,
                timeout,
                new_parser_state,
                restriction_category,
                fast
            )
        end_time = time.time()
        print('')
        if parse_timed_out:
            print("*** Parse timed out. ***")
        if disambig_timed_out:
            print("*** Disambiguation timed out. ***")
        if emergency_disambig:
            print("*** Using emergency (non-optimal) disambiguation. ***")
        print('')
        print("Total parse time: " + str(
            round(end_time - start_time, 3)) + " seconds")
        print("Total number of parses: " + str(len(self._parses)))
        print("Total number of whole parses: " + str(self._whole_parses))
        print('')
        self.do_current()

    def do_parse(self, line):
        """Parse an input string and print the highest-scoring parse for
        it."""
        self._handle_parse(line)

    def do_as(self, line):
        """Parse an input string as a particular category and print the
        highest-scoring parse for it."""
        if not line:
            print("No category specified.")
            return
        category_definition = line.split()[0]
        category = self._parser_loader.parse_category(category_definition)
        line = line[len(category_definition):].strip()
        self._handle_parse(line, restriction_category=category)

    def do_extend(self, line):
        """Extend the previous input string with additional text and print
         the highest-scoring parse for the combined input strings."""
        self._handle_parse(line, new_parser_state=False)

    def do_files(self, line):
        """Lists the word list files containing a given word."""
        if not line:
            print("No word specified.")
            return
        if len(line.split()) > 1:
            print("Expected only one word.")
            return
        w = line.strip()
        config_info = (
            self._parser.config_info
            if self._parser and self._parser.config_info
            else ParserConfigInfo(
                os.path.abspath('pyramids.ini')
            )
        )
        found = False
        for folder_path in config_info.word_sets_folders:
            for filename in os.listdir(folder_path):
                if not filename.lower().endswith('.ctg'):
                    continue
                file_path = os.path.join(folder_path, filename)
                with open(file_path) as word_set_file:
                    words = set(word_set_file.read().split())
                if w in words:
                    print(repr(w) + " found in " + file_path + ".")
                    found = True
        if not found:
            print(repr(w) + " not found in any word list files.")

    def do_add(self, line):
        """Adds a word to a given category's word list file."""
        if not line:
            print("No category specified.")
            return
        category_definition = line.split()[0]
        category = self._parser_loader.parse_category(category_definition)
        words_to_add = sorted(
            set(line[len(category_definition):].strip().split()))
        if not words_to_add:
            print("No words specified.")
            return
        config_info = (
            self._parser.config_info
            if self._parser and self._parser.config_info
            else ParserConfigInfo(
                os.path.abspath('pyramids.ini')
            )
        )
        found = False
        for folder_path in config_info.word_sets_folders:
            for filename in os.listdir(folder_path):
                if not filename.lower().endswith('.ctg'):
                    continue
                file_category = self._parser_loader.parse_category(
                    filename[:-4]
                )
                if file_category != category:
                    continue
                file_path = os.path.join(folder_path, filename)
                with open(file_path) as word_set_file:
                    words = set(word_set_file.read().split())
                for w in words_to_add:
                    if w in words:
                        print(
                            repr(w) + " was already in " + file_path + "."
                        )
                    else:
                        print(
                            "Adding " + repr(w) + " to " + file_path + "."
                        )
                        words.add(w)
                with open(file_path, 'w') as word_set_file:
                    word_set_file.write('\n'.join(sorted(words)))
                found = True
        if not found:
            for folder_path in config_info.word_sets_folders:
                file_path = os.path.join(
                    folder_path,
                    str(category) + '.ctg'
                )
                print("Creating " + file_path + ".")
                with open(file_path, 'w') as word_set_file:
                    word_set_file.write('\n'.join(sorted(words_to_add)))
                break
            else:
                print("No word sets folder identified. Cannot add words.")
                return
        self.do_reload()

    def do_remove(self, line):
        """Removes a word from a given category's word list file."""
        if not line:
            print("No category specified.")
            return
        category_definition = line.split()[0]
        words_to_remove =\
            set(line[len(category_definition):].strip().split())
        if not words_to_remove:
            print("No words specified.")
            return
        category = self._parser_loader.parse_category(category_definition)
        config_info = (
            self._parser.config_info
            if self._parser and self._parser.config_info
            else ParserConfigInfo(
                os.path.abspath('pyramids.ini')
            )
        )
        found = set()
        for folder_path in config_info.word_sets_folders:
            for filename in os.listdir(folder_path):
                if not filename.lower().endswith('.ctg'):
                    continue
                file_category = self._parser_loader.parse_category(
                    filename[:-4])
                if file_category != category:
                    continue
                file_path = os.path.join(folder_path, filename)
                with open(file_path) as words_file:
                    words = set(words_file.read().split())
                for w in sorted(words_to_remove):
                    if w in words:
                        print(
                            "Removing " + repr(w) + " from " +
                            file_path + "."
                        )
                        words.remove(w)
                        found.add(w)
                    else:
                        print(repr(w) + " not found in " + file_path + ".")
                if words:
                    with open(file_path, 'w') as words_file:
                        words_file.write('\n'.join(sorted(words)))
                else:
                    print(
                        "Deleting empty word list file " + file_path + "."
                    )
                    os.remove(file_path)
        if words_to_remove - found:
            print(
                "No file(s) found containing the following words: " +
                ' '.join(
                    repr(word)
                    for word in sorted(words_to_remove - found)
                ) + "."
            )
            return
        self.do_reload()

    def do_profile(self, line):
        """Profiles the execution of a command, printing the profile
        statistics."""

        # Only a function at the module level can be profiled. To get
        # around this limitation, we define a temporary module-level
        # function that calls the method we want to profile.
        global foo

        def foo():
            self.onecmd(line)

        profile.run('foo()')

    def do_analyze(self, line):
        """Analyzes the last parse and prints statistics useful for
        debugging."""
        if line:
            print("'analyze' command does not accept arguments.")
            return
        if self._parser_state is None:
            print("Nothing to analyze.")
            return
        # TODO: Add to this as further needs arise.
        print('Covered: ' + repr(self._parser_state.is_covered()))
        cat_map = self._parser_state.category_map
        rule_counts = {}
        rule_nodes = {}
        for start, category, end in cat_map:
            for node_set in cat_map.iter_node_sets(start, category, end):
                for node in node_set:
                    rule_counts[node.rule] = rule_counts.get(
                        node.rule,
                        0
                    ) + 1
                    rule_nodes[node.rule] = rule_nodes.get(
                        node.rule,
                        []
                    ) + [node]
        counter = 0
        for rule in sorted(rule_counts, key=rule_counts.get, reverse=True):
            print(str(rule) + " (" + str(rule_counts[rule]) + " nodes)")
            for node_str in sorted(
                    node.to_str(True)
                    for node in rule_nodes[rule]):
                print('    ' + node_str.replace('\n', '\n    '))
                counter += node_str.count('\n') + 1
            if counter >= 100:
                break
        print("Rules in waiting:")
        rule_counts = {}
        for node in self._parser_state.insertion_queue:
            rule_counts[node.rule] = rule_counts.get(node.rule, 0) + 1
        for rule in sorted(rule_counts, key=rule_counts.get, reverse=True):
            print(str(rule) + " (" + str(rule_counts[rule]) + " nodes)")

    def do_links(self, line):
        """Display the semantic net links for the current parse."""
        if line:
            print("'links' command does not accept arguments.")
            return
        if self.parses_available:
            parse = self._parses[self._parse_index]
            graph_builder = graphs.ParseGraphBuilder()
            parse.visit(graph_builder)
            for sentence in graph_builder.get_graphs():
                print(sentence)
                print('')
        else:
            print("No parses found.")

    def do_reverse(self, line):
        """Display token sequences that produce the same semantic net links
        as the current parse."""
        if line:
            print("'reverse' command does not accept arguments.")
            return
        if self.parses_available:
            parse = self._parses[self._parse_index]
            graph_builder = graphs.ParseGraphBuilder()
            start_time = time.time()
            parse.visit(graph_builder)
            sentences = list(graph_builder.get_graphs())
            results = [
                self._parser.generate(sentence)
                for sentence in sentences
            ]
            end_time = time.time()
            for sentence, result in zip(sentences, results):
                print(sentence)
                print('')
                for tree in sorted(result):
                    text = ' '.join(tree.tokens)
                    text = text[:1].upper() + text[1:]
                    for punctuation in ',.?!:;)]}':
                        text = text.replace(' ' + punctuation, punctuation)
                    for punctuation in '([{':
                        text = text.replace(punctuation + ' ', punctuation)
                    print('"' + text + '"')
                    print(tree)
                    print('')
                print('')
                print("Total time: " + str(end_time - start_time) +
                      " seconds")
                print('')
        else:
            print("No parses found.")

    def do_current(self, line=''):
        """Reprint the current parse for the most recent input string."""
        if line:
            print("'current' command does not accept arguments.")
            return
        if self.parses_available:
            parse = self._parses[self._parse_index]
            gaps = parse.total_gap_size()
            size = len(parse.parse_trees)
            score, confidence = parse.get_weighted_score()
            print("Parses #" + str(self._parse_index + 1) + " of " +
                  str(self.max_parse_index + 1) + ":")
            print(parse.to_str(self._simple))
            print("Gaps: " + str(gaps))
            print("Size: " + str(size))
            print("Score: " + str(score))
            print("Confidence: " + str(confidence))
            print("Coverage: " + str(parse.coverage))
        else:
            print("No parses found.")

    def do_next(self, line=''):
        """Print the next parse for the most recent input string."""
        if line:
            print("'next' command does not accept arguments.")
            return
        if self.parses_available:
            if self._parse_index >= self.max_parse_index:
                print("No more parses available.")
                return
            self._parse_index += 1
        self.do_current()

    def do_previous(self, line):
        """Print the previous parse for the most recent input string."""
        if line:
            print("'next' command does not accept arguments.")
            return
        if self.parses_available:
            if self._parse_index <= 0:
                print("No more parses available.")
                return
            self._parse_index -= 1
        self.do_current()

    def do_first(self, line):
        """Print the first parse for the most recent input string."""
        if line:
            print("'first' command does not accept arguments.")
            return
        self._parse_index = 0
        self.do_current()

    def do_last(self, line):
        """Print the last parse for the most recent input string."""
        if line:
            print("'last' command does not accept arguments.")
            return
        self._parse_index = self.max_parse_index
        self.do_current()

    def do_show(self, line):
        """Print the requested parse for the most recent input string."""
        if len(line.split()) != 1:
            print("'show' command requires a single integer argument.")
            return
        try:
            index = int(line.strip())
        except ValueError:
            print("'show' command requires a single integer argument.")
            return
        if not (index and
                (-(self.parses_available + 1) <=
                 index <=
                 self.parses_available + 1)):
            print("Index out of range.")
            return
        if index < 0:
            index += self.parses_available + 1
        else:
            index -= 1
        self._parse_index = index
        self.do_current()

    def do_gaps(self, line):
        """Print the gaps in the current parse."""
        if line:
            print("'gaps' command does not accept arguments.")
            return
        if self.parses_available:
            parse = self._parses[self._parse_index]
            print("Gaps: " + str(parse.total_gap_size()))
            for start, end in parse.iter_gaps():
                print('  ' + str(start) + ' to ' + str(
                    end) + ': ' + ' '.join(parse.tokens[start:end]))
        else:
            print("No parses found.")

    def do_best(self, line):
        """Update the scoring measures of the most recently printed parse
        (and any predecessors it might have had) to show that it was the
        best parse for its input string."""
        if line:
            print("'best' command does not accept arguments.")
            return
        if not self._parses:
            print("No parses available for adjustment.")
            return
        best_parse = self._parses[self._parse_index]
        for iteration in range(100):
            self._parses[self._parse_index].adjust_score(True)
            ranks = {}
            for parse in self._parses:
                ranks[parse] = parse.get_rank()
            self._parses.sort(key=ranks.get, reverse=True)
            self._parse_index = [id(parse) for parse in
                                 self._parses].index(id(best_parse))
            if (self._parses[0] is best_parse or
                    len(self._parses[self._parse_index - 1].parse_trees) !=
                    len(best_parse.parse_trees) or
                    self._parses[self._parse_index - 1].total_gap_size() !=
                    best_parse.total_gap_size()):
                break
        if self._parse_index == 0:
            print("Successfully made this parse the highest ranked.")
        else:
            print("Failed to make this parse the highest ranked.")

    def do_worst(self, line):
        """Update the scoring measures of the most recently printed parse
        (and any successors it might have had) to show that it was the
        worst parse for its input string."""
        if line:
            print("'worst' command does not accept arguments.")
            return
        if not self._parses:
            print("No parses available for adjustment.")
            return
        worst_parse = self._parses[self._parse_index]
        for iteration in range(100):
            self._parses[self._parse_index].adjust_score(False)
            ranks = {}
            for parse in self._parses:
                ranks[parse] = parse.get_rank()
            self._parses.sort(key=ranks.get, reverse=True)
            self._parse_index = [id(parse) for parse in
                                 self._parses].index(id(worst_parse))
            if (self._parses[-1] is worst_parse or
                    len(self._parses[self._parse_index + 1].parse_trees) !=
                    len(worst_parse.parse_trees) or
                    self._parses[self._parse_index + 1].total_gap_size() !=
                    worst_parse.total_gap_size()):
                break
        if self._parse_index == self.max_parse_index:
            print("Successfully made this parse the lowest ranked.")
        else:
            print("Failed to make this parse the lowest ranked.")

    def do_good(self, line):
        """Update the scoring measures of the most recently printed parse
        to show that it was a good parse for its input string."""
        if line:
            print("'next' command does not accept arguments.")
            return
        if not self._parses:
            print("No parses available for adjustment.")
            return
        self._parses[self._parse_index].adjust_score(True)

    def do_bad(self, line):
        """Update the scoring measures of the most recently printed parse
        to show that it was a bad parse for its input string."""
        if line:
            print("'next' command does not accept arguments.")
            return
        if not self._parses:
            print("No parses available for adjustment.")
            return
        self._parses[self._parse_index].adjust_score(False)

    def _get_benchmark_target(self):
        parse = self._parses[self._parse_index]
        graph_builder = graphs.ParseGraphBuilder()
        parse.visit(graph_builder)
        result = set()
        for sentence in graph_builder.get_graphs():
            result.add(str(sentence))
        return '\n'.join(sorted(result))

    def do_keep(self, line):
        """Save the current parse as benchmark case."""
        if line:
            print("'keep' command does not accept arguments.")
            return
        if not self._parses:
            print("No parses available.")
            return
        assert self._benchmark is not None
        self._benchmark.samples[self.last_input_text] = \
            self._get_benchmark_target()
        self._benchmark_dirty = True

    def _benchmark_output(self, text):
        start_time = time.time()
        emergency_disambig, parse_timed_out, disambig_timed_out = \
            self._do_parse(text, start_time + self._timeout_interval)
        end_time = time.time()
        self._benchmark_emergency_disambiguations += \
            int(emergency_disambig)
        self._benchmark_parse_timeouts += int(parse_timed_out)
        self._benchmark_disambiguation_timeouts += \
            int(disambig_timed_out)
        self._benchmark_time += end_time - start_time
        return self._get_benchmark_target()

    def _report_benchmark_progress(self, input_val, output_val, target):
        assert self._benchmark is not None

        self._benchmark_tests_completed += 1
        if time.time() >= self._benchmark_update_time + 1:
            print(
                "Benchmark " +
                str(
                    round(
                        (100 * self._benchmark_tests_completed /
                         float(len(self._benchmark.samples))),
                        1
                    )
                ) + "% complete..."
            )
            self._benchmark_update_time = time.time()

    def do_benchmark(self, line):
        """Parse all benchmark samples and report statistics on them as a
        batch."""
        if line:
            print("'benchmark' command does not accept arguments.")
            return
        if not self._benchmark.samples:
            print("No benchmarking samples.")
            return
        self._benchmark_emergency_disambiguations = 0
        self._benchmark_parse_timeouts = 0
        self._benchmark_disambiguation_timeouts = 0
        self._benchmark_time = 0.0
        self._benchmark_tests_completed = 0
        self._benchmark_update_time = time.time()
        failures, score = self._benchmark.test_and_score(
            self._benchmark_output, self._report_benchmark_progress)
        print("")
        print("Score: " + str(round(100 * score, 1)) + "%")
        print(
            "Average Parse Time: " +
            str(round(self._benchmark_time /
                      float(len(self._benchmark.samples)), 1)) +
            ' seconds per parse'
        )
        print("Samples Evaluated: " + str(len(self._benchmark.samples)))
        print(
            "Emergency Disambiguations: " +
            str(self._benchmark_emergency_disambiguations) + " (" +
            str(round(100 * self._benchmark_emergency_disambiguations /
                      float(len(self._benchmark.samples)), 1)) + '%)'
        )
        print(
            "Parse Timeouts: " +
            str(self._benchmark_parse_timeouts) + " (" +
            str(round(100 * self._benchmark_parse_timeouts /
                      float(len(self._benchmark.samples)), 1)) + '%)'
        )
        print(
            "Disambiguation Timeouts: " +
            str(self._benchmark_disambiguation_timeouts) + " (" +
            str(round(100 * self._benchmark_disambiguation_timeouts /
                      float(len(self._benchmark.samples)), 1)) + '%)'
        )
        if failures:
            print('')
            print("Failures:")
            for input_val, output_val, target in failures:
                print(input_val)
                print(output_val)
                print(target)
                print('')

    # def do_failures(self, line):
    #     if line:
    #         print("'failures' command does not accept arguments.")
    #         return
    #     if self._benchmark_failures is None:
    #         print("No benchmarking batches have been run yet.")
    #     if not self._benchmark_failures:
    #         print("No failures for most recent benchmarking batch.")

    def _scoring_function(self, target):
        # NOTE: It is important that positive reinforcement not
        #       occur if the first try gives the right answer and
        #       the score is already >= .9; otherwise, it will
        #       throw off the relative scoring of other parses.
        if (not target or
                self._parse_index or
                (self._parses[self._parse_index].get_weighted_score()[0] <
                 .9)):
            self._parses[self._parse_index].adjust_score(target)

    def _training_iterator(self, text):
        start_time = time.time()
        emergency_disambig, parse_timed_out, disambig_timed_out = \
            self._do_parse(text, start_time + self._timeout_interval)
        end_time = time.time()
        self._benchmark_emergency_disambiguations += int(
            emergency_disambig)
        self._benchmark_parse_timeouts += int(parse_timed_out)
        self._benchmark_disambiguation_timeouts += int(
            disambig_timed_out)
        self._benchmark_time += end_time - start_time
        if self.parses_available:
            while self._parse_index <= self.max_parse_index:
                # (benchmark target, scoring function)
                yield (
                    self._get_benchmark_target(),
                    self._scoring_function
                )
                self._parse_index += 1

    def do_train(self, line):
        """Automatically adjust scoring to improve benchmark statistics."""
        if line:
            print("'train' command does not accept arguments.")
            return
        if not self._benchmark.samples:
            print("No benchmarking samples.")
            return
        # TODO: Record failures on both training & benchmarking sessions,
        #       and allow a training or benchmarking session only for the
        #       most recently failed benchmark samples by commands of the
        #       form "benchmark failures" and "train failures". Also, add a
        #       "failures" command which lists failures in the form they
        #       are listed in for these two functions, and have these two
        #       functions call into that command instead of printing them
        #       directly.
        self._benchmark_emergency_disambiguations = 0
        self._benchmark_parse_timeouts = 0
        self._benchmark_disambiguation_timeouts = 0
        self._benchmark_time = 0.0
        self._benchmark_tests_completed = 0
        self._benchmark_update_time = time.time()
        failures, score = self._benchmark.train(
            self._training_iterator,
            self._report_benchmark_progress
        )
        print("")
        print("Score: " + str(round(100 * score, 1)) + "%")
        print(
            "Average Parse Time: " +
            str(round(self._benchmark_time /
                      float(len(self._benchmark.samples)), 1)) +
            ' seconds per parse'
        )
        print("Samples Evaluated: " + str(len(self._benchmark.samples)))
        print(
            "Emergency Disambiguations: " +
            str(self._benchmark_emergency_disambiguations) + " (" +
            str(round(100 * self._benchmark_emergency_disambiguations /
                      float(len(self._benchmark.samples)), 1)) + '%)'
        )
        print(
            "Parse Timeouts: " +
            str(self._benchmark_parse_timeouts) + " (" +
            str(round(100 * self._benchmark_parse_timeouts /
                      float(len(self._benchmark.samples)), 1)) + '%)'
        )
        print(
            "Disambiguation Timeouts: " +
            str(self._benchmark_disambiguation_timeouts) + " (" +
            str(round(100 * self._benchmark_disambiguation_timeouts /
                      float(len(self._benchmark.samples)), 1)) + '%)'
        )
        if failures:
            print('')
            print("Failures:")
            for input_val, output_val, target in failures:
                print(input_val)
                print(output_val)
                print(target)
                print('')

    def do_list(self, line):
        """List all benchmark samples."""
        if line:
            print("'list' command does not accept arguments.")
            return
        if not self._benchmark.samples:
            print("No benchmarking samples.")
            return
        print(str(
            len(self._benchmark.samples)) + " recorded benchmark samples:")
        max_tokens = 0
        total_tokens = 0
        for input_val in sorted(self._benchmark.samples):
            print("  " + input_val)
            count = len(list(self._parser.tokenizer.tokenize(input_val)))
            total_tokens += count
            if count > max_tokens:
                max_tokens = count
        print('')
        print("Longest benchmark sample: " + str(max_tokens) + " tokens")
        print("Average benchmark sample length: " + str(
            round(total_tokens / float(len(self._benchmark.samples)),
                  1)) + " tokens")


def load_parser(path=None):
    """Load a parser. If no path is specified, the default parser is
    loaded."""
    if path is None:
        path = 'pyramids.ini'
    parser_path = os.path.abspath(path)
    parser_config_info = ParserConfigInfo(parser_path)
    parser_loader = ParserLoader()
    parser = parser_loader.load_parser(parser_config_info)
    return parser
