// ══════════════════════════════════════════════════════════════
// main.bicep — Orchestrator
// This is the "entry point" for your infrastructure deployment.
// It calls each module and wires their inputs/outputs together.
//
// Think of it like a main() function:
//   main.bicep calls → appservice.bicep, botservice.bicep, openai.bicep
//   Each module returns outputs that feed into the next module.
// ══════════════════════════════════════════════════════════════

// === TARGET SCOPE ===
// Tells Bicep this deploys to a Resource Group (not subscription-level)
targetScope = 'resourceGroup'

// === PARAMETERS ===
// These come from parameters.json OR from the pipeline command line.
// The pipeline passes them via: az deployment group create --parameters ...

@description('Azure region for all resources')
param location string = 'eastus'

@description('Base name used to derive resource names (keeps naming consistent)')
param projectName string = 'contoso'

@description('Environment suffix (dev, staging, prod)')
@allowed(['dev', 'staging', 'prod'])
param environment string = 'dev'

@description('Name of the EXISTING Azure OpenAI resource in this resource group')
param existingOpenAiName string

@secure()
@description('Azure OpenAI API key (pass from pipeline secret variable or Key Vault)')
param azureOpenAiApiKey string

@description('Azure OpenAI model deployment name')
param azureOpenAiDeploymentName string = 'gpt-4.1-mini'

@description('Bot Framework Microsoft App ID (from Entra ID app registration)')
param microsoftAppId string = ''

@secure()
@description('Bot Framework Microsoft App Password')
param microsoftAppPassword string = ''

@description('Bot Framework Tenant ID')
param microsoftAppTenantId string = ''

@description('App Service SKU')
param appServiceSku string = 'B1'

@description('Bot Service SKU')
param botServiceSku string = 'F0'

// === NAMING CONVENTION ===
// Derive consistent names from projectName + environment.
// e.g. projectName='contoso', environment='dev' → 'app-contoso-dev'
var appServiceName = 'app-${projectName}-${environment}'
var botServiceName = 'bot-${projectName}-${environment}'

// ── MODULE 1: OpenAI (existing) ─────────────────────────────
// Looks up your existing Azure OpenAI to get its endpoint URL.
module openAi 'modules/openai/openai.bicep' = {
  name: 'openai-lookup'
  params: {
    openAiName: existingOpenAiName
  }
}

// ── MODULE 2: App Service ───────────────────────────────────
// Creates the Linux App Service + Plan and configures app settings.
// Notice how openAi.outputs.openAiEndpoint flows INTO appService —
// this is how modules pass data to each other.
module appService 'modules/appservice/appservice.bicep' = {
  name: 'appservice-deploy'
  params: {
    appServiceName: appServiceName
    location: location
    skuName: appServiceSku
    azureOpenAiEndpoint: openAi.outputs.openAiEndpoint  // ← wired from OpenAI module
    azureOpenAiApiKey: azureOpenAiApiKey
    azureOpenAiDeploymentName: azureOpenAiDeploymentName
    microsoftAppId: microsoftAppId
    microsoftAppPassword: microsoftAppPassword
    microsoftAppTenantId: microsoftAppTenantId
  }
}

// ── MODULE 3: Bot Service ───────────────────────────────────
// Registers the bot and points it at the App Service's /api/messages endpoint.
module botService 'modules/botservice/botservice.bicep' = {
  name: 'botservice-deploy'
  params: {
    botName: botServiceName
    location: location
    // Build the messaging endpoint from App Service's URL
    messagingEndpoint: '${appService.outputs.appServiceUrl}/api/messages'
    microsoftAppId: microsoftAppId
    microsoftAppTenantId: microsoftAppTenantId
    skuName: botServiceSku
  }
}

// === OUTPUTS ===
// These appear in the pipeline logs after deployment — useful for debugging
output appServiceUrl string = appService.outputs.appServiceUrl
output appServiceName string = appService.outputs.appServiceName
output botServiceId string = botService.outputs.botServiceId
output openAiEndpoint string = openAi.outputs.openAiEndpoint
