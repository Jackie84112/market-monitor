$ErrorActionPreference = 'Continue'
$env:PYTHONIOENCODING = 'utf-8'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$log = Join-Path $root 'pipeline\run_update.log'
function Log($m) { "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m" | Out-File -Append -Encoding utf8 $log }

Log '--- start'
git pull --rebase --autostash -X theirs 2>&1 | ForEach-Object { Log $_ }
& 'C:\Users\green\AppData\Local\Programs\Python\Python314\python.exe' pipeline\build.py 2>&1 | Select-Object -Last 5 | ForEach-Object { Log $_ }
git add data 2>&1 | Out-Null
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    git commit -q -m "資料更新 $(Get-Date -Format 'yyyy-MM-dd HH:mm') 本機排程" 2>&1 | ForEach-Object { Log $_ }
    git pull --rebase -X theirs 2>&1 | ForEach-Object { Log $_ }
    git push 2>&1 | ForEach-Object { Log $_ }
} else { Log 'no data change' }
Log '--- done'
