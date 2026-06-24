# Visualization Feature Change Log

## Scope
This document captures the final, production-relevant visualization feature changes implemented in this repository during the Teams chart rendering hardening cycle.

## 1. Visualization Engine and Chart Payloads
- Scope:
  - Generate reliable chart artifacts for both web and Teams channels.
  - Support robust chart aggregation and export behavior under App Service constraints.
- Files:
  - agent/plugins/viz_plugin.py
- Included changes:
  - Added aggregated chart generation for line, bar, and pie chart types.
  - Added support for y-axis metrics: count, sum, avg.
  - Added duplicate-column-safe series selection during numeric aggregation.
  - Added Teams payload fields for both image_url and image_data_uri.
  - Added PNG export timeout handling and partial-file cleanup.
  - Added compact fallback export attempt after timeout.
  - Added lightweight date-likeness guard before datetime coercion.
- Out of scope:
  - No interactive Plotly execution inside Teams cards.

## 2. Teams Visualization Delivery
- Scope:
  - Ensure generated chart visuals are sent successfully in Teams.
- Files:
  - bot/bot_handler.py
- Included changes:
  - Adaptive Card image source now prefers inline data URI, then URL fallback.
  - Added send-mode logging (inline-data-uri vs image-url).
  - Added explicit skip path when no image payload is available.
- Out of scope:
  - No Teams app manifest redesign.

## 3. Chart Intent Parsing and Metric Resolution Hardening
- Scope:
  - Prevent avg/sum chart failures caused by ambiguous natural-language prompts.
- Files:
  - agent/kernel.py
- Included changes:
  - Improved metric phrase extraction for prompts like "average quantity by status".
  - Added grouping-phrase trimming around by/over/per/across/for.
  - Added quantity alias mapping (QOH/Qty/Quantity variants).
  - Added numeric-column validation for avg/sum requests.
  - Added fallback numeric metric-column resolver when parsed y-column is invalid.
- Out of scope:
  - No model retraining or LLM prompt-only fix dependency.

## 4. Runtime Endpoints, Auth Exemptions, and Chart File Lifecycle
- Scope:
  - Make chart images servable and safely managed at runtime.
- Files:
  - main.py
  - config/settings.py
- Included changes:
  - Added chart image endpoint for generated PNGs.
  - Added auth-exempt path prefix for chart image serving.
  - Added chart cleanup integration with refresh/reload flow.
  - Added chart lifecycle settings: retention, max count, cleanup toggle.
  - Preserved path traversal checks and scoped filename validation.
- Out of scope:
  - No widening of file-download authorization scope.

## 5. Deployment and Runtime Prerequisites for PNG Rendering
- Scope:
  - Ensure Kaleido + Chrome rendering path works on Azure App Service Linux.
- Files:
  - azure-pipelines.yml
  - startup.sh
  - requirements.txt
- Included changes:
  - Pipeline startup command set to run startup.sh.
  - App settings include generated dir, startup time limit, base URL, and PNG timeout.
  - Startup script ensures ODBC Driver 18 and Google Chrome availability.
  - Requirements include plotly and kaleido.
- Out of scope:
  - No infrastructure module refactor.

## 6. Data Shaping and Cross-Table Support Used by Visualization Requests
- Scope:
  - Stabilize source frames used by chart and filter requests.
- Files:
  - data/loader.py
  - agent/plugins/data_plugin.py
  - agent/kernel.py
- Included changes:
  - SQL shape alignment for primary and supplemental tables used by visualization paths.
  - Cross-table filter support used by structured chart/list requests.
  - Result projection and formatting support required by chart-adjacent responses.
- Out of scope:
  - No source database schema migration.

## 7. Local Web UI Support Surface
- Scope:
  - Keep local web UI able to render returned visualization payloads for validation.
- Files:
  - static/index.html
- Included changes:
  - Plotly rendering path maintained for visualizations returned by /api/chat.
- Out of scope:
  - No production Teams UX redesign.

## 8. Superseded One-Off Paths (Not Final Direction)
- Scope:
  - Clarify experiments that were intentionally replaced.
- Included:
  - Interactive-only Teams chart approach was superseded by inline PNG delivery.
  - Chromium-only install path was superseded by Google Chrome path for Kaleido compatibility.
  - Earlier startup-entry mismatch was superseded by stable startup script execution.

## 9. Final State Summary
- Visualization delivery in Teams is image-based and stable (inline-first).
- Avg/sum metric parsing and fallback behavior is hardened.
- PNG export now has timeout-aware fallback behavior.
- Deployment path is aligned with runtime prerequisites for chart rendering.
