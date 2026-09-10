"""Package only application resources; never ship local user databases."""
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parent
EXCLUDED = {'data', 'backups', 'dados_usuario', 'backups_usuario'}


def application_files(folder):
    for path in folder.rglob('*'):
        relative = path.relative_to(folder)
        if path.is_file() and not EXCLUDED.intersection(relative.parts) and path.suffix.lower() not in {'.db', '.sqlite', '.sqlite3'}:
            yield path, relative.as_posix()


def main():
    folder = ROOT / 'dist' / 'Sistema_PM11_PM13'
    if not (folder / 'Sistema_PM11_PM13.exe').is_file():
        raise RuntimeError('Compile o EXE antes de empacotar.')
    runtime = folder / 'offline_runtime'
    runtime.mkdir(exist_ok=True)
    shutil.copy2(ROOT / 'offline_runtime' / 'MicrosoftEdgeWebView2RuntimeInstallerX64.exe', runtime)
    shutil.copy2(ROOT / 'README_PORTABLE.md', folder)
    shutil.copy2(ROOT / 'COMO_ATUALIZAR.txt', folder)
    for name in ('dados_usuario', 'backups_usuario'):
        (folder / name).mkdir(exist_ok=True)
    for name, prefix in [('ATUALIZACAO_PM11_PM13.zip', ''), ('SISTEMA_PM11_PM13_DESKTOP_LIMPO.zip', 'Sistema_PM11_PM13/')]:
        with zipfile.ZipFile(ROOT / 'dist' / name, 'w', zipfile.ZIP_DEFLATED) as zf:
            for path, relative in application_files(folder):
                zf.write(path, prefix + relative)
            if prefix:
                zf.writestr(prefix + 'dados_usuario/', '')
                zf.writestr(prefix + 'backups_usuario/', '')


if __name__ == '__main__':
    main()
