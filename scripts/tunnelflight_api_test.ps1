param(
    [Parameter(Mandatory=$true)]
    [string]$Username,
    [Parameter(Mandatory=$true)]
    [string]$Password,
    [string]$LogFile = "tunnelflight_api_log.txt"
)

Start-Transcript -Path $LogFile -Append

try {
    $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession

    $browserHeaders = @{
        "User-Agent" = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    $apiBase = "https://api.tunnelflight.com/api"

    $loginBody = @{
        username       = $Username
        password       = $Password
        passcode       = ""
        enable2fa      = $false
        checkTwoFactor = $true
        passcodeOption = "email"
        device_platform = "web"
    } | ConvertTo-Json

    Write-Host "Logging in to Tunnelflight API..."
    $loginResponse = Invoke-WebRequest -UseBasicParsing -Uri "$apiBase/auth/login" -Method Post -Headers $browserHeaders -Body $loginBody -ContentType "application/json" -WebSession $session -ErrorAction Stop

    Write-Host "Login status code: $($loginResponse.StatusCode)"
    Write-Host "Login headers:\n$($loginResponse.Headers | Format-Table -AutoSize | Out-String)"
    Write-Host "Login content:\n$($loginResponse.Content)"

    $token = $null
    if ($loginResponse.Headers["Content-Type"] -match "application/json") {
        try {
            $json = $loginResponse.Content | ConvertFrom-Json
            $token = $json.token
            Write-Host "Token: $token"
        }
        catch {
            Write-Warning "Failed to parse login response as JSON: $_"
        }
    } else {
        Write-Warning "Login response is not JSON."
    }

    $headers = $browserHeaders.Clone()
    if ($token) {
        $headers["token"] = $token
    }

    Write-Host "Requesting profile endpoint..."
    $profileResponse = Invoke-WebRequest -UseBasicParsing -Uri "$apiBase/account/profile/user" -Headers $headers -WebSession $session -ErrorAction Stop
    Write-Host "Profile status code: $($profileResponse.StatusCode)"
    Write-Host "Profile headers:\n$($profileResponse.Headers | Format-Table -AutoSize | Out-String)"
    Write-Host "Profile content:\n$($profileResponse.Content)"

    Write-Host "Requesting certificate list endpoint..."
    $certResponse = Invoke-WebRequest -UseBasicParsing -Uri "$apiBase/account/profile/certificate-list" -Headers $headers -WebSession $session -ErrorAction Stop
    Write-Host "Cert status code: $($certResponse.StatusCode)"
    Write-Host "Cert headers:\n$($certResponse.Headers | Format-Table -AutoSize | Out-String)"
    Write-Host "Cert content:\n$($certResponse.Content)"
}
catch {
    Write-Error $_
}
finally {
    Stop-Transcript | Out-Null
}
