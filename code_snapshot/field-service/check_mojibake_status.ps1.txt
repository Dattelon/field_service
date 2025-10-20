#!/usr/bin/env pwsh
Write-Host "=== Checking mojibake status ===" -ForegroundColor Cyan

# Run the check
python tools/check_no_mojibake.py
$exitCode = $LASTEXITCODE

Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "✅ No mojibake found in project files!" -ForegroundColor Green
} else {
    Write-Host "⚠️  Mojibake found in some files (see output above)" -ForegroundColor Yellow
    Write-Host "Note: Files in .venv are external dependencies and can be ignored" -ForegroundColor Gray
}

Write-Host ""
Write-Host "=== Git changes ===" -ForegroundColor Cyan
git diff --stat tools/check_no_mojibake.py tools/fix_mojibake_per_line.py tools/fix_mojibake_in_repo.py

exit $exitCode
