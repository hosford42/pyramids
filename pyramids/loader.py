import ast
import bisect
import os

from pyramids import rules, categorization, exceptions
from pyramids.config import ModelConfig
from pyramids.model import Model
from pyramids.scoring import ScoringMeasure
from pyramids.tokenization import Tokenizer

__all__ = [
    'ModelLoader',
]


class ModelLoader:

    def __init__(self, name: str, model_path: str, verbose: bool = False):
        self.verbose = bool(verbose)
        self._name = name
        self._model_path = model_path
        self._model_config_info = self.load_model_config()

    @property
    def model_config_info(self) -> ModelConfig:
        return self._model_config_info

    def load_model(self, tokenizer: Tokenizer, config_info=None):
        if config_info is None:
            config_info = self._model_config_info

        if self.verbose:
            print("Loading model from", config_info.config_file_path, "...")

        # Tokenizer
        if config_info.tokenizer_type.lower() != 'standard':
            raise ValueError("Tokenizer type not supported: " + config_info.tokenizer_type)

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
            secondary_leaf_rules.append(rules.CaseRule(categorization.Category('name'), case))

        model = Model(primary_leaf_rules, secondary_leaf_rules, branch_rules, tokenizer,
                      config_info.any_promoted_properties, config_info.all_promoted_properties,
                      property_inheritance_rules, config_info)

        # Scoring
        if self.verbose:
            print("Loading scoring measures from", config_info.scoring_measures_file + "...")
        if os.path.isfile(config_info.scoring_measures_file):
            self.load_scoring_measures(model, config_info.scoring_measures_file)
        else:
            self.save_scoring_measures(model, config_info.scoring_measures_file)

        if self.verbose:
            print("Done loading model from", config_info.config_file_path + ".")

        return model

    def load_model_config(self, path=None):
        if path:
            if not os.path.isfile(path):
                raise FileNotFoundError(path)
        else:
            for path in (os.path.abspath('pyramids_%s.ini' % self._name),
                         os.path.abspath(os.path.expanduser('~/pyramids_%s.ini') % self._name),
                         os.path.join(self._model_path, 'pyramids_%s.ini' % self._name)):
                if os.path.isfile(path):
                    break
            else:
                raise FileNotFoundError('pyramids_%s.ini' % self._name)
        return ModelConfig(path)

    @staticmethod
    def parse_category(definition, offset=1):
        definition = definition.strip()
        if '(' in definition:
            if not definition.endswith(')'):
                raise exceptions.GrammarSyntaxError("Expected: ')' in category definition",
                                                    offset=offset + len(definition))
            if definition.count('(') > 1:
                raise exceptions.GrammarSyntaxError("Unexpected: '(' in category definition",
                                                    offset=offset + definition.find("(", definition.find("(") + 1))
            if definition.count(')') > 1:
                raise exceptions.GrammarSyntaxError("Unexpected: ')' in category definition",
                                                    offset=offset + definition.find(")", definition.find(")") + 1))
            name, properties = definition[:-1].split('(')
            if ',' in name:
                raise exceptions.GrammarSyntaxError("Unexpected: ',' in category definition",
                                                    offset=offset + definition.find(","))
            if len(name.split()) > 1:
                raise exceptions.GrammarSyntaxError("Unexpected: white space in category definition",
                                                    offset=offset + len(name) + 1)
            properties = [prop.strip() for prop in properties.split(',')]
            for prop in properties:
                if not prop.strip():
                    if ",," in definition:
                        raise exceptions.GrammarSyntaxError("Unexpected: ','",
                                                            offset=offset + definition.find(",,") + 1)
                    elif "(," in definition:
                        raise exceptions.GrammarSyntaxError("Unexpected: ','",
                                                            offset=offset + definition.find("(,") + 1)
                    elif ",)" in definition:
                        raise exceptions.GrammarSyntaxError("Unexpected: ')'",
                                                            offset=offset + definition.find(",)") + 1)
                    else:
                        raise exceptions.GrammarSyntaxError("Unexpected: ')'",
                                                            offset=offset + definition.find("()") + 1)
            positive = [prop for prop in properties if not prop.startswith('-')]
            negative = [prop[1:] for prop in properties if prop.startswith('-')]
            for prop in negative:
                if prop.startswith('-'):
                    raise exceptions.GrammarSyntaxError("Unexpected: '-'", offset=offset + definition.find('-' + prop))
                if prop in positive:
                    raise exceptions.GrammarSyntaxError("Unexpected: prop is both positive and negative",
                                                        offset=offset + definition.find(prop))
            return categorization.Category(name,
                                           [categorization.Property.get(n) for n in positive],
                                           [categorization.Property.get(n) for n in negative])
        else:
            if ')' in definition:
                raise exceptions.GrammarSyntaxError("Unexpected: ')' in category definition",
                                                    offset=offset + definition.find(")"))
            if ',' in definition:
                raise exceptions.GrammarSyntaxError("Unexpected: ',' in category definition",
                                                    offset=offset + definition.find(","))
            if len(definition.split()) > 1:
                raise exceptions.GrammarSyntaxError("Unexpected: white space in category definition",
                                                    offset=offset + len(definition.split()[0]) + 1)
            if not definition:
                raise exceptions.GrammarSyntaxError("Expected: category definition", offset=offset)
            return categorization.Category(definition)

    def parse_branch_rule_term(self, term, offset=1):
        is_head = False
        if term.startswith('*'):
            term = term[1:]
            offset += 1
            is_head = True
            if '*' in term:
                raise exceptions.GrammarSyntaxError("Unexpected: '*'", offset=offset + term.find('*'))
        subcategories = []
        subcategory_definitions = term.split('|')
        for definition in subcategory_definitions:
            subcategory = self.parse_category(definition, offset=offset)
            subcategories.append(subcategory)
            offset += len(definition) + 1
        if not subcategories:
            raise exceptions.GrammarSyntaxError("Expected: category", offset=offset)
        return is_head, subcategories

    @staticmethod
    def parse_branch_rule_link_type(term, offset=1):
        if '<' in term[1:]:
            raise exceptions.GrammarSyntaxError("Unexpected: '<'", offset=offset + term.find('<', term.find('<') + 1))
        if '>' in term[:-1]:
            raise exceptions.GrammarSyntaxError("Unexpected: '<'", offset=offset + term.find('>'))
        left = term.startswith('<')
        right = term.endswith('>')
        if left:
            term = term[1:]
        if right:
            term = term[:-1]
        if not term:
            raise exceptions.GrammarSyntaxError("Expected: link type", offset=offset + left)
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
                        raise exceptions.GrammarSyntaxError("Unexpected: link type", offset=offset + term_start)
                    link_type, left, right = self.parse_branch_rule_link_type(term, offset + term_start)
                    if head_index is None:
                        if right:
                            raise exceptions.GrammarSyntaxError("Unexpected: right link", offset=offset + term_start)
                    else:
                        if left:
                            raise exceptions.GrammarSyntaxError("Unexpected: left link", offset=offset + term_start)
                    link_types[-1].add((link_type, left, right))
                else:
                    is_head, subcategories = self.parse_branch_rule_term(term, offset=offset + term_start)
                    if is_head:
                        if head_index is not None:
                            raise exceptions.GrammarSyntaxError("Unexpected: '*'",
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
                    raise exceptions.GrammarSyntaxError("Unexpected: '*'", offset=offset + term_start + term.find('*'))
                head_index = len(subcategory_sets)
            subcategory_sets.append(subcategories)
            link_types.append(set())
        if not subcategory_sets:
            raise exceptions.GrammarSyntaxError("Expected: category", offset=offset)
        if link_types[-1]:
            raise exceptions.GrammarSyntaxError("Expected: category", offset=offset + term_start + len(term))
        link_types = link_types[:-1]
        if head_index is None:
            if len(subcategory_sets) != 1:
                raise exceptions.GrammarSyntaxError("Expected: '*'", offset=offset + term_start)
            head_index = 0
        return rules.SequenceRule(category, subcategory_sets, head_index, link_types)

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
                            raise exceptions.GrammarSyntaxError("Unexpected: ':'", offset=1 + line.find(':'))
                        if not category:
                            raise exceptions.GrammarSyntaxError("Expected: category header",
                                                                offset=1 + line.find(line.strip()))
                        branch_rules.append(
                            self.parse_branch_rule(category, line.lstrip(), offset=1 + line.find(line.lstrip())))
                        sequence_found = True
                    else:
                        if category is not None and not sequence_found:
                            raise exceptions.GrammarSyntaxError("Expected: category sequence", offset=1)
                        if ':' not in line:
                            raise exceptions.GrammarSyntaxError("Expected: ':'", offset=1 + len(line))
                        if line.count(':') > 1:
                            raise exceptions.GrammarSyntaxError("Unexpected: ':'",
                                                                offset=1 + line.find(':', line.find(':') + 1))
                        header, sequence = line.split(':')
                        category = self.parse_category(header)
                        if sequence.strip():
                            branch_rules.append(self.parse_branch_rule(category, sequence.lstrip(),
                                                                       offset=1 + sequence.find(sequence.lstrip())))
                            sequence_found = True
                        else:
                            sequence_found = False
                except exceptions.GrammarParserError as error:
                    error.set_info(path, line_number, None, raw_line)
                    raise error
                except Exception as original_exception:
                    raise exceptions.GrammarParserError(None, path, line_number, None, raw_line) from original_exception
        return branch_rules

    def parse_match_rule(self, definition, offset=1):
        if not definition.startswith('['):
            raise exceptions.GrammarSyntaxError("Expected: '['", offset)
        if not definition.endswith(']'):
            raise exceptions.GrammarSyntaxError("Expected: ']'", offset + len(definition) - 1)
        generator_map = {
            'any_term': rules.AnyTermMatchRule,
            'all_terms': rules.AllTermsMatchRule,
            'compound': rules.CompoundMatchRule,
            'head': rules.HeadMatchRule,
            'one_term': rules.OneTermMatchRule,
            'last_term': rules.LastTermMatchRule,
        }
        rule_list = []
        for category_definition in definition[1:-1].split():
            category = self.parse_category(category_definition, offset=1 + definition.find(category_definition))
            generator = generator_map.get(str(category.name), None)
            if generator is None:
                raise exceptions.GrammarSyntaxError("Unexpected: " + repr(category),
                                                    offset=1 + definition.find(category_definition))
            else:
                assert callable(generator)
                rule_list.append(generator(category.positive_properties, category.negative_properties))
        if not rule_list:
            raise exceptions.GrammarSyntaxError("Expected: category")
        return tuple(rule_list)

    def parse_conjunction_rule(self, category, match_rules, property_rules, definition, offset=1):
        single = False
        compound = False
        while definition[:1] in ('+', '-'):
            if definition[0] == '+':
                if compound:
                    raise exceptions.GrammarSyntaxError("Unexpected: '+'", offset=offset)
                compound = True
            else:
                if single:
                    raise exceptions.GrammarSyntaxError("Unexpected: '-'", offset=offset)
                single = True
            definition = definition[1:]
            offset += 1
        # TODO: While functional, this is a copy/paste from parse_branch_rule. Modify it to fit conjunctions more
        #       cleanly, or combine the two methods.
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
                        raise exceptions.GrammarSyntaxError("Unexpected: link type", offset=offset + term_start)
                    link_type, left, right = self.parse_branch_rule_link_type(term, offset + term_start)
                    if head_index is None:
                        if right:
                            raise exceptions.GrammarSyntaxError("Unexpected: right link", offset=offset + term_start)
                    else:
                        if left:
                            raise exceptions.GrammarSyntaxError("Unexpected: left link", offset=offset + term_start)
                    link_types[-1].add((link_type, left, right))
                else:
                    is_head, subcategories = self.parse_branch_rule_term(term, offset=offset + term_start)
                    if is_head:
                        if head_index is not None:
                            raise exceptions.GrammarSyntaxError("Unexpected: '*'",
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
            is_head, subcategories = self.parse_branch_rule_term(term, offset=offset + term_start)
            if is_head:
                if head_index is not None:
                    raise exceptions.GrammarSyntaxError("Unexpected: '*'", offset=offset + term_start + term.find('*'))
                head_index = len(subcategory_sets)
            subcategory_sets.append(subcategories)
            link_types.append(set())
        if not subcategory_sets:
            raise exceptions.GrammarSyntaxError("Expected: category", offset=offset)
        if link_types[-1]:
            raise exceptions.GrammarSyntaxError("Expected: category", offset=offset + term_start + len(term))
        link_types = link_types[:-1]
        if head_index is None:
            if len(subcategory_sets) != 1:
                raise exceptions.GrammarSyntaxError("Expected: '*'", offset=offset + term_start)
            head_index = 0
        # TODO: Specify offsets for these errors.
        if len(subcategory_sets) > 3:
            raise exceptions.GrammarSyntaxError("Unexpected: category")
        elif len(subcategory_sets) < 2:
            raise exceptions.GrammarSyntaxError("Expected: category")
        elif len(subcategory_sets) == 3:
            if head_index != 1:
                raise exceptions.GrammarSyntaxError("Unexpected: category")
            leadup_cats, conjunction_cats, followup_cats = subcategory_sets
            leadup_link_types, followup_link_types = link_types
        else:  # if len(subcategory_sets) == 2:
            if head_index != 0:
                raise exceptions.GrammarSyntaxError("Expected: category")
            leadup_cats = None
            conjunction_cats, followup_cats = subcategory_sets
            # TODO: While these are sets, ConjunctionRule expects
            #       individual links. Modify ConjunctionRule to expect sets
            leadup_link_types = set()

            followup_link_types = link_types[0]
        return rules.ConjunctionRule(category, match_rules, property_rules, leadup_cats, conjunction_cats,
                                     followup_cats, leadup_link_types, followup_link_types, single, compound)

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
                            raise exceptions.GrammarSyntaxError("Unexpected: ':'", offset=1 + line.find(':'))
                        if not category:
                            raise exceptions.GrammarSyntaxError("Expected: category header",
                                                                offset=1 + line.find(line.strip()))
                        if line.endswith(']') and '[' in line:
                            if line.lstrip().startswith('['):
                                if match_rules_closed:
                                    # TODO: offset?
                                    raise exceptions.GrammarSyntaxError("Unexpected: matching rule")
                                match_rules.append(self.parse_match_rule(line.lstrip(),
                                                                         offset=1 + line.find(line.lstrip())))
                            else:
                                if property_rules_closed:
                                    # TODO: offset?
                                    raise exceptions.GrammarSyntaxError("Unexpected: property rule")
                                match_rules_closed = True
                                left_bracket_index = line.index('[')
                                property_names = line[:left_bracket_index].strip().split(',')
                                properties = set()
                                for property_name in property_names:
                                    if property_name.startswith('-'):
                                        properties.add((categorization.Property.get(property_name[1:]), False))
                                    else:
                                        properties.add((categorization.Property.get(property_name), True))
                                line_remainder = line[left_bracket_index:]
                                property_rules.append(
                                    (frozenset(properties),
                                     self.parse_match_rule(line_remainder.lstrip(),
                                                           offset=1 + line.find(line_remainder.strip()))))
                        else:
                            match_rules_closed = True
                            property_rules_closed = True
                            if '[' in line:
                                raise exceptions.GrammarSyntaxError("Unexpected: '['", offset=1 + line.find('['))
                            if ']' in line:
                                raise exceptions.GrammarSyntaxError("Unexpected: ']'", offset=1 + line.find(']'))
                            branch_rules.append(self.parse_conjunction_rule(category, match_rules, property_rules,
                                                                            line.lstrip(),
                                                                            offset=1 + line.find(line.lstrip())))
                            sequence_found = True
                    else:
                        if category is not None and not sequence_found:
                            raise exceptions.GrammarSyntaxError("Expected: category sequence", offset=1)
                        if ':' not in line:
                            raise exceptions.GrammarSyntaxError("Expected: ':'", offset=1 + len(line))
                        if line.count(':') > 1:
                            raise exceptions.GrammarSyntaxError("Unexpected: ':'",
                                                                offset=1 + line.find(':', line.find(':') + 1))
                        header, sequence = line.split(':')
                        category = self.parse_category(header)
                        match_rules = []
                        match_rules_closed = False
                        property_rules = []
                        property_rules_closed = False
                        if sequence.strip():
                            branch_rules.append(
                                self.parse_conjunction_rule(category, match_rules, property_rules, sequence.lstrip(),
                                                            offset=1 + sequence.find(sequence.lstrip())))
                            sequence_found = True
                        else:
                            sequence_found = False
                except exceptions.GrammarParserError as error:
                    error.set_info(path, line_number, None, raw_line)
                    raise error
                except Exception as original_exception:
                    raise exceptions.GrammarParserError(None, path, line_number, None, raw_line) from original_exception
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
                        raise exceptions.GrammarSyntaxError("Expected: ':'", filename=path, lineno=line_number,
                                                            offset=1 + len(line), text=raw_line)
                    if line.count(':') > 1:
                        raise exceptions.GrammarSyntaxError("Unexpected: ':'", filename=path, lineno=line_number,
                                                            offset=1 + line.find(':', line.find(':') + 1),
                                                            text=raw_line)
                    definition, suffixes = line.split(':')
                    try:
                        category = self.parse_category(definition)
                    except exceptions.GrammarParserError as error:
                        error.set_info(path, line_number, None, line)
                        raise error
                    except Exception as original_exception:
                        raise exceptions.GrammarParserError(None, path, line_number, None, line) from original_exception
                    suffixes = suffixes.split()
                    if not suffixes or suffixes[0] not in ('+', '-'):
                        raise exceptions.GrammarSyntaxError("Expected: '+' or '-'", filename=path, lineno=line_number,
                                                            offset=1 + line.find(':') + 1, text=raw_line)
                    positive = suffixes.pop(0) == '+'
                    suffixes = frozenset(suffixes)
                    if not suffixes:
                        suffixes = frozenset([''])
                    leaf_rules.append(rules.SuffixRule(category, suffixes, positive))
                except exceptions.GrammarParserError as error:
                    error.set_info(path, line_number, text=raw_line)
                    raise error
                except Exception as original_exception:
                    raise exceptions.GrammarParserError(None, path, line_number, None, raw_line) from original_exception
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
                        raise exceptions.GrammarSyntaxError("Expected: ':'", filename=path, lineno=line_number,
                                                            offset=1 + len(line), text=raw_line)
                    line = line.split(':')
                    definition = line.pop(0)
                    token_str = ':'.join(line)
                    try:
                        category = self.parse_category(definition)
                    except exceptions.GrammarParserError as error:
                        error.set_info(path, line_number, None, line)
                        raise error
                    except Exception as original_exception:
                        raise exceptions.GrammarParserError(None, path, line_number, None, line) from original_exception
                    token_set = frozenset(token_str.split())
                    leaf_rules.append(rules.SetRule(category, token_set))
                except exceptions.GrammarParserError as error:
                    error.set_info(path, line_number, text=raw_line)
                    raise error
                except Exception as original_exception:
                    raise exceptions.GrammarParserError(None, path, line_number, None, raw_line) from original_exception
        return leaf_rules

    def load_word_set(self, file_path):
        folder, filename = os.path.split(file_path)
        category_definition = os.path.splitext(filename)[0]
        try:
            category = self.parse_category(category_definition)
        except exceptions.GrammarSyntaxError:
            raise IOError("Badly named word set file: " + file_path)
        if self.verbose:
            print("Loading category", str(category), "from", file_path, "...")
        with open(file_path) as token_file:
            token_set = token_file.read().split()
        return rules.SetRule(category, token_set)

    def load_word_sets_folder(self, folder):
        # TODO: Should this do a directory walk instead?
        leaf_rules = []
        for file_name in os.listdir(folder):
            file_path = os.path.join(folder, file_name)
            if os.path.splitext(file_name)[-1].lower() == '.ctg':
                leaf_rules.append(self.load_word_set(file_path))
            elif self.verbose:
                print("Skipping file " + file_path + "...")
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
                        raise exceptions.GrammarSyntaxError("Expected: ':'", filename=path, lineno=line_number,
                                                            offset=1 + len(line), text=raw_line)
                    if line.count(':') > 1:
                        raise exceptions.GrammarSyntaxError("Unexpected: ':'", filename=path, lineno=line_number,
                                                            offset=1 + line.find(':', line.find(':') + 1),
                                                            text=raw_line)
                    definition, additions = line.split(':')
                    try:
                        category = self.parse_category(definition)
                    except exceptions.GrammarParserError as error:
                        error.set_info(path, line_number, None, line)
                        raise error
                    except Exception as original_exception:
                        raise exceptions.GrammarParserError(None, path, line_number, None, line) from original_exception
                    additions = additions.split()
                    if not additions:
                        raise exceptions.GrammarSyntaxError("Expected: property", filename=path, lineno=line_number,
                                                            offset=1 + line.find(':') + 1, text=raw_line)
                    positive_additions = [addition for addition in additions if not addition.startswith('-')]
                    negative_additions = [addition[1:] for addition in additions if addition.startswith('-')]
                    # TODO: Check negative additions for a double '-'
                    # TODO: Check that positive & negative additions don't
                    #       conflict
                    inheritance_rules.append(rules.PropertyInheritanceRule(category, positive_additions,
                                                                           negative_additions))
                except exceptions.GrammarParserError as error:
                    exceptions.GrammarSyntaxError.set_info(path, line_number, text=raw_line)
                    raise error
                except Exception as original_exception:
                    raise exceptions.GrammarParserError(None, path, line_number, None, raw_line) from original_exception
        return inheritance_rules

    def standardize_word_set_file(self, file_path):
        with open(file_path) as word_set_file:
            original_data = word_set_file.read()
        data = '\n'.join(sorted(set(original_data.split())))
        if data != original_data:
            with open(file_path, 'w') as word_set_file:
                word_set_file.write(data)
        folder = os.path.dirname(file_path)
        file_name = os.path.basename(file_path)
        category = self.parse_category(os.path.splitext(file_name)[0])
        if str(category) + '.ctg' != file_name:
            os.rename(file_path, os.path.join(folder, str(category) + '.ctg'))

    def standardize_word_sets_folder(self, folder):
        for file_name in os.listdir(folder):
            file_path = os.path.join(folder, file_name)
            if file_path.endswith('.ctg'):
                self.standardize_word_set_file(file_path)

    def standardize_parser(self, config_info):
        for folder in config_info.word_sets_folders:
            self.standardize_word_sets_folder(folder)

    def get_word_set_categories(self, config_info):
        categories = set()
        for folder_path in config_info.word_sets_folders:
            for file_name in os.listdir(folder_path):
                if not file_name.lower().endswith('.ctg'):
                    continue
                category = self.parse_category(file_name[:-4])
                categories.add(category)
        return categories

    def find_word_set_path(self, config_info, category):
        for folder_path in config_info.word_sets_folders:
            for file_name in os.listdir(folder_path):
                if not file_name.lower().endswith('.ctg'):
                    continue
                file_category = self.parse_category(file_name[:-4])
                if file_category == category:
                    return os.path.join(folder_path, file_name)
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

    @staticmethod
    def load_scoring_measures(model: Model, path=None):
        if path is None:
            path = model.config_info.scoring_measures_file
        scores = {}
        with open(path, 'r') as save_file:
            for line in save_file:
                rule_str, measure_str, score_str, accuracy_str, count_str = line.strip().split('\t')
                if rule_str not in scores:
                    scores[rule_str] = {}
                measure = ast.literal_eval(measure_str)
                scores[rule_str][measure] = (float(score_str), float(accuracy_str), int(count_str))
            for rule in model.primary_leaf_rules | model.secondary_leaf_rules | model.branch_rules:
                rule_str = repr(str(rule))
                if rule_str not in scores:
                    continue
                for measure, (score, accuracy, count) in scores[rule_str].items():
                    rule.set_score(measure, score, accuracy, count)

    @staticmethod
    def save_scoring_measures(model: Model, path=None):
        if path is None:
            path = model.config_info.scoring_measures_file
        with open(path, 'w') as save_file:
            for rule in sorted(model.primary_leaf_rules | model.secondary_leaf_rules | model.branch_rules, key=str):
                for measure in rule.iter_all_scoring_measures():
                    score, accuracy, count = rule.get_score(measure)
                    if isinstance(measure, ScoringMeasure):
                        measure = measure.value
                    if not count:
                        continue
                    save_file.write('\t'.join(repr(item) for item in (str(rule), measure, score, accuracy, count)))
                    save_file.write('\n')

    # def load(self, path=None, verbose=False):
    #     config_info = self.load_parser_config(path)
    #     parser_loader = ModelLoader(verbose)
    #     self._parser = parser_loader.load_model(config_info)
    #     self._parser_state = self._parser.new_parser_state()
    #     return self._parser
    #
    # def save(self, path=None):
    #     if not self._parser:
    #         return  # Nothing to save.
    #
    #     if path:
    #         config_info = self.load_parser_config(path)
    #     else:
    #         config_info = self._parser.config_info
    #     self._parser.save_scoring_measures(config_info)


# def load_parser(path=None):
#     """Load a parser. If no path is specified, the default parser is loaded."""
#     if path is None:
#         path = 'pyramids.ini'
#     parser_path = os.path.abspath(path)
#     parser_config_info = ModelConfig(parser_path)
#     parser_factory = ModelLoader()
#     parser = parser_factory.load_model(parser_config_info)
#     return parser
