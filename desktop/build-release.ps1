param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('1.00.0', '1.00.1', '1.00.2', '1.00.3', '1.30', '1.31', '1.32', '1.33', '1.34', '1.34.1', '1.34.2', '1.34.3', '1.34.4', '1.34.5', '1.34.6', '1.34.7')]
    [string] $Version,
    [string] $PythonExe = 'python',
    [switch] $UseInstalledDependencies
)

$ErrorActionPreference = 'Stop'
$desktopRoot = $PSScriptRoot
$repoRoot = Split-Path $desktopRoot -Parent
$sourceDir = Join-Path $desktopRoot "versions\$Version"
$buildRoot = Join-Path $repoRoot "build\$Version"
$distRoot = Join-Path $buildRoot 'dist'
$outputRoot = Join-Path $repoRoot 'release-output'
New-Item -ItemType Directory -Force $buildRoot, $outputRoot | Out-Null

$iconBytes = [Convert]::FromBase64String((Get-Content (Join-Path $desktopRoot 'assets\ClipNest.ico.base64') -Raw).Trim())
[IO.File]::WriteAllBytes((Join-Path $sourceDir 'ClipNest.ico'), $iconBytes)

$dependencies = @('PySide6==6.9.2', 'PyInstaller==6.16.0', 'sqlcipher3==0.6.2')
if (-not $UseInstalledDependencies) {
    & $PythonExe -m pip install --disable-pip-version-check @dependencies
    if ($LASTEXITCODE -ne 0) { throw 'Installing Python build dependencies failed.' }
}
& $PythonExe -m PyInstaller --noconfirm --distpath $distRoot --workpath (Join-Path $buildRoot 'pyinstaller') (Join-Path $sourceDir 'ClipNest.spec')
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }
if ($Version -in @('1.00.0', '1.00.1', '1.00.2', '1.00.3', '1.34.3', '1.34.4', '1.34.5', '1.34.6', '1.34.7')) {
    foreach ($relative in @('_internal\LICENSE', '_internal\THIRD-PARTY-NOTICES.md', '_internal\licenses\LGPL-3.0.txt', '_internal\licenses\GPL-3.0.txt', '_internal\licenses\Apache-2.0.txt')) {
        if (-not (Test-Path (Join-Path $distRoot "ClipNest\$relative"))) { throw "Missing bundled license: $relative" }
    }
}

$innoInstaller = Join-Path $buildRoot 'innosetup-7.1.0-x64.exe'
$innoDir = Join-Path $buildRoot 'inno'
& $PythonExe -c "import urllib.request; urllib.request.urlretrieve('https://github.com/jrsoftware/issrc/releases/download/is-7_1_0/innosetup-7.1.0-x64.exe', r'$innoInstaller')"
if ($LASTEXITCODE -ne 0) { throw 'Downloading Inno Setup failed.' }
$expectedHash = '0362A383ED217D4C4239B5933866DD96D3EB2102737DA92F80F6057A4B40DF2F'
if ((Get-FileHash $innoInstaller -Algorithm SHA256).Hash -ne $expectedHash) { throw 'Inno Setup SHA-256 mismatch.' }
$inno = Start-Process -FilePath $innoInstaller -ArgumentList @('/SP-', '/VERYSILENT', '/NORESTART', '/CURRENTUSER', '/PORTABLE=1', ('/DIR="' + $innoDir + '"')) -Wait -PassThru -WindowStyle Hidden
if ($inno.ExitCode -ne 0) { throw "Inno Setup bootstrap failed: $($inno.ExitCode)" }

$template = Get-Content (Join-Path $desktopRoot 'installer\ClipNest.iss') -Raw
$template = $template.Replace('#define AppVersion "1.32"', "#define AppVersion `"$Version`"")
$template = $template.Replace('#define BuildDir "..\..\work\dist-v132\ClipNest"', "#define BuildDir `"$(Join-Path $distRoot 'ClipNest')`"")
$versionComponents = @($Version.Split('.'))
while ($versionComponents.Count -lt 4) { $versionComponents += '0' }
$template = $template.Replace('VersionInfoVersion=1.32.0.0', "VersionInfoVersion=$($versionComponents[0..3] -join '.')")
$template = $template.Replace('SetupIconFile=ClipNest.ico', "SetupIconFile=$(Join-Path $sourceDir 'ClipNest.ico')")
$template = $template.Replace('OutputDir=..', "OutputDir=$outputRoot")
$generatedScript = Join-Path $buildRoot 'ClipNest.iss'
[IO.File]::WriteAllText($generatedScript, $template, [Text.UTF8Encoding]::new($false))
& (Join-Path $innoDir 'ISCC.exe') /Q $generatedScript
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup compilation failed.' }
$package = Join-Path $outputRoot "ClipNest-$Version-Setup-x64.exe"
if (-not (Test-Path $package)) { throw "Missing package $package" }
Write-Output "Package=$package"
