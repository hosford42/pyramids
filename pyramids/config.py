# -*- coding: utf-8 -*-

"""
Parser model configuration
"""

import configparser
import os
from typing import Optional, Mapping, Any, FrozenSet, Tuple

from pyramids import categorization
from pyramids.language import Language

__author__ = 'Aaron Hosford'
__all__ = [
    'ModelConfig',
]


class ModelConfig:
    """Parser model configuration"""

    def __init__(self, config_file_path: str, defaults: Mapping[str, Any] = None):
        config_file_path = os.path.abspath(os.path.expanduser(config_file_path))

        if not os.path.isfile(config_file_path):
            raise FileNotFoundError(config_file_path)

        self._config_file_path = config_file_path

        data_folder = os.path.dirname(config_file_path)

        default_word_sets_folder = os.path.join(os.path.dirname(config_file_path), 'word_sets')

        if defaults is None:
            defaults = {}
        else:
            defaults = dict(defaults)
        for option, value in (('Tokenizer Type', 'standard'),
                              ('Discard Spaces', '1'),
                              ('Word Sets Folder', default_word_sets_folder)):
            if option not in defaults:
                defaults[option] = value

        config_parser = configparser.ConfigParser(defaults)
        config_parser.read(self._config_file_path)

        # Languages
        languages = {}
        for language_section in config_parser.sections():
            if not language_section.startswith('Language:'):
                continue
            language_header_name = language_section[9:].strip()
            language_name = config_parser.get(language_section, 'Name',
                                              fallback=language_header_name).strip()
            if not language_name:
                continue
            iso639_1 = config_parser.get(language_section, 'ISO 639-1', fallback=None)
            iso639_2 = config_parser.get(language_section, 'ISO 639-2', fallback=None)
            languages[language_header_name] = Language(language_name, iso639_1, iso639_2)

        # Model
        self._model_name = config_parser.get('Model', 'Name').strip()
        language_section_name = config_parser.get('Model', 'Language', fallback='').strip()
        self._model_language = (languages.get(language_section_name, None)
                                if language_section_name
                                else None)

        # Tokenizer
        self._tokenizer_provider = config_parser.get('Tokenizer', 'Provider').strip()
        self._tokenizer_type = config_parser.get('Tokenizer', 'Tokenizer Type').strip()
        self._discard_spaces = config_parser.getboolean('Tokenizer', 'Discard Spaces')
        language_section_name = config_parser.get('Tokenizer', 'Language', fallback='').strip()
        self._tokenizer_language = (languages.get(language_section_name, None)
                                    if language_section_name
                                    else None)

        # Properties
        self._default_restriction = config_parser.get('Properties', 'Default Restriction',
                                                      fallback='sentence')
        self._top_level_properties = frozenset(
            categorization.Property.get(prop.strip())
            for prop in config_parser.get('Properties', 'Top-Level Properties').split(';')
            if prop.strip()
        )
        self._any_promoted_properties = frozenset(
            categorization.Property.get(prop.strip())
            for prop in config_parser.get('Properties', 'Any-Promoted Properties').split(';')
            if prop.strip()
        )
        self._all_promoted_properties = frozenset(
            categorization.Property.get(prop.strip())
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
            categorization.Property.get(prop_name.strip())
            for prop_name in config_parser.get('Grammar', 'Name Cases').split(';')
            if prop_name.strip()
        )

        # Scoring
        self._score_file = os.path.join(data_folder, config_parser.get('Scoring', 'Score File'))

        # Benchmarking
        self._benchmark_file = os.path.join(data_folder,
                                            config_parser.get('Benchmarking', 'Benchmark File'))

    @property
    def config_file_path(self) -> str:
        """The expanded, absolute path to the primary configuration file for the model"""
        return self._config_file_path

    @property
    def model_name(self) -> str:
        """The name of the model."""
        return self._model_name

    @property
    def model_language(self) -> Optional[Language]:
        """The language of the model."""
        return self._model_language

    @property
    def tokenizer_provider(self) -> str:
        """The plugin provider for the tokenizer."""
        return self._tokenizer_provider

    @property
    def tokenizer_type(self) -> str:
        """The type of tokenizer to use with the model"""
        return self._tokenizer_type

    @property
    def tokenizer_language(self) -> Optional[Language]:
        """The language of the tokenizer."""
        return self._tokenizer_language

    @property
    def discard_spaces(self) -> bool:
        """Whether to discard spaces when tokenizing"""
        return self._discard_spaces

    @property
    def default_restriction(self) -> str:
        """The category that should be used as the restriction for most parsing operations."""
        return self._default_restriction

    @property
    def top_level_properties(self) -> FrozenSet[categorization.Property]:
        """Properties that are of relevance at the root of the parse tree."""
        return self._top_level_properties

    @property
    def any_promoted_properties(self) -> FrozenSet[categorization.Property]:
        """Properties promoted to the head if any child has them"""
        return self._any_promoted_properties

    @property
    def all_promoted_properties(self) -> FrozenSet[categorization.Property]:
        """Properties promoted to the head if all children have them"""
        return self._all_promoted_properties

    @property
    def property_inheritance_files(self) -> Tuple[str, ...]:
        """Property inheritance rule file paths"""
        return self._property_inheritance_files

    @property
    def grammar_definition_files(self) -> Tuple[str, ...]:
        """Grammar definition file paths"""
        return self._grammar_definition_files

    @property
    def conjunction_files(self) -> Tuple[str, ...]:
        """Conjunction rule file paths"""
        return self._conjunction_files

    @property
    def word_sets_folders(self) -> Tuple[str, ...]:
        """Folder paths where word files can be found"""
        return self._word_sets_folders

    @property
    def suffix_files(self) -> Tuple[str, ...]:
        """Suffix rule file paths"""
        return self._suffix_files

    @property
    def special_words_files(self) -> Tuple[str, ...]:
        """Special word rule file paths"""
        return self._special_words_files

    @property
    def score_file(self) -> str:
        """Score file path"""
        return self._score_file

    @property
    def benchmark_file(self) -> str:
        """Benchmark file path"""
        return self._benchmark_file

    @property
    def name_cases(self) -> FrozenSet[categorization.Property]:
        """Case properties that indicate names"""
        return self._name_cases
