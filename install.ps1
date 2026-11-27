param(
    [string]$Version = $env:SAYLANG_VERSION
)

$ErrorActionPreference = "Stop"

$Repo = "AchillesOrg/saylang"
$Releases = "https://github.com/$Repo/releases"
$Asset = "saylang-windows-x64.exe"
$Headers = @{ "Cache-Control" = "no-cache" }
$InstallDir = Join-Path $env:LOCALAPPDATA "Programs\SayLang"
$ExePath = Join-Path $InstallDir "saylang.exe"
$TmpPath = "$ExePath.$([guid]::NewGuid()).tmp"

if ([string]::IsNullOrEmpty($Version)) {
    $Version = "latest"
}

if ($Version -ceq "latest") {
    # Resolve the tag before downloading so a cached asset redirect cannot select an older release.
    $Check = [guid]::NewGuid()
    $Tag = $null
    try {
        $Release = Invoke-RestMethod -UseBasicParsing -Uri "https://api.github.com/repos/$Repo/releases/latest?saylang_check=$Check" -Headers $Headers
        $Tag = $Release.tag_name
    } catch {
        Write-Verbose "Could not look up the latest release tag. Using the GitHub download redirect."
    }
    if ($Tag -cmatch '\Av[0-9][0-9A-Za-z.+-]*\z') {
        $Url = "$Releases/download/$Tag/$Asset"
    } else {
        $Url = "$Releases/latest/download/${Asset}?saylang_check=$Check"
    }
} else {
    if ($Version -cnotmatch '\A(v?)([0-9]+\.[0-9]+\.[0-9]+([-+][0-9A-Za-z.+-]+)?)\z') {
        throw "Invalid SayLang version '$Version'. Use 'latest' or a version such as 'v0.3.2'."
    }
    $Tag = "v$($Matches[2])"
    $Url = "$Releases/download/$Tag/$Asset"
}

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Write-Host "Downloading $Url..."
try {
    try {
        Invoke-WebRequest -UseBasicParsing -Uri $Url -Headers $Headers -OutFile $TmpPath
    } catch {
        throw "Could not download $Asset for '$Version'. Check the published assets at ${Releases}. $($_.Exception.Message)"
    }
    Move-Item -Force -Path $TmpPath -Destination $ExePath
} finally {
    if (Test-Path -LiteralPath $TmpPath) {
        Remove-Item -LiteralPath $TmpPath -Force
    }
}

$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ([string]::IsNullOrEmpty($UserPath)) {
    $UserPath = ""
}
$PathEntries = $UserPath -split ";" | Where-Object { $_ -ne "" }
if ($PathEntries -notcontains $InstallDir) {
    $NewUserPath = ($PathEntries + $InstallDir) -join ";"
    [Environment]::SetEnvironmentVariable("Path", $NewUserPath, "User")
    Write-Host "Added $InstallDir to your user PATH."
}

if (($env:Path -split ";") -notcontains $InstallDir) {
    $env:Path = "$InstallDir;$env:Path"
}

Write-Host "Installed SayLang to $ExePath"
& $ExePath --version
