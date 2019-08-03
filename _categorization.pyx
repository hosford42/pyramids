# TODO:
#   * Update setup.py to handle the extension module properly.
#   * Update pyramids.categorization to assume the package is already compiled.
#   * Put the pure Python implementation of pyramids.categories back, and use it as a fallback if compilation fails.


from cpython cimport Py_INCREF, Py_DECREF


__author__ = 'Aaron Hosford'
__all__ = [
    'Property',
    'Category',
    'CATEGORY_WILDCARD'
]


EMPTY_SET = frozenset()


cdef class InternedString:
    cdef str value

    def __cinit__(self, str value):
        Py_INCREF(value)
        self.value = value

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return '%s(%r)' % (type(self).__name__, self.value)

    def __eq__(self, InternedString other) -> bool:
        return self.value is other.value

    def __ne__(self, InternedString other) -> bool:
        return self.value is not other.value

    def __lt__(self, InternedString other) -> bool:
        return self.value is not other.value and self.value < other.value

    def __le__(self, InternedString other) -> bool:
        return self.value is other.value or self.value <= other.value

    def __gt__(self, InternedString other) -> bool:
        return self.value is not other.value and self.value > other.value

    def __ge__(self, InternedString other) -> bool:
        return self.value is other.value or self.value >= other.value

    def __hash__(self) -> int:
        return id(self.value)

    def __add__(a, b) -> str:
        # Cython doesn't do __radd__. Instead it just calls the same method with the operands reversed.
        return str(a) + str(b)

    def startswith(self, other) -> bool:
        return self.value.startswith(str(other))

    def __getitem__(self, x):
        return self.value[x]

    cpdef long addr(self):
        return id(self.value)


cdef class StringInterner:
    cdef dict _intern_map
    cdef type _subtype

    def __init__(self, type subtype=InternedString):
        self._intern_map = {}
        self._subtype = subtype

    cpdef InternedString intern(self, str s):
        if s in self._intern_map:
            return self._intern_map[s]
        else:
            result = self._subtype(s)
            self._intern_map[s] = result
            return result


cdef class Property(InternedString):

    @staticmethod
    def get(name) -> Property:
        if isinstance(name, Property):
            return name
        else:
            return _property_interner.intern(name)

    def __repr__(self) -> str:
        return 'Property(%r)' % self.value

#    def __getstate__(self) -> str:
#        return self.value
#
#    def __setstate__(self, state) -> str:
#        self.value = _property_interner.intern(state).value


cpdef frozenset make_property_set(properties):
    cdef Property prop
    cdef list props

    if properties:
        props = []
        for p in properties:
            if isinstance(p, str):
                prop = Property.get(p)
            else:
                prop = p
            props.append(prop)
        return frozenset(props)
    else:
        return EMPTY_SET


cdef class Category:
    """Represents a category of classification for a parse tree or parse tree node."""
    cdef InternedString _name
    cdef frozenset _positive_properties
    cdef frozenset _negative_properties
    cdef long _hash

