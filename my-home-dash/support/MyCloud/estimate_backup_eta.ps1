[CmdletBinding()]
<#
.SYNOPSIS
Quick ETA calculator for the MyCloud robocopy workflow.

.DESCRIPTION
Estimates backup duration from a cached directory size plus either a prior robocopy log
or an explicit throughput value. It avoids recursive rescans unless -RefreshSizeCache is used.

.EXAMPLE
.
\estimate_backup_eta.ps1 -DirectoryName MyProjects -RefreshSizeCache -ThroughputMBps 42

Scans E:\MyProjects once, stores the size in eta_size_cache.json, and prints an ETA using 42 MiB/s.

.EXAMPLE
.
\estimate_backup_eta.ps1 -DirectoryName ProgramFiles -LogPath C:\Users\jpful\Documents\robocopy_myprojects_to_wdblack2.log
[CmdletBinding()]
<#
.SYNOPSIS
Quick ETA calculator for the MyCloud robocopy workflow.

.DESCRIPTION
Estimates backup completion from a cached source size plus either a robocopy log or an
explicit throughput value. For active robocopy runs, the script reads only newly appended
log content and stores incremental progress in a local cache so repeated ETA checks stay fast.

.EXAMPLE
.\estimate_backup_eta.ps1 -DirectoryName MyProjects -RefreshSizeCache -ThroughputMBps 42

Scans E:\MyProjects once, stores the size in eta_size_cache.json, and reports an expected
completion time using 42 MiB/s.

.EXAMPLE
.\estimate_backup_eta.ps1 -DirectoryName MyProjects -LogPath C:\Users\jpful\Documents\robocopy_myprojects_to_wdblack2.log

Uses the cached size for E:\MyProjects, reads only newly appended robocopy log content,
and reports the expected completion time for the active run.

.EXAMPLE
.\estimate_backup_eta.ps1 -ListCache

Shows cached directory sizes without rescanning anything.

.EXAMPLE
.\estimate_backup_eta.ps1 -ListProgressCache

Shows cached robocopy log progress state without touching the source or destination trees.
#>
param(
    [Parameter(Position = 0)]
    [string]$DirectoryName,

    [string]$SourcePath,

    [string]$LogPath,

    [double]$ThroughputMBps,

    [UInt64]$TotalBytes,

    [string]$CachePath = (Join-Path $PSScriptRoot 'eta_size_cache.json'),

    [string]$ProgressCachePath = (Join-Path $PSScriptRoot 'eta_progress_cache.json'),

    [switch]$RefreshSizeCache,

    [switch]$ListCache,

    [switch]$ListProgressCache,

    [switch]$AsJson
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function ConvertTo-ReadableSize {
    param(
        [Parameter(Mandatory = $true)]
        [double]$Bytes
    )

    $units = @('B', 'KB', 'MB', 'GB', 'TB', 'PB')
    $size = $Bytes
    $unitIndex = 0

    while ($size -ge 1024 -and $unitIndex -lt ($units.Count - 1)) {
        $size = $size / 1024
        $unitIndex++
    }

    return ('{0:N2} {1}' -f $size, $units[$unitIndex])
}

function ConvertTo-ReadableDuration {
    param(
        [Parameter(Mandatory = $true)]
        [TimeSpan]$Duration
    )

    if ($Duration.TotalSeconds -lt 1) {
        return 'less than 1 second'
    }

    $parts = @()

    if ($Duration.Days -gt 0) {
        $parts += ('{0}d' -f $Duration.Days)
    }

    if ($Duration.Hours -gt 0) {
        $parts += ('{0}h' -f $Duration.Hours)
    }

    if ($Duration.Minutes -gt 0) {
        $parts += ('{0}m' -f $Duration.Minutes)
    }

    if ($Duration.Seconds -gt 0 -and $parts.Count -eq 0) {
        $parts += ('{0}s' -f $Duration.Seconds)
    }

    return ($parts -join ' ')
}

function Get-ParsedDateTime {
    param(
        [string]$Text
    )

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return $null
    }

    $cultures = @(
        [System.Globalization.CultureInfo]::InvariantCulture,
        [System.Globalization.CultureInfo]::GetCultureInfo('en-US')
    )

    foreach ($culture in $cultures) {
        try {
            return [datetime]::Parse($Text.Trim(), $culture)
        }
        catch {
        }
    }

    return $null
}

