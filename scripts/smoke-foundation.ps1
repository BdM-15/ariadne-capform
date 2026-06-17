# Foundation E2E smoke — requires Thread API running (python app.py) + Postgres.
# Path: health → intel signal opp → packet edit → review approve → trusted verify
param(
    [string]$BaseUrl = "http://127.0.0.1:9622"
)

$ErrorActionPreference = "Stop"
$tag = [guid]::NewGuid().ToString("N").Substring(0, 8)

function Invoke-ThreadJson {
    param(
        [string]$Method,
        [string]$Uri,
        [object]$Body = $null
    )
    $params = @{
        Uri             = $Uri
        Method          = $Method
        UseBasicParsing = $true
        TimeoutSec      = 60
    }
    if ($null -ne $Body) {
        $params.ContentType = "application/json"
        $params.Body = ($Body | ConvertTo-Json -Depth 6)
    }
    $response = Invoke-WebRequest @params
    return $response.Content | ConvertFrom-Json
}

Write-Host "[smoke] Health $BaseUrl/api/health"
$health = Invoke-ThreadJson GET "$BaseUrl/api/health"
if (-not $health.postgres_ready) {
    throw "Postgres not ready. Start docker postgres and run migrations."
}

Write-Host "[smoke] Create opportunity from intel signal"
$opp = Invoke-ThreadJson POST "$BaseUrl/api/opportunities" @{
    name         = "Foundation Smoke $tag"
    award_key    = "SMOKE-$tag"
    naics_code   = "561210"
    entry_reason = "intel_signal"
}
$oppId = $opp.id

Write-Host "[smoke] Packet edit (candidate)"
$patched = Invoke-ThreadJson PATCH "$BaseUrl/api/opportunities/$oppId/packet/opportunity_name" @{
    value = "Smoke pursuit $tag"
}
if ($patched.trust_level -ne "candidate") {
    throw "Expected candidate trust_level, got $($patched.trust_level)"
}

Write-Host "[smoke] Approve pending review"
$answerId = $patched.id
if (-not $answerId) {
    throw "PATCH response missing answer id"
}
$pending = Invoke-ThreadJson GET "$BaseUrl/api/review/pending"
$review = @($pending | Where-Object {
        $_.entity_type -eq "packet_field_answer" -and $_.entity_id -eq $answerId
    } | Select-Object -First 1)
if (-not $review) {
    throw "No pending review for answer $answerId"
}
$approved = Invoke-ThreadJson POST "$BaseUrl/api/review/$($review.id)/approve" @{}
if ($approved.review_state -ne "accepted") {
    throw "Review not accepted: $($approved.review_state)"
}

Write-Host "[smoke] Verify trusted packet field"
$packet = Invoke-ThreadJson GET "$BaseUrl/api/opportunities/$oppId/packet"
$field = $packet.fields | Where-Object { $_.field_key -eq "opportunity_name" } | Select-Object -First 1
if ($field.trust_level -ne "trusted" -or $field.value -ne "Smoke pursuit $tag") {
    throw "Packet field not promoted to trusted"
}

Write-Host "[smoke] Foundation path passed (opp $oppId)"