import subprocess
import tempfile
import unittest
from pathlib import Path

from tools import release_version


class ReleaseVersionTests(unittest.TestCase):
    def test_changelog_version_excludes_unreleased_and_requires_semver(self):
        self.assertEqual(release_version.version("## [Unreleased]\n\n## [0.20.0] — today"), "v0.20.0")
        for text in ("## [Unreleased]", "## [$(malicious)]", "## [0.20]", "## [00.1.0]"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                release_version.version(text)

    def test_tag_collision_blocks_next_commit_and_same_commit_rerun_is_allowed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            def git(*args):
                return subprocess.check_output(["git", "-c", f"safe.directory={root.as_posix()}", *args],
                                               cwd=root, stderr=subprocess.STDOUT)

            git("init", "-q")
            git("config", "user.name", "Test")
            git("config", "user.email", "test@example.invalid")
            (root / "CHANGELOG.md").write_text("## [0.20.0]\n", encoding="utf-8")
            git("add", "CHANGELOG.md")
            git("commit", "-qm", "first")
            self.assertEqual(release_version.check(root), "v0.20.0")
            git("tag", "-a", "v0.20.0", "-m", "release")
            self.assertEqual(release_version.check(root), "v0.20.0")
            git("commit", "--allow-empty", "-qm", "second")
            with self.assertRaisesRegex(ValueError, "already exists"):
                release_version.check(root)


if __name__ == "__main__":
    unittest.main()
