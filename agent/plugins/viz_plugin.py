"""Visualization helpers for chat-friendly chart responses."""

import base64
import logging
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
import plotly.graph_objects as go

from data.loader import CHUNK_SIZE

logger = logging.getLogger(__name__)

GENERATED_DIR = os.environ.get(
    "GENERATED_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "generated"),
)
PNG_EXPORT_TIMEOUT_SECONDS = int(os.environ.get("PNG_EXPORT_TIMEOUT_SECONDS", "60"))
TEAMS_INLINE_IMAGE_MAX_BYTES = int(os.environ.get("TEAMS_INLINE_IMAGE_MAX_BYTES", "250000"))


def _cleanup_failed_image(filepath: Path) -> None:
    """Best-effort cleanup for partial PNG files after a failed export."""
    try:
        if filepath.exists():
            filepath.unlink(missing_ok=True)
    except Exception:
        # Cleanup failures are non-fatal and should not break chart responses.
        pass


def format_rows_as_markdown_chunks(rows: list[dict], columns: list[str]) -> list[str]:
    if not rows:
        return []

    chunks: list[str] = []
    total = len(rows)
    for index in range(0, total, CHUNK_SIZE):
        frame = pd.DataFrame(rows[index:index + CHUNK_SIZE]).reindex(columns=columns)
        frame = frame.where(pd.notna(frame), "")
        header = f"**Rows {index + 1}–{min(index + CHUNK_SIZE, total)} of {total}**\n\n"
        chunks.append(header + frame.to_markdown(index=False))
    return chunks


def _build_aggregated_series(
    frame: pd.DataFrame,
    *,
    x_column: str,
    y_metric: str,
    y_column: str | None = None,
    sort_by_x: bool = False,
) -> pd.DataFrame:
    if x_column not in frame.columns:
        raise ValueError(f"Column '{x_column}' was not found in the chart frame.")

    working = frame[[x_column] + ([y_column] if y_column else [])].copy()
    working = working.dropna(subset=[x_column])
    if working.empty:
        raise ValueError("No chartable rows remain after filtering null x-axis values.")

    if y_metric == "count":
        grouped = working.groupby(x_column).size().rename("value").reset_index()
    else:
        if not y_column:
            raise ValueError("A y-axis column is required for sum/avg charts.")
        if y_column not in frame.columns:
            raise ValueError(f"Column '{y_column}' was not found in the chart frame.")
        working[y_column] = pd.to_numeric(working[y_column], errors="coerce")
        working = working.dropna(subset=[y_column])
        if working.empty:
            raise ValueError(f"No numeric rows remain for y-axis column '{y_column}'.")
        agg_name = "sum" if y_metric == "sum" else "mean"
        grouped = working.groupby(x_column)[y_column].agg(agg_name).rename("value").reset_index()

    if sort_by_x:
        grouped = grouped.sort_values(by=x_column)
    return grouped


