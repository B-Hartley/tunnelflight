<##
.SYNOPSIS
    Exercises key Tunnelflight API endpoints and logs results.

.PARAMETER Username
    Tunnelflight username.

.PARAMETER Password
    Tunnelflight password.

.PARAMETER LogFile
    Destination file for request/response logs.
#>

param(
    [Parameter(Mandatory)][string]$Username,
    [Parameter(Mandatory)][string]$Password,
    [string]$LogFile = "tunnelflight_api_test.log"
)

function Write-Log {
    param([string]$Message)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts`t$Message" | Out-File -FilePath $LogFile -Append
}

$baseUri = "https://api.tunnelflight.com"
$headers = @{
    "User-Agent"  = "Mozilla/5.0 (Windows NT; Win64; x64)"
    "Accept"      = "application/json, text/javascript, */*; q=0.01"
    "Content-Type"= "application/json"
    "Origin"      = "https://www.tunnelflight.com"
    "Referer"     = "https://www.tunnelflight.com/"
}

$loginBody = @{
    username        = $Username
    password        = $Password
    passcode        = ""
    enable2fa       = $false
    checkTwoFactor  = $true
    passcodeOption  = "email"
    device_platform = "android"
} | ConvertTo-Json

try {
    Write-Log "Starting login request"
    $loginResponse = Invoke-RestMethod `
        -Uri "$baseUri/api/auth/login" `
        -Method POST -Headers $headers -Body $loginBody -ErrorAction Stop
    Write-Log "Login response: $($loginResponse | ConvertTo-Json -Compress)"
    $token    = $loginResponse.token
    $memberId = $loginResponse.member_id
}
catch {
    Write-Log "Login error: $($_.Exception.Message)"
    return
}

if (-not $token) {
    Write-Log "No token received. Aborting further tests."
    return
}

$authHeaders = $headers.Clone()
$authHeaders["token"] = $token

$endpoints = @(
    @{ Url = "$baseUri/api/account/notifications/requests"; Description = "Notifications" },
    @{ Url = "$baseUri/api/account/profile/user";         Description = "Profile" },
    @{ Url = "$baseUri/api/public/skills/";               Description = "Public skills" },
    @{ Url = "$baseUri/api/account/dashboard/flyer-skills-levels/$memberId"; Description = "Flyer skill levels" }
)

foreach ($ep in $endpoints) {
    try {
        Write-Log "Requesting $($ep.Description) ($($ep.Url))"
        $resp = Invoke-RestMethod -Uri $ep.Url -Method GET -Headers $authHeaders -ErrorAction Stop
        Write-Log "Response: $($resp | ConvertTo-Json -Compress)"
    }
    catch {
        Write-Log "Error calling $($ep.Url): $($_.Exception.Message)"
    }
}

Write-Log "API test script finished"
