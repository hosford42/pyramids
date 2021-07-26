# -*- coding: utf-8 -*-

"""
Pyramids
========
A dependency parser for the extraction of semantic information from natural language.

Copyright (c) Aaron Hosford 2011-2019
MIT License (http://opensource.org/licenses/MIT)

Pyramids gets its name from the way it constructs parse trees, working upwards from the leaves
towards the root, building up layers of progressively smaller size but greater scope. It is a
rule-based natural language parser which builds multiple competing parses for a sentence from the
bottom up using principles of dynamic programming. The parses are then scored for quality and
presented in order of descending rank. The parser is capable of accepting online feedback as to
which parses are or are not acceptable, adaptively adjusting its scoring to improve future parse
quality and ranking. Parses are returned as trees but can also be used to generate graphs
representing the semantic relationships between words. The syntactic rules of the parser can also be
run in reverse to generate sentences from semantic graphs resembling those it produces.
"""


__author__ = 'Aaron Hosford'
__copyright__ = "Copyright (c) 2011-2021, Aaron Hosford"
__credits__ = ['Aaron Hosford']
__license__ = 'MIT'
__version__ = '1.0'
__maintainer__ = 'Aaron Hosford'
__email__ = 'hosford42@gmail.com'
__status__ = 'Production'

__all__ = [
    '__author__',
    '__copyright__',
    '__credits__',
    '__license__',
    '__version__',
    '__maintainer__',
    '__email__',
    '__status__',
]
