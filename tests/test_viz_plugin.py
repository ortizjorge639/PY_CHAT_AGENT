import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from agent.plugins import viz_plugin


class TestVizPlugin(unittest.TestCase):
    def test_create_count_line_chart_returns_payload_and_png(self) -> None:
        frame = pd.DataFrame(
            {
                "DateAdded": [
                    "2024-01-01",
                    "2024-01-01",
                    "2024-01-02",
                ]
            }
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(viz_plugin, "GENERATED_DIR", temp_dir):
                payload = viz_plugin.create_count_line_chart(
                    frame,
                    x_column="DateAdded",
                    title="Count by date",
                    base_url="https://example.test",
                )

                image_path = Path(temp_dir) / payload["image_filename"]
                self.assertEqual(payload["chart_type"], "line")
                self.assertIn("plotly_spec", payload["web"])
                if payload["image_filename"]:
                    self.assertTrue(image_path.exists())
                    self.assertGreater(image_path.stat().st_size, 0)
                    self.assertEqual(
                        payload["teams"]["image_url"],
                        f"https://example.test/api/chart-images/{payload['image_filename']}",
                    )
                    self.assertIn("save_url", payload["web"])
                else:
                    self.assertEqual(payload["teams"]["image_url"], "")
                    self.assertNotIn("save_url", payload["web"])

    def test_create_bar_sum_chart_returns_plotly_payload(self) -> None:
        frame = pd.DataFrame(
            {
                "Status": ["A", "A", "B"],
                "QOH": [10, 5, 7],
            }
        )

        with patch("plotly.graph_objects.Figure.write_image", side_effect=RuntimeError("kaleido unavailable")):
            payload = viz_plugin.create_aggregated_chart(
                frame,
                chart_type="bar",
                x_column="Status",
                y_metric="sum",
                y_column="QOH",
                title="SUM by Status",
                base_url="https://example.test",
            )

        self.assertEqual(payload["chart_type"], "bar")
        self.assertIn("plotly_spec", payload["web"])
        self.assertEqual(payload["image_filename"], "")
        self.assertNotIn("save_url", payload["web"])

    def test_create_count_line_chart_supports_year_granularity(self) -> None:
        frame = pd.DataFrame(
            {
                "DateAdded": [
                    "2023-01-01",
                    "2023-09-10",
                    "2024-02-15",
                ]
            }
        )

        with patch("plotly.graph_objects.Figure.write_image", side_effect=RuntimeError("kaleido unavailable")):
            payload = viz_plugin.create_aggregated_chart(
                frame,
                chart_type="line",
                x_column="DateAdded",
                y_metric="count",
                title="Count by DateAdded (Year)",
                base_url="https://example.test",
                x_time_granularity="year",
            )

        x_values = payload["web"]["plotly_spec"]["data"][0]["x"]
        self.assertEqual(list(x_values), ["2023", "2024"])


if __name__ == "__main__":
    unittest.main()