param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('1.20', '1.21', '1.22', '1.23', '1.24', '1.25', '1.26', '1.27', '1.28', '1.29', '1.30', '1.31', '1.32')]
    [string] $Version
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

$dependencies = @('PySide6==6.9.2', 'PyInstaller==6.16.0')
if ($Version -in @('1.25', '1.26', '1.27', '1.28', '1.29', '1.30', '1.31', '1.32')) { $dependencies += 'sqlcipher3==0.6.2' }
python -m pip install --disable-pip-version-check @dependencies
if ($LASTEXITCODE -ne 0) { throw 'Installing Python build dependencies failed.' }
python -m PyInstaller --noconfirm --distpath $distRoot --workpath (Join-Path $buildRoot 'pyinstaller') (Join-Path $sourceDir 'ClipNest.spec')
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }

if ($Version -eq '1.20') {
    $package = Join-Path $outputRoot "ClipNest-$Version-Windows.zip"
    Compress-Archive -Path (Join-Path $distRoot 'ClipNest') -DestinationPath $package -Force
    Write-Output "Package=$package"
    exit 0
}

$innoInstaller = Join-Path $buildRoot 'innosetup-7.1.0-x64.exe'
$innoDir = Join-Path $buildRoot 'inno'
python -c "import urllib.request; urllib.request.urlretrieve('https://github.com/jrsoftware/issrc/releases/download/is-7_1_0/innosetup-7.1.0-x64.exe', r'$innoInstaller')"
if ($LASTEXITCODE -ne 0) { throw 'Downloading Inno Setup failed.' }
$expectedHash = '0362A383ED217D4C4239B5933866DD96D3EB2102737DA92F80F6057A4B40DF2F'
if ((Get-FileHash $innoInstaller -Algorithm SHA256).Hash -ne $expectedHash) { throw 'Inno Setup SHA-256 mismatch.' }
$inno = Start-Process -FilePath $innoInstaller -ArgumentList @('/SP-', '/VERYSILENT', '/NORESTART', '/CURRENTUSER', '/PORTABLE=1', ('/DIR="' + $innoDir + '"')) -Wait -PassThru -WindowStyle Hidden
if ($inno.ExitCode -ne 0) { throw "Inno Setup bootstrap failed: $($inno.ExitCode)" }

$template = Get-Content (Join-Path $desktopRoot 'installer\ClipNest.iss') -Raw
$template = $template.Replace('#define AppVersion "1.32"', "#define AppVersion `"$Version`"")
$template = $template.Replace('#define BuildDir "..\..\work\dist-v132\ClipNest"', "#define BuildDir `"$(Join-Path $distRoot 'ClipNest')`"")
$template = $template.Replace('VersionInfoVersion=1.32.0.0', "VersionInfoVersion=$Version.0.0")
$template = $template.Replace('SetupIconFile=ClipNest.ico', "SetupIconFile=$(Join-Path $sourceDir 'ClipNest.ico')")
$template = $template.Replace('OutputDir=..', "OutputDir=$outputRoot")
if ($Version -eq '1.21') {
    $template = $template.Replace('Filename: "{app}\ClipNest.exe"; Parameters: "--background"; Flags: nowait skipifnotsilent' + "`n", '')
    $template = $template.Replace('[UninstallDelete]' + "`n" + 'Type: files; Name: "{%LOCALAPPDATA}\ClipNest\github-token.dat"' + "`n" + 'Type: filesandordirs; Name: "{%LOCALAPPDATA}\ClipNest\updates"' + "`n", '')
}
$generatedScript = Join-Path $buildRoot 'ClipNest.iss'
[IO.File]::WriteAllText($generatedScript, $template, [Text.UTF8Encoding]::new($false))
& (Join-Path $innoDir 'ISCC.exe') /Q $generatedScript
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup compilation failed.' }
$package = Join-Path $outputRoot "ClipNest-$Version-Setup-x64.exe"
if (-not (Test-Path $package)) { throw "Missing package $package" }
Write-Output "Package=$package"
