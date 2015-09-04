# Pyramids
*English Language Semantic Extraction*

Copyright (c) Aaron Hosford 2011-2015

Available under the [MIT License](http://opensource.org/licenses/MIT)

Pyramids gets its name from the way it constructs parse trees, working 
upwards from the leaves towards the root, building up layers of 
progressively smaller size but greater scope. It is a rule-based natural 
language parser, tailored specifically for English, which builds multiple 
competing parses for a sentence from the bottom up using principles of 
dynamic programming. The parses are then scored for quality and presented 
in order of descending rank. The parser is also capable of accepting 
feedback as to which parses are or are not acceptable, adaptively adjusting 
its scoring measures to improve future parse quality and ranking. Parses 
are returned as trees but can also be used to generate graphs representing 
the semantic relationships between words. The syntactic rules of the parser 
can also be run in reverse to generate sentences from semantic graphs 
resembling those it produces.
