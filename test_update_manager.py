import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import update_manager
from update_manager import UpdateError, UpdateInfo, parse_version, release_update


def release(tag, url="https://github.com/Erikselimi/CrosshairSlight/releases/download/v1.1.0/Sightline.exe"):
    return {
        "tag_name": tag,
        "assets": [{
            "name": "Sightline.exe",
            "browser_download_url": url,
            "size": 1_000_000,
            "digest": "sha256:" + "a" * 64,
        }],
    }


class UpdateManagerTests(unittest.TestCase):
    def test_versions_compare_as_numeric_components(self):
        self.assertGreater(parse_version("v1.10.0"), parse_version("v1.9.9"))
        with self.assertRaises(UpdateError):
            parse_version("latest")

    def test_newer_release_exposes_its_exe_and_checksum(self):
        update = release_update(release("v1.1.0"), current_version="1.0.0")

        self.assertIsNotNone(update)
        self.assertEqual(update.version, "1.1.0")
        self.assertEqual(update.sha256, "a" * 64)

    def test_same_or_older_release_is_not_an_update(self):
        self.assertIsNone(release_update(release("v1.0.0"), current_version="1.0.0"))
        self.assertIsNone(release_update(release("v0.9.0"), current_version="1.0.0"))

    def test_release_must_include_the_expected_executable_and_trusted_url(self):
        invalid_asset = release("v1.1.0", "https://example.com/Sightline.exe")
        with self.assertRaisesRegex(UpdateError, "download URL"):
            release_update(invalid_asset, current_version="1.0.0")

        missing_asset = release("v1.1.0")
        missing_asset["assets"] = []
        with self.assertRaisesRegex(UpdateError, "no Sightline.exe"):
            release_update(missing_asset, current_version="1.0.0")

    def test_download_is_staged_only_after_size_and_checksum_match(self):
        executable = b"test exe bytes"
        update = UpdateInfo(
            "1.1.0",
            "v1.1.0",
            "https://github.com/Erikselimi/CrosshairSlight/releases/download/v1.1.0/Sightline.exe",
            len(executable),
            hashlib.sha256(executable).hexdigest(),
        )

        class FakeResponse(io.BytesIO):
            def geturl(self):
                return update.download_url

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                self.close()

        with tempfile.TemporaryDirectory() as folder, patch.object(
            update_manager.urllib.request, "urlopen", return_value=FakeResponse(executable)
        ):
            staged = update_manager.download_update(update, Path(folder))
            self.assertEqual(staged.read_bytes(), executable)
            self.assertEqual(staged.name, "Sightline-1.1.0.new.exe")

    def test_download_rejects_bad_checksum(self):
        update = UpdateInfo(
            "1.1.0",
            "v1.1.0",
            "https://github.com/Erikselimi/CrosshairSlight/releases/download/v1.1.0/Sightline.exe",
            3,
            "0" * 64,
        )

        class FakeResponse(io.BytesIO):
            def geturl(self):
                return update.download_url

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                self.close()

        with tempfile.TemporaryDirectory() as folder, patch.object(
            update_manager.urllib.request, "urlopen", return_value=FakeResponse(b"exe")
        ):
            with self.assertRaisesRegex(UpdateError, "SHA-256"):
                update_manager.download_update(update, Path(folder))
            self.assertEqual(list(Path(folder).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
