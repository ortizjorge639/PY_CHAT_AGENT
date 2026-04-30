// ──────────────────────────────────────────────────────────────
// Module: Azure OpenAI (Reference Existing)
// Purpose: Looks up your EXISTING OpenAI resource in rg-contoso-demo
//          and returns its endpoint + key so other modules can use them.
//
// WHY "existing"? You told me OpenAI is already deployed. Instead of
// creating a duplicate, we use the `existing` keyword to reference it.
// This is a Bicep pattern for "I know this resource exists, give me
// its properties."
// ──────────────────────────────────────────────────────────────

@description('Name of the existing Azure OpenAI resource')
param openAiName string

// === REFERENCE EXISTING RESOURCE ===
// The `existing` keyword tells Bicep: "don't create this, just look it up"
// It must match the exact name of the resource already in the resource group.
resource openAi 'Microsoft.CognitiveServices/accounts@2023-05-01' existing = {
  name: openAiName
}

// === OUTPUTS ===
// Pull the endpoint from the existing resource's properties
output openAiEndpoint string = openAi.properties.endpoint
output openAiResourceId string = openAi.id

// Note: We can't output the API key directly from Bicep for security reasons.
// The key is passed as a parameter to main.bicep (from pipeline variables/Key Vault).
