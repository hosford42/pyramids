#!/usr/bin/env python

"""
Pyramids
========
A parser for extraction of semantic information from natural language.
Copyright (c) Aaron Hosford 2011-2019
MIT License (http://opensource.org/licenses/MIT)

Pyramids gets its name from the way it constructs parse trees, working
upwards from the leaves towards the root, building up layers of
progressively smaller size but greater scope. It is a rule-based natural
language parser which builds multiple competing parses for a sentence from
the bottom up using principles of dynamic programming. The parses are then
scored for quality and presented in order of descending rank. The parser is
also capable of accepting feedback as to which parses are or are not acceptable,
adaptively adjusting its scoring measures to improve future parse quality and
ranking. Parses are returned as trees but can also be used to generate graphs
representing the semantic relationships between words. The syntactic rules of
the parser can also be run in reverse to generate sentences from semantic graphs
resembling those it produces.
"""

# =========================================================================
# Modification History:
#
#   7/14/2011:
#     - Created this module using basic_parser.py as a template.
#   8/4/2015:
#     - Python 2.7 => Python 3.4
#
# =========================================================================


import os
import time

from pyramids.trees import Parse
from pyramids.config import ParserConfig, ParserFactory
from pyramids.repl import ParserCmd
from pyramids.graphs import ParseGraphBuilder, ParseGraph


__author__ = 'Aaron Hosford'
__copyright__ = """
Copyright (c) 2011-2015 Aaron Hosford
All Rights Reserved.
""".strip()
__credits__ = ['Aaron Hosford']
__license__ = 'MIT'
__version__ = '0.1'
__maintainer__ = 'Aaron Hosford'
__email__ = 'hosford42@gmail.com'
__status__ = 'Prototype'
__all__ = [
    'load_parser',
    'clear_parser_state',
    'parse',
    'get_parse_graphs',
    'main',
    '__author__',
    '__license__',
    '__version__'
]


# TODO: Factor complexity costs into parse scores; the further a parse tree
#       is from the ideal depth, the worse it fares.

# TODO: Add in stopping conditions, so that if a full-coverage tree has
#       lower average score than a forest of sentences that together cover
#       the same text, the forest of sentences is used instead.

# TODO: Handle emergency parsing by ignoring properties when the best
#       parse's score is sufficiently terrible or no full-coverage tree is
#       found.

# TODO: Add a precedence system to the grammar, allowing us to indicate
#       just how desperate the parser has to be before it even tries a
#       particular rule. Then we can implement the above TODO by having
#       property-free versions automatically generated for each rule, with
#       last-ditch priority. It should also significantly reduce parsing
#       time for certain situations if we make less common usage have
#       slightly lower precedence, by avoiding checking those rules if they
#       aren't worth it. Another option would be to have a score-based
#       cutoff in the parsing routine which disregards potential parse
#       trees & stops early if a full- coverage parse has been found and
#       that parse's score is way higher than all the partial trees left to
#       be considered. Or it could compare the score of each new parse tree
#       to be considered against its direct competitors instead of the
#       parse as a whole, so we save time even when a parse fails.

# TODO: Where should the data folder go? Is it in the standard place?


_quiet_loader = ParserFactory()

_default_parser = None
_parser_state = None


def load_parser_config(path=None):
    if path:
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
    else:
        for path in (os.path.abspath('pyramids.ini'),
                     os.path.abspath('data/pyramids.ini'),
                     os.path.join(os.path.dirname(__file__),
                                  'data/pyramids.ini')):
            if os.path.isfile(path):
                break
        else:
            raise FileNotFoundError('pyramids.ini')

    return ParserConfig(path)


def load_parser(path=None, verbose=False):
    global _default_parser, _parser_state

    config_info = load_parser_config(path)
    parser_loader = ParserFactory(verbose)
    _default_parser = parser_loader.load_parser(config_info)
    _parser_state = _default_parser.new_parser_state()
    return _default_parser


def save_parser(path=None):
    global _default_parser
    if not _default_parser:
        return  # Nothing to save.

    config_info = load_parser_config(path)
    _default_parser.save_scoring_measures(config_info.scoring_measures_file)


def clear_parser_state():
    global _parser_state
    if _default_parser:
        _parser_state = _default_parser.new_parser_state()


# TODO: Fix this so it returns an empty list, rather than a list containing
#       an empty parse, if the text could not be parsed.
def parse(text, category=None, fast=False, timeout=None, fresh=True):
    if isinstance(category, str):
        category = _quiet_loader.parse_category(category)

    if fresh and _default_parser:
        clear_parser_state()

    if not _default_parser:
        load_parser()

    result = _default_parser.parse(text, _parser_state, fast, timeout)

    if timeout:
        parse_timed_out = time.time() >= timeout
    else:
        parse_timed_out = False

    if category:
        result = result.restrict(category)

    forests = [
        disambiguation
        for (disambiguation, rank) in result.get_sorted_disambiguations(
            None,
            None,
            timeout
        )
    ]

    if forests:
        emergency_disambiguation = False
    else:
        emergency_disambiguation = True
        forests = [result.disambiguate()]

    if timeout:
        disambiguation_timed_out = time.time() > timeout
    else:
        disambiguation_timed_out = False

    return (
        forests,
        emergency_disambiguation,
        parse_timed_out,
        disambiguation_timed_out
    )


def get_parse_graphs(forest):
    assert isinstance(forest, Parse)
    assert not forest.is_ambiguous()

    graph_builder = ParseGraphBuilder()
    forest.visit(graph_builder)
    return graph_builder.get_graphs()


def get_parse_trees(graph):
    assert isinstance(graph, ParseGraph)

    if not _default_parser:
        load_parser()

    return _default_parser.generate(graph)


def main():
    parser_cmd = ParserCmd()
    print('')
    parser_cmd.cmdloop()
