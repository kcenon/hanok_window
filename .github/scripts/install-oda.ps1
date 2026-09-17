# Optional Windows CI dependency. Usage terms and update procedure: generator/docs/DWG_CI.md.
$ErrorActionPreference = 'Stop'
if (-not $env:RUNNER_TEMP -or -not $env:GITHUB_ENV) {
    throw 'RUNNER_TEMP and GITHUB_ENV must identify the CI temporary directory and environment file.'
}

$odaVersion = '27.1.0'
# microsoft/winget-pkgs, commit 29b5dd318c692ec734ce503c7a7162da03535921.
$odaUrl = 'https://www.opendesign.com/guestfiles/get?filename=ODAFileConverter_QT6_vc16_amd64dll_27.1.msi'
$odaSha256 = '3D5961F510CF95F398B8E2920899DC8E8C51ADECDAF5B20A40B3D1A29269DE81'
$odaInstaller = Join-Path $env:RUNNER_TEMP 'ODAFileConverter-27.1.0.msi'
$odaLog = Join-Path $env:RUNNER_TEMP 'oda-install.log'
$odaExecutable = Join-Path $env:ProgramFiles "ODA/ODAFileConverter $odaVersion/ODAFileConverter.exe"

Write-Host "WinGet available: $([bool](Get-Command winget -ErrorAction SilentlyContinue)); using the pinned ODA MSI."
Invoke-WebRequest -Uri $odaUrl -OutFile $odaInstaller -TimeoutSec 90
if ((Get-FileHash -LiteralPath $odaInstaller -Algorithm SHA256).Hash -ne $odaSha256) {
    throw 'ODA installer SHA-256 mismatch; the downloaded file will not be executed.'
}

Write-Host "Installing ODA File Converter $odaVersion (SHA-256 verified)."
$odaProcess = Start-Process -FilePath msiexec.exe -ArgumentList @(
    '/i', ('"{0}"' -f $odaInstaller), '/qn', '/norestart', '/L*v', ('"{0}"' -f $odaLog)
) -Wait -PassThru -WindowStyle Hidden
if ($odaProcess.ExitCode -notin @(0, 3010)) {
    if (Test-Path -LiteralPath $odaLog -PathType Leaf) {
        Get-Content -LiteralPath $odaLog -Tail 40
    }
    throw "ODA installation failed with exit code $($odaProcess.ExitCode)."
}
if (-not (Test-Path -LiteralPath $odaExecutable -PathType Leaf)) {
    throw "ODA installation did not produce $odaExecutable."
}

# Publish only after successful setup. The workflow's missing-path override remains on failure.
Write-Host "ODA File Converter $odaVersion executable: $odaExecutable"
"HANOK_ODAFC=$odaExecutable" | Out-File -LiteralPath $env:GITHUB_ENV -Append -Encoding utf8