function Get-SizeCache {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return @{}
    }

    $raw = Get-Content -LiteralPath $Path -Raw
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return @{}
    }

    $parsed = $raw | ConvertFrom-Json
    $cache = @{}

    if ($parsed.PSObject.Properties.Name -contains 'entries') {
        foreach ($entry in $parsed.entries) {
            $cache[$entry.SourcePath.ToLowerInvariant()] = [pscustomobject]@{
                directoryName = $entry.DirectoryName
                sourcePath = $entry.SourcePath
                totalBytes = [UInt64]$entry.TotalBytes
                scannedAtUtc = $entry.ScannedAtUtc
            }
        }
    }

    return $cache
}

function Save-SizeCache {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [hashtable]$Cache
    )

    $entries = foreach ($key in ($Cache.Keys | Sort-Object)) {
        $item = $Cache[$key]
        [pscustomobject]@{
            DirectoryName = $item.directoryName
            SourcePath = $item.sourcePath
            TotalBytes = [UInt64]$item.totalBytes
            ScannedAtUtc = $item.scannedAtUtc
        }
    }

    $payload = [pscustomobject]@{
        entries = $entries
    }

    $json = $payload | ConvertTo-Json -Depth 4
    Set-Content -LiteralPath $Path -Value $json
}

function Get-ProgressCache {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return @{}
    }

    $raw = Get-Content -LiteralPath $Path -Raw
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return @{}
    }

    $parsed = $raw | ConvertFrom-Json
    $cache = @{}

    if ($parsed.PSObject.Properties.Name -contains 'entries') {
        foreach ($entry in $parsed.entries) {
            $cache[$entry.LogPath.ToLowerInvariant()] = [pscustomobject]@{
                logPath = $entry.LogPath
                logOffset = [Int64]$entry.LogOffset
                processedBytes = [UInt64]$entry.ProcessedBytes
                startedAtUtc = $entry.StartedAtUtc
                lastUpdatedUtc = $entry.LastUpdatedUtc
                parsedLines = [Int64]$entry.ParsedLines
            }
        }
    }

    return $cache
}

function Save-ProgressCache {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [hashtable]$Cache
    )

    $entries = foreach ($key in ($Cache.Keys | Sort-Object)) {
        $item = $Cache[$key]
        [pscustomobject]@{
            LogPath = $item.logPath
            LogOffset = [Int64]$item.logOffset
            ProcessedBytes = [UInt64]$item.processedBytes
            StartedAtUtc = $item.startedAtUtc
            LastUpdatedUtc = $item.lastUpdatedUtc
            ParsedLines = [Int64]$item.parsedLines
        }
    }

    $payload = [pscustomobject]@{
        entries = $entries
    }

    $json = $payload | ConvertTo-Json -Depth 4
    Set-Content -LiteralPath $Path -Value $json
}

function Get-DirectorySizeBytes {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        throw "Source directory not found: $Path"
    }

    $files = Get-ChildItem -LiteralPath $Path -File -Recurse -Force -ErrorAction Stop
    if (-not $files) {
        return [UInt64]0
    }

    $sum = ($files | Measure-Object -Property Length -Sum).Sum
    if ($null -eq $sum) {
        return [UInt64]0
    }

    return [UInt64]$sum
}

function ConvertFrom-RobocopySizeToken {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Token
    )

    $normalized = ($Token.Trim() -replace ',', '')

    if ($normalized -match '^(?<value>[0-9]+(?:\.[0-9]+)?)\s*(?<unit>[kKmMgGtTpPeE]?)$') {
        $value = [double]$matches.value
        $multiplier = switch ($matches.unit.ToUpperInvariant()) {
            ''  { 1 }
            'K' { 1KB }
            'M' { 1MB }
            'G' { 1GB }
            'T' { 1TB }
            'P' { 1PB }
            'E' { [math]::Pow(1024, 6) }
            default { 1 }
        }

        return [UInt64][math]::Round($value * $multiplier)
    }

    throw "Could not parse robocopy size token: $Token"
}

