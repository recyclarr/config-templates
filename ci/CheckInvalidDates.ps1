[CmdletBinding()]
param (
    [Parameter(Mandatory = $true)]
    [string[]] $ChangedFiles,

    [Parameter(Mandatory = $true)]
    [string] $ExpectedDate
)

$exitCode = 0

foreach ($file in $ChangedFiles) {
    $ext = [IO.Path]::GetExtension($file);
    if (@(".yml", ".yaml") -notcontains $ext.ToLower()) {
        "Skip ${file}: Not a YAML file"
        continue;
    }

    $lines = Get-Content -Path $file
    for ($i = 0; $i -lt $lines.Count; $i++) {
        $match = $lines[$i] | Select-String -Pattern 'Updated: ([\d-]+)'
        if (-not $match.Matches.Success) {
            continue
        }

        $yamlDate = $match.Matches.Groups[1]
        if ($yamlDate.Value -eq $ExpectedDate) {
            continue
        }

        $errorMsg = "Date $($yamlDate.Value) needs to be updated to $ExpectedDate"
        $errorDetails = $(
            "file=$file"
            "line=$($i + 1)"
            "col=$($yamlDate.Index)"
            "endColumn=$($yamlDate.Index + $yamlDate.Length)"
            "title=File Date Not Updated"
        )

        "::error $($errorDetails -join ',')::$errorMsg"
        $exitCode = 1
    }
}

exit $exitCode
