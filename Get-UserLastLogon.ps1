#Requires -Modules ActiveDirectory

<#
.SYNOPSIS
    Reports the last logon date for all Active Directory users.

.DESCRIPTION
    Queries AD for all user accounts (enabled and disabled) and exports a
    dated CSV report showing when each user last logged in. No changes are
    made to any accounts.

.NOTES
    Read-only — safe to run without elevated permissions as long as the
    account has read access to AD.

.EXAMPLE
    # Report all users
    .\Get-UserLastLogon.ps1

.EXAMPLE
    # Only enabled accounts, target a specific OU
    .\Get-UserLastLogon.ps1 -EnabledOnly -SearchBase 'OU=Staff,DC=contoso,DC=com'

.EXAMPLE
    # Show users who haven't logged in for 30+ days
    .\Get-UserLastLogon.ps1 -InactiveDays 30
#>

param (
    # Only include enabled accounts
    [switch]$EnabledOnly,

    # Only return users inactive for this many days (0 = return everyone)
    [int]$InactiveDays = 0,

    # Output folder for the CSV report
    [string]$ReportFolder = 'C:\temp\UserLogonReport',

    # OU to search (leave empty to search entire domain)
    [string]$SearchBase = ''
)

# -------------------------------------------------------------------------
# Setup
# -------------------------------------------------------------------------
Import-Module ActiveDirectory

$today     = Get-Date
$dateStamp = $today.ToString('yyyy-MM-dd')
$reportFile = Join-Path -Path $ReportFolder -ChildPath "UserLastLogon_$dateStamp.csv"

if (-not (Test-Path -Path $ReportFolder)) {
    New-Item -ItemType Directory -Path $ReportFolder -Force | Out-Null
}

# -------------------------------------------------------------------------
# Query AD
# -------------------------------------------------------------------------
$adParams = @{
    Filter     = '*'
    Properties = 'DisplayName', 'SamAccountName', 'UserPrincipalName',
                 'LastLogonDate', 'whenCreated', 'PasswordLastSet',
                 'EmailAddress', 'Department', 'Manager',
                 'DistinguishedName', 'Enabled'
}

if ($SearchBase -ne '') {
    $adParams['SearchBase'] = $SearchBase
}

Write-Host "Querying Active Directory..."

$users = Get-ADUser @adParams

if ($EnabledOnly) {
    $users = $users | Where-Object { $_.Enabled -eq $true }
}

if ($InactiveDays -gt 0) {
    $cutoff = $today.AddDays(-$InactiveDays)
    $users = $users | Where-Object {
        ($_.LastLogonDate -eq $null) -or ($_.LastLogonDate -lt $cutoff)
    }
}

$users = $users | Sort-Object LastLogonDate

Write-Host "$($users.Count) user(s) found."

# -------------------------------------------------------------------------
# Build report
# -------------------------------------------------------------------------
$report = foreach ($user in $users) {
    [PSCustomObject]@{
        Name              = $user.Name
        SamAccountName    = $user.SamAccountName
        UserPrincipalName = $user.UserPrincipalName
        DisplayName       = $user.DisplayName
        EmailAddress      = $user.EmailAddress
        Department        = $user.Department
        Manager           = $user.Manager
        Enabled           = $user.Enabled
        LastLogonDate     = if ($user.LastLogonDate) {
                                $user.LastLogonDate.ToString('yyyy-MM-dd')
                            } else { 'Never' }
        DaysSinceLogon    = if ($user.LastLogonDate) {
                                ($today - $user.LastLogonDate).Days
                            } else { 'N/A' }
        whenCreated       = $user.whenCreated.ToString('yyyy-MM-dd')
        PasswordLastSet   = if ($user.PasswordLastSet) {
                                $user.PasswordLastSet.ToString('yyyy-MM-dd')
                            } else { 'Never' }
        DistinguishedName = $user.DistinguishedName
    }
}

# -------------------------------------------------------------------------
# Export CSV
# -------------------------------------------------------------------------
$report | Export-Csv -Path $reportFile -NoTypeInformation -Encoding UTF8

Write-Host "Report saved to: $reportFile"
Write-Host ""

# -------------------------------------------------------------------------
# Console summary
# -------------------------------------------------------------------------
$report |
    Select-Object Name, SamAccountName, Enabled, LastLogonDate, DaysSinceLogon |
    Format-Table -AutoSize

Write-Host "Done. $($report.Count) user(s) in report."
