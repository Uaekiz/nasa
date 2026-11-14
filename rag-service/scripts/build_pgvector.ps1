param(
    [string]$PostgresRoot = 'C:\Program Files\PostgreSQL\18'
)

$ErrorActionPreference = 'Stop'
$ragServiceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$ragCheckout = Join-Path $ragServiceRoot '.local\pgvector-v0.8.7'
$ragPgConfig = Join-Path $PostgresRoot 'bin\pg_config.exe'
if (-not (Test-Path -LiteralPath $ragPgConfig)) { throw 'PostgreSQL pg_config.exe was not found.' }
$ragVersion = & $ragPgConfig --version
if ($LASTEXITCODE -ne 0 -or $ragVersion -notmatch '^PostgreSQL 18\.') {
    throw 'This local build command targets the detected PostgreSQL 18 installation.'
}
$ragVswhere = 'C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe'
if (-not (Test-Path -LiteralPath $ragVswhere)) { throw 'Visual Studio C++ Build Tools are required.' }
$ragVsRoot = & $ragVswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $ragVsRoot) { throw 'The x64 C++ compiler workload was not found.' }
$ragDevCmd = Join-Path $ragVsRoot 'Common7\Tools\VsDevCmd.bat'
if (-not (Test-Path -LiteralPath $ragDevCmd)) { throw 'Visual Studio developer command initialization was not found.' }

if (-not (Test-Path -LiteralPath $ragCheckout)) {
    New-Item -ItemType Directory -Path (Split-Path $ragCheckout -Parent) -Force | Out-Null
    & git clone --depth 1 --branch v0.8.7 https://github.com/pgvector/pgvector.git $ragCheckout
    if ($LASTEXITCODE -ne 0) { throw 'Downloading the pinned pgvector source failed.' }
}
$ragOrigin = & git -C $ragCheckout remote get-url origin
$ragTag = & git -C $ragCheckout describe --tags --exact-match HEAD
$ragChangedSource = & git -C $ragCheckout status --porcelain --untracked-files=no
if ($ragOrigin -ne 'https://github.com/pgvector/pgvector.git' -or $ragTag -ne 'v0.8.7' -or $ragChangedSource) {
    throw 'The existing build checkout is different or modified. It was not reset or overwritten.'
}

$ragBatch = Join-Path $ragCheckout 'pyrosphere-build.cmd'
$ragBatchContent = @'
@echo off
call "%RAG_VS_DEVCMD%" -host_arch=x64 -arch=x64
if errorlevel 1 exit /b %errorlevel%
nmake /F Makefile.win
'@
if ((Test-Path -LiteralPath $ragBatch) -and [IO.File]::ReadAllText($ragBatch) -ne $ragBatchContent) {
    throw 'A different local build wrapper already exists and was preserved.'
}
[IO.File]::WriteAllText($ragBatch, $ragBatchContent, [Text.Encoding]::ASCII)
$ragPreviousPgRoot = $env:PGROOT
$ragPreviousDevCmd = $env:RAG_VS_DEVCMD
try {
    $env:PGROOT = $PostgresRoot
    $env:RAG_VS_DEVCMD = $ragDevCmd
    Push-Location $ragCheckout
    try {
        & $env:ComSpec /d /c $ragBatch
        if ($LASTEXITCODE -ne 0) { throw 'The pgvector source build failed. No PostgreSQL installation files were changed.' }
    }
    finally { Pop-Location }
}
finally {
    $env:PGROOT = $ragPreviousPgRoot
    $env:RAG_VS_DEVCMD = $ragPreviousDevCmd
}
if (-not (Test-Path -LiteralPath (Join-Path $ragCheckout 'vector.dll'))) { throw 'The compiler did not produce vector.dll.' }
Write-Output ('Built pgvector v0.8.7 in: ' + $ragCheckout)
Write-Output 'No server installation files, databases, roles, or tables were changed by this build.'
Write-Output 'If vector is still absent, run these commands yourself in an Administrator x64 Native Tools Command Prompt:'
Write-Output ('set "PGROOT={0}"' -f $PostgresRoot)
Write-Output ('cd /d "{0}"' -f $ragCheckout)
Write-Output 'nmake /F Makefile.win install'
