# Muhammed görüntüleyicisini başlatır. PowerShell'de bu dosyanın klasöründen:
#   powershell -ExecutionPolicy Bypass -File .\kur.ps1
# İlk çalıştırmada bağımlılıkları kurar, her seferinde dalı günceller,
# sunucuyu 8000 portunda açar ve tarayıcıyı görüntüleyiciye yönlendirir.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Write-Host "Klasör: $PSScriptRoot"

try { git pull --ff-only 2>$null | Out-Null; Write-Host "Dal güncellendi." } catch { Write-Host "git pull atlandı." }

if (-not (Test-Path ".kuruldu")) {
    Write-Host "Bağımlılıklar kuruluyor..."
    python -m pip install -q -r requirements.txt
    New-Item -ItemType File -Path ".kuruldu" | Out-Null
}

$port = 8000
Start-Job -ScriptBlock { Start-Sleep -Seconds 1.5; Start-Process "http://localhost:$using:port/web/" } | Out-Null
Write-Host "Sunucu http://localhost:$port/web/ adresinde. Kapatmak için Ctrl+C."
python -m http.server $port