function Get-LogSummaryInfo {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Log file not found: $Path"
    }

    $lines = Get-Content -LiteralPath $Path -Tail 250
    $startedAt = $null
    $endedAt = $null
    $summaryBytes = $null
    $bytesPerSecond = $null
    $elapsed = $null

    foreach ($line in $lines) {
        if (-not $startedAt -and $line -match 'Started\s*:\s*(.+)$') {
            $startedAt = Get-ParsedDateTime -Text $matches[1]
        }
        if (-not $endedAt -and $line -match 'Ended\s*:\s*(.+)$') {
            $endedAt = Get-ParsedDateTime -Text $matches[1]
        }
        if (-not $bytesPerSecond -and $line -match 'Speed\s*:\s*([0-9,\.]+)\s+Bytes/sec') {
            $bytesPerSecond = [double](($matches[1] -replace ',', ''))
        }
        if (-not $summaryBytes -and $line -match '^\s*Bytes\s*:\s*([0-9,]+)') {
            $summaryBytes = [UInt64](($matches[1] -replace ',', ''))
        }
        if (-not $elapsed -and $line -match '^\s*Times\s*:\s*([0-9]+):([0-9]+):([0-9]+)') {
            $elapsed = [TimeSpan]::FromHours([int]$matches[1]).Add([TimeSpan]::FromMinutes([int]$matches[2])).Add([TimeSpan]::FromSeconds([int]$matches[3]))
        }
    }

    if (-not $bytesPerSecond -and $summaryBytes -and $elapsed -and $elapsed.TotalSeconds -gt 0) {
        $bytesPerSecond = $summaryBytes / $elapsed.TotalSeconds
    }

    return [pscustomobject]@{
        StartedAt = $startedAt
        EndedAt = $endedAt
        SummaryBytes = $summaryBytes
        BytesPerSecond = $bytesPerSecond
    }
}

function Get-IncrementalLogProgress {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$ProgressCacheFile
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Log file not found: $Path"
    }

    $resolvedLogPath = [System.IO.Path]::GetFullPath($Path)
    $cacheKey = $resolvedLogPath.ToLowerInvariant()
    $cache = Get-ProgressCache -Path $ProgressCacheFile

    if ($cache.ContainsKey($cacheKey)) {
        $entry = $cache[$cacheKey]
    }
    else {
        $entry = [pscustomobject]@{
            logPath = $resolvedLogPath
            logOffset = [Int64]0
            processedBytes = [UInt64]0
            startedAtUtc = $null
            lastUpdatedUtc = $null
            parsedLines = [Int64]0
        }
    }

    $fileInfo = Get-Item -LiteralPath $resolvedLogPath
    if ($fileInfo.Length -lt $entry.logOffset) {
        $entry.logOffset = 0
        $entry.processedBytes = [UInt64]0
        $entry.startedAtUtc = $null
        $entry.parsedLines = 0
    }

    $fileStream = [System.IO.File]::Open($resolvedLogPath, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
    try {
        $fileStream.Position = $entry.logOffset
        $reader = New-Object System.IO.StreamReader($fileStream)
        try {
            $newContent = $reader.ReadToEnd()
        }
        finally {
            $reader.Dispose()
        }
        $newOffset = $fileInfo.Length
    }
    finally {
        $fileStream.Dispose()
    }

    $parsedLines = 0
    if (-not [string]::IsNullOrWhiteSpace($newContent)) {
        $lines = $newContent -split "`r?`n"
        foreach ($line in $lines) {
            if ([string]::IsNullOrWhiteSpace($line)) {
                continue
            }

            if (-not $entry.startedAtUtc -and $line -match 'Started\s*:\s*(.+)$') {
                $startedAt = Get-ParsedDateTime -Text $matches[1]
                if ($startedAt) {
                    $entry.startedAtUtc = $startedAt.ToUniversalTime().ToString('o')
                }
            }

            if ($line -match '^\s*(?<status>New File|Newer|Older|Same|Changed|Tweaked|Modified|Extra File|Extra|Lonely)\s+(?<size>[0-9][0-9,\.]*\s*[kKmMgGtTpPeE]?)\s+(?<path>([A-Za-z]:\\|\\\\).+)$') {
                $entry.processedBytes = [UInt64]($entry.processedBytes + (ConvertFrom-RobocopySizeToken -Token $matches.size))
                $parsedLines++
            }
        }
    }

    $entry.logOffset = [Int64]$newOffset
    $entry.lastUpdatedUtc = [DateTime]::UtcNow.ToString('o')
    $entry.parsedLines = [Int64]($entry.parsedLines + $parsedLines)
    $cache[$cacheKey] = $entry
    Save-ProgressCache -Path $ProgressCacheFile -Cache $cache

    $summary = Get-LogSummaryInfo -Path $resolvedLogPath
    $startedAtUtc = if ($entry.startedAtUtc) { [datetime]::Parse($entry.startedAtUtc, [System.Globalization.CultureInfo]::InvariantCulture) } else { $null }
    $startedAtLocal = if ($startedAtUtc) { $startedAtUtc.ToLocalTime() } else { $summary.StartedAt }

    $processedBytes = if ($summary.SummaryBytes) { [UInt64]$summary.SummaryBytes } else { [UInt64]$entry.processedBytes }
    $bytesPerSecond = $null
    $throughputSource = $null

    if ($summary.BytesPerSecond -and $summary.BytesPerSecond -gt 0) {
        $bytesPerSecond = [double]$summary.BytesPerSecond
        $throughputSource = "robocopy summary in $resolvedLogPath"
    }
    elseif ($startedAtLocal -and $processedBytes -gt 0) {
        $elapsedSeconds = ((Get-Date) - $startedAtLocal).TotalSeconds
        if ($elapsedSeconds -gt 0) {
            $bytesPerSecond = $processedBytes / $elapsedSeconds
            $throughputSource = "incremental log progress since $($startedAtLocal.ToString('yyyy-MM-dd HH:mm:ss'))"
        }
    }

    return [pscustomobject]@{
        LogPath = $resolvedLogPath
        ProcessedBytes = [UInt64]$processedBytes
        StartedAtLocal = $startedAtLocal
        Completed = [bool]$summary.EndedAt
        BytesPerSecond = $bytesPerSecond
        ThroughputSource = $throughputSource
        ParsedLines = [Int64]$entry.parsedLines
        LogOffset = [Int64]$entry.logOffset
    }
}

