import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import urllib.error

spec = importlib.util.spec_from_file_location('installer', Path(__file__).parents[1] / 'install_server.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class SafetyTests(unittest.TestCase):
    def test_busy_and_unknown_refuse(self):
        for result in ({'busy': True}, {}, {'busy': 0}, {'busy': None}, []):
            with self.subTest(result=result), patch.object(installer, 'request', return_value=result):
                with self.assertRaises(RuntimeError):
                    installer.require_idle(18450, True)

    def test_idle_loaded_allowed_but_unmanaged_refused(self):
        with patch.object(installer, 'request', return_value={'busy': False}):
            installer.require_idle(18450, True)
            with self.assertRaises(RuntimeError):
                installer.require_idle(18450, False)

    def test_only_connection_refused_without_job_allows_first_install(self):
        for loaded in (False, True):
            for error in (ConnectionRefusedError(), TimeoutError()):
                with self.subTest(loaded=loaded, error=error), patch.object(
                        installer, 'request', side_effect=urllib.error.URLError(error)):
                    if not loaded and isinstance(error, ConnectionRefusedError):
                        installer.require_idle(18450, loaded)
                    else:
                        with self.assertRaises(RuntimeError):
                            installer.require_idle(18450, loaded)

    def test_waits_for_removal(self):
        with patch.object(installer, 'run') as run, patch.object(
                installer, 'loaded', side_effect=[True, False]), patch.object(installer.time, 'sleep') as sleep:
            installer.stop('gui/501/test')
            run.assert_called_once_with('launchctl', 'bootout', 'gui/501/test')
            sleep.assert_called_once_with(.1)

    def test_removal_timeout_is_failure(self):
        with patch.object(installer, 'run'), patch.object(installer, 'loaded', return_value=True), patch.object(
                installer.time, 'monotonic', side_effect=[0, 6]):
            with self.assertRaises(RuntimeError):
                installer.stop('gui/501/test')


if __name__ == '__main__':
    unittest.main()
