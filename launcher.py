"""
Inicializador Inteligente com Atalho de Área de Trabalho — Sistema PM13 / PM11
Cria atalho no Desktop, gerencia/reinicia o servidor em segundo plano na porta 8765 e abre no navegador.
"""

import sys
import os
import time
import urllib.request
import subprocess
import webbrowser

PORT = 8765
URL = f"http://127.0.0.1:{PORT}/"

def get_root_dir():
    return os.path.dirname(os.path.abspath(__file__))

def create_desktop_shortcut():
    """Cria atalho do sistema na Área de Trabalho do Windows (Desktop)."""
    try:
        desktop = os.path.join(os.environ["USERPROFILE"], "Desktop")
        if not os.path.exists(desktop):
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            
        if not os.path.exists(desktop):
            return

        shortcut_path = os.path.join(desktop, "Sistema PM13 - PM11.lnk")
        root_dir = get_root_dir()
        target_bat = os.path.join(root_dir, "INICIAR_SISTEMA.bat")

        if not os.path.exists(target_bat):
            target_bat = os.path.join(root_dir, "INICIAR_PM13.bat")

        icon_path = os.path.join(root_dir, "app_icon.ico")
        icon_setting = f'shortcut.IconLocation = "{icon_path}"' if os.path.exists(icon_path) else ''

        # Usar VBScript via Windows Script Host para criar atalho .lnk sem dependência externa
        vbs_script = f"""
Set WshShell = CreateObject("WScript.Shell")
Set shortcut = WshShell.CreateShortcut("{shortcut_path}")
shortcut.TargetPath = "{target_bat}"
shortcut.WorkingDirectory = "{root_dir}"
shortcut.Description = "Inicializador do Sistema PM13 / PM11"
{icon_setting}
shortcut.WindowStyle = 1
shortcut.Save
"""
        temp_vbs = os.path.join(root_dir, "_create_shortcut.vbs")
        with open(temp_vbs, "w", encoding="latin-1") as f:
            f.write(vbs_script)

        subprocess.run(["cscript", "//Nologo", temp_vbs], capture_output=True)
        if os.path.exists(temp_vbs):
            os.remove(temp_vbs)
            
        print(f"✓ Atalho criado na Área de Trabalho: {shortcut_path}")
    except Exception as e:
        print("Aviso na criação do atalho de Desktop:", e)

def is_server_running():
    """Verifica se o servidor responde na porta 8765."""
    try:
        with urllib.request.urlopen(URL, timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False

def stop_server_process():
    """Encerra processos do servidor Python ativos na porta 8765."""
    try:
        subprocess.run(
            ["cmd", "/c", f"for /f \"tokens=5\" %a in ('netstat -aon ^| findstr :{PORT}') do taskkill /f /pid %a"],
            capture_output=True,
            text=True
        )
        time.sleep(1)
    except Exception:
        pass

def start_server_in_background():
    """Inicia o servidor python app.py em segundo plano (sem janela CMD visível)."""
    root_dir = get_root_dir()
    app_py = os.path.join(root_dir, "app.py")

    # Iniciar processo oculto em segundo plano usando pythonw.exe ou subprocess DETACHED_PROCESS
    python_exe = sys.executable
    pythonw_exe = os.path.join(os.path.dirname(python_exe), "pythonw.exe")
    exec_bin = pythonw_exe if os.path.exists(pythonw_exe) else python_exe

    # Flags de criação para processo independente no Windows
    DETACHED_PROCESS = 0x00000008
    CREATE_NO_WINDOW = 0x08000000

    subprocess.Popen(
        [exec_bin, app_py],
        cwd=root_dir,
        creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
        close_fds=True
    )

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    print("========================================================")
    print("   INICIALIZADOR INTELIGENTE — SISTEMA PM13 / PM11")
    print("========================================================")
    print()

    # 1. Garantir atalho na área de trabalho
    create_desktop_shortcut()

    # 2. Gerenciar processo do servidor na porta 8765
    if is_server_running():
        print("⚡ Servidor já em execução detectado. Reiniciando para garantir versão atualizada...")
        stop_server_process()

    print("🚀 Iniciando servidor do sistema em segundo plano...")
    start_server_in_background()

    # 3. Aguardar disponibilidade e abrir navegador
    max_wait = 10
    start_time = time.time()
    opened = False

    while time.time() - start_time < max_wait:
        if is_server_running():
            print("✓ Servidor online na porta 8765!")
            webbrowser.open(URL)
            opened = True
            break
        time.sleep(0.5)

    if not opened:
        print("⚡ Abrindo navegador...")
        webbrowser.open(URL)

    print("\n🎉 Sistema inicializado com sucesso!")

if __name__ == "__main__":
    main()

