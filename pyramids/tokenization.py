# -*- coding: utf-8 -*-

"""Tokenization data types and interfaces."""

from abc import ABCMeta, abstractmethod
from functools import reduce
from sys import intern
from typing import Tuple, Optional

from pyramids.config import ModelConfig
from pyramids.language import Language

__author__ = 'Aaron Hosford'
__all__ = [
    'Tokenizer',
    'TokenSequence',
]


class TokenSequence:
    """A sequence of tokens generated for the parse input."""

    def __init__(self, tokens):
        interned_tokens = []
        spans = []
        for token, start, end in tokens:
            if not isinstance(token, str):
                raise TypeError(token, str)
            if not isinstance(start, int):
                raise TypeError(start, int)
            if not isinstance(end, int):
                raise TypeError(end, int)
            interned_tokens.append(intern(token))
            spans.append((start, end))
        self._tokens = tuple(interned_tokens)
        self._spans = tuple(spans)
        self._hash = reduce(lambda a, b: a ^ id(b), self._tokens, 0) ^ reduce(lambda a, b: a ^ hash(b), self._spans, 0)

    @property
    def tokens(self) -> Tuple[str, ...]:
        """Get the interned token strings."""
        return self._tokens

    @property
    def spans(self) -> Tuple[Tuple[int, int], ...]:
        """Get the token_start_index/token_end_index index spans of the tokens."""
        return self._spans

    def __str__(self):
        return ' '.join(self._tokens)

    def __repr__(self):
        return type(self).__name__ + "(" + repr(self._tokens) + ")"

    def __hash__(self):
        return self._hash

    def __eq__(self, other):
        if not isinstance(other, TokenSequence):
            return NotImplemented
        return self is other or (self._hash == other._hash and
                                 self._tokens == other._tokens and
                                 self._spans == other._spans)

    def __ne__(self, other):
        if not isinstance(other, TokenSequence):
            return NotImplemented
        return not self == other

    def __le__(self, other):
        if not isinstance(other, TokenSequence):
            return NotImplemented
        if len(self._tokens) != len(other._tokens):
            return len(self._tokens) < len(other._tokens)
        if self._tokens != other._tokens:
            return self._tokens < other._tokens
        return self._spans <= other._spans

    def __gt__(self, other):
        if not isinstance(other, TokenSequence):
            return NotImplemented
        return not self <= other

    def __ge__(self, other):
        if not isinstance(other, TokenSequence):
            return NotImplemented
        return other <= self

    def __lt__(self, other):
        if not isinstance(other, TokenSequence):
            return NotImplemented
        return not self >= other

    def __getitem__(self, index):
        return self._tokens[index]

    def __len__(self):
        return len(self._tokens)

    def __iter__(self):
        return iter(self._tokens)


class Tokenizer(metaclass=ABCMeta):
    """Abstract interface for Pyramids tokenizers."""

    @classmethod
    @abstractmethod
    def from_config(cls, config_info: ModelConfig) -> 'Tokenizer':
        """Create a tokenizer instance from the given configuration info."""
        raise NotImplementedError()

    @abstractmethod
    def tokenize(self, text: str) -> TokenSequence:
        """Tokenize a piece of text."""
        raise NotImplementedError()

    @property
    @abstractmethod
    def language(self) -> Optional[Language]:
        """Get the language this tokenizer is designed for, if indicated."""
        raise NotImplementedError()
