import os
import subprocess
import sys
from unittest import TestCase


class TestImportCycles(TestCase):
    """
    Ensures that every module can be imported in isolation. Sometimes due to import cycles or
    delayed imports, a module import will succeed if it comes after a dependency has already been
    imported, but fail if the dependency has not already been imported. By importing each module in
    a completely fresh interpreter instance, we can verify that every single module can be
    successfully imported, and that no module needs another module to be imported first in order to
    be successfully imported itself.
    """

    def test_import_cycles(self):
        base_path = __file__
        while base_path:
            if base_path.endswith('test_semantics'):
                base_path = os.path.dirname(base_path)
                break
            else:
                base_path = os.path.dirname(base_path)
        base_path = base_path + '/'
        for dir_path, dir_names, file_names in os.walk(base_path + 'semantics'):
            assert dir_path.startswith(base_path)
            relative_dir_path = dir_path[len(base_path):].replace('\\', '/')
            assert os.path.isdir(os.path.join(base_path, relative_dir_path))
            try:
                dir_names.remove('__pycache__')
            except ValueError:
                pass
            for file_name in file_names:
                relative_file_path: str = os.path.join(relative_dir_path, file_name)
                assert '\\' not in relative_file_path
                assert os.path.isfile(os.path.join(base_path, relative_file_path))
                if file_name == '__init__.py':
                    module_name_identifiers = relative_file_path[:-12].split('/')
                else:
                    module_name_identifiers = relative_file_path[:-3].split('/')
                self.assertTrue(module_name_identifiers)
                self.assertEqual(module_name_identifiers[0], 'semantics')
                for identifier in module_name_identifiers:
                    self.assertTrue(identifier.isidentifier(),
                                    "%s is not a valid Python identifier." % identifier)
                module_name = '.'.join(module_name_identifiers)
                # print("Testing import of %s (%s)" % (module_name, relative_file_path))
                result = subprocess.call([sys.executable, '-c', 'import %s' % module_name])
                self.assertFalse(result, "Import of %s failed." % module_name)
