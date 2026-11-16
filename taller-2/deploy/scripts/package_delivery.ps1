# Empaqueta la entrega SIN secretos, caches ni metadatos de git.
# Uso:
#   powershell -ExecutionPolicy Bypass -File deploy/scripts/package_delivery.ps1
#   powershell -ExecutionPolicy Bypass -File deploy/scripts/package_delivery.ps1 -IncludeLogs
param(
    [string]$OutputPath = "dist/taller2-entrega.zip",
    [string]$StageRoot = "dist/stage",
    [switch]$IncludeLogs
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.IO.Compression.FileSystem

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Stage = Join-Path $Root $StageRoot
$ZipPath = Join-Path $Root $OutputPath
$Scanner = Join-Path $PSScriptRoot "check_no_secrets.py"

$ExcludedDirs = @(
    ".git", ".hg", ".svn", ".venv", "venv", "env", "__pycache__",
    ".pytest_cache", ".ruff_cache", ".mypy_cache", "node_modules",
    ".langgraph_api", ".langgraph", ".ipynb_checkpoints", "dist",
    ".vscode", ".idea"
)

$ExcludedNames = @(
    ".env", "verificacion-plan.md", "taller_implementacion_agentes.pdf",
    "Thumbs.db", ".DS_Store"
)

$ExcludedSuffixes = @(
    ".zip", ".7z", ".pyc", ".pyo", ".code-workspace"
)

function Test-Excluded {
    param([System.IO.FileInfo]$File)
    $relative = $File.FullName.Substring($Root.Length).TrimStart("\", "/")
    $parts = $relative -split "[\\/]"
    foreach ($part in $parts) {
        if ($ExcludedDirs -contains $part) { return $true }
    }
    if ($ExcludedNames -contains $File.Name) { return $true }
    if ($File.Name -like ".env.*" -and $File.Name -ne ".env.example") { return $true }
    if ($ExcludedSuffixes -contains $File.Extension.ToLowerInvariant()) { return $true }
    if (-not $IncludeLogs -and $File.Extension.ToLowerInvariant() -in @(".log", ".run.log")) { return $true }
    return $false
}

if (Test-Path -LiteralPath $Stage) { Remove-Item -LiteralPath $Stage -Recurse -Force }
if (Test-Path -LiteralPath $ZipPath) { Remove-Item -LiteralPath $ZipPath -Force }
New-Item -ItemType Directory -Force -Path $Stage | Out-Null

$copied = 0
Get-ChildItem -LiteralPath $Root -Recurse -File -Force | ForEach-Object {
    if (Test-Excluded -File $_) { return }
    $relative = $_.FullName.Substring($Root.Length).TrimStart("\", "/")
    $destination = Join-Path $Stage $relative
    $parent = Split-Path -Parent $destination
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    Copy-Item -LiteralPath $_.FullName -Destination $destination -Force
    $copied++
}

if ($copied -eq 0) { throw "No se copio ningun archivo. Revisar las rutas." }

Write-Host "Archivos preparados: $copied"
Write-Host "Ejecutando escaneo de secretos sobre el stage..."
& python $Scanner $Stage
if ($LASTEXITCODE -ne 0) {
    throw "El escaneo encontro problemas. No se genera el ZIP. Revisar: $Stage"
}

$forbidden = Get-ChildItem -LiteralPath $Stage -Recurse -Force | Where-Object {
    $_.Name -eq ".env" -or
    ($_.Name -like ".env.*" -and $_.Name -ne ".env.example") -or
    $_.Name -eq ".git" -or
    $_.FullName -match "[\\/]\.git[\\/]"
}
if ($forbidden) {
    $forbidden | ForEach-Object { Write-Host "PROHIBIDO: $($_.FullName)" }
    throw "El stage contiene archivos prohibidos."
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ZipPath) | Out-Null
Compress-Archive -Path (Join-Path $Stage "*") -DestinationPath $ZipPath -CompressionLevel Optimal -Force

$archive = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
$zipEntries = $archive.Entries
$badEntries = $zipEntries | Where-Object {
    $_.FullName -match "(^|/)\.env$" -or
    ($_.FullName -match "(^|/)\.env\." -and $_.FullName -notmatch "\.env\.example$") -or
    $_.FullName -match "(^|/)\.git/" -or
    $_.FullName -match "(^|/)\.venv/" -or
    $_.FullName -match "__pycache__" -or
    $_.FullName -match "\.log$"
}
$count = $zipEntries.Count
$archive.Dispose()
if ($badEntries) {
    $badEntries | ForEach-Object { Write-Host "PROHIBIDO EN ZIP: $($_.FullName)" }
    throw "El ZIP contiene archivos prohibidos."
}

$hash = (Get-FileHash -LiteralPath $ZipPath -Algorithm SHA256).Hash
Write-Host ""
Write-Host "ZIP generado: $ZipPath"
Write-Host "Entradas: $count"
Write-Host "SHA256: $hash"
Write-Host "Verificado: sin .env, sin .git, sin .venv, sin caches, sin logs."