if (-not $DirectoryName -and -not $SourcePath -and -not $ListCache -and -not $ListProgressCache) {
    throw 'Provide -DirectoryName, -SourcePath, -ListCache, or -ListProgressCache.'
}

$sizeCache = Get-SizeCache -Path $CachePath

if ($ListCache) {
    $entries = foreach ($key in ($sizeCache.Keys | Sort-Object)) {
        $item = $sizeCache[$key]
        [pscustomobject]@{
            DirectoryName = $item.directoryName
            SourcePath = $item.sourcePath
            TotalBytes = [UInt64]$item.totalBytes
            TotalSize = ConvertTo-ReadableSize -Bytes $item.totalBytes
            ScannedAtUtc = $item.scannedAtUtc
        }
    }

    if ($AsJson) {
        $entries | ConvertTo-Json -Depth 3
    }
    else {
        $entries | Format-Table -AutoSize
    }

    return
}

if ($ListProgressCache) {
    $progressCache = Get-ProgressCache -Path $ProgressCachePath
    $entries = foreach ($key in ($progressCache.Keys | Sort-Object)) {
        $item = $progressCache[$key]
        [pscustomobject]@{
            LogPath = $item.logPath
            LogOffset = [Int64]$item.logOffset
            ProcessedBytes = [UInt64]$item.processedBytes
            ProcessedSize = ConvertTo-ReadableSize -Bytes $item.processedBytes
            StartedAtUtc = $item.startedAtUtc
            LastUpdatedUtc = $item.lastUpdatedUtc
            ParsedLines = [Int64]$item.parsedLines
        }
    }

    if ($AsJson) {
        $entries | ConvertTo-Json -Depth 3
    }
    else {
        $entries | Format-Table -AutoSize
    }

    return
}

if (-not $SourcePath) {
    $SourcePath = Join-Path 'E:\' $DirectoryName
}

$resolvedSourcePath = [System.IO.Path]::GetFullPath($SourcePath)
if (-not $DirectoryName) {
    $DirectoryName = Split-Path -Path $resolvedSourcePath -Leaf
}

$cacheKey = $resolvedSourcePath.ToLowerInvariant()
$sizeSource = $null

if ($PSBoundParameters.ContainsKey('TotalBytes')) {
    $resolvedTotalBytes = [UInt64]$TotalBytes
    $sizeSource = 'explicit -TotalBytes value'
}
elseif ($RefreshSizeCache) {
    Write-Host "Refreshing cached size for $resolvedSourcePath ..."
    $resolvedTotalBytes = Get-DirectorySizeBytes -Path $resolvedSourcePath
    $sizeCache[$cacheKey] = [pscustomobject]@{
        directoryName = $DirectoryName
        sourcePath = $resolvedSourcePath
        totalBytes = [UInt64]$resolvedTotalBytes
        scannedAtUtc = [DateTime]::UtcNow.ToString('o')
    }
    Save-SizeCache -Path $CachePath -Cache $sizeCache
    $sizeSource = "fresh recursive scan saved to $CachePath"
}
elseif ($sizeCache.ContainsKey($cacheKey)) {
    $resolvedTotalBytes = [UInt64]$sizeCache[$cacheKey].totalBytes
    $sizeSource = "cached size from $CachePath"
}
else {
    throw "No cached size found for $resolvedSourcePath. Run once with -RefreshSizeCache, or pass -TotalBytes to avoid a scan."
}

$doneBytes = [UInt64]0
$progressSource = 'no live progress source'
$bytesPerSecond = $null
$throughputSource = $null
$runStartedAtLocal = $null

