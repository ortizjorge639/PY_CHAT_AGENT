import json
import unittest

from agent.plugins.data_plugin import create_data_tools


class _FakeLoader:
    def __init__(self, *, tables: dict, roles: dict, columns_by_table: dict):
        self._tables = tables
        self._roles = roles
        self._columns_by_table = columns_by_table

    def lookup_part(self, part_number: str) -> dict:
        return {
            "part_number": part_number,
            "tables": self._tables,
            "columns_by_table": self._columns_by_table,
        }

    def get_table_roles(self) -> dict:
        return self._roles


class TestLookupPartDetailsTool(unittest.TestCase):
    def _get_tool(self, loader: _FakeLoader, data_buffer: list, last_result: dict):
        tools = create_data_tools(
            loader=loader,
            data_buffer=data_buffer,
            file_buffer=[],
            last_result=last_result,
            base_url="",
        )
        return next(t for t in tools if t.__name__ == "lookup_part_details")

    def test_returns_error_when_part_missing_in_supplemental(self) -> None:
        loader = _FakeLoader(
            tables={"operations.Obsolescence_Results": [{"PartNumber": "1001"}]},
            roles={"operations.Obsolescence_Results": "primary"},
            columns_by_table={"operations.Obsolescence_Results": ["PartNumber"]},
        )
        data_buffer: list[str] = []
        last_result: dict = {}
        tool = self._get_tool(loader, data_buffer, last_result)

        payload = json.loads(tool("1001"))

        self.assertIn("error", payload)
        self.assertIn("not found in product catalogue", payload["error"])
        self.assertEqual(data_buffer, [])
        self.assertEqual(last_result, {})

    def test_returns_rows_when_supplemental_hit_exists(self) -> None:
        loader = _FakeLoader(
            tables={
                "operations.Obsolescence_Results": [{"PartNumber": "1001", "Status": "No stock"}],
                "production.dimProducts": [{"PartNumber": "1001", "Description": "Demo part", "Phase": "A"}],
            },
            roles={
                "operations.Obsolescence_Results": "primary",
                "production.dimProducts": "supplemental",
            },
            columns_by_table={
                "operations.Obsolescence_Results": ["PartNumber", "Status"],
                "production.dimProducts": ["PartNumber", "Description", "Phase"],
            },
        )
        data_buffer: list[str] = []
        last_result: dict = {}
        tool = self._get_tool(loader, data_buffer, last_result)

        payload = json.loads(tool("1001"))

        self.assertEqual(payload["rows_retrieved"], 1)
        self.assertEqual(last_result.get("table"), "production.dimProducts")
        self.assertEqual(len(last_result.get("rows", [])), 1)
        self.assertTrue(data_buffer)


if __name__ == "__main__":
    unittest.main()
