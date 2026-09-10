"""Explicit Windows integration check for the compiled app, with temporary data."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from contextlib import contextmanager
import time
import urllib.request


@contextmanager
def test_directory():
    temp = tempfile.TemporaryDirectory(prefix='pm-desktop-smoke-')
    try:
        yield temp.name
    finally:
        # WebView2 releases its metrics files shortly after the host exits.
        for attempt in range(20):
            try:
                temp.cleanup()
                break
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(.5)


def main():
    exe = Path(__file__).resolve().parents[1] / 'dist/Sistema_PM11_PM13/Sistema_PM11_PM13.exe'
    with test_directory() as temp:
        data = Path(temp) / 'data'
        env = dict(os.environ, MCM_USER_DATA_DIR=str(data), MCM_BACKUP_DIR=str(Path(temp) / 'backups'))
        process = subprocess.Popen([str(exe)], env=env, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            deadline = time.monotonic() + 60
            url = None
            while time.monotonic() < deadline:
                log = data / 'desktop.log'
                text = log.read_text(encoding='utf-8') if log.exists() else ''
                match = re.search(r'port=(\d+)', text)
                if match:
                    url = 'http://127.0.0.1:' + match[1]
                    break
                if process.poll() is not None:
                    raise AssertionError('EXE saiu antes de iniciar: ' + text)
                time.sleep(.25)
            assert url, 'Servidor não iniciou'
            with urllib.request.urlopen(url + '/api/auth/me') as response:
                user = json.load(response)['user']
                assert user['local_identity'] and user['sid'] and user['account']
            with urllib.request.urlopen(url + '/') as response:
                assert b'build-code-6' in response.read()
            # Verify an actual native window, not just an HTTP server.
            user32 = ctypes.WinDLL('user32')
            user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
            user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
            callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            found = []
            def inspect(hwnd, _):
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                title = ctypes.create_unicode_buffer(512)
                user32.GetWindowTextW(hwnd, title, 512)
                if pid.value == process.pid and title.value == 'Sistema PM11 / PM13':
                    found.append(hwnd)
                return True
            while time.monotonic() < deadline and not found:
                user32.EnumWindows(callback_type(inspect), 0)
                time.sleep(.25)
            assert found, 'Janela desktop não abriu'
            duplicate = subprocess.Popen([str(exe)], env=env, creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                duplicate_windows = []
                def inspect_duplicate(hwnd, _):
                    pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    title = ctypes.create_unicode_buffer(512)
                    user32.GetWindowTextW(hwnd, title, 512)
                    if pid.value == duplicate.pid and title.value == 'PM11 / PM13':
                        duplicate_windows.append(hwnd)
                    return True
                until = time.monotonic() + 10
                while time.monotonic() < until and not duplicate_windows:
                    user32.EnumWindows(callback_type(inspect_duplicate), 0)
                    time.sleep(.1)
                assert duplicate_windows, 'Segunda instância não exibiu o aviso esperado'
                user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
                user32.PostMessageW(duplicate_windows[0], 0x10, 0, 0)
                assert duplicate.wait(timeout=10) == 0
                assert process.poll() is None, 'A segunda instância encerrou a primeira'
            finally:
                if duplicate.poll() is None:
                    duplicate.terminate()
                    duplicate.wait(timeout=10)
            if '--close-window' in sys.argv:
                user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
                assert user32.PostMessageW(found[0], 0x10, 0, 0)
            else:
                req = urllib.request.Request(url + '/api/shutdown', data=b'{}', headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(req) as response:
                    assert response.status == 200
            assert process.wait(timeout=20) == 0
            print('OK: EXE sem Python externo, janela nativa, identidade Windows, HTTP local e encerramento completo.')
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)


if __name__ == '__main__':
    main()