if ($LogPath) {
    $progressInfo = Get-IncrementalLogProgress -Path $LogPath -ProgressCacheFile $ProgressCachePath
    if ([double]$progressInfo.ProcessedBytes -gt [double]$resolvedTotalBytes) {
        $doneBytes = [UInt64]$resolvedTotalBytes
    }
    else {
        $doneBytes = [UInt64]$progressInfo.ProcessedBytes
    }
    $progressSource = "incremental robocopy log state in $($progressInfo.LogPath)"
    $runStartedAtLocal = $progressInfo.StartedAtLocal

    if ($progressInfo.BytesPerSecond -and $progressInfo.BytesPerSecond -gt 0) {
        $bytesPerSecond = [double]$progressInfo.BytesPerSecond
        $throughputSource = $progressInfo.ThroughputSource
    }
}

if ($ThroughputMBps -gt 0) {
    $bytesPerSecond = $ThroughputMBps * 1MB
    $throughputSource = 'explicit -ThroughputMBps value'
}

if (-not $bytesPerSecond -or $bytesPerSecond -le 0) {
    throw 'Provide -LogPath for live log-based ETA or -ThroughputMBps for a manual throughput estimate.'
}

$remainingBytesDouble = [double]$resolvedTotalBytes - [double]$doneBytes
if ($remainingBytesDouble -lt 0) {
    $remainingBytes = [UInt64]0
}
else {
    $remainingBytes = [UInt64]$remainingBytesDouble
}
$eta = [TimeSpan]::FromSeconds($remainingBytes / $bytesPerSecond)
$expectedCompletion = (Get-Date).Add($eta)
$throughputMiBps = $bytesPerSecond / 1MB
$progressPercent = if ($resolvedTotalBytes -gt 0) { [Math]::Round(($doneBytes / $resolvedTotalBytes) * 100, 2) } else { 0 }

$result = [pscustomobject]@{
    DirectoryName = $DirectoryName
    SourcePath = $resolvedSourcePath
    TotalBytes = [UInt64]$resolvedTotalBytes
    TotalSize = ConvertTo-ReadableSize -Bytes $resolvedTotalBytes
    SizeSource = $sizeSource
    DoneBytes = [UInt64]$doneBytes
    DoneSize = ConvertTo-ReadableSize -Bytes $doneBytes
    RemainingBytes = [UInt64]$remainingBytes
    RemainingSize = ConvertTo-ReadableSize -Bytes $remainingBytes
    ProgressPercent = $progressPercent
    ProgressSource = $progressSource
    RunStartedLocal = if ($runStartedAtLocal) { $runStartedAtLocal.ToString('yyyy-MM-dd HH:mm:ss') } else { $null }
    ThroughputBytesPerSecond = [Math]::Round($bytesPerSecond, 2)
    ThroughputMiBPerSecond = [Math]::Round($throughputMiBps, 2)
    ThroughputSource = $throughputSource
    RemainingDuration = ConvertTo-ReadableDuration -Duration $eta
    ExpectedCompletionLocal = $expectedCompletion.ToString('yyyy-MM-dd HH:mm:ss')
}

if ($AsJson) {
    $result | ConvertTo-Json -Depth 4
}
else {
    Write-Host ''
    Write-Host ('Directory             : {0}' -f $result.DirectoryName)
    Write-Host ('Source                : {0}' -f $result.SourcePath)
    Write-Host ('Total size            : {0} ({1} bytes)' -f $result.TotalSize, $result.TotalBytes)
    Write-Host ('Processed so far      : {0} ({1} bytes)' -f $result.DoneSize, $result.DoneBytes)
    Write-Host ('Remaining             : {0} ({1} bytes)' -f $result.RemainingSize, $result.RemainingBytes)
    Write-Host ('Progress              : {0:N2}%%' -f $result.ProgressPercent)
    Write-Host ('Size source           : {0}' -f $result.SizeSource)
    Write-Host ('Progress source       : {0}' -f $result.ProgressSource)
    if ($result.RunStartedLocal) {
        Write-Host ('Run started           : {0}' -f $result.RunStartedLocal)
    }
    Write-Host ('Throughput            : {0:N2} MiB/s' -f $result.ThroughputMiBPerSecond)
    Write-Host ('Throughput source     : {0}' -f $result.ThroughputSource)
    Write-Host ('Time remaining        : {0}' -f $result.RemainingDuration)
    Write-Host ('Expected completion   : {0}' -f $result.ExpectedCompletionLocal)
    Write-Host ''
    Write-Host 'Tip: for repeated live checks, reuse -LogPath so the script reads only newly appended log content.'
}