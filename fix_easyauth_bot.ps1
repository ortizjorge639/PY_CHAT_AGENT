<#
.SYNOPSIS
    Excludes /api/messages from Easy Auth so Azure Bot Service can reach the bot.

.DESCRIPTION
    When Easy Auth (App Service Authentication) is enabled, it blocks ALL
    unauthenticated requests — including the server-to-server calls from
    Azure Bot Service to /api/messages. This script adds /api/messages to
    the Easy Auth excluded paths, letting Bot Framework handle its own JWT
    authentication on that endpoint.

.PARAMETER SubscriptionId
    Azure subscription ID.

.PARAMETER ResourceGroup
    Resource group containing the App Service.

.PARAMETER AppServiceName
    Name of the App Service (e.g. contoso-data-bot-app).

.EXAMPLE
    .\fix_easyauth_bot.ps1 -SubscriptionId "a85b2387-..." -ResourceGroup "rg-contoso" -AppServiceName "contoso-data-bot-app"
#>

param(
    [Parameter(Mandatory)] [string] $SubscriptionId,
    [Parameter(Mandatory)] [string] $ResourceGroup,
    [Parameter(Mandatory)] [string] $AppServiceName
)

$ErrorActionPreference = "Stop"

$url = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Web/sites/$AppServiceName/config/authsettingsV2?api-version=2022-09-01"

# ── Step 1: Check current state ─────────────────────────
Write-Host "`n=== Checking current Easy Auth config ===" -ForegroundColor Cyan
$current = az rest --method get --url $url --query "properties.globalValidation.excludedPaths" -o json 2>$null | ConvertFrom-Json

if ($current -contains "/api/messages") {
    Write-Host "/api/messages is already excluded. Nothing to do." -ForegroundColor Green
    exit 0
}

Write-Host "Current excludedPaths: $($current | ConvertTo-Json -Compress)" -ForegroundColor Yellow
Write-Host "/api/messages is NOT excluded — fixing now..." -ForegroundColor Yellow

# ── Step 2: Build the JSON body ─────────────────────────
$body = @{
    properties = @{
        globalValidation = @{
            excludedPaths               = @("/api/messages")
            requireAuthentication       = $true
            unauthenticatedClientAction = "RedirectToLoginPage"
            redirectToProvider          = "azureactivedirectory"
        }
        platform = @{ enabled = $true }
    }
} | ConvertTo-Json -Depth 5 -Compress

$tempFile = Join-Path $env:TEMP "easyauth_body.json"
$body | Out-File -Encoding utf8 $tempFile

# ── Step 3: Apply the change ────────────────────────────
Write-Host "`n=== Applying excluded paths ===" -ForegroundColor Cyan
az rest --method put --url $url --body "@$tempFile" -o none
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to apply. Check your Azure CLI login and permissions." -ForegroundColor Red
    exit 1
}

# ── Step 4: Verify ──────────────────────────────────────
Write-Host "`n=== Verifying ===" -ForegroundColor Cyan
$updated = az rest --method get --url $url `
    --query "properties.{excludedPaths:globalValidation.excludedPaths, clientId:identityProviders.azureActiveDirectory.registration.clientId, tokenStore:login.tokenStore.enabled}" `
    -o json | ConvertFrom-Json

Write-Host "excludedPaths : $($updated.excludedPaths -join ', ')"
Write-Host "clientId      : $($updated.clientId)"
Write-Host "tokenStore    : $($updated.tokenStore)"

if ($updated.excludedPaths -contains "/api/messages") {
    Write-Host "`nDone! /api/messages is now excluded from Easy Auth." -ForegroundColor Green
    Write-Host "Go test: Bot resource -> Test in Web Chat" -ForegroundColor Green
} else {
    Write-Host "`nWARNING: excludedPaths does not contain /api/messages. Check manually." -ForegroundColor Red
}

# Clean up temp file
Remove-Item $tempFile -ErrorAction SilentlyContinue
