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

    $loginBody = @{
        username      = $Username.ToLower()
        password      = $Password
        passcode      = ""
        enable2fa     = $false
        checkTwoFactor = $true
        passcodeOption = "email"
    } | ConvertTo-Json

    Write-Host "Logging in to Tunnelflight..."
    $loginResponse = Invoke-WebRequest -Uri "https://www.tunnelflight.com/login" -Method Post -Headers $browserHeaders -Body $loginBody -ContentType "application/json" -WebSession $session -ErrorAction Stop

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
        $headers["Authorization"] = "Bearer $token"
    }

    Write-Host "Requesting protected endpoint..."
    $checkResponse = Invoke-WebRequest -Uri "https://www.tunnelflight.com/user/module-type/flyer-card/" -Headers $headers -WebSession $session -ErrorAction Stop

    Write-Host "Check status code: $($checkResponse.StatusCode)"
    Write-Host "Check headers:\n$($checkResponse.Headers | Format-Table -AutoSize | Out-String)"
    Write-Host "Check content:\n$($checkResponse.Content)"
}
catch {
    Write-Error $_
}
finally {
    Stop-Transcript | Out-Null
}
