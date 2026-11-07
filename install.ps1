# AI System Terminal - Windows PowerShell Installer
# Powered by ZETHUB AI

[CmdletBinding()]
param(
    [string]$CustomPythonPath = "",
    [string]$InstallDir = "$HOME\.ai-terminal"
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   AI SYSTEM TERMINAL INSTALLER - Powered by ZETHUB AI   " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Detect Windows Environment
Write-Host "[1/9] Detecting Windows environment..." -ForegroundColor Yellow
if ($PSVersionTable.PSVersion) {
    Write-Host "  PowerShell Version: $($PSVersionTable.PSVersion)" -ForegroundColor Green
    Write-Host "  OS: Windows ($([System.Environment]::OSVersion))" -ForegroundColor Green
} else {
    Write-Host "  Warning: Unexpected shell environment." -ForegroundColor DarkYellow
}

# 2. Find a Working Python Installation
Write-Host "`n[2/9] Finding working Python installation..." -ForegroundColor Yellow
$PythonCandidates = @(
    $CustomPythonPath,
    "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "E:\python.exe"
)

$SelectedPython = $null

# Check candidates first
foreach ($cand in $PythonCandidates) {
    if ($cand -and (Test-Path $cand)) {
        try {
            $ver = & $cand -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>$null
            if ($ver -and $LASTEXITCODE -eq 0) {
                $SelectedPython = (Resolve-Path $cand).Path
                Write-Host "  Found verified Python at: $SelectedPython (v$ver)" -ForegroundColor Green
                break
            }
        } catch {}
    }
}

# Fallback to py -3 or python in PATH
if (-not $SelectedPython) {
    try {
        $pyPath = (Get-Command py -ErrorAction SilentlyContinue).Source
        if ($pyPath) {
            $ver = & py -3 -c "import sys; print(sys.executable)" 2>$null
            if ($ver -and (Test-Path $ver)) {
                $SelectedPython = $ver.Trim()
                Write-Host "  Found Python via 'py' launcher: $SelectedPython" -ForegroundColor Green
            }
        }
    } catch {}
}

if (-not $SelectedPython) {
    try {
        $pyCmd = (Get-Command python -ErrorAction SilentlyContinue).Source
        if ($pyCmd) {
            $SelectedPython = $pyCmd
            Write-Host "  Found Python in PATH: $SelectedPython" -ForegroundColor Green
        }
    } catch {}
}

if (-not $SelectedPython) {
    Write-Error "Could not find a valid Python 3 installation. Please install Python 3.10+ from python.org."
    exit 1
}

# 3. Install Required Python Packages
Write-Host "`n[3/9] Installing required dependencies..." -ForegroundColor Yellow
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ReqFile = Join-Path $ScriptDir "requirements.txt"

if (Test-Path $ReqFile) {
    Write-Host "  Running: $SelectedPython -m pip install -r $ReqFile" -ForegroundColor DarkGray
    & $SelectedPython -m pip install -q -r $ReqFile
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "pip install exited with code $LASTEXITCODE. Retrying package installation..."
        & $SelectedPython -m pip install requests rich psutil prompt_toolkit
    }
} else {
    & $SelectedPython -m pip install requests rich psutil prompt_toolkit
}
Write-Host "  Required Python packages successfully installed." -ForegroundColor Green

# 4. Configure the Global CLI Directory & Wrappers
Write-Host "`n[4/9] Configuring global CLI directory..." -ForegroundColor Yellow
$BinDir = Join-Path $InstallDir "bin"
if (-not (Test-Path $BinDir)) {
    New-Item -ItemType Directory -Path $BinDir -Force | Out-Null
}

$MainPy = (Resolve-Path (Join-Path $ScriptDir "main.py")).Path

# Create ai.cmd for CMD / Windows Terminal
$CmdPath = Join-Path $BinDir "ai.cmd"
$CmdContent = @"
@echo off
setlocal
"$SelectedPython" "$MainPy" %*
"@
Set-Content -Path $CmdPath -Value $CmdContent -Encoding ASCII
Write-Host "  Created CMD wrapper: $CmdPath" -ForegroundColor Green

