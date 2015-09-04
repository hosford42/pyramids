__author__ = 'Aaron Hosford'
__all__ = [
    'Timeout',
    'GrammarParserError',
    'GrammarSyntaxError',
]


class Timeout(Exception):
    pass


class GrammarParserError(Exception):

    def __init__(self, msg=None, filename=None, lineno=1, offset=1,
                 text=None):
        super().__init__(msg, (filename, lineno, offset, text))
        self.msg = msg
        self.args = (msg, (filename, lineno, offset, text))

        self.filename = filename
        self.lineno = lineno
        self.offset = offset
        self.text = text

    def __repr__(self):
        return (
            type(self).__name__ +
            repr(
                (
                    self.msg,
                    (self.filename, self.lineno, self.offset, self.text)
                )
            )
        )

    def set_info(self, filename=None, lineno=None, offset=None, text=None):
        if filename is not None:
            self.filename = filename
        if lineno is not None:
            self.lineno = lineno
        if offset is not None:
            self.offset = offset
        if text is not None:
            self.text = text
        self.args = (
            self.msg,
            (self.filename, self.lineno, self.offset, self.text)
        )


class GrammarSyntaxError(GrammarParserError, SyntaxError):

    def __init__(self, msg, filename=None, lineno=1, offset=1, text=None):
        super().__init__(msg, (filename, lineno, offset, text))

    def __repr__(self):
        return super(GrammarParserError, self).__repr__()
