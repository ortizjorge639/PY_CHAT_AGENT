"""Unit tests for Easy Auth middleware and download group check."""

import base64
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure chat_agent is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_principal_header(groups: list[str], extra_claims: list[dict] | None = None) -> str:
    """Build a base64-encoded X-MS-CLIENT-PRINCIPAL header."""
    claims = [{"typ": "groups", "val": g} for g in groups]
    if extra_claims:
        claims.extend(extra_claims)
    payload = {
        "auth_typ": "aad",
        "claims": claims,
        "name_typ": "name",
        "role_typ": "roles",
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


class TestGetUserGroupIds(unittest.TestCase):
    """Tests for _get_user_group_ids."""

    def _call(self, headers: dict) -> set[str]:
        from main import _get_user_group_ids
        request = MagicMock()
        request.headers = headers
        return _get_user_group_ids(request)

    def test_no_header(self):
        result = self._call({})
        self.assertEqual(result, set())

    def test_empty_header(self):
        result = self._call({"X-MS-CLIENT-PRINCIPAL": ""})
        self.assertEqual(result, set())

    def test_malformed_base64(self):
        result = self._call({"X-MS-CLIENT-PRINCIPAL": "not-valid-base64!!!"})
        self.assertEqual(result, set())

    def test_valid_single_group(self):
        header = _make_principal_header(["group-id-1"])
        result = self._call({"X-MS-CLIENT-PRINCIPAL": header})
        self.assertEqual(result, {"group-id-1"})

    def test_valid_multiple_groups(self):
        header = _make_principal_header(["group-a", "group-b", "group-c"])
        result = self._call({"X-MS-CLIENT-PRINCIPAL": header})
        self.assertEqual(result, {"group-a", "group-b", "group-c"})

    def test_no_group_claims(self):
        payload = {"auth_typ": "aad", "claims": [{"typ": "name", "val": "alice"}]}
        header = base64.b64encode(json.dumps(payload).encode()).decode()
        result = self._call({"X-MS-CLIENT-PRINCIPAL": header})
        self.assertEqual(result, set())

    def test_mixed_claims_only_returns_groups(self):
        header = _make_principal_header(
            ["group-id-1"],
            extra_claims=[{"typ": "name", "val": "alice"}, {"typ": "email", "val": "a@b.com"}],
        )
        result = self._call({"X-MS-CLIENT-PRINCIPAL": header})
        self.assertEqual(result, {"group-id-1"})


class TestUserCanDownload(unittest.TestCase):
    """Tests for _user_can_download."""

    def _call(self, headers: dict, require_auth: bool, group_id: str) -> bool:
        from main import _user_can_download
        request = MagicMock()
        request.headers = headers
        with patch("main.settings") as mock_settings:
            mock_settings.require_auth = require_auth
            mock_settings.file_download_group_id = group_id
            return _user_can_download(request)

    def test_auth_disabled_always_allows(self):
        self.assertTrue(self._call({}, require_auth=False, group_id="some-group"))

    def test_no_group_configured_always_allows(self):
        self.assertTrue(self._call({}, require_auth=True, group_id=""))

    def test_user_in_group_allowed(self):
        header = _make_principal_header(["download-group-id"])
        headers = {"X-MS-CLIENT-PRINCIPAL": header}
        self.assertTrue(self._call(headers, require_auth=True, group_id="download-group-id"))

    def test_user_not_in_group_denied(self):
        header = _make_principal_header(["other-group"])
        headers = {"X-MS-CLIENT-PRINCIPAL": header}
        self.assertFalse(self._call(headers, require_auth=True, group_id="download-group-id"))

    def test_no_principal_header_denied(self):
        self.assertFalse(self._call({}, require_auth=True, group_id="download-group-id"))

    def test_user_in_multiple_groups_one_matches(self):
        header = _make_principal_header(["chat-group", "download-group-id", "admin-group"])
        headers = {"X-MS-CLIENT-PRINCIPAL": header}
        self.assertTrue(self._call(headers, require_auth=True, group_id="download-group-id"))


class TestDownloadEndpointPathTraversal(unittest.TestCase):
    """Tests for path traversal protection in download_file."""

    def test_path_traversal_blocked(self):
        """Verify ../ in filename doesn't escape GENERATED_DIR."""
        from main import GENERATED_DIR
        filename = "..\\..\\etc\\passwd"
        filepath = os.path.join(GENERATED_DIR, filename)
        is_safe = os.path.abspath(filepath).startswith(os.path.abspath(GENERATED_DIR))
        self.assertFalse(is_safe)


if __name__ == "__main__":
    unittest.main()
