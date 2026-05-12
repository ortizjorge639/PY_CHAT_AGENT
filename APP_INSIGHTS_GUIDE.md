# Application Insights - Setup & Operations Guide

Observability for the Obsolescence Chat Bot using Azure Monitor OpenTelemetry. Once enabled, requests, dependencies (Azure OpenAI, SQL), exceptions, and Python logs are all tracked automatically.

Once enabled, requests, dependencies (Azure OpenAI, SQL), exceptions, and Python logs are all tracked automatically.

---

## 1. Prerequisites

| Resource | Where to create or find it |
|---|---|
| Application Insights | Azure Portal -> Create a resource -> Application Insights |
| Connection String | App Insights -> Overview -> top-right panel -> copy Connection String |

### Create an Application Insights resource

1. Open [portal.azure.com](https://portal.azure.com)
2. Click **+ Create a resource**
3. Search for **Application Insights** and click **Create**
4. Fill in Subscription, Resource Group, Name, and Region
5. Under **Resource Mode**, select **Workspace-based**
6. Click **Review + Create** and then **Create**

### Get the Connection String

1. Open the new **Application Insights** resource
2. On the **Overview** page, find **Connection String** in the top-right panel
3. Click the copy icon
4. Save it for the App Service configuration step

---

## 2. What Was Added to the Code

Three files changed and two packages were added.

### `requirements.txt`
```text
azure-monitor-opentelemetry>=1.6.0
opentelemetry-instrumentation-aiohttp-server>=0.48b0
```

### `config/settings.py`
```python
applicationinsights_connection_string: str = ""
```

This reads from the `APPLICATIONINSIGHTS_CONNECTION_STRING` environment variable.

### `main_test.py` (entry point)
```python
if settings.applicationinsights_connection_string:
    from azure.monitor.opentelemetry import configure_azure_monitor

    configure_azure_monitor(
        connection_string=settings.applicationinsights_connection_string,
    )
    logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
    logging.getLogger("azure.monitor.opentelemetry.exporter").setLevel(logging.WARNING)
    logger.info("Azure Monitor OpenTelemetry enabled")
```

If the environment variable is empty, telemetry is skipped entirely.

---

## 3. Azure Configuration

### Add the Connection String to App Service

1. Open your **App Service** resource in the Azure Portal
2. Go to **Settings** -> **Configuration**
3. Open the **Application settings** tab
4. Click **+ New application setting**
5. Name: `APPLICATIONINSIGHTS_CONNECTION_STRING`
6. Value: paste the connection string copied from App Insights
7. Click **OK** and then **Save**

### Restart the App Service

1. Go to **App Service** -> **Overview**
2. Click **Restart** and confirm

### Change Data Retention (optional)

1. Open the **Application Insights** resource
2. Go to **Configure** -> **Usage and estimated costs**
3. Click **Data Retention**
4. Choose 30, 60, 90, 120, 180, 270, 365, or 730 days
5. Click **OK**

Default retention is 90 days.

---

## 4. Deploy

Run the pipeline manually from Azure DevOps:

1. Go to **Pipelines**
2. Select the pipeline and click **Run pipeline**
3. Choose the branch/tag dropdown and select your branch
4. Click **Run**

The pipeline reads `requirements.txt` and installs the new packages automatically. No pipeline YAML changes are needed.
---

## 5. Verify It Works

### Check the Log Stream

1. Open **App Service** -> **Monitoring** -> **Log stream**
2. Wait for startup after deploy
3. Look for:

```text
[INFO] __main__: Azure Monitor OpenTelemetry enabled
```

If you see it, telemetry is active.

### Check Live Metrics

1. Open **Application Insights** -> **Investigate** -> **Live metrics**
2. Send a message to the bot
3. You should see request spikes in real time

---

## 6. Daily Operations

### First stop: Failures

1. Open **Application Insights** -> **Investigate** -> **Failures**
2. If the failure count is 0, move on
3. If there are failures, click a red bar and inspect the failed request

This is the fastest way to answer: is anything broken right now?

### Second stop: Traces

1. Open **Application Insights** -> **Monitoring** -> **Logs**
2. Close any **Queries** popup if it appears
3. Run this query:

```kql
traces
| where timestamp > ago(24h)
| order by timestamp desc
| take 200
```

This is the searchable history of Log Stream. Change `24h` to `7d` for the past week.

#### Filter out Azure SDK noise

```kql
traces
| where timestamp > ago(24h)
| where severityLevel >= 1
| where cloud_RoleName !contains "azure"
| order by timestamp desc
```

### Save your query for quick access

After running a query, click **Save** -> **Save as query** and name it something like **App Logs (24h)**.

---

## 7. Useful KQL Queries

### All bot conversations
```kql
traces
| where timestamp > ago(24h)
| where message contains "Web chat"
| order by timestamp desc
```

### All errors with stack traces
```kql
exceptions
| where timestamp > ago(24h)
| order by timestamp desc
```

### Azure OpenAI call latency
```kql
dependencies
| where timestamp > ago(1h)
| where target contains "openai"
| project timestamp, duration, resultCode, target
| order by timestamp desc
```

### SQL query performance
```kql
dependencies
| where timestamp > ago(1h)
| where type == "SQL"
| project timestamp, duration, data, resultCode
| order by duration desc
```

### Find a specific part number lookup
```kql
traces
| where timestamp > ago(24h)
| where message contains "60-2632-11"
| order by timestamp desc
```

### Failed requests by endpoint
```kql
requests
| where timestamp > ago(24h)
| where success == false
| summarize count() by name
| order by count_ desc
```

