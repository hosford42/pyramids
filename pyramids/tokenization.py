from functools import reduce
from sys import intern


__author__ = 'Aaron Hosford'
__all__ = [
    'Tokenizer',
    'StandardTokenizer',
    'tokenize',
    'TokenSequence',
]


class Tokenizer:

    def tokenize(self, text):
        raise NotImplementedError()


class StandardTokenizer(Tokenizer):

    def __init__(self, discard_spaces=True):
        self._discard_spaces = bool(discard_spaces)
        self.contractions = ("'", "'m", "'re", "'s", "'ve", "'d", "'ll")

    @property
    def discard_spaces(self):
        return self._discard_spaces

    @staticmethod
    def is_word_char(char):
        return char.isalnum() or char == "'"

    def tokenize(self, text):
        token = ''
        start = 0
        end = 0

        for char in text:
            if (not token or 
                    token[-1] == char or
                    (self.is_word_char(token[-1]) and
                     self.is_word_char(char))):
                token += char
            else:
                if not self.discard_spaces or token.strip():
                    if token.endswith(self.contractions):
                        split = token.split("'")
                        if len(split) > 1 and (
                                len(split) != 2 or split[0]):
                            yield (
                                "'".join(split[:-1]),
                                start,
                                end - len(split[-1])
                            )
                        yield "'" + split[-1], end - len(split[-1]), end
                    elif (token[-2:].lower() in ('am', 'pm') and
                            token[:-2].isdigit()):
                        yield token[:-2], start, end - 2
                        yield token[-2:], end - 2, end
                    elif (token[-1:].lower() in ('a', 'p') and
                            token[:-1].isdigit()):
                        yield token[:-1], start, end - 1
                        yield token[-1:], end - 1, end
                    else:
                        yield token, start, end
                token = char
                start = end
            end += 1

        if token and (not self.discard_spaces or token.strip()):
            if token.endswith(
                    ("'", "'m", "'re", "'s", "'ve", "'d", "'ll")):
                split = token.split("'")
                if len(split) > 1:
                    yield "'".join(split[:-1]), start, end - len(split[-1])
                yield "'" + split[-1], end - len(split[-1]), end
            elif (token[-2:].lower() in ('am', 'pm') and
                    token[:-2].isdigit()):
                yield token[:-2], start, end - 2
                yield token[-2:], end - 2, end
            elif token[-1:].lower() in ('a', 'p') and token[:-1].isdigit():
                yield token[:-1], start, end - 1
                yield token[-1:], end - 1, end
            else:
                yield token, start, end


_tokenizer = StandardTokenizer()


def tokenize(text):
    return _tokenizer.tokenize(text)


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
        self._hash = (
            reduce(lambda a, b: a ^ id(b), self._tokens, 0) ^
            reduce(lambda a, b: a ^ hash(b), self._spans, 0)
        )

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
        return not (self == other)

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
        return not (self <= other)

    def __ge__(self, other):
        if not isinstance(other, TokenSequence):
            return NotImplemented
        return other <= self

    def __lt__(self, other):
        if not isinstance(other, TokenSequence):
            return NotImplemented
        return not (self >= other)

    def __getitem__(self, index):
        return self._tokens[index]

    def __len__(self):
        return len(self._tokens)

    def __iter__(self):
        return iter(self._tokens)

    @property
    def tokens(self):
        return self._tokens

    @property
    def spans(self):
        return self._spans
