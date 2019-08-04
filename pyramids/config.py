import configparser
import os

from pyramids import categorization

__author__ = 'Aaron Hosford'
__all__ = [
    'ModelConfig',
]


class ModelConfig:

    def __init__(self, config_file_path, defaults=None):
        if not os.path.isfile(config_file_path):
            raise FileNotFoundError(config_file_path)

        self._config_file_path = config_file_path

        data_folder = os.path.dirname(config_file_path)

        default_word_sets_folder = os.path.join(os.path.dirname(config_file_path), 'word_sets')

        if defaults is None:
            self._defaults = {}
        else:
            self._defaults = dict(defaults)
        for option, value in (('Tokenizer Type', 'standard'),
                              ('Discard Spaces', '1'),
                              ('Word Sets Folder', default_word_sets_folder)):
            if option not in self._defaults:
                self._defaults[option] = value

        config_parser = configparser.ConfigParser(self._defaults)
        config_parser.read(self._config_file_path)

        # Tokenizer
        self._tokenizer_type = config_parser.get('Tokenizer', 'Tokenizer Type').strip()
        self._discard_spaces = config_parser.getboolean('Tokenizer', 'Discard Spaces')

        # Properties
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
            prop_name.strip()
            for prop_name in config_parser.get('Grammar', 'Name Cases').split(';')
            if prop_name.strip()
        )

        # Scoring
        self._scoring_measures_file = os.path.join(data_folder, config_parser.get('Scoring', 'Scoring Measures File'))

        # Benchmarking
        self._benchmark_file = os.path.join(data_folder, config_parser.get('Benchmarking', 'Benchmark File'))

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
