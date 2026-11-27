$ErrorActionPreference = "Stop"

$Repo = "AchillesOrg/saylang"
$InstallDir = Join-Path $env:LOCALAPPDATA "Programs\SayLang"
$ExePath = Join-Path $InstallDir "saylang.exe"
$TmpPath = "$ExePath.tmp"

$Tag = $env:SAYLANG_VERSION
if ([string]::IsNullOrWhiteSpace($Tag)) {
    try {
        $Release = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/latest"
        $Tag = $Release.tag_name
    } catch {
        $Tag = ""
    }
}

if (-not [string]::IsNullOrWhiteSpace($Tag)) {
    $Url = "https://github.com/$Repo/releases/download/$Tag/saylang-windows-x64.exe"
} else {
    $Url = "https://github.com/$Repo/releases/latest/download/saylang-windows-x64.exe"
}

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Write-Host "Downloading $Url..."
Invoke-WebRequest -Uri $Url -OutFile $TmpPath
Move-Item -Force -Path $TmpPath -Destination $ExePath

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
