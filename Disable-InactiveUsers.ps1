#Requires -Modules ActiveDirectory
#Requires -RunAsAdministrator

<#
.SYNOPSIS
    Finds and disables Active Directory users inactive for 60+ days.

.DESCRIPTION
    Searches AD for enabled user accounts that have not logged in for 60 days
    or more — including accounts that have NEVER logged in — disables those
    accounts, and exports a dated CSV report to the specified folder.

.NOTES
    Intended to run as a Scheduled Task with an account that has permission
    to disable AD users.

.EXAMPLE
    # Dry run — see what would be disabled without making changes
    .\Disable-InactiveUsers.ps1 -WhatIf

.EXAMPLE
    # Target a specific OU and use a custom inactivity threshold
    .\Disable-InactiveUsers.ps1 -InactiveDays 90 -SearchBase 'OU=Staff,DC=contoso,DC=com'
#>

[CmdletBinding(SupportsShouldProcess)]
param (
    # Number of days of inactivity before disabling an account
    [int]$InactiveDays = 60,

    # Output folder for the CSV report
    [string]$ReportFolder = 'C:\temp\DisabledUsers',

    # OU to search (leave empty to search entire domain)
    [string]$SearchBase = '',

    # OUs to exclude — any user whose DistinguishedName contains one of these
    # strings will be skipped. Accepts partial OU paths.
    # Example: 'OU=IT,DC=contoso,DC=com','OU=ServiceAccounts,DC=contoso,DC=com'
    [string[]]$ExcludedOUs = @()
)

# -------------------------------------------------------------------------
# Setup
# -------------------------------------------------------------------------
Import-Module ActiveDirectory

$today      = Get-Date
$cutoffDate = $today.AddDays(-$InactiveDays)
$dateStamp  = $today.ToString('yyyy-MM-dd')
$reportFile = Join-Path -Path $ReportFolder -ChildPath "DisabledUsers_$dateStamp.csv"

# Ensure the output folder exists
if (-not (Test-Path -Path $ReportFolder)) {
    New-Item -ItemType Directory -Path $ReportFolder -Force | Out-Null
    Write-Verbose "Created report folder: $ReportFolder"
}

# -------------------------------------------------------------------------
# Query AD — pull all enabled users, then filter in PowerShell so that
# accounts with a NULL LastLogonDate (never logged in) are also caught.
# -------------------------------------------------------------------------
$adParams = @{
    Filter     = { Enabled -eq $true }
    Properties = 'DisplayName', 'SamAccountName', 'UserPrincipalName',
                 'LastLogonDate', 'whenCreated', 'PasswordLastSet',
                 'EmailAddress', 'Department', 'Manager', 'DistinguishedName'
}

if ($SearchBase -ne '') {
    $adParams['SearchBase'] = $SearchBase
}

Write-Host "Searching for users inactive since $($cutoffDate.ToString('yyyy-MM-dd')) (or never logged in)..."

$inactiveUsers = Get-ADUser @adParams | Where-Object {
    $dn = $_.DistinguishedName
    # Must be inactive or never logged in
    (($_.LastLogonDate -eq $null) -or ($_.LastLogonDate -lt $cutoffDate)) -and
    # Must not belong to any excluded OU
    (-not ($ExcludedOUs | Where-Object { $dn -like "*$_*" }))
} | Sort-Object LastLogonDate

if (-not $inactiveUsers) {
    Write-Host "No inactive users found. No changes made."
    exit 0
}

Write-Host "$($inactiveUsers.Count) inactive user(s) found."

# -------------------------------------------------------------------------
# Disable each user and collect report data
# -------------------------------------------------------------------------
$report = foreach ($user in $inactiveUsers) {
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
        Name              = $user.Name
        SamAccountName    = $user.SamAccountName
        UserPrincipalName = $user.UserPrincipalName
        DisplayName       = $user.DisplayName
        EmailAddress      = $user.EmailAddress
        Department        = $user.Department
        Manager           = $user.Manager
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
        DisabledOn        = $today.ToString('yyyy-MM-dd HH:mm:ss')
        DistinguishedName = $user.DistinguishedName
        Error             = $disableError
    }
}

# -------------------------------------------------------------------------
# Export CSV report
# -------------------------------------------------------------------------
$report | Export-Csv -Path $reportFile -NoTypeInformation -Encoding UTF8

Write-Host "Report saved to: $reportFile"
Write-Host ""

# -------------------------------------------------------------------------
# Console summary (mirrors your original Format-Table output)
# -------------------------------------------------------------------------
$report |
    Select-Object Name, SamAccountName, UserPrincipalName, LastLogonDate, DaysSinceLogon, DisabledOn |
    Format-Table -AutoSize

Write-Host "Done. $($report.Count) user(s) disabled."
