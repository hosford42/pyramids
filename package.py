#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Prepares for registration.

# TODO: Clean this hacked together script up!
# TODO: Check results of each os.system call.

import glob
import os
import unittest
import zipfile

import build_readme

from pyramids import __version__, __file__ as module_path


module_name = os.path.basename(module_path)
if module_name.endswith('__init__.py'):
    module_name = os.path.basename(os.path.dirname(module_path))
elif module_name.endswith('.py'):
    module_name = module_name[:-3]


# Build README.rst from README.md
build_readme.build_readme()


# Convert IPython notebooks to HTML
if os.path.isdir('.\\doc'):
    os.chdir('.\\doc')
    try:
        for notebook_path in glob.glob('*.ipynb'):
            os.system('ipython nbconvert "' +
                      os.path.basename(notebook_path) + '"')
    finally:
        os.chdir('..')


# Package the distribution
os.system('python setup.py sdist bdist_wheel')


# Clean up the PKG-INFO file. This is necessary because newlines are
# handled incorrectly, causing the file to be double-spaced, which in turn
# affects PyPI's ability to read it.
pkg_info = module_name + '.egg-info/PKG-INFO'
with open(pkg_info, encoding='utf-8', mode='rU') as infile:
    with open(pkg_info + '-FIXED', encoding='utf-8', mode='w') as outfile:
        prev_skipped = False
        for line in infile:
            if line.strip() or prev_skipped:
                outfile.write(line)
                prev_skipped = False
            else:
                prev_skipped = True
os.remove(pkg_info)
os.rename(pkg_info + '-FIXED', pkg_info)


# Overwrite the PKG-INFO file in the .zip with a correctly formatted
# version.
zip_path = 'dist/' + module_name + '-' + __version__ + '.zip'
old_zip_path = '_old'.join(os.path.splitext(zip_path))
os.rename(zip_path, old_zip_path)
with zipfile.ZipFile(old_zip_path, mode='r') as old_zip:
    with zipfile.ZipFile(zip_path, mode='w') as new_zip:
        for item in old_zip.infolist():
            if item.filename.endswith('/PKG-INFO'):
                new_zip.write(pkg_info, item.filename)
            else:
                data = old_zip.read(item.filename)
                new_zip.writestr(item, data)
os.remove(old_zip_path)


# Identify the newly created wheel and verify that it can be installed.
dist = glob.glob('dist/*-' + __version__ + '-*.whl')[-1]
print(dist)
os.system('pip install ' +
          os.path.join('dist', os.path.basename(dist)) +
          ' --upgrade')


# If there is any HTML documentation, package it up into a .zip file that
# can be uploaded to pythonhosted. Note that currently an index is NOT
# automatically generated.
html_paths = glob.glob('doc/*.html') + glob.glob('doc/*.htm')
if html_paths:
    zip_path = os.path.join('dist/pythonhosted.zip')
    if os.path.isfile(zip_path):
        os.remove(zip_path)

    for doc_path in html_paths:
        with zipfile.ZipFile(zip_path, mode="w") as zf:
            zf.write(doc_path, os.path.basename(doc_path))


# Run the unit tests to make sure everything looks good.
print("Running unit tests.")
suite = unittest.defaultTestLoader.discover('.')
result = unittest.TestResult()
result.failfast = True
suite.run(result)
if result.wasSuccessful():
    print("Unit testing was successful.")
else:
    print("One or more unit tests failed.")
