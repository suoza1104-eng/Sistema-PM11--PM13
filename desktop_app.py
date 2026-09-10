"""Portable desktop entry point; no browser or external Python process."""
import ctypes
from ctypes import wintypes
import logging
import os
import subprocess
import sys
import threading
from runtime_paths import DATA_DIR, INSTALL_DIR, RESOURCE_DIR, prepare_migrations


def runtime_installed():
    import winreg
    key = r'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
            try:
                with winreg.OpenKey(hive, key, 0, winreg.KEY_READ | view) as k:
                    version = winreg.QueryValueEx(k, 'pv')[0]
                    if version and version != '0.0.0.0':
                        return True
            except OSError:
                pass
    return False


def ensure_runtime():
    if runtime_installed():
        return
    installer = INSTALL_DIR / 'offline_runtime' / 'MicrosoftEdgeWebView2RuntimeInstallerX64.exe'
    if not installer.is_file():
        raise RuntimeError('O WebView2 não está instalado. Extraia a pasta completa do pacote, incluindo offline_runtime.')
    # Validate the signer immediately before execution, without downloading anything.
    env = dict(os.environ, MCM_RUNTIME_INSTALLER=str(installer))
    command = "$s=Get-AuthenticodeSignature -LiteralPath $env:MCM_RUNTIME_INSTALLER; if ($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') { exit 1 }"
    checked = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                             env=env, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    if checked.returncode:
        raise RuntimeError('A assinatura Microsoft do instalador WebView2 não pôde ser validada. Solicite um pacote íntegro.')
    completed = subprocess.run([str(installer), '/silent', '/install'], timeout=600,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    if completed.returncode not in (0, 3010) or not runtime_installed():
        raise RuntimeError('Não foi possível instalar o WebView2 offline. Solicite ao suporte a instalação do componente incluído no pacote.')


def main():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    mutex = kernel.CreateMutexW(None, False, r'Local\Sistema_PM11_PM13_Desktop')
    if not mutex:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        ctypes.windll.user32.MessageBoxW(None, 'O sistema já está aberto. Use a janela existente.', 'PM11 / PM13', 64)
        kernel.CloseHandle(mutex)
        return
    server = None
    worker = None
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        log = open(DATA_DIR / 'desktop.log', 'a', encoding='utf-8', buffering=1)
        if sys.stdout is None:
            sys.stdout = log
        if sys.stderr is None:
            sys.stderr = log
        logging.basicConfig(filename=DATA_DIR / 'desktop.log', level=logging.INFO)
        ensure_runtime()
        prepare_migrations()
        import app
        import webview
        webview.settings['ALLOW_DOWNLOADS'] = True
        webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER'] = False
        conn = app.get_db_connection()
        try:
            app.run_migrations(conn)
        finally:
            conn.close()
        app.pm11_migrations.run_migrations()
        server = app.ExclusiveThreadingHTTPServer(('127.0.0.1', 0), app.PM13RequestHandler)
        server.daemon_threads = True
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        logging.info('Desktop server listening on port=%s', server.server_port)
        window = webview.create_window('Sistema PM11 / PM13',
                    f'http://127.0.0.1:{server.server_port}/', width=1440, height=900, min_size=(960, 640))
        server.shutdown_callback = window.destroy
        webview.start(gui='edgechromium', debug=False, private_mode=False,
                      storage_path=str(DATA_DIR / 'webview'))
    except Exception:
        logging.exception('Falha ao iniciar desktop')
        ctypes.windll.user32.MessageBoxW(None,
            'Não foi possível abrir o sistema.\n' + str(sys.exc_info()[1]) + '\nConsulte dados_usuario/desktop.log.',
            'Sistema PM11 / PM13', 16)
    finally:
        if server:
            if worker and worker.is_alive():
                server.shutdown()
                worker.join(timeout=5)
            server.server_close()
        kernel.CloseHandle(mutex)


if __name__ == '__main__':
    main()
