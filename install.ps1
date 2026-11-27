$ErrorActionPreference = "Stop"

$Repo = "AchillesOrg/saylang"
$InstallDir = Join-Path $env:LOCALAPPDATA "Programs\SayLang"
$ExePath = Join-Path $InstallDir "saylang.exe"
$Url = "https://github.com/$Repo/releases/latest/download/saylang-windows-x64.exe"

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Write-Host "Downloading $Url..."
Invoke-WebRequest -Uri $Url -OutFile $ExePath

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
