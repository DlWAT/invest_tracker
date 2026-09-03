$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$db = Join-Path $scriptDir "..\..\data\listings.db"
$outDir = Join-Path $scriptDir "..\assets"
$out = Join-Path $outDir "listings.db"

if (-not (Test-Path -LiteralPath $db)) {
    throw "Base introuvable : $db`nLancez d'abord la collecte (python main.py) pour générer la base."
}

New-Item -ItemType Directory -Force -Path $outDir | Out-Null
Copy-Item -LiteralPath $db -Destination $out -Force
Write-Host "Base copiee : $db -> $out"
