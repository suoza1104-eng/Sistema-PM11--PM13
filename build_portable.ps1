param([switch]$PrepareOnline)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Set-Location -LiteralPath $PSScriptRoot
foreach ($name in @('dados_usuario', 'backups_usuario', 'data', 'backups')) {
    $existingData = Join-Path $PSScriptRoot "dist\Sistema_PM11_PM13\$name"
    if ((Test-Path -LiteralPath $existingData) -and (Get-ChildItem -LiteralPath $existingData -Recurse -File | Select-Object -First 1)) {
        throw "Build interrompido: $existingData contém dados. Mova a instalação de uso para outra pasta antes de recompilar."
    }
}
$buildPython = Join-Path $PSScriptRoot '.venv-desktop\Scripts\python.exe'
if (!(Test-Path -LiteralPath $buildPython)) {
    if (Get-Command py -ErrorAction SilentlyContinue) { & py -3 -m venv .venv-desktop }
    elseif (Get-Command python -ErrorAction SilentlyContinue) { & python -m venv .venv-desktop }
    else { throw 'Python não encontrado na máquina de compilação. O destinatário do EXE não precisa de Python.' }
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao preparar ambiente Python.' }
}
if ($PrepareOnline) {
    New-Item -ItemType Directory -Force offline_packages, offline_runtime | Out-Null
    & $buildPython -m pip wheel --wheel-dir offline_packages -r requirements-desktop.txt
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao obter dependências offline.' }
    Invoke-WebRequest -UseBasicParsing -Uri 'https://go.microsoft.com/fwlink/?linkid=2124701' -OutFile 'offline_runtime\MicrosoftEdgeWebView2RuntimeInstallerX64.exe'
}
$runtime = Join-Path $PSScriptRoot 'offline_runtime\MicrosoftEdgeWebView2RuntimeInstallerX64.exe'
if (!(Test-Path -LiteralPath $runtime)) { throw 'Falta o instalador offline WebView2. Execute build_portable.ps1 -PrepareOnline nesta máquina de compilação.' }
$signature = Get-AuthenticodeSignature -LiteralPath $runtime
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') {
    throw 'Instalador WebView2 sem assinatura Microsoft válida.'
}
& $buildPython -m pip install --no-index --find-links offline_packages -r requirements-desktop.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependências offline ausentes. Prepare com -PrepareOnline.' }
& $buildPython -m PyInstaller --noconfirm Sistema_PM11_PM13.spec
if ($LASTEXITCODE -ne 0) { throw 'Falha ao compilar o aplicativo.' }
& $buildPython package_desktop.py
if ($LASTEXITCODE -ne 0) { throw 'Falha ao empacotar desktop.' }
Write-Host 'Concluído: dist\Sistema_PM11_PM13 e os ZIPs de instalação e atualização.'
