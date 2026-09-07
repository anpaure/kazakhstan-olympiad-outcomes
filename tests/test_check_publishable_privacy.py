import io
import unittest
import zipfile
from uuid import UUID

from scripts.check_publishable_privacy import findings


class PublishablePrivacyTest(unittest.TestCase):
    def test_flags_local_paths_without_returning_the_contents(self):
        path = b"/Us" + b"ers/developer/project/file.py"
        result = findings(path)
        self.assertEqual(result, [{"kind": "local_home_path", "member": "", "line": 1}])
        self.assertNotIn("developer", str(result))

    def test_flags_windows_home_paths(self):
        path = b"C:\\Us" + b"ers\\developer\\project"
        self.assertEqual(findings(path)[0]["kind"], "local_home_path")

    def test_flags_embedded_exa_and_ga_secrets(self):
        for field in ("EXA_API_KEY", "api_secret", "x-api-key"):
            with self.subTest(field=field):
                payload = f'{field} = "{UUID(int=1)}"'.encode()
                self.assertEqual(findings(payload)[0]["kind"], "inline_api_secret")

    def test_allows_environment_references_and_public_measurement_ids(self):
        self.assertEqual(findings(b'key = os.environ["EXA_API_KEY"]'), [])
        self.assertEqual(findings(b'gtag("config", "G-GPDVHJ29G6")'), [])

    def test_inspects_workbook_xml(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("xl/sharedStrings.xml", b"/ho" + b"me/developer/project")
        result = findings(output.getvalue())
        self.assertEqual(result[0]["member"], "xl/sharedStrings.xml")
        self.assertEqual(result[0]["kind"], "local_home_path")

    def test_invalid_zip_does_not_hide_plaintext_findings(self):
        payload = b"PK\x03\x04" + b"/Us" + b"ers/developer/project"
        self.assertEqual(findings(payload)[0]["kind"], "local_home_path")


if __name__ == "__main__":
    unittest.main()
