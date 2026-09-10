from PyInstaller.utils.hooks import collect_all
datas, binaries, hiddenimports = collect_all('webview')
datas += [('static', 'static'), ('catalogs', 'catalogs'), ('app_icon.ico', '.'), ('read_xlsb.ps1', '.')]
a = Analysis(['desktop_app.py'], pathex=[], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports, excludes=['PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'cefpython3'])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Sistema_PM11_PM13',
          console=False, icon='app_icon.ico')
coll = COLLECT(exe, a.binaries, a.datas, name='Sistema_PM11_PM13')
