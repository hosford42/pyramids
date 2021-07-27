# -*- coding: utf-8 -*-

"""Model loading & saving."""

import ast
import os
from typing import List, Iterable, Set, Tuple, Dict

from sortedcontainers import SortedSet

from pyramids.categorization import Category
from pyramids.config import ModelConfig
from pyramids.grammar import GrammarParser
from pyramids.model import Model
from pyramids.rules.case import CaseRule
from pyramids.rules.conjunction import ConjunctionRule
from pyramids.rules.property_inheritance import PropertyInheritanceRule
from pyramids.rules.sequence import SequenceRule
from pyramids.rules.suffix import SuffixRule
from pyramids.rules.token_set import SetRule
from pyramids.scoring import ScoringFeature
from pyramids.tokenization import Tokenizer
from pyramids.word_sets import WordSetUtils

__all__ = [
    'ModelLoader',
    'ScoreMap',
]


ScoreMap = Dict[str, Dict[ScoringFeature, Tuple[float, float, int]]]


class ModelLoader:
    """Model loading & saving."""

    def __init__(self, name: str, model_path: str, verbose: bool = False):
        self.verbose = bool(verbose)
        self._name = name
        self._model_path = model_path
        self._model_config_info = self.load_model_config()
        self._grammar_parser = GrammarParser()

    @property
    def model_config_info(self) -> ModelConfig:
        """Get the configuration info for the model."""
        return self._model_config_info

    def load_tokenizer(self, config_info: ModelConfig = None) -> Tokenizer:
        """Load an appropriately configured tokenizer instance."""
        from pyramids import plugins
        if config_info is None:
            config_info = self._model_config_info

        # Tokenizer
        tokenizer = plugins.get_tokenizer(config_info.tokenizer_provider,
                                          config_info.tokenizer_type,
                                          self._model_config_info)
        if tokenizer is None:
            raise ValueError("Unrecognized tokenizer type: " + config_info.tokenizer_type +
                             "\nDo you have the required plugin package installed?")
        return tokenizer

    def load_model(self, config_info: ModelConfig = None) -> Model:
        """Load the model and return it."""
        if config_info is None:
            config_info = self._model_config_info

        if self.verbose:
            print("Loading model from", config_info.config_file_path, "...")

        tokenizer = self.load_tokenizer(config_info)
        model = self._create_model(config_info, tokenizer)
        self._init_model_scoring(config_info, model)

        if self.verbose:
            print("Done loading model from", config_info.config_file_path + ".")

        return model

    def _init_model_scoring(self, config_info: ModelConfig, model: 'Model') -> None:
        # Scoring
        if self.verbose:
            print("Loading scoring features from", config_info.score_file + "...")
        if os.path.isfile(config_info.score_file):
            score_map = self.load_scoring_features(model, config_info.score_file)
            self.update_model_scoring_features(model, score_map)
        else:
            self.save_scoring_features(model, config_info.score_file)

    def _create_model(self, config_info: ModelConfig, tokenizer: Tokenizer) -> 'Model':
        default_restriction = GrammarParser.parse_category(config_info.default_restriction)
        top_level_properties = config_info.top_level_properties

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

        model_link_types = set()
        for rule in branch_rules:
            model_link_types.update(rule.all_link_types)
        model_link_types = frozenset(model_link_types)

        return Model(default_restriction, top_level_properties, model_link_types,
                     primary_leaf_rules, secondary_leaf_rules, branch_rules, tokenizer,
                     config_info.any_promoted_properties, config_info.all_promoted_properties,
                     property_inheritance_rules, config_info.model_language, config_info)

    def load_model_config(self, path: str = None) -> ModelConfig:
        """Load the model config info and return it."""
        if path and os.path.isfile(path):
            return ModelConfig(path)
        for search_path in (path,
                            os.path.abspath('.'),
                            os.path.abspath(os.path.expanduser('~')),
                            self._model_path):
            if search_path is None:
                continue
            for file_name in 'pyramids_%s.ini' % self._name, '%s.ini' % self._name:
                file_path = os.path.join(search_path, file_name)
                if os.path.isfile(file_path):
                    return ModelConfig(file_path)
        raise FileNotFoundError(path or '%s.ini' % self._name)

    def load_word_sets_folder(self, folder: str) -> List[SetRule]:
        """Load an entire folder of word sets in one go."""
        leaf_rules = []
        for file_name in os.listdir(folder):
            file_path = os.path.join(folder, file_name)
            if os.path.splitext(file_name)[-1].lower() == '.ctg':
                leaf_rules.append(SetRule.from_word_set(file_path, verbose=self.verbose))
            elif self.verbose:
                print("Skipping file " + file_path + "...")
        return leaf_rules

    def load_property_inheritance_file(self, path: str) -> List[PropertyInheritanceRule]:
        """Load a property inheritance file as a list of property inheritance rules."""
        with open(path, encoding='utf-8') as inheritance_file:
            return self._grammar_parser.parse_property_inheritance_file(inheritance_file,
                                                                        filename=path)

    def load_grammar_definition_file(self, path: str) -> List[SequenceRule]:
        """Load a grammar definition file as a list of branch rules."""
        with open(path, encoding='utf-8') as grammar_file:
            return self._grammar_parser.parse_grammar_definition_file(grammar_file, filename=path)

    def standardize_word_set_file(self, file_path: str) -> None:
        """Rewrite a word set file, removing duplicates and sorting the contents."""
        WordSetUtils.save_word_set(file_path, WordSetUtils.load_word_set(file_path))
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

    def add_words(self, config_info: ModelConfig, category: Category,
                  added: Iterable[str]) -> Set[str]:
        """Add words to the word set file associated with a particular category."""
        path = self.find_word_set_path(config_info, category)
        if os.path.isfile(path):
            known_words = WordSetUtils.load_word_set(path)
        else:
            known_words = SortedSet()
        added = set(added)
        added.difference_update(known_words)
        known_words.update(added)
        WordSetUtils.save_word_set(path, known_words)
        return added

    def remove_words(self, config_info: ModelConfig, category: Category,
                     removed: Iterable[str]) -> Set[str]:
        """Remove words from the word set file associated with a particular category."""
        path = self.find_word_set_path(config_info, category)
        if not os.path.isfile(path):
            return set()
        known_words = WordSetUtils.load_word_set(path)
        removed = set(removed)
        removed.difference_update(known_words)
        WordSetUtils.save_word_set(path, known_words)
        return removed

    @staticmethod
    def load_scoring_features(model: Model, path: str = None) -> ScoreMap:
        """Load the scoring features for a model, assigning them to the appropriate rules of the
        model."""
        if path is None:
            path = model.config_info.score_file
        scores = {}  # type: ScoreMap
        with open(path, encoding='utf-8') as save_file:
            for line in save_file:
                rule_str, feature_str, score_str, accuracy_str, count_str = line.strip().split('\t')
                if rule_str not in scores:
                    scores[rule_str] = {}
                feature = ast.literal_eval(feature_str)
                scores[rule_str][feature] = (float(score_str), float(accuracy_str), int(count_str))
        return scores

    @staticmethod
    def update_model_scoring_features(model: Model, scores: ScoreMap) -> None:
        """Update the mode's scoring features in place, from a score map returned by
        load_scoring_features."""
        for rule in model.primary_leaf_rules | model.secondary_leaf_rules | model.branch_rules:
            rule_str = repr(str(rule))
            if rule_str not in scores:
                continue
            for feature, (score, accuracy, count) in scores[rule_str].items():
                rule.set_score(feature, score, accuracy, count)

    @staticmethod
    def save_scoring_features(model: Model, path: str = None) -> None:
        """Save the scoring features for a model, gathering them from the model's rules."""
        if path is None:
            path = model.config_info.score_file
        with open(path, 'w', encoding='utf-8') as save_file:
            for rule in sorted(model.primary_leaf_rules |
                               model.secondary_leaf_rules |
                               model.branch_rules,
                               key=str):
                for feature in rule.iter_all_scoring_features():
                    score, accuracy, count = rule.get_score(feature)
                    if isinstance(feature, ScoringFeature):
                        feature = feature.key
                    if not count:
                        continue
                    save_file.write('\t'.join(repr(item) for item in (str(rule), feature, score,
                                                                      accuracy, count)))
                    save_file.write('\n')

    def load_conjunctions_file(self, path: str) -> List[ConjunctionRule]:
        """Load a conjunction grammar file, returning the conjunction rules parsed from it."""
        with open(path, encoding='utf-8') as conjunctions_file:
            return self._grammar_parser.parse_conjunctions_file(conjunctions_file, filename=path)

    def load_suffix_file(self, path: str) -> List[SuffixRule]:
        """Load a suffix grammar file, returning the suffix rules parsed from it."""
        with open(path, encoding='utf-8') as suffix_file:
            return self._grammar_parser.parse_suffix_file(suffix_file, filename=path)

    def load_special_words_file(self, path: str) -> List[SetRule]:
        """Load a special words grammar file, returning the set rules parsed from it."""
        with open(path, encoding='utf-8') as word_file:
            return self._grammar_parser.parse_special_words_file(word_file, filename=path)
