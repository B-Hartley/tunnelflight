param(
    [Parameter(Mandatory)] [string]$Username,
    [Parameter(Mandatory)] [string]$Password,
    [string]$LogFile = "tunnelflight_api_test.log"
)

function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$timestamp`t$Message" | Out-File -FilePath $LogFile -Append
}

$headers = @{
    "User-Agent"  = "Mozilla/5.0 (Windows NT; Win64; x64)"
    "Accept"      = "application/json, text/javascript, */*; q=0.01"
    "Content-Type"= "application/json"
    "Origin"      = "https://www.tunnelflight.com"
    "Referer"     = "https://www.tunnelflight.com/"
}

$loginBody = @{
    username       = $Username
    password       = $Password
    passcode       = ""
    enable2fa      = $false
    checkTwoFactor = $true
    passcodeOption = "email"
    device_platform= "android"
} | ConvertTo-Json

try {
    Write-Log "Starting login request"
    $loginResponse = Invoke-RestMethod `
        -Uri "https://api.tunnelflight.com/api/auth/login" `
        -Method POST -Headers $headers -Body $loginBody -ErrorAction Stop
    Write-Log "Login response: $($loginResponse | ConvertTo-Json -Compress)"
    $token = $loginResponse.token
} catch {
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
    "https://api.tunnelflight.com/api/user/module-type/flyer-card",
    "https://api.tunnelflight.com/api/user/module-type/flyer-charts",
    "https://api.tunnelflight.com/api/account/logbook/tunnels",
    "https://api.tunnelflight.com/api/account/notifications/requests"
)

foreach ($endpoint in $endpoints) {
    try {
        Write-Log "Requesting ${endpoint}"
        $response = Invoke-RestMethod -Uri $endpoint -Method GET -Headers $authHeaders -ErrorAction Stop
        Write-Log "Response from ${endpoint}: $($response | ConvertTo-Json -Compress)"
    } catch {
        Write-Log "Error calling ${endpoint}: $($_.Exception.Message)"
    }
}

Write-Log "API test script finished"
