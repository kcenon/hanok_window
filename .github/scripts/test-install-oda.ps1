# Exercise setup failures without downloading or installing software. No Pester dependency.
$ErrorActionPreference = 'Stop'
$odaTestRoot = Join-Path ([IO.Path]::GetTempPath()) ("hanok oda setup " + [guid]::NewGuid())
$odaPreviousTemp = $env:RUNNER_TEMP
$odaPreviousEnv = $env:GITHUB_ENV
New-Item -ItemType Directory -Path $odaTestRoot | Out-Null

function Test-OdaSetup([string]$Scenario) {
    $env:RUNNER_TEMP = $odaTestRoot
    $env:GITHUB_ENV = Join-Path $odaTestRoot "$Scenario.env"
    [IO.File]::WriteAllText($env:GITHUB_ENV, '')
    $calls = [Collections.Generic.List[string]]::new()

    function Invoke-WebRequest($Uri, $OutFile, $TimeoutSec) {
        $calls.Add('download')
        if ($TimeoutSec -ne 90 -or $Uri -notlike 'https://www.opendesign.com/guestfiles/get?filename=*.msi') {
            throw 'Unexpected download source or timeout.'
        }
        if ($Scenario -eq 'download-failure') { throw 'Simulated download failure.' }
    }
    function Get-FileHash($LiteralPath, $Algorithm) {
        $calls.Add('hash')
        if ($Algorithm -ne 'SHA256') { throw 'Expected SHA-256 verification.' }
        $hash = '3D5961F510CF95F398B8E2920899DC8E8C51ADECDAF5B20A40B3D1A29269DE81'
        if ($Scenario -eq 'hash-mismatch') { $hash = '0' * 64 }
        [pscustomobject]@{ Hash = $hash }
    }
    function Start-Process($FilePath, $ArgumentList, [switch]$Wait, [switch]$PassThru, $WindowStyle) {
        $calls.Add('install')
        if ($FilePath -ne 'msiexec.exe' -or -not $Wait -or -not $PassThru -or $WindowStyle -ne 'Hidden' -or
            '/qn' -notin $ArgumentList -or '/norestart' -notin $ArgumentList -or
            $ArgumentList[1] -ne ('"{0}"' -f (Join-Path $odaTestRoot 'ODAFileConverter-27.1.0.msi')) -or
            $ArgumentList[-1] -ne ('"{0}"' -f (Join-Path $odaTestRoot 'oda-install.log'))) {
            throw 'Expected silent installation, no restart, and quoted paths containing spaces.'
        }
        $code = switch ($Scenario) { 'installer-failure' { 1603 }; 'reboot-required' { 3010 }; default { 0 } }
        [pscustomobject]@{ ExitCode = $code }
    }
    function Test-Path($LiteralPath, $PathType) {
        $LiteralPath -like '*ODAFileConverter.exe' -and $Scenario -ne 'missing-executable'
    }

    $failure = $null
    try { & "$PSScriptRoot/install-oda.ps1" }
    catch { $failure = $_.Exception.Message }
    $export = [IO.File]::ReadAllText($env:GITHUB_ENV)
    $expectedFailure = switch ($Scenario) {
        'download-failure' { 'Simulated download failure' }
        'hash-mismatch' { 'SHA-256 mismatch' }
        'installer-failure' { 'exit code 1603' }
        'missing-executable' { 'did not produce' }
        default { $null }
    }
    if ($expectedFailure) {
        if (-not $failure -or $failure -notlike "*$expectedFailure*" -or $export) {
            throw "${Scenario}: expected '$expectedFailure', no exported converter; got '$failure', '$export'."
        }
    } else {
        $expectedPath = Join-Path $env:ProgramFiles 'ODA/ODAFileConverter 27.1.0/ODAFileConverter.exe'
        if ($failure -or $export.Trim() -ne "HANOK_ODAFC=$expectedPath") {
            throw "${Scenario}: expected a usable converter export; got '$failure', '$export'."
        }
    }
    if ($Scenario -in @('download-failure', 'hash-mismatch') -and 'install' -in $calls) {
        throw "${Scenario}: an unverified installer was executed."
    }
    Write-Host "PASS: $Scenario"
}

try {
    foreach ($odaScenario in @('success', 'reboot-required', 'download-failure', 'hash-mismatch',
                               'installer-failure', 'missing-executable')) {
        Test-OdaSetup $odaScenario
    }
} finally {
    $env:RUNNER_TEMP = $odaPreviousTemp
    $env:GITHUB_ENV = $odaPreviousEnv
    # Only remove this test's unique, fully qualified temporary directory.
    $odaResolvedRoot = (Resolve-Path -LiteralPath $odaTestRoot).Path
    if ([IO.Path]::GetDirectoryName($odaResolvedRoot) -ne [IO.Path]::GetTempPath().TrimEnd('\', '/')) {
        throw 'Unexpected ODA test temporary directory.'
    }
    Remove-Item -LiteralPath $odaResolvedRoot -Recurse -Force
}
