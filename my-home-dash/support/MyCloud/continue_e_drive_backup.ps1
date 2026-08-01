[CmdletBinding()]
param(
    [string]$SourceRoot = 'E:\',

    [string]$DestinationRoot = '\\wdmycloud\WD_Black\E_Drive_Backup',

    [string]$LogDirectory = "$env:USERPROFILE\Documents",

    [string]$QueueLogPath = (Join-Path $PSScriptRoot 'logs\continue_e_drive_backup_queue.log')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$excludedDirectories = @(
    '$RECYCLE.BIN',
    'System Volume Information',
    'MyProjects'
)

$preferredDirectoryOrder = @(
    'ProgramFiles',
    '.pnpm-store',
    'Backup',
    'Downloads',
    'tmp'
)

function Write-QueueLog {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $line = "[$timestamp] $Message"
    $directory = Split-Path -Path $QueueLogPath -Parent

    if (-not (Test-Path -LiteralPath $directory)) {
        New-Item -Path $directory -ItemType Directory -Force | Out-Null
    }

    Add-Content -LiteralPath $QueueLogPath -Value $line
    Write-Output $line
}

function Connect-BackupShare {
    if (Test-Path -LiteralPath $DestinationRoot) {
        return
    }

    $commands = @(
        'net use \\wdmycloud\WD_Black "" /user:admin /persistent:no',
        'net use \\192.168.86.38\WD_Black "" /user:admin /persistent:no'
    )

    foreach ($command in $commands) {
        Write-QueueLog "Authenticating NAS share with: $command"
        & cmd.exe /c $command | Out-Null
        if (Test-Path -LiteralPath $DestinationRoot) {
            Write-QueueLog 'NAS share authentication succeeded.'
            return
        }
    }

    throw "Unable to access backup destination: $DestinationRoot"
}

function Get-OrderedRemainingDirectories {
    $directories = Get-ChildItem -LiteralPath $SourceRoot -Force -Directory |
        Where-Object { $excludedDirectories -notcontains $_.Name }

    $orderLookup = @{}
    for ($index = 0; $index -lt $preferredDirectoryOrder.Count; $index++) {
        $orderLookup[$preferredDirectoryOrder[$index]] = $index
    }

    return $directories |
        Sort-Object @{ Expression = {
            if ($orderLookup.ContainsKey($_.Name)) {
                return $orderLookup[$_.Name]
            }

            return 1000
        } }, @{ Expression = { $_.Name.ToLowerInvariant() } }
}

function Invoke-RobocopyPhase {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourcePath,

        [Parameter(Mandatory = $true)]
        [string]$DestinationPath,

        [Parameter(Mandatory = $true)]
        [string]$LogPath,

        [switch]$Mirror,

        [string[]]$FileList
    )

    Connect-BackupShare

    if (-not (Test-Path -LiteralPath $DestinationRoot)) {
        throw "Backup root is unavailable: $DestinationRoot"
    }

    $arguments = @(
        $SourcePath,
        $DestinationPath
    )

    if ($Mirror) {
        $arguments += '/MIR'
    }
    elseif ($FileList -and $FileList.Count -gt 0) {
        $arguments += $FileList
    }

    $arguments += @(
        '/Z',
        '/FFT',
        '/R:2',
        '/W:5',
        '/XJ',
        '/MT:16',
        '/DCOPY:DAT',
        '/COPY:DAT',
        '/NP',
        '/TEE',
        "/LOG:$LogPath"
    )

    $displayArguments = $arguments -join ' '
    Write-QueueLog "Starting robocopy: robocopy $displayArguments"

    & robocopy.exe @arguments
    $exitCode = $LASTEXITCODE
    Write-QueueLog "Robocopy finished with exit code $exitCode for $SourcePath"

    if ($exitCode -ge 8) {
        throw "Robocopy reported a failure for $SourcePath with exit code $exitCode"
    }
}

Write-QueueLog 'Continuation run started.'
Connect-BackupShare

$remainingDirectories = Get-OrderedRemainingDirectories

foreach ($directory in $remainingDirectories) {
    $logLeaf = $directory.Name.ToLowerInvariant().Replace('.', '')
    $logPath = Join-Path $LogDirectory ("robocopy_{0}_to_wdblack2.log" -f $logLeaf)
    $destinationPath = Join-Path $DestinationRoot $directory.Name

    Invoke-RobocopyPhase -SourcePath $directory.FullName -DestinationPath $destinationPath -LogPath $logPath -Mirror
}

$rootFiles = Get-ChildItem -LiteralPath $SourceRoot -Force -File |
    Where-Object { $_.Name -notlike 'robocopy_*_to_wdblack2.log' }

if ($rootFiles) {
    $rootLogPath = Join-Path $LogDirectory 'robocopy_root_files_to_wdblack2.log'
    $fileList = $rootFiles | ForEach-Object { $_.Name }
    Invoke-RobocopyPhase -SourcePath $SourceRoot -DestinationPath $DestinationRoot -LogPath $rootLogPath -FileList $fileList
}
else {
    Write-QueueLog 'No root-level files were found to copy.'
}

Write-QueueLog 'Continuation run finished successfully.'