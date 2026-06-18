import unittest

from agent.kernel import (
    _build_part_query_response,
    classify_part_query_intent,
    interpret_scrap_status,
)


class TestPartQueryResponseRouting(unittest.TestCase):
    def test_primary_table_uses_scrap_status_mapping(self) -> None:
        rows = [{"PartNumber": "12345", "Status": "May be eligible to be scrapped"}]

        response = _build_part_query_response(
            requested_part="12345",
            rows=rows,
            model_text="",
            source_role="primary",
        )

        self.assertEqual(
            response,
            interpret_scrap_status("12345", "May be eligible to be scrapped"),
        )

    def test_supplemental_table_always_uses_formatted_data(self) -> None:
        """Supplemental queries always format data; don't rely on model_text."""
        rows = [{"PartNumber": "12345", "Description": "Test part", "Phase": "A"}]

        response = _build_part_query_response(
            requested_part="12345",
            rows=rows,
            model_text="Part 12345 is a test part in phase A.",
            source_role="supplemental",
            user_message="What is the description of part 12345?",
        )

        # Should use formatted data, not model_text, to ensure consistent product details
        self.assertEqual(response, "Part 12345 description: Test part")

    def test_supplemental_table_has_concise_fallback(self) -> None:
        rows = [{"PartNumber": "12345", "Description": "Test part", "Phase": "A"}]

        response = _build_part_query_response(
            requested_part="12345",
            rows=rows,
            model_text="",
            source_role="supplemental",
            user_message="Tell me about part 12345",
        )

        self.assertIn("Part 12345 product details:", response)
        self.assertIn("Description: Test part", response)
        self.assertIn("Phase: A", response)

    def test_classifies_custom_button_as_supplemental(self) -> None:
        self.assertEqual(
            classify_part_query_intent("Is part 12345 a custom button?"),
            "supplemental",
        )

    def test_supplemental_table_answers_custom_button_flag(self) -> None:
        rows = [{"PartNumber": "12345", "CustomButton": 1}]

        response = _build_part_query_response(
            requested_part="12345",
            rows=rows,
            model_text="",
            source_role="supplemental",
            user_message="Is part 12345 a custom button?",
        )

        self.assertEqual(response, "Part 12345 is a custom button.")

    def test_supplemental_table_answers_phase_directly(self) -> None:
        rows = [{"PartNumber": "12345", "Description": "Test part", "Phase": "A"}]

        response = _build_part_query_response(
            requested_part="12345",
            rows=rows,
            model_text="",
            source_role="supplemental",
            user_message="What phase is part 12345 in?",
        )

        self.assertEqual(response, "Part 12345 phase: A")


if __name__ == "__main__":
    unittest.main()
