param(
    [string]$MongoUri = "",
    [string]$DbName = "",
    [switch]$InstallDeps
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $PythonCmd = $VenvPython
    Write-Host "[OK] Usando Python del entorno virtual: $VenvPython" -ForegroundColor Green
} else {
    $PythonCmd = "python"
    Write-Host "[WARN] No se encontro .venv. Se usara 'python' del sistema." -ForegroundColor Yellow
}

if ($InstallDeps) {
    Write-Host "[INFO] Instalando dependencias del servidor..." -ForegroundColor Cyan
    & $PythonCmd -m pip install -r ".\server\requirements.txt"
}

if ($MongoUri -ne "") {
    $env:MONGO_URI = $MongoUri
    Write-Host "[INFO] MONGO_URI configurada desde parametro." -ForegroundColor Cyan
}

if ($DbName -ne "") {
    $env:DB_NAME = $DbName
    Write-Host "[INFO] DB_NAME configurada: $DbName" -ForegroundColor Cyan
}

Write-Host "[INFO] Iniciando EcoRide API en http://localhost:5000 ..." -ForegroundColor Cyan
& $PythonCmd ".\server\application.py"