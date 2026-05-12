# Application Insights — Setup & Operations Guide

Observability for the Obsolescence Chat Bot using Azure Monitor OpenTelemetry.

Once enabled, requests, dependencies (Azure OpenAI, SQL), exceptions, and Python logs are all tracked automatically.

---

## 1. Prerequisites

### Create an Application Insights resource

1. Open [portal.azure.com](https://portal.azure.com)
2. Click **+ Create a resource** (top-left)
3. Search for **Application Insights** → click **Create**
4. Fill in: Subscription, Resource Group, Name, Region
5. Under **Resource Mode**, select **Workspace-based**
6. Click **Review + Create** → **Create**

### Get the Connection String

1. Open your new **Application Insights** resource
2. On the **Overview** page, look at the top-right panel
3. Find **Connection String** → click the **copy** icon
4. Save this — you'll paste it into App Service settings next

---

## 2. What Was Added to the Code

Three files changed, two packages added:

### `requirements.txt`
```
azure-monitor-opentelemetry>=1.6.0
opentelemetry-instrumentation-aiohttp-server>=0.48b0
```

### `config/settings.py`
```python
applicationinsights_connection_string: str = ""
```
Reads from env var `APPLICATIONINSIGHTS_CONNECTION_STRING`.

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

If the env var is empty, telemetry is completely skipped — zero overhead.

---

## 3. Azure Configuration

### Add the Connection String to App Service

1. Open [portal.azure.com](https://portal.azure.com)
2. Go to your **App Service** resource
3. Left sidebar → **Settings** → **Configuration**
4. Click the **Application settings** tab
5. Click **+ New application setting**
6. Name: `APPLICATIONINSIGHTS_CONNECTION_STRING`
7. Value: paste the connection string you copied in step 1
8. Click **OK** → click **Save** (top bar) → click **Continue** to confirm

### Restart the App Service

1. Go to your **App Service** resource
2. Left sidebar → **Overview**
3. Click **Restart** (top bar) → click **Yes** to confirm

### Change Data Retention (optional)

1. Open your **Application Insights** resource
2. Left sidebar → **Configure** → **Usage and estimated costs**
3. Click **Data Retention**
4. Use the slider to pick: 30, 60, 90, 120, 180, 270, 365, or 730 days
5. Click **OK**

Default is 90 days. Beyond 90 days costs extra per GB.

---

## 4. Deploy

Deploy via your existing CI/CD pipeline. The pipeline reads `requirements.txt` and installs the new packages automatically. No pipeline YAML changes needed.

---

## 5. Verify It Works

### Check the Log Stream

1. Open your **App Service** resource
2. Left sidebar → **Monitoring** → **Log stream**
3. Wait for the app to start (may take 1-2 minutes after a deploy)
4. Look for this line:
```
[INFO] __main__: Azure Monitor OpenTelemetry enabled
```
If you see it, telemetry is active. If not, check that the connection string env var is set correctly.

### Check Live Metrics

1. Open your **Application Insights** resource
2. Left sidebar → **Investigate** → **Live metrics**
3. The page should show "Connected" with real-time charts
4. Send a message to the bot (via Teams or the web UI)
5. You should see a spike in the **Incoming Requests** chart

---

## 6. Daily Operations — Where to Look

### First stop: Failures

1. Open your **Application Insights** resource
2. Left sidebar → **Investigate** → **Failures**
3. Check the chart — if the failure count is 0, you're good
4. If there are failures: click any red bar to see the list of failed requests
5. Click any failed request → see the full stack trace and timeline

This is your "is anything broken right now?" check.

### Second stop: Traces (your persistent Log Stream)

1. Open your **Application Insights** resource
2. Left sidebar → **Monitoring** → **Logs**
3. If a "Queries" popup appears, close it (click **X**)
4. In the query editor, paste this and click **Run**:

```kql
traces
| where timestamp > ago(24h)
| order by timestamp desc
| take 200
```

This is the same data as Log Stream, but searchable and stored for up to 90 days. Change `24h` to `7d` for the past week.

#### Filter out Azure SDK noise (show only your app logs):
```kql
traces
| where timestamp > ago(24h)
| where severityLevel >= 1
| where cloud_RoleName !contains "azure"
| order by timestamp desc
```

### Save your query for quick access

1. After running a query, click **Save** (top bar of the query editor)
2. Select **Save as query**
3. Name it something like "App Logs (24h)"
4. Click **Save**
5. Next time: click **Queries** (top bar) → find your saved query → click **Run**

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

---

## 8. Learn More

- [Azure Monitor OpenTelemetry for Python](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-enable?tabs=python)
- [KQL quick reference](https://learn.microsoft.com/en-us/azure/data-explorer/kusto/query/kql-quick-reference)
- [Application Insights overview](https://learn.microsoft.com/en-us/azure/azure-monitor/app/app-insights-overview)
- [Live Metrics troubleshooting](https://learn.microsoft.com/en-us/troubleshoot/azure/azure-monitor/app-insights/troubleshoot-live-metrics)
- [Log-based vs pre-aggregated metrics](https://learn.microsoft.com/en-us/azure/azure-monitor/app/pre-aggregated-metrics-log-metrics)
