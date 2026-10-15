param(
    [Parameter(Mandatory = $true)]
    [string] $ApiBaseUrl,

    [ValidateSet('debug', 'release')]
    [string] $BuildType = 'debug',

    [ValidateSet('development', 'production')]
    [string] $AppEnvironment = 'development',

    [string] $SupabaseUrl,
    [string] $SupabasePublishableKey
)

$ErrorActionPreference = 'Stop'
$apiUri = $null
if (-not [Uri]::TryCreate($ApiBaseUrl.Trim(), [UriKind]::Absolute, [ref] $apiUri) -or
    $apiUri.Scheme -notin @('http', 'https') -or
    $apiUri.UserInfo -or $apiUri.Query -or $apiUri.Fragment -or
    -not $apiUri.AbsolutePath.TrimEnd('/').EndsWith('/api/v1', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'ApiBaseUrl must be an absolute HTTP(S) URL ending in /api/v1.'
}

$normalizedApiBaseUrl = $apiUri.AbsoluteUri.TrimEnd('/')
$isRelease = $BuildType -eq 'release'
$isProductionBuild = $isRelease -or $AppEnvironment -eq 'production'
if ($isRelease -and $AppEnvironment -ne 'production') {
    throw 'Release APKs must use AppEnvironment=production.'
}
if ($isProductionBuild -and $apiUri.Scheme -ne 'https') {
    throw 'Production APKs require a public HTTPS API URL.'
}
if ($isProductionBuild -and (-not $SupabaseUrl -or -not $SupabasePublishableKey)) {
    throw 'Production APKs require explicit SupabaseUrl and SupabasePublishableKey values.'
}
if ($isProductionBuild -and
    ($apiUri.IsLoopback -or $apiUri.Host -match '^(\d{1,3}\.){3}\d{1,3}$' -or
     $apiUri.Host -match '(^|\.)localhost$|\.local$|:')) {
    throw 'Release APKs cannot target loopback, private-IP, or local-domain API hosts.'
}

# Probe the exact backend that will be embedded in the APK. Readiness checks
# database, Supabase Auth, and Redis; a liveness-only response is not enough.
$healthUrl = "$normalizedApiBaseUrl/health"
$readyUrl = "$normalizedApiBaseUrl/ready"
try {
    $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 12
    $ready = Invoke-RestMethod -Uri $readyUrl -TimeoutSec 12
} catch {
    throw "The configured VoltStop API did not pass its health/readiness check. No APK was built. Verify the API is deployed and reachable at $normalizedApiBaseUrl. $($_.Exception.Message)"
}
if ($health.success -ne $true -or $ready.success -ne $true -or $ready.data.status -ne 'ready') {
    throw "The configured VoltStop API is not ready. No APK was built. Readiness status: $($ready.data.status)."
}
if (-not $isRelease -and -not $apiUri.IsLoopback -and $apiUri.Host -match '^(\d{1,3}\.){3}\d{1,3}$') {
    Write-Warning 'The API URL uses an IP address. This development APK only works on networks that can route to that address; mobile data requires a public HTTPS API.'
}

$flutter = Get-Command flutter -ErrorAction SilentlyContinue
if (-not $flutter) {
    throw 'Flutter was not found on PATH. Install/configure Flutter, then run this script again.'
}

$dartDefines = @(
    "--dart-define=APP_ENV=$AppEnvironment",
    "--dart-define=API_BASE_URL=$normalizedApiBaseUrl"
)
if ($SupabaseUrl) {
    $dartDefines += "--dart-define=SUPABASE_URL=$SupabaseUrl"
}
if ($SupabasePublishableKey) {
    $dartDefines += "--dart-define=SUPABASE_PUBLISHABLE_KEY=$SupabasePublishableKey"
}

Push-Location $PSScriptRoot
try {
    & $flutter.Source build apk "--$BuildType" @dartDefines
    if ($LASTEXITCODE -ne 0) {
        throw "Flutter APK build failed with exit code $LASTEXITCODE."
    }
    $artifactPath = Join-Path $PSScriptRoot "build\app\outputs\flutter-apk\app-$BuildType.apk"
    if (-not (Test-Path -LiteralPath $artifactPath)) {
        throw "Flutter reported success but the expected APK was not found: $artifactPath"
    }
    Write-Output "APK ready: $artifactPath"
} finally {
    Pop-Location
}
