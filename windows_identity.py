"""Informational identity from the Windows account APIs (never authorization)."""
import base64
import ctypes
from ctypes import wintypes
from functools import lru_cache
import os
from pathlib import Path


@lru_cache(maxsize=1)
def get_identity():
    result = dict(name='Usuário local', account='', sid='', computer='', photo=None,
                  initials='UL', role='ADMIN', login='', local_identity=True)
    if os.name != 'nt':
        return result
    secur32 = ctypes.WinDLL('secur32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    advapi32 = ctypes.WinDLL('advapi32', use_last_error=True)
    def username(kind):
        size = wintypes.ULONG(0)
        secur32.GetUserNameExW(kind, None, ctypes.byref(size))
        if not size.value:
            return ''
        buf = ctypes.create_unicode_buffer(size.value)
        return buf.value if secur32.GetUserNameExW(kind, buf, ctypes.byref(size)) else ''
    account = username(2)
    full_name = username(3)
    if not account:
        size = wintypes.DWORD(256)
        buf = ctypes.create_unicode_buffer(256)
        if advapi32.GetUserNameW(buf, ctypes.byref(size)):
            account = buf.value
    if not full_name and account:
        # GetUserNameEx(Display) may be unavailable for local accounts.
        class USER_INFO_10(ctypes.Structure):
            _fields_ = [(n, wintypes.LPWSTR) for n in ('name', 'comment', 'usr_comment', 'full_name')]
        netapi = ctypes.WinDLL('netapi32')
        info = ctypes.c_void_p()
        if netapi.NetUserGetInfo(None, account.split('\\')[-1], 10, ctypes.byref(info)) == 0:
            try:
                full_name = ctypes.cast(info, ctypes.POINTER(USER_INFO_10)).contents.full_name or ''
            finally:
                netapi.NetApiBufferFree(info)
    result.update(name=full_name or account or result['name'], account=account, login=account)
    size = wintypes.DWORD(256)
    buf = ctypes.create_unicode_buffer(256)
    if kernel32.GetComputerNameW(buf, ctypes.byref(size)):
        result['computer'] = buf.value
    token = wintypes.HANDLE()
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi32.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    if advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), 8, ctypes.byref(token)):
        try:
            needed = wintypes.DWORD()
            advapi32.GetTokenInformation(token, 1, None, 0, ctypes.byref(needed))
            token_data = ctypes.create_string_buffer(needed.value)
            if advapi32.GetTokenInformation(token, 1, token_data, needed, ctypes.byref(needed)):
                sid = ctypes.cast(token_data, ctypes.POINTER(ctypes.c_void_p))[0]
                sid_text = wintypes.LPWSTR()
                advapi32.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
                if advapi32.ConvertSidToStringSidW(sid, ctypes.byref(sid_text)):
                    result['sid'] = sid_text.value
                    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
                    kernel32.LocalFree(ctypes.cast(sid_text, ctypes.c_void_p))
        finally:
            kernel32.CloseHandle(token)
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 'SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\AccountPicture\\Users\\' + result['sid']) as key:
            photo = Path(winreg.QueryValueEx(key, 'Image96')[0])
            if photo.is_file() and photo.stat().st_size < 1024 * 1024:
                data = photo.read_bytes()
                mime = 'image/png' if data.startswith(b'\x89PNG') else 'image/jpeg'
                result['photo'] = 'data:' + mime + ';base64,' + base64.b64encode(data).decode('ascii')
    except (OSError, ValueError):
        pass
    result['initials'] = ''.join(w[0] for w in result['name'].split()[:2]).upper()
    return result
