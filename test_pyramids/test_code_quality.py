#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests to ensure code quality standards are met."""

import os

from pylama.main import check_path, parse_options

ERROR_TYPE_MAP = {
    'W': 'Warning',
    'D': 'Documentation',
    'E': 'Code Checker Error',
    'C': 'Coding Style',
    'R': 'Code Complexity',
}

PYLAMA_OPTION_OVERRIDES = {
    'linters': ['pep257', 'pydocstyle', 'pycodestyle', 'pyflakes', 'mccabe',
                'pylint', 'radon', 'eradicate', 'mypy'],
    'ignore': [
        'W0212',  # pylint can't tell the difference between same-type and different-type protected member
        # access based on inferred types.

        'D102',  # pylint, pydocstyle, and pep257 are redundant on this one. Pylint has its own code, while
        # the other two share this code.
        'D103',  # Likewise for this one.

        'D105',  # I disagree with the standard. Magic methods don't need docstrings. They are universal
        # and can easily be googled.
        'D107',  # Same with __init__. The class's docstring is sufficient.

        'D212',  # This is optional and directly conflicts with an alternative one.
        'D203',  # Likewise.

        'W0611',  # PyFlakes gets confused by MyPy type annotations, which require imports to be present.
    ],
    'async': True,
    'concurrent': True,
}


def test_code_quality():
    """Test various code quality metrics."""
    old_cwd = os.getcwd()
    try:
        root_path = os.path.dirname(os.path.dirname(__file__))
        os.chdir(root_path)

        top_level = get_python_source_paths(root_path)

        options = parse_options(top_level, **PYLAMA_OPTION_OVERRIDES)
        errors = check_path(options, rootdir='.')
        if errors:
            print('-' * 80)

            for error in errors:
                print_pylama_error(error, root_path)
                print('-' * 80)

        assert not errors, "%s code quality errors detected." % len(errors)
    finally:
        os.chdir(old_cwd)


def print_pylama_error(error, root_path):
    """Print a pylama error in a readable format."""
    column = error.get('col')
    line_no = error.get('lnum')
    error_type = error.get('type')
    text = error.get('text')
    relative_file_path = error.get('filename')
    error_type = ERROR_TYPE_MAP.get(error_type, error_type)
    if relative_file_path:
        print()
        print('File "%s", line %s, col %s:' % (os.path.join(root_path, relative_file_path), line_no, column))
        if line_no is not None:
            with open(relative_file_path, encoding='utf-8') as file:
                for index, line in enumerate(file):
                    if index + 1 == line_no:
                        break
                else:
                    line = None
            if line:
                print('    ' + line.rstrip('\n'))
                if column is not None and not line[:column].isspace():
                    print('    ' + ' ' * column + '^')
        print('%s: %s' % (error_type, text))
    else:
        print('%s: %s' % (error_type, text))


def get_python_source_paths(root_path):
    """Get a list of all python sources appearing recursively under the given root path."""
    results = []
    for dir_path, _, file_names in os.walk(root_path):
        for filename in file_names:
            if filename.endswith('.py'):
                results.append(os.path.join(dir_path, filename))
    return results


if __name__ == '__main__':
    test_code_quality()
