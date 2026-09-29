"""Offline unit tests for the normalized box and response parsing contracts."""

from __future__ import annotations

import unittest

from src.dataset.normalizer import denormalize_box, normalize_box
from src.generator.code_cleaner import clean_react_code, validate_react_code
from src.grounding.box_parser import parse_boxes


class CoreContractTests(unittest.TestCase):
    def test_coordinate_round_trip_preserves_aspect_ratio(self) -> None:
        pixel_box = [120, 45, 900, 510]
        normalized = normalize_box(pixel_box, 1200, 600)
        self.assertEqual(normalized, [100, 75, 750, 850])
        self.assertEqual(denormalize_box(normalized, 1200, 600), pixel_box)

    def test_normalization_clamps_to_image(self) -> None:
        self.assertEqual(normalize_box([-4, 10, 120, 60], 100, 100), [0, 100, 1000, 600])

    def test_box_parser_clamps_and_pairs_labels(self) -> None:
        response = "<grounding><box>[-2, 10, 500, 9999]</box><label>Search input</label></grounding>"
        self.assertEqual(parse_boxes(response), [{"box": [0, 10, 500, 1000], "label": "Search input"}])

    def test_code_cleaner_extracts_component(self) -> None:
        response = "Here is the UI:\n```jsx\nexport default function App() { return <main className=\"p-4\" />; }\n```"
        code = clean_react_code(response)
        self.assertIn("function App", code)
        self.assertTrue(validate_react_code(code)[0])


if __name__ == "__main__":
    unittest.main()
