"""Execute the CI SSH wrapper offline; a fake ssh receives only synthetic secrets."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


class NativeSSH(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.bash = ("C:/Program Files/Git/bin/bash.exe" if os.name == "nt" else shutil.which("bash"))
        if not cls.bash or not Path(cls.bash).is_file():
            raise unittest.SkipTest("bash unavailable: native SSH wrapper requires offline shell verification")

    def run_wrapper(self, ssh_exit):
        tmp = tempfile.TemporaryDirectory(dir=self.root / "news" / "out")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        binaries, scratch, capture = [root / name for name in ("bin", "scratch", "capture")]
        for folder in (binaries, scratch, capture):
            folder.mkdir()
        fake = binaries / "ssh"
        fake.write_text(
            '#!/usr/bin/env bash\nset -eu\n'
            'printf "%s\\0" "$@" > "$CAPTURE/args"\n'
            'cat > "$CAPTURE/stdin"\n'
            'while [ "$#" -gt 0 ]; do\n'
            '  case "$1" in\n'
            '    -i) cp "$2" "$CAPTURE/key"; shift;;\n'
            '    UserKnownHostsFile=*) cp "${1#*=}" "$CAPTURE/known";;\n'
            '  esac\n'
            '  shift\n'
            'done\nexit "$FAKE_EXIT"\n', encoding="utf-8", newline="\n")
        fake.chmod(0o755)
        values = {"DEPLOY_SHA": "synthetic sha with spaces", "NEWS_TAG": "tag;echo injected",
                  "GHCR_USER": "synthetic'user", "GHCR_TOKEN": "fake $(touch INJECTED) `echo unsafe`\nsecond line"}
        env = {**os.environ, **values, "VPS_HOST": "example.invalid", "VPS_USER": "synthetic",
               "VPS_SSH_KEY": "SYNTHETIC KEY\nsecond line", "VPS_HOST_KEY": "ssh-ed25519 SYNTHETIC",
               "CAPTURE": capture.as_posix(), "TMPDIR": scratch.as_posix(), "FAKE_EXIT": str(ssh_exit),
               "FAKE_BIN": binaries.as_posix(), "WRAPPER": (self.root / "deploy" / "ci-ssh.sh").as_posix()}
        bootstrap = ('if command -v cygpath >/dev/null; then FAKE_BIN=$(cygpath -u "$FAKE_BIN"); fi; '
                     'export PATH="$FAKE_BIN:$PATH"; '
                     '[[ $(command -v ssh) == "$FAKE_BIN/ssh" ]] || exit 98; source "$WRAPPER"')
        result = subprocess.run([self.bash, "-c", bootstrap],
                                env=env, cwd=root, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, ssh_exit, result.stderr.decode(errors="replace"))
        self.assertEqual(list(scratch.iterdir()), [], "temporary private key/known_hosts leaked")
        self.assertFalse((root / "INJECTED").exists())
        args = (capture / "args").read_bytes().decode().rstrip("\0").split("\0")
        self.assertIn("StrictHostKeyChecking=yes", args)
        self.assertIn("BatchMode=yes", args)
        self.assertIn("IdentitiesOnly=yes", args)
        self.assertIn("-T", args)
        self.assertEqual(args[-3:], ["synthetic@example.invalid", "bash", "-s"])
        self.assertEqual((capture / "key").read_text(), env["VPS_SSH_KEY"] + "\n")
        self.assertEqual((capture / "known").read_text(), "example.invalid ssh-ed25519 SYNTHETIC\n")
        payload = (capture / "stdin").read_text()
        for secret in (values["GHCR_TOKEN"], env["VPS_SSH_KEY"]):
            self.assertNotIn(secret, result.stdout.decode(errors="replace"))
            self.assertNotIn(secret, result.stderr.decode(errors="replace"))
        exports = "\n".join(payload.splitlines()[:4])
        # Evaluate only the exported assignments, never the remote deploy commands.
        probe = exports + '\nprintf "%s\\0" "$DEPLOY_SHA" "$NEWS_TAG" "$GHCR_USER" "$GHCR_TOKEN"\n'
        decoded = subprocess.run([self.bash, "-c", probe], cwd=root, env=env,
                                 capture_output=True, timeout=10, check=True)
        self.assertEqual(decoded.stdout.decode().rstrip("\0").split("\0"), list(values.values()))
        self.assertFalse((root / "INJECTED").exists(), "export quoting executed token content")
        self.assertIn("git -C /opt/hockey-platform diff --quiet", payload)
        self.assertIn("git -C /opt/hockey-platform diff --cached --quiet", payload)
        self.assertIn('git -C /opt/hockey-platform switch --detach "$DEPLOY_SHA"', payload)
        self.assertIn("--password-stdin", payload)
        self.assertIn("docker logout ghcr.io", payload)
        self.assertIn('NEWS_TAG="$NEWS_TAG" bash /opt/hockey-platform/deploy/deploy.sh', payload)

    def test_exports_are_quoted_host_verified_and_temporary_credentials_cleaned(self):
        self.run_wrapper(0)

    def test_remote_ssh_failure_is_propagated_and_credentials_still_cleaned(self):
        self.run_wrapper(37)
