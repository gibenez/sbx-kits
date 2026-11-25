"""Exercise the opt-in checker with a local protocol stub, never real sbx."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SMOKE = Path(__file__).with_name("smoke_rpc.py")
STUB = r'''#!PYTHON
import json
import os
from pathlib import Path
import sys
import time

assert os.environ.get("SBX_PI_REQUIRE_EXISTING") == "1"
assert os.environ.get("SBX_PI_SANDBOX_NAME") == "existing-test"
assert sys.argv[1:] == ["--mode", "rpc", "--offline"]
mode = os.environ.get("SMOKE_STUB_MODE", "ok")
print("PRIVATE_DIAGNOSTIC_DO_NOT_ECHO", file=sys.stderr)
if mode == "timeout":
    time.sleep(10)
if mode == "bad-json":
    print("PRIVATE_NON_JSON_DO_NOT_ECHO", flush=True)
    sys.exit(0)
for _ in range(2):
    command = json.loads(sys.stdin.buffer.readline())
    assert command["type"] in ("get_state", "get_commands")
    if command["type"] == "get_state":
        data = {"sessionFile": os.environ["SMOKE_SESSION_FILE"]}
    else:
        data = {"commands": [{"name": "skill:review", "source": "skill"}]}
    print(json.dumps({"type": "response", "id": command["id"],
                      "success": True, "data": data}), flush=True)
assert sys.stdin.buffer.read() == b"", "checker sent a model prompt"
'''


class SmokeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pi-smoke-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.stub = self.root / "wrapper"
        self.stub.write_text(STUB.replace("#!PYTHON", "#!" + sys.executable))
        self.stub.chmod(0o755)
        self.env = dict(os.environ, SMOKE_SESSION_FILE=str(self.root / "session.jsonl"))

    def run_smoke(self, *args, **env):
        result = subprocess.run(
            [sys.executable, str(SMOKE), "--wrapper", str(self.stub),
             "--project", str(self.root), "--sandbox", "existing-test", *args],
            env={**self.env, **env}, capture_output=True, text=True, timeout=8,
        )
        self.assertNotIn("PRIVATE_", result.stdout + result.stderr)
        return result

    def test_discovers_skill_without_message_and_closes_stdin(self):
        result = self.run_smoke("--expect-skill", "review")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("1 skills loaded", result.stdout)
        self.assertFalse((self.root / "session.jsonl").exists(),
                         "checker must not require a pre-message session file")

    def test_missing_expected_skill_fails(self):
        result = self.run_smoke("--expect-skill", "missing")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expected skill", result.stderr)

    def test_protocol_pollution_fails_without_echoing_data(self):
        result = self.run_smoke(SMOKE_STUB_MODE="bad-json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("non-JSON", result.stderr)

    def test_timeout_stops_local_child(self):
        result = self.run_smoke("--timeout", "0.1", SMOKE_STUB_MODE="timeout")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("timed out", result.stderr)

    def test_session_parent_must_be_host_visible(self):
        result = self.run_smoke(SMOKE_SESSION_FILE=str(self.root / "missing" / "session.jsonl"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("host-visible", result.stderr)


if __name__ == "__main__":
    unittest.main()
