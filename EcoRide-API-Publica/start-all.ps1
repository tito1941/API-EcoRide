param(
    [string]$MongoUri = "",
    [string]$DbName = "",
    [string]$ApiUrl = "http://localhost:5000",
    [switch]$InstallDeps
)

$ErrorActionPreference = "Stop"

function Quote-Single([string]$Value) {
    return "'" + $Value.Replace("'", "''") + "'"
}

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ApiScript = Join-Path $ProjectRoot "start-api.ps1"

if (-not (Test-Path $ApiScript)) {
    throw "No se encontro start-api.ps1 en la raiz del proyecto."
}

$ApiCommand = "& " + (Quote-Single $ApiScript)
if ($InstallDeps) {
    $ApiCommand += " -InstallDeps"
}
if ($MongoUri -ne "") {
    $ApiCommand += " -MongoUri " + (Quote-Single $MongoUri)
}
if ($DbName -ne "") {
    $ApiCommand += " -DbName " + (Quote-Single $DbName)
}

$ClientCommandParts = @()
$ClientCommandParts += "Set-Location " + (Quote-Single $ProjectRoot)
$ClientCommandParts += '$VenvPython = ".\\.venv\\Scripts\\python.exe"'
$ClientCommandParts += 'if (Test-Path $VenvPython) { $PythonCmd = $VenvPython } else { $PythonCmd = "python" }'
if ($InstallDeps) {
    $ClientCommandParts += '& $PythonCmd -m pip install -r ".\\client\\requirements.txt"'
}
$ClientCommandParts += '$env:ECORIDE_API = ' + (Quote-Single $ApiUrl)
$ClientCommandParts += 'Write-Host "[INFO] ECORIDE_API=$env:ECORIDE_API" -ForegroundColor Cyan'
$ClientCommandParts += '& $PythonCmd ".\\client\\main.py"'

$ClientCommand = $ClientCommandParts -join "; "

$ApiProcess = Start-Process -FilePath "powershell" -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-Command", $ApiCommand
) -PassThru

$ClientProcess = Start-Process -FilePath "powershell" -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-Command", $ClientCommand
) -PassThru

Write-Host "[OK] API iniciada en una nueva terminal (PID $($ApiProcess.Id))." -ForegroundColor Green
Write-Host "[OK] Cliente iniciado en una nueva terminal (PID $($ClientProcess.Id))." -ForegroundColor Green
Write-Host "[INFO] Cierra cada ventana para detener API/cliente." -ForegroundColor Cyan