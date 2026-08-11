"""Unit tests for machine-bound AI API key encryption."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from btf_viewer_pkg.rc_secrets import (  # noqa: E402
    decrypt_secret,
    encrypt_secret,
    is_ai_api_key_option,
    is_encrypted_secret,
)


class RcSecretsTests(unittest.TestCase):
    def test_roundtrip(self) -> None:
        blob = encrypt_secret("sk-test-key")
        self.assertTrue(is_encrypted_secret(blob))
        self.assertNotIn("sk-test-key", blob)
        self.assertEqual(decrypt_secret(blob), "sk-test-key")

    def test_empty_and_idempotent(self) -> None:
        self.assertEqual(encrypt_secret(""), "")
        self.assertEqual(encrypt_secret("   "), "")
        blob = encrypt_secret("abc")
        self.assertEqual(encrypt_secret(blob), blob)

    def test_plaintext_passthrough_on_decrypt(self) -> None:
        self.assertEqual(decrypt_secret("legacy-plain"), "legacy-plain")

    def test_tamper_rejects(self) -> None:
        blob = encrypt_secret("secret")
        tampered = blob[:-4] + ("A" if blob[-4] != "A" else "B") + blob[-3:]
        self.assertEqual(decrypt_secret(tampered), "")

    def test_other_machine_cannot_decrypt(self) -> None:
        blob = encrypt_secret("machine-bound")
        with mock.patch(
            "btf_viewer_pkg.rc_secrets._machine_material",
            return_value=b"other-host|other-user",
        ):
            # Clear would not help — patch material directly.
            self.assertEqual(decrypt_secret(blob), "")

    def test_ai_key_option_helper(self) -> None:
        self.assertTrue(is_ai_api_key_option("ai", "gemini_api_key"))
        self.assertFalse(is_ai_api_key_option("ai", "gemini_model"))
        self.assertFalse(is_ai_api_key_option("view", "theme_api_key"))


if __name__ == "__main__":
    unittest.main()
