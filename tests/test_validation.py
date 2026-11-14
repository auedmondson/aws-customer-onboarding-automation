"""Run from the repository root: python -m unittest discover -s tests -v"""

import unittest

from src.validation.app import lambda_handler, validate_request


class TestRequestValidation(unittest.TestCase):
    def setUp(self):
        self.payload = {
            "businessName": "Example Company",
            "contactName": "Jordan Smith",
            "contactEmail": "jordan@example.com",
        }

    def test_valid_request(self):
        result = lambda_handler(self.payload, None)

        self.assertTrue(result["isValid"])
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["customer"], self.payload)

    def test_trims_surrounding_whitespace(self):
        self.payload["businessName"] = "  Example Company  "

        result = validate_request(self.payload)

        self.assertTrue(result["isValid"])
        self.assertEqual(
            result["customer"]["businessName"],
            "Example Company",
        )

    def test_required_fields(self):
        for field in self.payload:
            for invalid_value in (None, "", "   ", 123, []):
                with self.subTest(field=field, value=invalid_value):
                    payload = {**self.payload, field: invalid_value}
                    result = validate_request(payload)

                    self.assertFalse(result["isValid"])
                    self.assertNotIn("customer", result)

    def test_missing_field(self):
        del self.payload["contactName"]

        result = validate_request(self.payload)

        self.assertFalse(result["isValid"])
        self.assertIn(
            "contactName must be a non-empty string.",
            result["errors"],
        )

    def test_invalid_email_formats(self):
        for email in ("invalid", "name@", "@example.com", "a b@example.com"):
            with self.subTest(email=email):
                self.payload["contactEmail"] = email
                result = validate_request(self.payload)

                self.assertFalse(result["isValid"])

    def test_field_length_limits(self):
        limits = {
            "businessName": 200,
            "contactName": 100,
            "contactEmail": 254,
        }

        for field, limit in limits.items():
            with self.subTest(field=field):
                payload = {**self.payload, field: "x" * (limit + 1)}
                result = validate_request(payload)

                self.assertFalse(result["isValid"])
                self.assertIn(
                    f"{field} must not exceed {limit} characters.",
                    result["errors"],
                )

    def test_non_object_input(self):
        for payload in (None, [], "text", 123):
            with self.subTest(payload=payload):
                result = validate_request(payload)

                self.assertFalse(result["isValid"])
                self.assertEqual(
                    result["errors"],
                    ["Request must be a JSON object."],
                )

    def test_input_is_not_modified(self):
        self.payload["contactName"] = "  Jordan Smith  "
        original = self.payload.copy()

        validate_request(self.payload)

        self.assertEqual(self.payload, original)


if __name__ == "__main__":
    unittest.main()
