// Azure Bicep template for WocconWaker deployment
// This template creates all necessary Azure resources for hosting WocconWaker

// Note: resourceGroupName is available via resourceGroup().name, so we don't need it as a parameter

@description('The Azure region for all resources')
param location string = 'eastus'

@description('The name of the Container Apps environment')
param containerAppEnvName string = 'wocconwaker-env'

@description('The name of the Container App')
param containerAppName string = 'wocconwaker-app'

@description('The name of the Container Registry (must be globally unique)')
param containerRegistryName string = 'wocconwaker${uniqueString(resourceGroup().id)}'

@description('The Docker image to deploy (must include registry server, e.g., myregistry.azurecr.io/wocconwaker:latest)')
param dockerImage string = ''

@description('Ollama Cloud endpoint (default: https://api.ollama.com)')
param ollamaCloudEndpoint string = 'https://api.ollama.com'

@description('Ollama Cloud API key (stored as secret)')
@secure()
param ollamaCloudApiKey string

@description('Ollama model name')
param ollamaModel string = 'llama3:8b'

@description('Facebook Messenger Page Access Token (optional)')
@secure()
param pageAccessToken string = ''

@description('Facebook Messenger Verify Token (optional)')
param verifyToken string = ''

@description('Container CPU (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0)')
@allowed(['0.25', '0.5', '0.75', '1.0', '1.25', '1.5', '1.75', '2.0'])
param containerCpu string = '2.0'

@description('Container memory in GiB (0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0)')
param containerMemory string = '4.0'

@description('Minimum number of container instances')
param minReplicas int = 0

@description('Maximum number of container instances')
param maxReplicas int = 10

// Resource: Container Registry
resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-01-01-preview' = {
  name: containerRegistryName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: true
  }
}

// Resource: Container Apps Environment
resource containerAppEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: containerAppEnvName
  location: location
  properties: {
    workloadProfiles: []
  }
}

// Role Assignment: Grant Container App access to pull from ACR
resource acrPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(containerRegistry.id, containerApp.id, 'acrPull')
  scope: containerRegistry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d') // AcrPull role
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Resource: Container App
resource containerApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: containerAppName
  location: location
  properties: {
    managedEnvironmentId: containerAppEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        allowInsecure: false
        transport: 'auto'
      }
      registries: [
        {
          server: containerRegistry.properties.loginServer
          identity: 'system'
        }
      ]
      secrets: [
        {
          name: 'ollama-cloud-api-key'
          value: ollamaCloudApiKey
        }
        {
          name: 'page-access-token'
          value: pageAccessToken
        }
      ]
    }
    template: {
      containers: [
        {
          name: containerAppName
          image: !empty(dockerImage) ? dockerImage : 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest' // Placeholder - will be updated after image is built
          resources: {
            cpu: json(containerCpu)
            memory: '${containerMemory}Gi'
          }
          env: [
            {
              name: 'WOCCON_MODE'
              value: 'server'
            }
            {
              name: 'OLLAMA_CLOUD_ENDPOINT'
              value: ollamaCloudEndpoint
            }
            {
              name: 'OLLAMA_CLOUD_API_KEY'
              secretRef: 'ollama-cloud-api-key'
            }
            {
              name: 'OLLAMA_MODEL'
              value: ollamaModel
            }
            {
              name: 'PORT'
              value: '8000'
            }
            {
              name: 'PAGE_ACCESS_TOKEN'
              secretRef: 'page-access-token'
            }
            {
              name: 'VERIFY_TOKEN'
              value: verifyToken
            }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 10
              periodSeconds: 10
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/health'
                port: 8000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 5
              periodSeconds: 5
              failureThreshold: 3
            }
            {
              type: 'Startup'
              httpGet: {
                path: '/health'
                port: 8000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 10
              periodSeconds: 10
              failureThreshold: 20
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
        rules: [
          {
            name: 'http-scale'
            http: {
              metadata: {
                concurrentRequests: '10'
              }
            }
          }
        ]
      }
    }
  }
  identity: {
    type: 'SystemAssigned'
  }
}

// Outputs
output containerAppUrl string = containerApp.properties.configuration.ingress.fqdn
output containerAppName string = containerApp.name
output containerRegistryName string = containerRegistry.name
output containerRegistryLoginServer string = containerRegistry.properties.loginServer

