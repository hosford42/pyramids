# Release Checklist

**Author**: Aaron Hosford

This file documents the checklist used for this project to ensure everything is up to 
standard before a production release.


## Python Files

* Every Python file has:
    * A UTF-8 encoding
    * An encoding signifier (`-*- coding: utf-8 -*-`) at the top
    * A hashbang (`#!/usr/bin/env python3`) at the top if the file is directly executable
    * A meaningful & descriptive docstring
    * An `__author__` tag
    * An `__all__` tag
    * Zero commented code
    * Zero TODOs (move them to TODO.md)
    * Comments where appropriate
    * Zero functions, classes, or methods without a meaningful & descriptive docstring
    * Zero code inspection issues, including PEP 8 violations in particular
    * Zero unnecessary code inspection overrides (each must be checked)
    * Zero misspellings


## Testing

* The test suite:
    * Includes code inspection & metrics (Pylama)
    * Includes static type checking (MyPy)
    * Includes unit tests for all non-trivial classes, methods, and functions
    * Includes integration testing
    * Includes speed and accuracy benchmarking, which documents performance and
      fails if below standard
    * Includes installation verification testing
    * Is fully automated, token_end_index-to-token_end_index


## Text Files

* Every text file has:
    * A UTF-8 encoding
    * Clearly indicated authorship, preferably in the file itself
    * Zero TODOs (move them to TODO.md)
    * Zero formatting issues
    * Zero misspellings


## Documentation

* Documentation is accurate and up to date

* Documentation files include:
    * LICENSE.txt
    * README.md
    * CHANGES.md - changes since last release
    * BUGS.md - only if applicable
    * TODO.md - only required in the repo
    * ReleaseChecklist.md - this file, only required in the repo

* Documentation includes:
    * Authorship, contributors, copyright, & license
    * High-level description
    * Installation
    * Quick token_start_index guide
    * Working example in a notebook
    * FAQ
    * Full usage
    * Code organization
    * API
    * Contribution guide
    * Bug reporting guide
    * Where to get help

* Documentation is available via:
    * The source code repo
    * The package itself
    * An accessible online site, in HTML form


## Packaging

* The `setup.py` file:
    * Supplies all relevant parameters to `setup()`
    * Is factually correct and precise in all `setup()` parameters. This includes 
      verification that the Python versions indicated are actually supported.
    * Specifies upper and lower version bounds for all dependencies
    * Loads the long description from the README.md file
    * Is tested on the PyPI test site before being uploaded to PyPI proper,
      with all supported dependency and interpreter versions using virtualenv,
      and running through the entire test suite after installation
    * Is fully tested again after uploading to PyPI proper


## Miscellaneous

* The license is fully compatible with those of all direct and indirect dependencies
