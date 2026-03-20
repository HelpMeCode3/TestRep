#Requires -Modules ActiveDirectory
#Requires -RunAsAdministrator

<#
.SYNOPSIS
    Finds and disables Active Directory users inactive for 60+ days.

.DESCRIPTION
    Searches AD for enabled user accounts that have not logged in for 60 days
    or more, disables those accounts, and exports a report to CSV in
    C:\temp\DisabledUsers with the current date in the filename.

.NOTES
    Intended to run as a Scheduled Task with an account that has permission
    to disable AD users.
#>

[CmdletBinding(SupportsShouldProcess)]
param (
    # Number of days of inactivity before disabling an account
    [int]$InactiveDays = 60,

    # Output folder for the CSV report
    [string]$ReportFolder = 'C:\temp\DisabledUsers',

    # OU to search (leave empty to search entire domain)
    [string]$SearchBase = ''
)

# -------------------------------------------------------------------------
# Setup
# -------------------------------------------------------------------------
$today        = Get-Date
$cutoffDate   = $today.AddDays(-$InactiveDays)
$dateStamp    = $today.ToString('yyyy-MM-dd')
$reportFile   = Join-Path -Path $ReportFolder -ChildPath "DisabledUsers_$dateStamp.csv"

# Ensure the output folder exists
if (-not (Test-Path -Path $ReportFolder)) {
    New-Item -ItemType Directory -Path $ReportFolder -Force | Out-Null
    Write-Verbose "Created report folder: $ReportFolder"
}

# -------------------------------------------------------------------------
# Query Active Directory for inactive, enabled users
# -------------------------------------------------------------------------
$adParams = @{
    Filter     = { Enabled -eq $true -and LastLogonDate -lt $cutoffDate }
    Properties = 'DisplayName', 'SamAccountName', 'LastLogonDate',
                 'EmailAddress', 'Department', 'Manager', 'DistinguishedName'
}

if ($SearchBase -ne '') {
    $adParams['SearchBase'] = $SearchBase
}

Write-Host "Searching for users inactive since $($cutoffDate.ToString('yyyy-MM-dd'))..."
$inactiveUsers = Get-ADUser @adParams | Sort-Object LastLogonDate

if (-not $inactiveUsers) {
    Write-Host "No inactive users found. No changes made."
    exit 0
}

Write-Host "$($inactiveUsers.Count) inactive user(s) found."

# -------------------------------------------------------------------------
# Disable each user and collect report data
# -------------------------------------------------------------------------
$report = foreach ($user in $inactiveUsers) {
    $disabledOn  = $today.ToString('yyyy-MM-dd HH:mm:ss')
    $disableError = $null

    if ($PSCmdlet.ShouldProcess($user.SamAccountName, "Disable AD account")) {
        try {
            Disable-ADAccount -Identity $user.DistinguishedName -ErrorAction Stop
            Write-Verbose "Disabled: $($user.SamAccountName)"
        }
        catch {
            $disableError = $_.Exception.Message
            Write-Warning "Failed to disable $($user.SamAccountName): $disableError"
        }
    }

    [PSCustomObject]@{
        DisplayName       = $user.DisplayName
        SamAccountName    = $user.SamAccountName
        EmailAddress      = $user.EmailAddress
        Department        = $user.Department
        Manager           = $user.Manager
        LastLogonDate     = if ($user.LastLogonDate) {
                                $user.LastLogonDate.ToString('yyyy-MM-dd')
                            } else { 'Never' }
        DaysSinceLogon    = if ($user.LastLogonDate) {
                                ($today - $user.LastLogonDate).Days
                            } else { 'N/A' }
        DisabledOn        = $disabledOn
        DistinguishedName = $user.DistinguishedName
        Error             = $disableError
    }
}

# -------------------------------------------------------------------------
# Export report to CSV
# -------------------------------------------------------------------------
$report | Export-Csv -Path $reportFile -NoTypeInformation -Encoding UTF8

Write-Host "Report saved to: $reportFile"
Write-Host "Done. $($report.Count) user(s) processed."
