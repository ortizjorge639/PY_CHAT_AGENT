// ──────────────────────────────────────────────────────────────
// Module: Azure Bot Service
// Purpose: Registers a bot with the Bot Framework so it can
//          communicate via Teams, Web Chat, etc.
// ──────────────────────────────────────────────────────────────

@description('Name of the Bot Service resource')
param botName string

@description('Azure region (Bot Service is global, but metadata needs a location)')
param location string

@description('The messaging endpoint — where Bot Framework sends messages to your app')
param messagingEndpoint string

@description('Microsoft App ID (from Entra ID app registration)')
param microsoftAppId string

@description('SKU: F0=Free (10k messages/month), S1=Standard (unlimited)')
@allowed(['F0', 'S1'])
param skuName string = 'F0'

@description('Microsoft App Tenant ID')
param microsoftAppTenantId string = ''

// === BOT SERVICE ===
// This is a "registration" — it doesn't run code itself.
// It tells Bot Framework: "when a user sends a message, forward it to <messagingEndpoint>"
resource bot 'Microsoft.BotService/botServices@2022-09-15' = {
  name: botName
  location: 'global'      // Bot Service is always global
  kind: 'azurebot'        // 'azurebot' = Azure Bot (vs 'sdk' for legacy)
  sku: {
    name: skuName
  }
  properties: {
    displayName: botName
    // This is the URL Azure Bot Framework POSTs messages to
    // e.g. https://myapp.azurewebsites.net/api/messages
    endpoint: messagingEndpoint
    msaAppId: microsoftAppId
    msaAppTenantId: microsoftAppTenantId
    msaAppType: 'SingleTenant'   // SingleTenant = your org only
  }
}

// === MS TEAMS CHANNEL ===
// Enables the bot to work in Microsoft Teams
resource teamsChannel 'Microsoft.BotService/botServices/channels@2022-09-15' = {
  parent: bot
  name: 'MsTeamsChannel'
  location: 'global'
  properties: {
    channelName: 'MsTeamsChannel'
    properties: {
      isEnabled: true
    }
  }
}

// === WEB CHAT CHANNEL ===
// Enables the embedded web chat (your static/index.html uses this)
resource webChatChannel 'Microsoft.BotService/botServices/channels@2022-09-15' = {
  parent: bot
  name: 'WebChatChannel'
  location: 'global'
  properties: {
    channelName: 'WebChatChannel'
    properties: {
      sites: [
        {
          siteName: 'Default'
          isEnabled: true
        }
      ]
    }
  }
}

output botServiceId string = bot.id
output botName string = bot.name
