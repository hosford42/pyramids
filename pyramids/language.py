from typing import NamedTuple, Optional

Language = NamedTuple('Language', [('name', str), ('iso639_1', Optional[str]),
                                   ('iso639_2', Optional[str])])