#    @staticmethod
#    def get(name, positive_properties=None, negative_properties=None) -> Category:
#        cdef InternedString i_name
#        cdef Property prop
#        cdef frozenset positives
#        cdef frozenset negatives
#        cdef Category result
#
#        if isinstance(name, str):
#            i_name = _category_name_interner.intern(name)
#        else:
#            i_name = name
#        positives = make_property_set(positive_properties)
#        negatives = make_property_set(negative_properties)
#
#        result = Category(i_name, positives, negatives)
#        return result

    def __cinit__(self, name, positive_properties=None, negative_properties=None):
        cdef long hash_value
        cdef Property prop
        cdef frozenset both
        cdef InternedString i_name
        cdef frozenset positives
        cdef frozenset negatives

        if isinstance(name, str):
            i_name = _category_name_interner.intern(name)
        else:
            i_name = name

        positives = make_property_set(positive_properties)
        negatives = make_property_set(negative_properties)

        hash_value = hash(i_name)
        for prop in positives:
            hash_value ^= (hash(prop) << 1)
        for prop in negatives:
            hash_value ^= -hash(prop) << 2

        both = positives & negatives
        if both:
            raise ValueError("Property is both positive and negative: %s" % ', '.join(str(prop) for prop in both))

        Py_INCREF(i_name)
        Py_INCREF(positives)
        Py_INCREF(negatives)

        self._name = i_name
        self._positive_properties = positives
        self._negative_properties = negatives
        self._hash = hash_value

    @property
    def name(self) -> InternedString:
        return self._name

    @property
    def positive_properties(self) -> frozenset:
        return self._positive_properties

    @property
    def negative_properties(self) -> frozenset:
        return self._negative_properties

    #cdef bint has_props(self, vector[Property] properties):

    def has_properties(self, *properties) -> bool:
        cdef Property i_prop
        for prop in properties:
            i_prop = Property.get(prop)
            if i_prop not in self._positive_properties:
                return False
        return True

    def lacks_properties(self, *properties) -> bool:
        cdef Property i_prop
        for prop in properties:
            i_prop = Property.get(prop)
            if i_prop in self._positive_properties:
                return False
        return True

    def to_str(self, bint simplify=True) -> str:
        properties = []
        if self._positive_properties:
            properties = sorted(str(prop) for prop in self._positive_properties)
        if not simplify and self._negative_properties:
            properties.extend(sorted('-' + str(prop) for prop in self._negative_properties))
        if properties:
            return str(self._name) + '(%s)' % ','.join(properties)
        else:
            return str(self._name)

    def __str__(self) -> str:
        return self.to_str()

    def __repr__(self) -> str:
        return 'Category(%r, %r, %r)' % (str(self._name), sorted(str(prop) for prop in self._positive_properties),
                                         sorted(str(prop) for prop in self._negative_properties))

    def __hash__(self) -> int:
        return self._hash

    def __eq__(self, Category other) -> bool:
        # We can use "is" instead of "==" for names because we intern them all ahead of time.
        return self is other or (
            self._hash == other._hash and
            self._name is other._name and
            self._positive_properties == other._positive_properties and
            self._negative_properties == other._negative_properties
        )

    def __ne__(self, Category other) -> bool:
        return not self.__eq__(other)

    def __le__(self, Category other) -> bool:
        if self._name is not other._name:  # They are interned...
            return self._name < other._name
        if len(self._positive_properties) != len(other._positive_properties):
            return len(self._positive_properties) < len(other._positive_properties)
        if len(self._negative_properties) != len(other._negative_properties):
            return len(self._negative_properties) < len(other._negative_properties)
        my_sorted_positive = sorted(self._positive_properties)
        other_sorted_positive = sorted(other._positive_properties)
        if my_sorted_positive != other_sorted_positive:
            return my_sorted_positive < other_sorted_positive
        return sorted(self._negative_properties) <= sorted(other._negative_properties)

    def __lt__(self, Category other) -> bool:
        if self._name is not other._name:  # They are interned...
            return self._name < other._name
        if len(self._positive_properties) != len(other._positive_properties):
            return len(self._positive_properties) < len(other._positive_properties)
        if len(self._negative_properties) != len(other._negative_properties):
            return len(self._negative_properties) < len(other._negative_properties)
        self_sorted_positive = sorted(self._positive_properties)
        other_sorted_positive = sorted(other._positive_properties)
        if self_sorted_positive != other_sorted_positive:
            return self_sorted_positive < other_sorted_positive
        return sorted(self._negative_properties) < sorted(other._negative_properties)

    def __ge__(self, Category other) -> bool:
        return other <= self

    def __gt__(self, Category other) -> bool:
        return not (self <= other)

    def __contains__(self, Category other) -> bool:
        # They must have the same name, and all the properties that apply
        # to this category must apply to the other category. We can use
        # "is" instead of "==" because we intern the names ahead of time.
        return self is other or (
            (self._name is other._name or self.is_wildcard()) and
            self._positive_properties <= other._positive_properties and
            not self._negative_properties & other._positive_properties
        )

    def is_wildcard(self) -> bool:
        return self._name is CATEGORY_WILDCARD

    def promote_properties(self, positive, negative) -> Category:
        cdef frozenset positives
        cdef frozenset negatives
        cdef Category category

        positives = make_property_set(positive)
        negatives = make_property_set(negative)
        category = Category(self._name, (self._positive_properties | (positives - self._negative_properties)),
                            (self._negative_properties | (negatives - self._positive_properties)))
        return category

#    def __getstate__(self):
#        return (str(self.name), [str(prop) for prop in self._positive_properties],
#                [str(prop) for prop in self._negative_properties])
#
#    def __setstate__(self, state):
#        name, pos, neg = state
#        assert isinstance(name, str)
#        cat = Category.get(name, pos, neg)
#        self.init(cat._name, cat._positive_properties, cat._negative_properties)


cdef StringInterner _category_name_interner = StringInterner()
cdef StringInterner _property_interner = StringInterner(Property)
cdef InternedString _CATEGORY_WILDCARD = _category_name_interner.intern("_")


CATEGORY_WILDCARD = _CATEGORY_WILDCARD