def _build_chart_payload(
    figure: go.Figure,
    *,
    title: str,
    chart_type: str,
    base_url: str,
) -> dict[str, Any]:
    output_dir = Path(GENERATED_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"chart_{uuid4().hex[:12]}.png"
    filepath = output_dir / filename
    image_path = ""
    image_url = ""
    image_data_uri = ""
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(figure.write_image, filepath)
    try:
        future.result(timeout=PNG_EXPORT_TIMEOUT_SECONDS)
        image_path = f"/api/chart-images/{filename}"
        image_url = f"{base_url.rstrip('/')}{image_path}" if base_url else image_path
    except FutureTimeoutError:
        future.cancel()
        _cleanup_failed_image(filepath)
        logger.warning(
            "Chart PNG export timed out after %ss; returning interactive chart only.",
            PNG_EXPORT_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        _cleanup_failed_image(filepath)
        message = str(exc)
        if "Couldn't close or kill browser subprocess" in message:
            logger.debug("Kaleido cleanup issue; returning interactive chart only: %s", message)
        else:
            logger.warning("Chart PNG export failed; returning interactive chart only: %s", message)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    if image_url:
        try:
            file_size = filepath.stat().st_size
            if file_size <= TEAMS_INLINE_IMAGE_MAX_BYTES:
                with filepath.open("rb") as image_file:
                    image_bytes = image_file.read()
                encoded = base64.b64encode(image_bytes).decode("ascii")
                image_data_uri = f"data:image/png;base64,{encoded}"
            else:
                logger.info(
                    "Skipping inline Teams image embedding for %s (size=%s bytes exceeds limit=%s bytes)",
                    filename,
                    file_size,
                    TEAMS_INLINE_IMAGE_MAX_BYTES,
                )
        except Exception as exc:
            logger.warning("Failed to prepare inline Teams image payload: %s", exc)

    web_payload: dict[str, Any] = {
        "plotly_spec": figure.to_plotly_json(),
    }
    if image_url:
        web_payload["save_url"] = image_url

    return {
        "chart_type": chart_type,
        "title": title,
        "image_filename": filename if image_url else "",
        "web": web_payload,
        "teams": {
            "image_url": image_url,
            "image_data_uri": image_data_uri,
            "alt_text": title,
        },
    }


def create_aggregated_chart(
    frame: pd.DataFrame,
    *,
    chart_type: str,
    x_column: str,
    y_metric: str,
    y_column: str | None = None,
    title: str,
    base_url: str = "",
) -> dict[str, Any]:
    chart_type = chart_type.lower().strip()
    y_metric = y_metric.lower().strip()

    if chart_type not in {"line", "bar", "pie"}:
        raise ValueError(f"Unsupported chart type '{chart_type}'.")
    if y_metric not in {"count", "sum", "avg"}:
        raise ValueError(f"Unsupported y metric '{y_metric}'.")

    working_frame = frame.copy()
    sort_by_x = False
    
    # Normalize x-axis column for date-based charts
    if chart_type in {"line", "bar"}:
        working_frame[x_column] = pd.to_datetime(working_frame[x_column], errors="coerce", utc=True)
        working_frame = working_frame.dropna(subset=[x_column])
        if working_frame.empty:
            raise ValueError("No chartable rows remain after normalizing the x-axis column.")
        working_frame[x_column] = working_frame[x_column].dt.strftime("%Y-%m-%d")
        sort_by_x = True
    else:
        # For pie charts, ensure x_column is string to avoid Timestamp serialization
        working_frame[x_column] = working_frame[x_column].astype(str)

    grouped = _build_aggregated_series(
        working_frame,
        x_column=x_column,
        y_metric=y_metric,
        y_column=y_column,
        sort_by_x=sort_by_x,
    )

    if chart_type == "line":
        trace = go.Scatter(
            x=grouped[x_column].astype(str).tolist(),
            y=grouped["value"].tolist(),
            mode="lines+markers",
            name=y_metric,
        )
    elif chart_type == "bar":
        trace = go.Bar(
            x=grouped[x_column].astype(str).tolist(),
            y=grouped["value"].tolist(),
            name=y_metric,
        )
    else:
        trace = go.Pie(
            labels=grouped[x_column].astype(str).tolist(),
            values=grouped["value"].tolist(),
            name=y_metric,
        )

    figure = go.Figure(data=[trace])
    if chart_type == "pie":
        figure.update_layout(title=title, template="plotly_white")
    else:
        y_label = "Count" if y_metric == "count" else f"{y_metric.upper()}({y_column})"
        figure.update_layout(
            title=title,
            xaxis_title=x_column,
            yaxis_title=y_label,
            template="plotly_white",
        )

    return _build_chart_payload(
        figure,
        title=title,
        chart_type=chart_type,
        base_url=base_url,
    )


def create_count_line_chart(
    frame: pd.DataFrame,
    *,
    x_column: str,
    title: str,
    base_url: str = "",
) -> dict[str, Any]:
    return create_aggregated_chart(
        frame,
        chart_type="line",
        x_column=x_column,
        y_metric="count",
        title=title,
        base_url=base_url,
    )