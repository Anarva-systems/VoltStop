param(
    [Parameter(Mandatory = $true)]
    [string] $ApiBaseUrl,

    [switch] $RequirePaymentCheckout,
    [switch] $RequireWebhook
)

$ErrorActionPreference = 'Stop'

try {
    $uri = [Uri] $ApiBaseUrl.TrimEnd('/')
} catch {
    throw 'ApiBaseUrl must be an absolute HTTPS URL ending in /api/v1.'
}

if ($uri.Scheme -ne 'https') {
    throw 'Staging readiness checks require HTTPS.'
}
if ($uri.Host -eq 'volt-stop.vercel.app') {
    throw 'Refusing to run a staging check against the production API host.'
}
if (-not $uri.AbsolutePath.TrimEnd('/').EndsWith('/api/v1')) {
    throw 'ApiBaseUrl must end in /api/v1.'
}

$base = $uri.AbsoluteUri.TrimEnd('/')
$health = Invoke-RestMethod -Uri "$base/health" -Method Get -TimeoutSec 20
if ($health.success -ne $true -or $health.data.status -ne 'healthy') {
    throw 'The API liveness endpoint did not report healthy.'
}
Write-Host 'API liveness: healthy'

$ready = Invoke-RestMethod -Uri "$base/ready" -Method Get -TimeoutSec 30
if ($ready.success -ne $true -or $ready.data.status -ne 'ready') {
    $state = $ready.data.dependencies | ConvertTo-Json -Compress
    throw "API dependencies are not ready. Dependency states: $state"
}
Write-Host 'API dependencies:'
$ready.data.dependencies | Format-List

$capabilities = $ready.data.capabilities
if ($RequirePaymentCheckout -and $capabilities.customer_payment_collection -ne 'configured') {
    throw 'Razorpay checkout is not configured for this staging API.'
}
if ($RequireWebhook -and $capabilities.payment_webhooks -ne 'configured') {
    throw 'Razorpay webhook verification is not configured for this staging API.'
}

Write-Host 'Payment capabilities:'
$capabilities | Format-List
Write-Host 'Staging readiness check passed.'
