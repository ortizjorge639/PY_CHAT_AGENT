# Application Insights — Setup & Operations Guide

Observability for the Obsolescence Chat Bot using Azure Monitor OpenTelemetry.

---

## 1. Prerequisites

| Resource | Where to create |
|---|---|
| **Application Insights** (workspace-based) | Azure Portal → Create resource → Application Insights |
| **Connection String** | App Insights → Overview → top-right → "Connection String" → copy |

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

### App Service → Configuration → Application Settings

Add this setting:

| Name | Value |
|---|---|
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | `InstrumentationKey=xxxxx;IngestionEndpoint=https://...` |

Get the value from: **App Insights resource → Overview → Connection String**.

### Restart the App Service

After setting the env var: **App Service → Overview → Restart**.

### Data Retention

Default is **90 days**. To change:

**App Insights → Configure → Usage and estimated costs → Data Retention**

Options: 30, 60, 90, 120, 180, 270, 365, 730 days. Beyond 90 days costs extra per GB.

---

## 4. Deploy

Deploy via your existing CI/CD pipeline. The pipeline reads `requirements.txt` and installs the new packages automatically. No pipeline YAML changes needed.

---

## 5. Verify It Works

### Check the Log Stream

**App Service → Monitoring → Log stream**

Look for this line after startup:
```
[INFO] __main__: Azure Monitor OpenTelemetry enabled
```

If you see it, telemetry is active.

### Check Live Metrics

**App Insights → Investigate → Live metrics**

Send a message to the bot. You should see request spikes in real time.

---

## 6. Daily Operations — Where to Look

### First stop: Failures

**App Insights → Investigate → Failures**

Glance at it. If the count is 0, move on. If not, click into any failure to see the full stack trace. This is your "is anything broken?" check.

### Second stop: Traces (your persistent Log Stream)

**App Insights → Monitoring → Logs**

Default query — save this as a favorite:
```kql
traces
| where timestamp > ago(24h)
| order by timestamp desc
| take 200
```

This is Log Stream with history. Change `24h` to `7d` for the past week.

#### Filter out Azure SDK noise (show only your app logs):
```kql
traces
| where timestamp > ago(24h)
| where severityLevel >= 1
| where cloud_RoleName !contains "azure"
| order by timestamp desc
```

### Save your query

In the Logs editor → **Save** → **Save as query** → name it "App Logs (24h)". Next time: click **Queries** at the top and it's one click away.

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

## 8. What Gets Tracked Automatically

| Category | What you see | Where |
|---|---|---|
| **Requests** | Every `/api/messages` and `/api/chat` call with status and latency | Transaction Search, Performance |
| **Dependencies** | Outbound calls to Azure OpenAI and SQL Server | Transaction Search, Application Map |
| **Exceptions** | Unhandled errors with full stack traces | Failures blade |
| **Traces** | All Python `logger.info/warning/error` calls | Logs → traces table |
| **Live Metrics** | Real-time request rate, failures, CPU, memory | Live Metrics blade |

---

## 9. Optional Enhancements

| Feature | How to enable | What it gives you |
|---|---|---|
| **GenAI tracing** | Add env var `AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING=true` in App Service config | Prompt text, completions, token counts |
| **Alerts** | App Insights → Alerts → New alert rule → Failed requests > 0 in 5 min | Email/Teams notification when something breaks |
| **Availability tests** | App Insights → Availability → Add test → ping your bot URL every 5 min | Get alerted if the bot goes down |
| **Dashboards** | Any KQL query → Pin to dashboard | Custom monitoring view in Azure Portal |
| **Custom spans** | Add OpenTelemetry spans in `kernel.py` around tool calls | Per-tool-call timing (how long `lookup_part` vs `get_rows` took) |

---

## 10. Learn More

- [Azure Monitor OpenTelemetry for Python](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-enable?tabs=python)
- [KQL quick reference](https://learn.microsoft.com/en-us/azure/data-explorer/kusto/query/kql-quick-reference)
- [Application Insights overview](https://learn.microsoft.com/en-us/azure/azure-monitor/app/app-insights-overview)
- [Live Metrics troubleshooting](https://learn.microsoft.com/en-us/troubleshoot/azure/azure-monitor/app-insights/troubleshoot-live-metrics)
- [Log-based vs pre-aggregated metrics](https://learn.microsoft.com/en-us/azure/azure-monitor/app/pre-aggregated-metrics-log-metrics)
