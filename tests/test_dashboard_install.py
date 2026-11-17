import importlib.util
from pathlib import Path
import plistlib
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('dashboard_build', Path(__file__).resolve().parents[1]/'scripts/build_macos.py')
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)

class DashboardRetirementTests(unittest.TestCase):
    def test_only_dashboard_is_retired_and_remains_recoverable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app = root/'Old.app'
            (app/'Contents').mkdir(parents=True)
            info = app/'Contents/Info.plist'
            info.write_bytes(plistlib.dumps({'CFBundleIdentifier':'com.crispierry.network-monitor.service'}))
            with patch.object(build.Path, 'home', return_value=root), patch.object(build.subprocess, 'run') as command:
                with self.assertRaises(ValueError):
                    build.retire_dashboard(app)
                self.assertTrue(app.exists())
                command.assert_not_called()
                info.write_bytes(plistlib.dumps({'CFBundleIdentifier':build.BUNDLE_ID}))
                build.retire_dashboard(app)
                self.assertFalse(app.exists())
                retired = list((root/'.Trash').glob('*.app'))
                self.assertEqual(len(retired), 1)
                self.assertEqual(plistlib.loads((retired[0]/'Contents/Info.plist').read_bytes())['CFBundleIdentifier'], build.BUNDLE_ID)
