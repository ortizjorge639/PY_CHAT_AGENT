import unittest

import pandas as pd

from config.settings import Settings
from data.loader import DataLoader


class TestCrossTableFiltering(unittest.TestCase):
    def setUp(self) -> None:
        self.loader = DataLoader(Settings(), auto_load=False)
        self.loader._tables = {
            "primary_table": pd.DataFrame(
                [
                    {"PartNumber": "P1", "Status": "May be eligible to be scrapped", "Processed_Date": "2024-01-01"},
                    {"PartNumber": "P2", "Status": "May be eligible to be scrapped", "Processed_Date": "2024-01-02"},
                    {"PartNumber": "P3", "Status": "May be eligible to be scrapped", "Processed_Date": "2024-01-03"},
                    {"PartNumber": "P4", "Status": "No stock", "Processed_Date": "2024-01-04"},
                    {"PartNumber": "P5", "Status": "May be eligible to be scrapped", "Processed_Date": "2024-01-05"},
                ]
            ),
            "dim_products": pd.DataFrame(
                [
                    {"PartNumber": "P1", "Phase": "active"},
                    {"PartNumber": "P2", "Phase": "active"},
                    {"PartNumber": "P3", "Phase": "active"},
                    {"PartNumber": "P4", "Phase": "obsolete"},
                    {"PartNumber": "P5", "Phase": "hold"},
                ]
            ),
        }
        self.loader._table_roles = {
            "primary_table": "primary",
            "dim_products": "supplemental",
        }
        for table_name, df in list(self.loader._tables.items()):
            self.loader._tables[table_name] = self.loader._normalize_dataframe(df)

    def test_query_table_with_cross_filter_returns_primary_rows(self) -> None:
        result = self.loader.query_table_with_cross_filter(
            "primary_table",
            "Status == 'May be eligible to be scrapped'",
            {"Phase": "active"},
        )

        self.assertEqual(result["total"], 3)
        self.assertEqual([row["PartNumber"] for row in result["rows"]], ["P1", "P2", "P3"])

    def test_cross_filter_populates_cache_and_reuses_key(self) -> None:
        self.assertEqual(self.loader.get_filter_cache_size(), 0)

        first = self.loader.query_table_with_cross_filter(
            "primary_table",
            "Status == 'May be eligible to be scrapped'",
            {"Phase": "active"},
        )
        cache_size_after_first = self.loader.get_filter_cache_size()

        second = self.loader.query_table_with_cross_filter(
            "primary_table",
            "Status == 'May be eligible to be scrapped'",
            {"Phase": "active"},
        )

        self.assertEqual(first["rows"], second["rows"])
        self.assertEqual(cache_size_after_first, 1)
        self.assertEqual(self.loader.get_filter_cache_size(), 1)

    def test_get_cross_filtered_frame_can_include_all_supplemental_columns(self) -> None:
        frame = self.loader.get_cross_filtered_frame(
            "primary_table",
            query_expr="Status == 'May be eligible to be scrapped'",
            include_all_supplemental=True,
        )

        self.assertEqual(len(frame), 4)
        self.assertIn("Phase", frame.columns)
        self.assertEqual(set(frame["PartNumber"].tolist()), {"P1", "P2", "P3", "P5"})


if __name__ == "__main__":
    unittest.main()