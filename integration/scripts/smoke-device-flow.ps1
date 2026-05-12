# Device Gateway smoke — requires backend running (Lite Mode recommended).
# Usage: from repo root or integration/: .\scripts\smoke-device-flow.ps1 [-BaseUrl ...]
param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$UserId = "user_001",
    [string]$DeviceId = "smoke-pc-001"
)

$ErrorActionPreference = "Stop"
$requestId = [guid]::NewGuid().ToString()
Write-Host "=== smoke-device-flow x-request-id=$requestId user_id=$UserId device_id=$DeviceId ==="

function Invoke-JsonPost {
    param([string]$Uri, [object]$Body)
    $json = $Body | ConvertTo-Json -Depth 8 -Compress
    return Invoke-RestMethod -Uri $Uri -Method Post -ContentType "application/json; charset=utf-8" `
        -Headers @{ "X-Request-Id" = $requestId } -Body ([System.Text.Encoding]::UTF8.GetBytes($json))
}

function Invoke-JsonGet {
    param([string]$Uri)
    return Invoke-RestMethod -Uri $Uri -Method Get -Headers @{ "X-Request-Id" = $requestId }
}

# 1) health
$health = Invoke-JsonGet -Uri "$BaseUrl/health"
Write-Host "[1] health OK"

# 2) register
$reg = Invoke-JsonPost -Uri "$BaseUrl/device/register" -Body @{
    device_id  = $DeviceId
    user_id    = $UserId
    device_type = "pc"
    device_name = "smoke client"
    platform   = "app"
    capabilities = @("ping", "show_notification", "open_url", "get_device_status")
}
if (-not $reg.device_token) { throw "register missing device_token" }
$token = $reg.device_token
Write-Host "[2] register OK device_token=(redacted)"

# 3) heartbeat
Invoke-JsonPost -Uri "$BaseUrl/device/heartbeat" -Body @{
    device_id     = $DeviceId
    device_token  = $token
} | Out-Null
Write-Host "[3] heartbeat OK"

# 4) send ping
$send = Invoke-JsonPost -Uri "$BaseUrl/device/send_command" -Body @{
    user_id   = $UserId
    device_id = $DeviceId
    command   = "ping"
    payload   = @{}
}
if (-not $send.success) { throw "send_command failed: $($send | ConvertTo-Json -Compress)" }
$commandId = $send.command.command_id
if (-not $commandId) { throw "send_command missing command_id" }
Write-Host "[4] send_command OK command_id=$commandId"

# 5) claim_next
$claim = Invoke-JsonPost -Uri "$BaseUrl/device/commands/claim_next" -Body @{
    device_id    = $DeviceId
    device_token = $token
}
if (-not $claim.command) {
    Start-Sleep -Seconds 1
    $claim = Invoke-JsonPost -Uri "$BaseUrl/device/commands/claim_next" -Body @{
        device_id    = $DeviceId
        device_token = $token
    }
}
if (-not $claim.command) { throw "claim_next returned no command (check pc-client not stealing queue or retry)" }
$claimedId = $claim.command.command_id
Write-Host "[5] claim_next OK command_id=$claimedId"

# 6) mark_running
Invoke-JsonPost -Uri "$BaseUrl/device/commands/$claimedId/mark_running" -Body @{
    device_id    = $DeviceId
    device_token = $token
} | Out-Null
Write-Host "[6] mark_running OK"

# 7) command_result
Invoke-JsonPost -Uri "$BaseUrl/device/command_result" -Body @{
    command_id   = $claimedId
    device_id    = $DeviceId
    device_token = $token
    status       = "succeeded"
    result       = @{ pong = $true }
} | Out-Null
Write-Host "[7] command_result OK"

# 8) audit
$audit = Invoke-JsonGet -Uri "$BaseUrl/device/audit?user_id=$UserId"
$count = $audit.count
Write-Host "[8] audit OK count=$count"
Write-Host "=== smoke-device-flow PASSED ==="
