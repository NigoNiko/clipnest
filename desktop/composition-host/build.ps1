param([string] $DotnetExe = 'dotnet')

$ErrorActionPreference = 'Stop'
$publishDir = Join-Path $PSScriptRoot 'publish-framework'
$marker = Join-Path $publishDir 'dotnet-runtime-required.marker'
if (Test-Path -LiteralPath $marker) { Remove-Item -LiteralPath $marker }
$projectFile = Join-Path $PSScriptRoot 'ClipNest.BlurHost.csproj'
$offlinePackages = Join-Path $PSScriptRoot '..\..\local-tests\composition-prototype\offline-packages'
if (Test-Path -LiteralPath $offlinePackages) {
    & $DotnetExe restore $projectFile -r win-x64 --source $offlinePackages
}
if (-not (Test-Path -LiteralPath $offlinePackages) -or $LASTEXITCODE -ne 0) {
    & $DotnetExe restore $projectFile -r win-x64 --source 'https://api.nuget.org/v3/index.json'
}
if ($LASTEXITCODE -ne 0) { throw 'Blur host restore failed.' }

& $DotnetExe publish $projectFile -c Release -r win-x64 --no-restore --self-contained false `
    -p:PublishSingleFile=false -p:CopyDebugSymbolFilesFromPackages=false `
    -p:DebugSymbols=false -p:DebugType=None `
    -o $publishDir
if ($LASTEXITCODE -ne 0) { throw 'Framework-dependent blur host publish failed.' }

$hostExe = Join-Path $publishDir 'ClipNest.BlurHost.exe'
if (-not (Test-Path -LiteralPath $hostExe)) {
    throw 'Missing blur host executable.'
}
$runtimeConfig = Get-Content -LiteralPath (Join-Path $publishDir 'ClipNest.BlurHost.runtimeconfig.json') -Raw | ConvertFrom-Json
if ($runtimeConfig.runtimeOptions.framework.name -ne 'Microsoft.NETCore.App' -or
    $runtimeConfig.runtimeOptions.includedFrameworks) {
    throw 'Blur host does not declare its .NET 8 Runtime dependency.'
}
Get-ChildItem -LiteralPath $publishDir -File -Filter '*.pdb' |
    ForEach-Object { Remove-Item -LiteralPath $_.FullName }
Set-Content -LiteralPath $marker -Value 'win-x64; .NET 8 Runtime x64 required' -Encoding ascii
