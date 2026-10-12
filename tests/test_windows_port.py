"""Cross-platform contracts for the Windows package (native GUI needs Windows)."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from maw import local_bootstrap
from maw.app_update import check_latest_release, update_cache_root
from maw.gui_platform import asset_path, process_group_kwargs


class Response:
    def __init__(self, data): self.data=json.dumps(data).encode()
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def read(self,*args): return self.data


class WindowsPortTests(unittest.TestCase):
    def test_windows_runtime_lives_outside_the_program_and_uses_scripts_python(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'LOCALAPPDATA':temp,'MAW_BD_DATA_ROOT':''}), patch('sys.platform','win32'):
            root=Path(temp)/'MAW-bd'
            self.assertEqual(local_bootstrap.data_root(),root)
            self.assertEqual(local_bootstrap.runtime_python(),root/'local-runtime/Scripts/python.exe')
            self.assertEqual(update_cache_root(),Path(temp)/'MAW/updates')

    def test_windows_source_and_bundle_use_their_own_dependency_lock(self):
        with patch('sys.platform','win32'), patch('sys.frozen',False,create=True):
            self.assertEqual(local_bootstrap.requirements_path().name,'requirements-local-windows.txt')
        with patch('sys.platform','win32'), patch('sys.frozen',True,create=True), patch('maw.local_bootstrap.resources',return_value=Path('bootstrap')):
            self.assertEqual(local_bootstrap.requirements_path(),Path('bootstrap/requirements-local.txt'))

    def test_windows_bootstrap_uses_packaged_uv_exe(self):
        with tempfile.TemporaryDirectory() as temp, patch('sys.platform','win32'), patch('sys.frozen',True,create=True), patch('maw.local_bootstrap.resources',return_value=Path(temp)):
            uv=Path(temp)/'uv.exe';uv.touch();uv.chmod(0o755)
            self.assertEqual(local_bootstrap.bootstrap_uv(),uv)

    def test_windows_resources_resolve_from_internal_not_macos_resources(self):
        with tempfile.TemporaryDirectory() as temp, patch('sys.frozen',True,create=True):
            root=Path(temp);target=root/'_internal/local-runtime/generate_subtitle_local.py'
            target.parent.mkdir(parents=True);target.touch()
            with patch('sys._MEIPASS',str(root/'_internal'),create=True), patch('sys.executable',str(root/'MAW-bd.exe')):
                self.assertEqual(asset_path('local-runtime/generate_subtitle_local.py'),target)

    def test_windows_processes_never_request_posix_sessions(self):
        with patch('sys.platform','win32'), patch('subprocess.CREATE_NO_WINDOW',0x08000000,create=True), patch('subprocess.CREATE_NEW_PROCESS_GROUP',0x200,create=True):
            kwargs=process_group_kwargs()
            self.assertNotIn('start_new_session',kwargs)
            self.assertEqual(kwargs['creationflags'],0x08000200)

    def test_windows_update_selects_only_windows_asset_and_never_mac_delta(self):
        prefix='https://github.com/Swing233/MAW-bd/releases/download/v1.9.0/'
        names=['MAW-bd-1.9.0-macOS-arm64.zip','MAW-bd-1.9.0-Windows-x64.zip','MAW-bd-1.8.0-to-1.9.0-macOS-arm64.delta.zip']
        payload={'tag_name':'v1.9.0','assets':[{'name':n,'browser_download_url':prefix+n,'size':100-i,'digest':'sha256:'+'a'*64} for i,n in enumerate(names)]}
        with patch('sys.platform','win32'), patch('maw.app_update.urllib.request.urlopen',return_value=Response(payload)):
            result=check_latest_release('1.8.0')
        self.assertTrue(result['available']);self.assertTrue(result['assetName'].endswith('Windows-x64.zip'))
        self.assertIsNone(result['incremental']);self.assertFalse(result['autoInstallSupported'])

    def test_mac_only_release_does_not_advertise_a_windows_update(self):
        with patch('sys.platform','win32'), patch('maw.app_update.urllib.request.urlopen',return_value=Response({'tag_name':'v1.9.0','assets':[]})):
            result=check_latest_release('1.8.0')
        self.assertFalse(result['available']);self.assertIn('Windows',result['platformNotice'])

    def test_windows_dependency_lock_and_portable_build_are_included(self):
        root=Path(__file__).resolve().parents[1]
        lock=(root/'assets/runtime/requirements-local-windows.txt').read_text()
        self.assertIn('--python-platform windows',lock);self.assertIn('--hash=sha256:',lock)
        spec=(root/'MAW.spec').read_text();self.assertIn('requirements-local-windows.txt',spec)
        workflow=(root/'.github/workflows/windows-build.yml').read_text()
        self.assertIn('windows-2022',workflow);self.assertIn('workflow_dispatch',workflow)
        self.assertNotIn('contents: write',workflow)
