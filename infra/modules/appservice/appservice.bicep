// ──────────────────────────────────────────────────────────────
// Module: App Service (Linux + Python 3.11)
// Purpose: Hosts the chat_agent Python application
// ──────────────────────────────────────────────────────────────

// === PARAMETERS ===
// These are inputs the parent (main.bicep) passes into this module.
// Think of them like function arguments.

@description('Name of the App Service (must be globally unique — it becomes <name>.azurewebsites.net)')
param appServiceName string

@description('Azure region to deploy into')
param location string

@description('SKU for the App Service Plan (B1=Basic, S1=Standard, P1v3=Premium)')
@allowed(['B1', 'B2', 'S1', 'S2', 'P1v3'])
param skuName string = 'B1'

@description('Azure OpenAI endpoint URL (passed as app setting)')
param azureOpenAiEndpoint string

@description('Azure OpenAI API key (passed as app setting)')
@secure()  // <-- This tells Bicep to treat this as a secret (won't show in logs)
param azureOpenAiApiKey string

@description('Azure OpenAI deployment/model name')
param azureOpenAiDeploymentName string = 'gpt-4.1-mini'

@description('Bot Framework App ID')
param microsoftAppId string = ''

@secure()
@description('Bot Framework App Password')
param microsoftAppPassword string = ''

@description('Bot Framework Tenant ID')
param microsoftAppTenantId string = ''

// === APP SERVICE PLAN ===
// This is the "server" that hosts your app. On Linux, you MUST set
// reserved=true and kind='linux'. The SKU controls cost + performance.
resource appServicePlan 'Microsoft.Web/serverfarms@2022-09-01' = {
  name: '${appServiceName}-plan'
  location: location
  kind: 'linux'           // <-- Tells Azure this is a Linux plan
  sku: {
    name: skuName         // e.g. 'B1' = ~$13/month
  }
  properties: {
    reserved: true        // <-- REQUIRED for Linux. Without this, you get Windows.
  }
}

// === APP SERVICE (Web App) ===
// This is your actual web application. It runs on the plan above.
resource appService 'Microsoft.Web/sites@2022-09-01' = {
  name: appServiceName
  location: location
  kind: 'app,linux'       // <-- 'app,linux' for a Linux web app
  properties: {
    serverFarmId: appServicePlan.id   // Links to the plan above
    httpsOnly: true                    // Force HTTPS (security best practice)
    siteConfig: {
      // Python 3.11 runtime on Linux
      linuxFxVersion: 'PYTHON|3.11'

      // Startup command — tells App Service how to run your aiohttp app
      // Without this, Azure guesses (usually gunicorn) and your app won't start
      appCommandLine: 'python main.py'

      // Always-on keeps the app warm (prevents cold starts on idle)
      alwaysOn: true
    }
  }
}

// === APP SETTINGS ===
// Separated from the site resource so they're easier to manage.
// These become environment variables your Python code reads via os.environ
// or pydantic-settings (your Settings class).
resource appSettings 'Microsoft.Web/sites/config@2022-09-01' = {
  parent: appService
  name: 'appsettings'
  properties: {
    // Azure OpenAI credentials — your Settings class reads these
    AZURE_OPENAI_ENDPOINT: azureOpenAiEndpoint
    AZURE_OPENAI_API_KEY: azureOpenAiApiKey
    AZURE_OPENAI_DEPLOYMENT_NAME: azureOpenAiDeploymentName

    // Bot Framework credentials
    MICROSOFT_APP_ID: microsoftAppId
    MICROSOFT_APP_PASSWORD: microsoftAppPassword
    MICROSOFT_APP_TENANT_ID: microsoftAppTenantId

    // Tell App Service to run from a zip package (faster deploys)
    WEBSITE_RUN_FROM_PACKAGE: '1'

    // Python-specific: sets the startup file
    SCM_DO_BUILD_DURING_DEPLOYMENT: 'true'
  }
}

// === OUTPUTS ===
// These values get passed back to main.bicep (like return values)
output appServiceUrl string = 'https://${appService.properties.defaultHostName}'
output appServiceName string = appService.name
output appServiceResourceId string = appService.id
