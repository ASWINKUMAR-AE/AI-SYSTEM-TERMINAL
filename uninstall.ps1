# AI System Terminal - Uninstaller
# Removes global wrappers, PATH entries, and PowerShell profile integration

[CmdletBinding()]
param(
    [switch]$PurgeAll = $false,
    [string]$InstallDir = "$HOME\.ai-terminal"
)

Write-Host "==========================================================" -ForegroundColor Yellow
Write-Host "   AI SYSTEM TERMINAL UNINSTALLER                         " -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Yellow
Write-Host ""

$BinDir = Join-Path $InstallDir "bin"

# 1. Remove from User PATH
Write-Host "[1/4] Removing from User PATH..." -ForegroundColor Cyan
$CurrentPath = [System.Environment]::GetEnvironmentVariable("PATH", [System.EnvironmentVariableTarget]::User)
if ($CurrentPath -like "*$BinDir*") {
    $PathParts = $CurrentPath.Split(';') | Where-Object { $_ -ne $BinDir -and $_ -ne "" }
    $NewPath = $PathParts -join ';'
    [System.Environment]::SetEnvironmentVariable("PATH", $NewPath, [System.EnvironmentVariableTarget]::User)
    Write-Host "  Removed $BinDir from User PATH." -ForegroundColor Green
} else {
    Write-Host "  $BinDir was not found in User PATH." -ForegroundColor DarkGray
}

# 2. Remove from PowerShell Profile
Write-Host "`n[2/4] Removing function from PowerShell Profile..." -ForegroundColor Cyan
try {
    if (Test-Path $PROFILE) {
        $content = Get-Content $PROFILE -Raw
        if ($content -like "*AI System Terminal Wrapper*") {
            $filtered = ($content -split "`r?`n") | Where-Object { 
                $_ -notlike "*AI System Terminal Wrapper*" -and 
                $_ -notlike "*function ai {*" -and 
                $_ -notlike "*& *main.py*`$args*"
            }
            Set-Content -Path $PROFILE -Value ($filtered -join "`r`n") -Encoding UTF8
            Write-Host "  Removed 'ai' function from $PROFILE." -ForegroundColor Green
        }
    }
} catch {
    Write-Warning "Could not update `$PROFILE: $_"
}

# 3. Remove Wrappers
Write-Host "`n[3/4] Removing launcher wrappers..." -ForegroundColor Cyan
if (Test-Path $BinDir) {
    Remove-Item -Path $BinDir -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "  Deleted directory: $BinDir" -ForegroundColor Green
}

# 4. Optional Purge
if ($PurgeAll) {
    Write-Host "`n[4/4] Purging configuration and backups..." -ForegroundColor Cyan
    if (Test-Path $InstallDir) {
        Remove-Item -Path $InstallDir -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "  Purged all data at: $InstallDir" -ForegroundColor Green
    }
} else {
    Write-Host "`n[4/4] Configuration preserved at: $InstallDir" -ForegroundColor DarkGray
    Write-Host "  (To completely remove configuration and history, re-run with: .\uninstall.ps1 -PurgeAll)" -ForegroundColor DarkGray
}

Write-Host "`nUninstallation complete. AI System Terminal has been removed." -ForegroundColor Green

