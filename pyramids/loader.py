"""
Model loading & saving
"""

import ast
import os
from typing import List, Iterable, Set

import pkg_resources
from sortedcontainers import SortedSet

from pyramids.categorization import Category
from pyramids.config import ModelConfig
from pyramids.grammar import GrammarParser, GrammarSyntaxError
from pyramids.model import Model
from pyramids.rules import PropertyInheritanceRule, CaseRule, SetRule, SuffixRule, ConjunctionRule
from pyramids.scoring import ScoringMeasure

__all__ = [
    'ModelLoader',
]


TOKENIZER_TYPES = {
    entry_point.name: entry_point.load()
    for entry_point in pkg_resources.iter_entry_points('pyramids.tokenizers')
}


class ModelLoader:
    """Model loading & saving"""

    def __init__(self, name: str, model_path: str, verbose: bool = False):
        self.verbose = bool(verbose)
        self._name = name
        self._model_path = model_path
        self._model_config_info = self.load_model_config()
        self._grammar_parser = GrammarParser()

    @property
    def model_config_info(self) -> ModelConfig:
        """Configuration info for the model"""
        return self._model_config_info

    def load_model(self, config_info: ModelConfig = None) -> Model:
        """Load the model and return it."""
        if config_info is None:
            config_info = self._model_config_info

        if self.verbose:
            print("Loading model from", config_info.config_file_path, "...")

        # Tokenizer
        if config_info.tokenizer_type not in TOKENIZER_TYPES:
            raise ValueError("Tokenizer type not supported: " + config_info.tokenizer_type)
        tokenizer = TOKENIZER_TYPES[config_info.tokenizer_type].from_config(self._model_config_info)

        # Properties
        property_inheritance_rules = []
        for path in config_info.property_inheritance_files:
            property_inheritance_rules.extend(self.load_property_inheritance_file(path))

        # Grammar
        branch_rules = []
        primary_leaf_rules = []
        secondary_leaf_rules = []
        for path in config_info.grammar_definition_files:
            branch_rules.extend(self.load_grammar_definition_file(path))
        for path in config_info.conjunction_files:
            branch_rules.extend(self.load_conjunctions_file(path))
        for folder in config_info.word_sets_folders:
            primary_leaf_rules.extend(self.load_word_sets_folder(folder))
        for path in config_info.suffix_files:
            secondary_leaf_rules.extend(self.load_suffix_file(path))
        for path in config_info.special_words_files:
            primary_leaf_rules.extend(self.load_special_words_file(path))
        for case in config_info.name_cases:
            secondary_leaf_rules.append(CaseRule(Category('name'), case))

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

    def load_model_config(self, path: str = None) -> ModelConfig:
        """Load the model config info and return it."""
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

    def load_word_set(self, file_path: str) -> SetRule:
        """Load a word set and return it as a set rule."""
        folder, filename = os.path.split(file_path)
        category_definition = os.path.splitext(filename)[0]
        try:
            category = self._grammar_parser.parse_category(category_definition)
        except GrammarSyntaxError as error:
            raise IOError("Badly named word set file: " + file_path) from error
        if self.verbose:
            print("Loading category", str(category), "from", file_path, "...")
        with open(file_path) as token_file:
            token_set = token_file.read().split()
        return SetRule(category, token_set)

    def load_word_sets_folder(self, folder: str) -> List[SetRule]:
        """Load an entire folder of word sets in one go."""
        leaf_rules = []
        for file_name in os.listdir(folder):
            file_path = os.path.join(folder, file_name)
            if os.path.splitext(file_name)[-1].lower() == '.ctg':
                leaf_rules.append(self.load_word_set(file_path))
            elif self.verbose:
                print("Skipping file " + file_path + "...")
        return leaf_rules

    def load_property_inheritance_file(self, path: str) -> List[PropertyInheritanceRule]:
        """Load a property inheritance file as a list of property inheritance rules."""
        with open(path) as inheritance_file:
            return self._grammar_parser.parse_property_inheritance_file(inheritance_file, filename=path)

    def load_grammar_definition_file(self, path: str):
        with open(path) as grammar_file:
            return self._grammar_parser.parse_grammar_definition_file(grammar_file, filename=path)

    def standardize_word_set_file(self, file_path: str) -> None:
        """Rewrite a word set file, removing duplicates and sorting the contents."""
        with open(file_path) as word_set_file:
            original_data = word_set_file.read()
        data = '\n'.join(sorted(set(original_data.split())))
        if data != original_data:
            with open(file_path, 'w') as word_set_file:
                word_set_file.write(data)
        folder = os.path.dirname(file_path)
        file_name = os.path.basename(file_path)
        category = self._grammar_parser.parse_category(os.path.splitext(file_name)[0])
        if str(category) + '.ctg' != file_name:
            os.rename(file_path, os.path.join(folder, str(category) + '.ctg'))

    def standardize_word_sets_folder(self, folder: str) -> None:
        """Standardize an entire folder of word set files in one go."""
        for file_name in os.listdir(folder):
            file_path = os.path.join(folder, file_name)
            if file_path.endswith('.ctg'):
                self.standardize_word_set_file(file_path)

    def standardize_model(self, config_info: ModelConfig) -> None:
        """Clean up, normalize, and otherwise standardize the parser model."""
        for folder in config_info.word_sets_folders:
            self.standardize_word_sets_folder(folder)

    def get_word_set_categories(self, config_info: ModelConfig) -> Set[Category]:
        """Return the set of categories associated with word set files."""
        categories = set()
        for folder_path in config_info.word_sets_folders:
            for file_name in os.listdir(folder_path):
                if not file_name.lower().endswith('.ctg'):
                    continue
                category = self._grammar_parser.parse_category(file_name[:-4])
                categories.add(category)
        return categories

    def find_word_set_path(self, config_info: ModelConfig, category: Category) -> str:
        """Locate the word set file associated with a particular category, and return its path."""
        for folder_path in config_info.word_sets_folders:
            for file_name in os.listdir(folder_path):
                if not file_name.lower().endswith('.ctg'):
                    continue
                file_category = self._grammar_parser.parse_category(file_name[:-4])
                if file_category == category:
                    return os.path.join(folder_path, file_name)
        for folder_path in config_info.word_sets_folders:
            return os.path.join(folder_path, str(category) + '.ctg')
        raise IOError("Could not find a word sets folder.")

    def add_words(self, config_info: ModelConfig, category: Category, added: Iterable[str]) -> Set[str]:
        """Add words to the word set file associated with a particular category."""
        path = self.find_word_set_path(config_info, category)
        if os.path.isfile(path):
            with open(path) as word_set_file:
                known_words = SortedSet(word_set_file.read().split())
        else:
            known_words = SortedSet()
        added = set(added)
        added.difference_update(known_words)
        known_words.update(added)
        with open(path, 'w') as word_set_file:
            word_set_file.write('\n'.join(known_words))
        return added

    def remove_words(self, config_info: ModelConfig, category: Category, removed: Iterable[str]) -> Set[str]:
        """Remove words from the word set file associated with a particular category."""
        path = self.find_word_set_path(config_info, category)
        if not os.path.isfile(path):
            return set()
        with open(path) as word_set_file:
            known_words = SortedSet(word_set_file.read().split())
        removed = set(removed)
        removed.difference_update(known_words)
        with open(path, 'w') as word_set_file:
            word_set_file.write('\n'.join(known_words))
        return removed

    @staticmethod
    def load_scoring_measures(model: Model, path: str = None) -> None:
        """Load the scoring measures for a model, assigning them to the appropriate rules of the model."""
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
    def save_scoring_measures(model: Model, path: str = None) -> None:
        """Save the scoring measures for a model, gathering them from the model's rules."""
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

    def load_conjunctions_file(self, path: str) -> List[ConjunctionRule]:
        """Load a conjunction grammar file, returning the conjunction rules parsed from it."""
        with open(path) as conjunctions_file:
            return self._grammar_parser.parse_conjunctions_file(conjunctions_file, filename=path)

    def load_suffix_file(self, path: str) -> List[SuffixRule]:
        """Load a suffix grammar file, returning the suffix rules parsed from it."""
        with open(path) as suffix_file:
            return self._grammar_parser.parse_suffix_file(suffix_file, filename=path)

    def load_special_words_file(self, path: str) -> List[SetRule]:
        """Load a special words grammar file, returning the set rules parsed from it."""
        with open(path) as word_file:
            return self._grammar_parser.parse_special_words_file(word_file, filename=path)
