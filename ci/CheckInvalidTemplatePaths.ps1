[CmdletBinding()]
param (
    [Parameter(Mandatory = $true)]
    [string] $JsonPath
)

function GetPaths($serviceType) {
    Get-Content -Path $JsonPath
        | ConvertFrom-Json
        | ForEach-Object { $_.$serviceType.template }
}

$nonExistentFiles = $(GetPaths("radarr"); GetPaths("sonarr"))
    | Where-Object {!(Test-Path -Path $_ -PathType Leaf)}


if ($nonExistentFiles.length -gt 0) {
    "FAILED: More than one invalid file path found:"
    foreach ($file in $nonExistentFiles) {
        "::error title=Invalid Template Path::$file"
    }
    exit 1
}

"No invalid file paths found"
exit 0
