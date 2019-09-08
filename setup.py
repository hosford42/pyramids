#!/usr/bin/env python
# -*- coding: utf-8 -*-


"""Setup script for Pyramids Parser."""

from codecs import open as codecs_open
from os import path

from setuptools import setup

from pyramids import __author__, __version__


HERE = path.abspath(path.dirname(__file__))


# Default long description
LONG_DESCRIPTION = """

Pyramids Parser
===============

*Natural Language Semantic Extraction*

""".strip()


# Get the long description from the relevant file. First try README.rst,
# then fall back on the default string defined here in this file.
if path.isfile(path.join(HERE, 'README.rst')):
    with codecs_open(path.join(HERE, 'README.rst'), encoding='utf-8', mode='rU') as description_file:
        LONG_DESCRIPTION = description_file.read()


# See https://pythonhosted.org/setuptools/setuptools.html for a full list
# of parameters and their meanings.
setup(
    name='pyramids',
    version=__version__,
    author=__author__,
    author_email='hosford42@gmail.com',
    url='https://github.com/hosford42/pyramids',
    license='MIT',
    platforms=['any'],
    description='Pyramids Parser: Natural Language Semantic Extraction',
    long_description=LONG_DESCRIPTION,

    # See https://pypi.python.org/pypi?:action=list_classifiers
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Science/Research',
        'Topic :: Scientific/Engineering :: Artificial Intelligence',
        'License :: OSI Approved :: MIT License',

        # Specify the Python versions you support here. In particular,
        # ensure that you indicate whether you support Python 2, Python 3
        # or both.
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3 :: Only',
    ],

    keywords='pyramids parser natural language semantic',
    packages=['pyramids'],
    package_data={'packages': ['*.txt', '*.ctg', '*.ini']},
    include_package_data=True,
    install_requires=['sortedcontainers', 'cython']
)
