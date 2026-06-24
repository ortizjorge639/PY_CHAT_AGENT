import unittest

from agent.kernel import (
    _build_primary_query_expr,
    _extract_chart_metric,
    _extract_primary_status_filters,
    _extract_chart_type,
    _extract_time_granularity,
    _extract_chart_x_column,
    _extract_phase_filter,
    _extract_supplemental_filters,
    _is_chart_request,
    _is_line_chart_request,
)


class TestKernelStructuredRequests(unittest.TestCase):
    def test_extract_phase_filter_supports_plain_language(self) -> None:
        self.assertEqual(
            _extract_phase_filter("Give me a list of parts that can be scrapped with a part phase of active."),
            "active",
        )

    def test_extract_chart_x_column_prefers_date_added(self) -> None:
        self.assertEqual(
            _extract_chart_x_column("Give me a line chart, x axis is date added and y axis is count", ["DateAdded", "count"]),
            "DateAdded",
        )

    def test_extract_chart_x_column_prefers_primary_date_added_over_supplemental(self) -> None:
        self.assertEqual(
            _extract_chart_x_column(
                "count scrappable parts by date added",
                ["DateAdded", "DateAdded_supplemental", "Status"],
            ),
            "DateAdded",
        )

    def test_extract_time_granularity_year(self) -> None:
        self.assertEqual(
            _extract_time_granularity("count scrappable parts by date_added by year"),
            "year",
        )

    def test_detects_line_chart_intent(self) -> None:
        self.assertTrue(_is_line_chart_request("Give me a line chart visualization"))

    def test_detects_trend_chart_intent(self) -> None:
        self.assertTrue(_is_line_chart_request("show trend for scrappable parts over model processed date"))

    def test_detects_bar_chart_intent(self) -> None:
        self.assertTrue(_is_chart_request("show me a bar chart by status"))

    def test_extracts_pie_chart_type(self) -> None:
        self.assertEqual(_extract_chart_type("build a donut chart by phase"), "pie")

    def test_extracts_sum_metric_from_y_axis(self) -> None:
        self.assertEqual(
            _extract_chart_metric(
                "show a bar chart x axis is status y axis is qoh",
                ["Status", "QOH", "PartNumber"],
            ),
            ("sum", "QOH"),
        )

    def test_extracts_avg_metric_from_phrase(self) -> None:
        self.assertEqual(
            _extract_chart_metric(
                "show average of qoh by status",
                ["Status", "QOH", "PartNumber"],
            ),
            ("avg", "QOH"),
        )

    def test_extracts_custom_button_filter(self) -> None:
        self.assertEqual(
            _extract_supplemental_filters('Give me a list of parts with custom button.'),
            {'CustomButton': '1'},
        )

    def test_extracts_custombutton_compact_alias(self) -> None:
        self.assertEqual(
            _extract_supplemental_filters('list parts with custombutton'),
            {'CustomButton': '1'},
        )

    def test_extracts_intl_power_alias(self) -> None:
        self.assertEqual(
            _extract_supplemental_filters('list parts with intl power cord'),
            {'International_PowerCord': '1'},
        )

    def test_extracts_product_usage_status_filter(self) -> None:
        self.assertEqual(
            _extract_primary_status_filters("show product usage over time"),
            ["Product USAGE"],
        )

    def test_build_query_prefers_explicit_status_over_scrappable_keyword(self) -> None:
        self.assertEqual(
            _build_primary_query_expr(
                "show product usage across scrappable parts over processed date",
                wants_scrap=True,
            ),
            "Status == 'Product USAGE'",
        )

    def test_build_query_uses_scrappable_when_no_explicit_status(self) -> None:
        self.assertEqual(
            _build_primary_query_expr("show scrappable parts over time", wants_scrap=True),
            "Status == 'May be eligible to be scrapped'",
        )


if __name__ == "__main__":
    unittest.main()