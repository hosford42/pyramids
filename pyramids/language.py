import os
import time
from typing import Optional

from pyramids.config import ParserFactory, ParserConfig
from pyramids.parsing import Parser

__author__ = 'Aaron Hosford'
__version__ = '1.0.0'
__all__ = [
    '__author__',
    '__version__',
    'Language',
]


class Language:

    def __init__(self, name, data_path):
        self._name = name
        self._data_path = data_path
        self._quiet_loader = ParserFactory()
        self._default_parser = None  # type: Optional[Parser]
        self._parser_state = None

    def load_parser_config(self, path=None):
        if path:
            if not os.path.isfile(path):
                raise FileNotFoundError(path)
        else:
            for path in (os.path.abspath('pyramids_%s.ini' % self._name),
                         os.path.abspath(os.path.expanduser('~/pyramids_%s.ini') % self._name),
                         os.path.join(self._data_path, 'pyramids_%s.ini' % self._name)):
                if os.path.isfile(path):
                    break
            else:
                raise FileNotFoundError('pyramids_%s.ini' % self._name)
        return ParserConfig(path)

    def load_parser(self, path=None, verbose=False):
        config_info = self.load_parser_config(path)
        parser_loader = ParserFactory(verbose)
        self._default_parser = parser_loader.load_parser(config_info)
        self._parser_state = self._default_parser.new_parser_state()
        return self._default_parser

    def save_parser(self, path=None):
        if not self._default_parser:
            return  # Nothing to save.

        if path:
            config_info = self.load_parser_config(path)
        else:
            config_info = self._default_parser.config_info
        self._default_parser.save_scoring_measures(config_info)

    def clear_parser_state(self):
        if self._default_parser:
            self._parser_state = self._default_parser.new_parser_state()

    # TODO: Fix this so it returns an empty list, rather than a list containing
    #       an empty parse, if the text could not be parsed.
    def parse(self, text, category=None, fast=False, timeout=None, fresh=True):
        if isinstance(category, str):
            category = self._quiet_loader.parse_category(category)

        if fresh and self._default_parser:
            self.clear_parser_state()

        if not self._default_parser:
            self.load_parser()

        result = self._default_parser.parse(text, self._parser_state, fast, timeout)

        if timeout:
            parse_timed_out = time.time() >= timeout
        else:
            parse_timed_out = False

        if category:
            result = result.restrict(category)

        forests = [disambiguation for (disambiguation, rank) in result.get_sorted_disambiguations(None, None, timeout)]

        if forests:
            emergency_disambiguation = False
        else:
            emergency_disambiguation = True
            forests = [result.disambiguate()]

        if timeout:
            disambiguation_timed_out = time.time() > timeout
        else:
            disambiguation_timed_out = False

        return forests, emergency_disambiguation, parse_timed_out, disambiguation_timed_out

    def repl(self):
        from pyramids.repl import ParserCmd
        parser_cmd = ParserCmd(self)
        print('')
        parser_cmd.cmdloop()
