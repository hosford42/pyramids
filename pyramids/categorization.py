from functools import reduce
from sys import intern


__author__ = 'Aaron Hosford'
__all__ = [
    'Property',
    'Category',
]


class Property:

    def __init__(self, name):
        if isinstance(name, Property):
            self._name = name._name
            self._hash = name._hash
        else:
            self._name = intern(name)
            self._hash = id(self._name)

    def __str__(self):
        return self._name

    def __repr__(self):
        return type(self).__name__ + "(" + repr(self._name) + ")"

    def __hash__(self):
        return self._hash

    def __eq__(self, other):
        if not isinstance(other, Property):
            return NotImplemented
        return self._name is other._name

    def __ne__(self, other):
        if not isinstance(other, Property):
            return NotImplemented
        return self._name is not other._name

    def __le__(self, other):
        if not isinstance(other, Property):
            return NotImplemented
        return self._name is other._name or self._name < other._name

    def __ge__(self, other):
        if not isinstance(other, Property):
            return NotImplemented
        return self._name is other._name or self._name > other._name

    def __lt__(self, other):
        if not isinstance(other, Property):
            return NotImplemented
        return self._name is not other._name and self._name < other._name

    def __gt__(self, other):
        if not isinstance(other, Property):
            return NotImplemented
        return self._name is not other._name and self._name > other._name

    @property
    def name(self):
        return self._name


class Category:
    """Represents a category of classification for a parse tree or parse
    tree node."""

    def __init__(self, name, positive_properties=None,
                 negative_properties=None):
        if not isinstance(name, str):
            raise TypeError(name, str)
        self._name = intern(name)
        self._positive_properties = (
            frozenset([Property(prop) for prop in positive_properties])
            if positive_properties
            else frozenset()
        )
        self._negative_properties = (
            frozenset([Property(prop) for prop in negative_properties])
            if negative_properties
            else frozenset()
        )
        if self._positive_properties & self._negative_properties:
            raise ValueError("Property is both positive and negative.")
        # This works because we intern the name & properties beforehand:
        self._hash = (
            id(self._name) ^
            reduce(
                lambda a, b: a ^ hash(b),
                self._positive_properties,
                0) ^
            reduce(
                lambda a, b: a ^ -hash(b),
                self._negative_properties,
                0
            )
        )

    @property
    def name(self):
        return self._name

    @property
    def positive_properties(self):
        return self._positive_properties

    @property
    def negative_properties(self):
        return self._negative_properties

    def has_properties(self, *properties):
        for prop in properties:
            if not isinstance(prop, Property):
                prop = Property(prop)
            if prop not in self._positive_properties:
                return False
        return True

    def lacks_properties(self, *properties):
        for prop in properties:
            if not isinstance(prop, Property):
                prop = Property(prop)
            if prop in self._positive_properties:
                return False
        return True

    def to_str(self, simplify=True):
        result = self._name
        properties = []
        if self._positive_properties:
            properties = sorted(
                [str(prop) for prop in self._positive_properties])
        if not simplify and self._negative_properties:
            properties.extend(
                sorted('-' + str(prop)
                       for prop in self._negative_properties)
            )
        if properties:
            result += '(' + ','.join(properties) + ')'
        return result

    def __str__(self):
        return self.to_str()

    def __repr__(self):
        return type(self).__name__ + "(" + repr(self._name) + ", " + repr(
            sorted(self._positive_properties)) + ", " + repr(
            sorted(self._negative_properties)) + ")"

    def __hash__(self):
        return self._hash

    def __eq__(self, other):
        if not isinstance(other, Category):
            return NotImplemented
        # We can use "is" instead of "==" for names because we intern them
        # all ahead of time.
        return self is other or (
            self._hash == other._hash and
            self._name is other._name and
            self._positive_properties == other._positive_properties and
            self._negative_properties == other._negative_properties
        )

    def __ne__(self, other):
        return not (self == other)

    def __le__(self, other):
        if not isinstance(other, Category):
            return NotImplemented
        if self._name is not other._name:  # They are interned...
            return self._name < other._name
        if len(self._positive_properties) != \
                len(other._positive_properties):
            return (
                len(self._positive_properties) <
                len(other._positive_properties)
            )
        if len(self._negative_properties) != \
                len(other._negative_properties):
            return (
                len(self._negative_properties) <
                len(other._negative_properties)
            )
        my_sorted_positive = sorted(self._positive_properties)
        other_sorted_positive = sorted(other._positive_properties)
        if my_sorted_positive != other_sorted_positive:
            return my_sorted_positive < other_sorted_positive
        return (
            sorted(self._negative_properties) <=
            sorted(other._negative_properties)
        )

    def __lt__(self, other):
        if not isinstance(other, Category):
            return NotImplemented
        if self._name is not other._name:  # They are interned...
            return self._name < other._name
        if len(self._positive_properties) != \
                len(other._positive_properties):
            return (
                len(self._positive_properties) <
                len(other._positive_properties)
            )
        if len(self._negative_properties) != \
                len(other._negative_properties):
            return (
                len(self._negative_properties) <
                len(other._negative_properties)
            )
        self_sorted_positive = sorted(self._positive_properties)
        other_sorted_positive = sorted(other._positive_properties)
        if self_sorted_positive != other_sorted_positive:
            return self_sorted_positive < other_sorted_positive
        return (
            sorted(self._negative_properties) <
            sorted(other._negative_properties)
        )

    def __ge__(self, other):
        if not isinstance(other, Category):
            return NotImplemented
        return other <= self

    def __gt__(self, other):
        if not isinstance(other, Category):
            return NotImplemented
        return not (self <= other)

    def __contains__(self, other):
        if not isinstance(other, Category):
            return NotImplemented
        # They must have the same name, and all the properties that apply
        # to this category must apply to the other category. We can use
        # "is" instead of "==" because we intern the names ahead of time.
        return self is other or (
            (self._name is other._name or self.is_wildcard()) and
            self._positive_properties <= other._positive_properties and
            not self._negative_properties & other._positive_properties
        )

    def is_wildcard(self):
        return self._name == "_"

    def promote_properties(self, positive, negative):
        return type(self)(
            self._name,
            (self._positive_properties |
             (frozenset(positive) - self._negative_properties)),
            (self._negative_properties |
             (frozenset(negative) - self._positive_properties))
        )
