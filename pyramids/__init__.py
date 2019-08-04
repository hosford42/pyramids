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


__author__ = 'Aaron Hosford'
__copyright__ = """
Copyright (c) 2011-2019 Aaron Hosford
All Rights Reserved.
""".strip()
__credits__ = ['Aaron Hosford']
__license__ = 'MIT'
__version__ = '0.1'
__maintainer__ = 'Aaron Hosford'
__email__ = 'hosford42@gmail.com'
__status__ = 'Prototype'
__all__ = [
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
#       particular rule. Then we can implement the above to-do by having
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
