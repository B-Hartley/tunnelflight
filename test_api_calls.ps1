param(
    [string]$Username,
    [string]$Password,
    [string]$LogFile = "tunnelflight_api_test.log"
)

function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$timestamp`t$Message" | Out-File -FilePath $LogFile -Append
}

$headers = @{
    "User-Agent" = "Mozilla/5.0 (Windows NT; Win64; x64)"
    "Content-Type" = "application/json"
}

try {
    Write-Log "Starting login request"
    $loginBody = @{
        username = $Username.ToLower()
        password = $Password
        passcode = ""
        enable2fa = $false
        checkTwoFactor = $true
        passcodeOption = "email"
    } | ConvertTo-Json
    $loginResponse = Invoke-RestMethod -Uri "https://www.tunnelflight.com/login" -Method Post -Headers $headers -Body $loginBody
    Write-Log "Login response: $($loginResponse | ConvertTo-Json -Compress)"
    $token = $loginResponse.token
} catch {
    Write-Log "Login error: $_"
    return
}

if (-not $token) {
    Write-Log "No token received. Aborting further tests."
    return
}

$authHeaders = $headers.Clone()
$authHeaders["Authorization"] = "Bearer $token"

$endpoints = @(
    "https://www.tunnelflight.com/user/module-type/flyer-card/",
    "https://www.tunnelflight.com/user/module-type/flyer-charts/",
    "https://www.tunnelflight.com/account/logbook/tunnels/"
)

foreach ($endpoint in $endpoints) {
    try {
        Write-Log "Requesting $endpoint"
        $response = Invoke-RestMethod -Uri $endpoint -Method Get -Headers $authHeaders
        Write-Log "Response from $endpoint: $($response | ConvertTo-Json -Compress)"
    } catch {
        Write-Log "Error calling $endpoint: $_"
    }
}

Write-Log "API test script finished"
