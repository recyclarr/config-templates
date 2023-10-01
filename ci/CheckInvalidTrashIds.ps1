[CmdletBinding()]
param (
    [Parameter(Mandatory = $true)]
    [string[]] $PathToTrashRepo,

    [Parameter(Mandatory = $true)]
    [string] $PathToConfigRepo
)

$exitCode = 0

function GetTrashIds($path) {
    return Get-ChildItem -Recurse $path -Include "*.json"
        | Get-Content -Raw
        | ConvertFrom-Json
        | Select-Object -ExpandProperty trash_id
}

function OutputError($file, $line, $message) {
    $errorDetails = $(
        "file=$file"
        "line=$line"
        "title=Trash ID Validation Failure"
    )

    "::error $($errorDetails -join ',')::$message"
    $script:exitCode = 1
}

function CheckTrashIdCorrect($yamlDir, $shouldBeIn, $shouldNotBeIn) {
    $yamlFiles = Get-ChildItem -Recurse "$yamlDir" -Include "*.yml"

    foreach ($file in $yamlFiles) {
        "Processing $file"
        $lines = Get-Content $file

        for ($i = 0; $i -lt $lines.Count; $i++) {
            $match = $lines[$i] | Select-String -Pattern ' +- ([a-z0-9]+) +# +.+'
            if (-not $match.Matches.Success) {
                continue
            }

            $trashId = $match.Matches.Groups[1]
            $lineNumber = $i + 1

            if ($trashId -in $shouldNotBeIn) {
                OutputError $file $lineNumber "$trashId is from the wrong service"
            }
            elseif ($trashId -notin $shouldBeIn) {
                OutputError $file  $lineNumber  "$trashId is not in the guide"
            }
        }
    }
}

$radarrTrashIds = GetTrashIds "$PathToTrashRepo/docs/json/radarr/cf"
$sonarrTrashIds = GetTrashIds "$PathToTrashRepo/docs/json/sonarr/cf"

CheckTrashIdCorrect "$PathToConfigRepo/sonarr" $sonarrTrashIds $radarrTrashIds
CheckTrashIdCorrect "$PathToConfigRepo/radarr" $radarrTrashIds $sonarrTrashIds

exit $exitCode