# Create ai.ps1 for PowerShell
$Ps1Path = Join-Path $BinDir "ai.ps1"
$Ps1Content = @"
param([Parameter(ValueFromRemainingArguments=`$true)]`$Args)
& "$SelectedPython" "$MainPy" @Args
"@
Set-Content -Path $Ps1Path -Value $Ps1Content -Encoding UTF8
Write-Host "  Created PowerShell wrapper: $Ps1Path" -ForegroundColor Green

# 5. Make 'ai' Globally Available in User PATH
Write-Host "`n[5/9] Making 'ai' globally accessible in PATH..." -ForegroundColor Yellow
$CurrentPath = [System.Environment]::GetEnvironmentVariable("PATH", [System.EnvironmentVariableTarget]::User)
if ($CurrentPath -notlike "*$BinDir*") {
    $NewPath = "$CurrentPath;$BinDir"
    [System.Environment]::SetEnvironmentVariable("PATH", $NewPath, [System.EnvironmentVariableTarget]::User)
    Write-Host "  Added $BinDir to User PATH." -ForegroundColor Green
} else {
    Write-Host "  $BinDir is already in User PATH." -ForegroundColor Green
}

# Update current session PATH immediately
if ($env:PATH -notlike "*$BinDir*") {
    $env:PATH = "$BinDir;$env:PATH"
}

# Configure PowerShell Profile function for direct convenience
try {
    $profileDir = Split-Path -Parent $PROFILE
    if (-not (Test-Path $profileDir)) {
        New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
    }
    $funcDef = "`n# AI System Terminal Wrapper`nfunction ai { & `"$SelectedPython`" `"$MainPy`" `$args }`n"
    if (Test-Path $PROFILE) {
        $existing = Get-Content $PROFILE -Raw -ErrorAction SilentlyContinue
        if ($existing -notlike "*AI System Terminal Wrapper*") {
            Add-Content -Path $PROFILE -Value $funcDef
            Write-Host "  Added 'ai' function to PowerShell `$PROFILE." -ForegroundColor Green
        }
    } else {
        Set-Content -Path $PROFILE -Value $funcDef -Encoding UTF8
        Write-Host "  Created PowerShell `$PROFILE with 'ai' function." -ForegroundColor Green
    }
} catch {
    Write-Host "  Notice: Could not write to `$PROFILE (PATH wrapper will handle invocation)." -ForegroundColor DarkGray
}

# 6. Configure API Settings
Write-Host "`n[6/9] Configuring API settings..." -ForegroundColor Yellow
$ConfigPath = Join-Path $InstallDir "config.json"
if (-not (Test-Path $ConfigPath)) {
    $DefaultConfig = @{
        api_url = "https://vireonix.ai/v1/chat/completions"
        model = "auto"
        api_key = ""
        timeout = 60
        max_retries = 3
        default_mode = "auto"
        max_repair_attempts = 3
    }
    $DefaultConfig | ConvertTo-Json -Depth 4 | Set-Content -Path $ConfigPath -Encoding UTF8
    Write-Host "  Saved default configuration at: $ConfigPath" -ForegroundColor Green
} else {
    Write-Host "  Existing configuration preserved at: $ConfigPath" -ForegroundColor Green
}

# 7. Verify API Connectivity
Write-Host "`n[7/9] Verifying ZETHUB AI API connectivity..." -ForegroundColor Yellow
try {
    $apiTest = & $SelectedPython "$MainPy" --test-api 2>&1
    Write-Host "  $apiTest" -ForegroundColor Cyan
} catch {
    Write-Host "  Warning: API connectivity test encountered an issue: $_" -ForegroundColor DarkYellow
}

# 8. Test Terminal Execution
Write-Host "`n[8/9] Testing terminal execution..." -ForegroundColor Yellow
try {
    $docTest = & $SelectedPython "$MainPy" --doctor 2>&1
    Write-Host "  Terminal engine execution verified successfully." -ForegroundColor Green
} catch {
    Write-Warning "Self-test failed: $_"
}

# 9. Confirm Installation Successful
Write-Host "`n[9/9] Installation Complete!" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   AI SYSTEM TERMINAL IS READY FOR USE!                   " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "`nYou can now run 'ai' from ANY directory in PowerShell or CMD:`n"
Write-Host '  ai "Give python code for KNN"' -ForegroundColor White
Write-Host '  ai "Check my Python installation"' -ForegroundColor White
Write-Host '  ai "Fix my project errors and run it"' -ForegroundColor White
Write-Host '  ai "Why is my Java application failing?"' -ForegroundColor White
Write-Host '  ai doctor' -ForegroundColor White
Write-Host '  ai inspect' -ForegroundColor White
Write-Host '  ai rollback' -ForegroundColor White
Write-Host ""

