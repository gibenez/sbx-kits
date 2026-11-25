"""Black-box wrapper tests: real Bash wrapper, fake external sbx, no sandbox/network.

Run with: python3 -m unittest discover -s pi-dev/tests -v
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


WRAPPER = Path(__file__).resolve().parents[1] / "wrapper" / "pi"
FAKE_SBX = r'''#!PYTHON
import json
import os
from pathlib import Path
import sys

args = sys.argv[1:]
with open(os.environ["FAKE_SBX_LOG"], "a") as log:
    log.write(json.dumps(args) + "\n")
version_call = args[0] == "exec" and "-c" in args and args[args.index("-c") + 2:] == ["pi", "--version"]
metadata = (args[0] == "ls" or (args[0] == "run" and "-d" in args)
            or (args[0] == "exec" and ("pi-sbx-check" in args or version_call)))
if metadata:
    if "--no-input" not in args:
        raise SystemExit("metadata/provisioning must disable sbx prompts")
    if sys.stdin.buffer.read():
        raise SystemExit("metadata/provisioning consumed protocol stdin")
if args[0] == "ls":
    sys.stdout.write(os.environ.get("FAKE_SBX_LS", ""))
    sys.stderr.write(os.environ.get("FAKE_SBX_LS_ERROR", ""))
    sys.exit(int(os.environ.get("FAKE_SBX_LS_STATUS", "0")))
if args[0] == "run" and "-d" in args:
    print("CREATE OUTPUT MUST NOT REACH PROTOCOL STDOUT")
    sys.exit(int(os.environ.get("FAKE_SBX_CREATE_STATUS", "0")))
if args[0] == "exec" and "pi-sbx-check" in args:
    status = int(os.environ.get("MOCK_MOUNT_FAIL", "0"))
    if status:
        sys.stderr.write("fake missing shared mount\n")
    elif not os.environ.get("MOCK_MOUNT_NO_WRITE"):
        Path(args[-1]).write_text("shared\n")
    sys.exit(status)
if version_call:
    sys.stdout.write(os.environ.get("FAKE_SBX_VERSION", "1.2.3\n"))
    sys.stderr.write(os.environ.get("FAKE_SBX_VERSION_ERROR", ""))
    sys.exit(int(os.environ.get("FAKE_SBX_VERSION_STATUS", "0")))
if args[0] == "exec":
    sys.stdout.buffer.write(sys.stdin.buffer.read())
    sys.stdout.buffer.flush()
    sys.stderr.write("fake pi diagnostic\n")
    sys.exit(int(os.environ.get("FAKE_SBX_LAUNCH_STATUS", "0")))
if args[0] == "run":
    sys.exit(int(os.environ.get("FAKE_SBX_LAUNCH_STATUS", "0")))
raise SystemExit("unexpected fake sbx invocation: " + repr(args))
'''


class WrapperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pi-wrapper-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cwd = self.root / "A project_!"
        self.cwd.mkdir()
        self.home = self.root / "home"
        self.home.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "sbx.jsonl"
        self.cache = self.root / "version-cache"
        self.state = self.root / "state"
        self.name = "pi-A-project"
        sbx = self.bin / "sbx"
        sbx.write_text(FAKE_SBX.replace("#!PYTHON", "#!" + sys.executable))
        sbx.chmod(0o755)
        # Catch accidental package-manager use rather than permitting network I/O.
        for command in ("npm", "npx", "node", "curl", "wget"):
            executable = self.bin / command
            executable.write_text(
                '#!/bin/sh\nprintf "%s\\n" "$0" >> "$FORBIDDEN_LOG"\nexit 97\n'
            )
            executable.chmod(0o755)
        self.env = {
            "PATH": str(self.bin) + os.pathsep + os.defpath,
            "HOME": str(self.home),
            "PWD": str(self.cwd),
            "XDG_STATE_HOME": str(self.root / "xdg-state"),
            "SBX_PI_VERSION_CACHE_DIR": str(self.cache),
            "SBX_PI_STATE_DIR": str(self.state),
            "FAKE_SBX_LOG": str(self.log),
            "FORBIDDEN_LOG": str(self.root / "forbidden.log"),
        }

    def setup_existing(self, env):
        """Model provenance written by an earlier successful wrapper creation."""
        name = env.get("SBX_PI_SANDBOX_NAME", self.name)
        skills = Path(env.get("SBX_PI_SKILLS_DIR", str(Path(env["HOME"]) / ".agents" / "skills")))
        skills.mkdir(parents=True, exist_ok=True)
        state_root = Path(env.get("SBX_PI_STATE_DIR", str(Path(env["XDG_STATE_HOME"]) / "pi-sbx")))
        state = state_root / name
        (state / "sessions").mkdir(parents=True, exist_ok=True)
        (state / ".skills-source").write_text(str(skills.resolve()) + "\n")
        env.setdefault("FAKE_SBX_LS", name + " running\n")

    def run_wrapper(self, *args, stdin="", existing=False, **env):
        env = {**self.env, **env}
        if existing:
            self.setup_existing(env)
        result = subprocess.run(
            [str(WRAPPER), *args], cwd=self.cwd,
            env=env, input=stdin, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10,
        )
        self.assertFalse((self.root / "forbidden.log").exists(),
                         "wrapper invoked a package manager/network tool")
        return result

    def calls(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def seed_cache(self, text="1.2.3\n", name=None):
        self.cache.mkdir(exist_ok=True)
        path = self.cache / ((name or self.name) + ".version")
        path.write_text(text)
        return path

    def assert_offline(self):
        self.assertEqual(self.calls(), [], "offline operation invoked sbx")
        self.assertFalse(self.state.exists())
        self.assertFalse((self.home / ".agents").exists())
        self.assertFalse((self.root / "xdg-state").exists())

    def test_cached_version_is_offline_for_both_aliases(self):
        self.seed_cache("1.2.3\nignored second line\n")
        for flag in ("--version", "-v"):
            with self.subTest(flag=flag):
                result = self.run_wrapper(flag)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "1.2.3\n")
                self.assertEqual(result.stderr, "")
                self.assert_offline()


    def test_missing_or_invalid_cache_is_offline_and_unavailable(self):
        for value in (None, "", "pi 1.2.3\n", "1.2\n", "1.2.3 garbage\n", "01.2.3\n",
                      "1.2.3-01\n", "1.2.3-rc..1\n", "1.2.3+build..1\n"):
            with self.subTest(value=value):
                path = self.cache / (self.name + ".version")
                if path.exists():
                    path.unlink()
                if value is not None:
                    self.seed_cache(value)
                result = self.run_wrapper("--version")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertIn("version unavailable", result.stderr.lower())
                self.assert_offline()

    def test_version_accepts_semver_prerelease_and_build_metadata(self):
        self.seed_cache("2.0.0-rc.1+build.42\n")
        result = self.run_wrapper("--version")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "2.0.0-rc.1+build.42\n")
        self.assert_offline()

    def test_version_override_selects_only_named_cache(self):
        self.seed_cache("1.0.0\n")
        self.seed_cache("2.3.4\n", name="custom-box")
        result = self.run_wrapper("-v", SBX_PI_SANDBOX_NAME="custom-box")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "2.3.4\n")
        self.assert_offline()

    def test_clear_version_is_offline_and_preserves_other_caches(self):
        chosen = self.seed_cache()
        other = self.seed_cache("9.0.0\n", name="other")
        for _ in range(2):
            result = self.run_wrapper("--sbx-clear-version")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertFalse(chosen.exists())
            self.assertEqual(other.read_text(), "9.0.0\n")
            self.assert_offline()

    def test_clear_version_honors_sandbox_override(self):
        original = self.seed_cache()
        chosen = self.seed_cache(name="custom-box")
        result = self.run_wrapper("--sbx-clear-version", SBX_PI_SANDBOX_NAME="custom-box")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(chosen.exists())
        self.assertTrue(original.exists())
        self.assert_offline()

    def launches(self):
        return [args for args in self.calls()
                if args[0] in ("run", "exec") and "-d" not in args
                and not ("-c" in args and args[args.index("-c") + 2:] == ["pi", "--version"])
                and "pi-sbx-check" not in args]

    def creations(self):
        return [args for args in self.calls() if args[0] == "run" and "-d" in args]

    def assert_option(self, args, option, value):
        self.assertIn(option, args)
        self.assertEqual(args[args.index(option) + 1], value)

    def test_creation_mounts_configurable_skills_readonly_and_state(self):
        skills = self.root / "shared skills with spaces"
        skills.mkdir()
        result = self.run_wrapper(
            "hello", SBX_PI_SKILLS_DIR=str(skills),
            SBX_PI_KIT="git+https://example.invalid/custom#dir=kit",
            SBX_PI_LLMAPI_DOMAIN="llm.example.invalid",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.calls()[0], ["ls", "--no-input"])
        self.assertEqual(len(self.creations()), 1)
        create = self.creations()[0]
        self.assertIn("--no-input", create)
        self.assert_option(create, "--name", self.name)
        self.assertIn("git+https://example.invalid/custom#dir=kit", create)
        self.assertIn("llmapi_domain=llm.example.invalid", create)
        self.assertIn(str(self.cwd), create)
        self.assertIn(str(skills.resolve()) + ":/mnt/pi-host-skills:ro", create)
        state = str(self.state / self.name)
        self.assertTrue(any(state in arg for arg in create), create)
        self.assertTrue((self.state / self.name).is_dir())
        self.assertEqual("/var/folders/_j" in create, Path("/var/folders/_j").is_dir())
        final = self.launches()[-1]
        self.assertIn("PI_CODING_AGENT_DIR=/home/agent/.pi/agent", " ".join(create + final))
        self.assert_option(final, "--skill", "/mnt/pi-host-skills")
        self.assert_option(final, "--workdir", str(self.cwd))

    def test_default_kit_and_default_skills_mount(self):
        skills = self.home / ".agents" / "skills"
        skills.mkdir(parents=True)
        result = self.run_wrapper("hello")
        self.assertEqual(result.returncode, 0, result.stderr)
        create = self.creations()[0]
        self.assertIn("git+https://github.com/gibenez/sbx-kits.git#dir=pi-dev", create)
        self.assertIn("llmapi_domain=your.llmapi.domain", create)
        self.assertIn(str(skills) + ":/mnt/pi-host-skills:ro", create)

    def test_tui_keeps_native_arguments_as_individual_argv(self):
        args = ["--model", "provider/model", "--session", "session with spaces",
                "a prompt with 'quotes' and $dollars; $(touch NEVER)", "", "--", "--mode", "rpc"]
        result = self.run_wrapper(*args, existing=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.creations(), [])
        final = self.launches()[-1]
        self.assertEqual(final[0], "run")
        self.assertNotIn("--no-input", final)
        self.assertEqual(final[-len(args):], args)
        self.assert_option(final, "--name", self.name)
        self.assert_option(final, "--workdir", str(self.cwd))
        self.assertIn("PI_CODING_AGENT_DIR=/home/agent/.pi/agent", " ".join(final))
        self.assertFalse((self.cwd / "NEVER").exists())

    def test_rpc_preserves_protocol_and_exit_status_without_tty(self):
        protocol = '{"id":"a","type":"get_state"}\n{"id":"b","type":"abort"}\n'
        result = self.run_wrapper("--mode", "rpc", "--model", "a model", stdin=protocol,
                                  FAKE_SBX_LAUNCH_STATUS="23")
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertEqual(result.stdout, protocol)
        self.assertIn("fake pi diagnostic", result.stderr)
        final = self.launches()[-1]
        self.assertEqual(final[0], "exec")
        self.assertIn("-i", final)
        self.assertIn("--no-input", final)
        self.assertNotIn("-t", final)
        self.assertNotIn("-it", final)
        self.assert_option(final, "--workdir", str(self.cwd))
        self.assertIn(self.name, final)
        self.assertIn("bash", final)
        self.assertIn("-c", final)
        script = final[final.index("-c") + 1]
        self.assertIn('exec pi "$@"', script)
        self.assertTrue("source " in script or ". " in script, script)
        self.assertIn("PI_CODING_AGENT_DIR=/home/agent/.pi/agent", " ".join(final))
        self.assert_option(final, "--skill", "/mnt/pi-host-skills")
        self.assertEqual(final[-4:], ["--mode", "rpc", "--model", "a model"])

    def test_prompt_mode_payload_is_not_rpc(self):
        for args in (["--prompt", "--mode rpc"], ["--", "--mode", "rpc"],
                     ["say --mode rpc literally"]):
            with self.subTest(args=args):
                result = self.run_wrapper(*args, existing=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                final = self.launches()[-1]
                self.assertEqual(final[0], "run")
                self.assertEqual(final[-len(args):], args)

    def test_version_after_approval_prefix_is_offline(self):
        self.seed_cache("9.9.9\n")
        result = self.run_wrapper("--approve", "--version")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "9.9.9\n")
        self.assert_offline()

    def test_version_used_as_option_value_or_after_delimiter_is_not_shortcut(self):
        self.seed_cache("9.9.9\n")
        for args in (["--system-prompt", "--version"], ["--", "--version"]):
            with self.subTest(args=args):
                result = self.run_wrapper(*args, existing=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertEqual(self.calls()[-1][-len(args):], args)

    def test_existing_sandbox_is_not_created_and_cache_is_updated_before_launch(self):
        cache = self.seed_cache("0.1.0\n")
        result = self.run_wrapper("hello", existing=True,
                                  FAKE_SBX_VERSION="3.4.5\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.creations(), [])
        self.assertEqual(cache.read_text(), "3.4.5\n")
        calls = self.calls()
        self.assertEqual(calls[0], ["ls", "--no-input"])
        versions = [i for i, call in enumerate(calls)
                    if call[0] == "exec" and "--version" in call]
        self.assertEqual(len(versions), 1)
        self.assertLess(versions[0], len(calls) - 1)

    def test_ls_failure_is_not_treated_as_missing_sandbox(self):
        result = self.run_wrapper("hello", FAKE_SBX_LS_STATUS="7",
                                  FAKE_SBX_LS_ERROR="sbx unavailable\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [["ls", "--no-input"]])
        self.assertEqual(result.stdout, "")

    def test_refresh_existing_sandbox_prints_and_caches_raw_version(self):
        result = self.run_wrapper("--sbx-refresh-version",
                                  FAKE_SBX_LS=self.name + " running\n",
                                  FAKE_SBX_VERSION="4.5.6\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "4.5.6\n")
        self.assertEqual((self.cache / (self.name + ".version")).read_text(), "4.5.6\n")
        self.assertEqual(self.calls()[0], ["ls", "--no-input"])
        self.assertEqual(self.creations(), [])
        self.assertEqual(self.launches(), [])
        self.assertEqual([p.name for p in self.cache.iterdir()], [self.name + ".version"])

    def test_refresh_missing_sandbox_does_not_create_and_invalidates_cache(self):
        cache = self.seed_cache()
        result = self.run_wrapper("--sbx-refresh-version")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.calls(), [["ls", "--no-input"]])
        self.assertFalse(cache.exists())

    def test_refresh_rejects_banner_invalid_output_and_execution_failure(self):
        for output, status in (("pi 1.2.3\n", "0"), ("banner\n1.2.3\n", "0"),
                               ("1.2.3\nbanner\n", "0"), ("1.2\n", "0"),
                               ("", "0"), ("1.2.3\n", "9")):
            with self.subTest(output=output, status=status):
                cache = self.seed_cache()
                result = self.run_wrapper("--sbx-refresh-version",
                                          FAKE_SBX_LS=self.name + " running\n",
                                          FAKE_SBX_VERSION=output,
                                          FAKE_SBX_VERSION_STATUS=status)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertFalse(cache.exists())
                self.assertEqual(self.creations(), [])
                self.assertEqual(self.launches(), [])


    def test_no_skills_aliases_preserve_caller_choice_in_both_routes(self):
        for flag in ("--no-skills", "-ns"):
            for mode in ([], ["--mode", "rpc"]):
                with self.subTest(flag=flag, mode=mode):
                    result = self.run_wrapper(*mode, flag,
                                              existing=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    final = self.launches()[-1]
                    self.assertNotIn("--skill", final)
                    self.assertIn(flag, final)

    def test_rpc_in_home_refuses_missing_sandbox_before_provisioning(self):
        result = self.run_wrapper("--mode", "rpc", HOME=str(self.cwd))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.calls(), [["ls", "--no-input"]])
        self.assertFalse(self.state.exists())
        self.assertFalse((self.cwd / ".agents").exists())

    def test_rpc_stages_external_resources_preserving_basename_and_content(self):
        external = self.root / "external resources"
        external.mkdir()
        instructions = external / "instructions.md"
        extension = external / "my-extension.ts"
        instructions.write_text("Follow these project instructions.\n")
        extension.write_text("export default function extension() {}\n")
        staged_paths = []
        for _ in range(2):
            result = self.run_wrapper(
                "--mode", "rpc", "--append-system-prompt", str(instructions),
                "--extension", str(extension),
                existing=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            final = self.launches()[-1]
            launch_paths = []
            for flag, original in (("--append-system-prompt", instructions),
                                   ("--extension", extension)):
                staged = Path(final[final.index(flag) + 1])
                self.assertNotEqual(staged, original)
                self.assertTrue(staged.is_relative_to(self.state / self.name))
                self.assertEqual(staged.name, original.name)
                self.assertEqual(staged.read_bytes(), original.read_bytes())
                launch_paths.append(staged)
            staged_paths.append(launch_paths)
        self.assertNotEqual(staged_paths[0], staged_paths[1],
                            "resources should be snapshots isolated per launch")

    def test_rpc_maps_explicit_host_skill_and_preserves_session_and_fork(self):
        skills = self.root / "custom skills"
        skill = skills / "review skill" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("# Review\n")
        original = ["--session", "session id with spaces", "--fork", "fork destination"]
        result = self.run_wrapper("--mode", "rpc", "--skill", str(skill), *original,
                                  SBX_PI_SKILLS_DIR=str(skills),
                                  existing=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        final = self.launches()[-1]
        self.assertIn("/mnt/pi-host-skills/review skill/SKILL.md", final)
        self.assertNotIn(str(skill), final)
        self.assert_option(final, "--session-dir", str(self.state / self.name / "sessions"))
        self.assertEqual(final[-len(original):], original)

    def test_rpc_preserves_explicit_session_directory_without_duplicate(self):
        custom = str(self.cwd / "my sessions")
        result = self.run_wrapper("--mode", "rpc", "--session-dir", custom,
                                  existing=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        final = self.launches()[-1]
        self.assertEqual(final.count("--session-dir"), 1)
        self.assert_option(final, "--session-dir", custom)

    def test_default_state_root_uses_xdg_state_home(self):
        del self.env["SBX_PI_STATE_DIR"]
        result = self.run_wrapper("--mode", "rpc")
        self.assertEqual(result.returncode, 0, result.stderr)
        state = self.root / "xdg-state" / "pi-sbx" / self.name
        self.assertTrue(state.is_dir())
        self.assertIn(str(state), self.creations()[0])
        self.assert_option(self.launches()[-1], "--session-dir", str(state / "sessions"))

    def test_skills_symlink_is_resolved_before_mounting(self):
        skills = self.root / "real skills"
        skills.mkdir()
        link = self.root / "linked skills"
        link.symlink_to(skills, target_is_directory=True)
        result = self.run_wrapper("hello", SBX_PI_SKILLS_DIR=str(link))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(skills) + ":/mnt/pi-host-skills:ro", self.creations()[0])

    def test_ls_requires_exact_sandbox_name_not_prefix(self):
        result = self.run_wrapper("hello", FAKE_SBX_LS=self.name + "-other running\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.creations()), 1)


    def test_refresh_replaces_cache_atomically_instead_of_truncating_old_file(self):
        cache = self.seed_cache("0.1.0\n")
        # An already-open reader must continue to see the complete old record.
        # This observes replacement through the filesystem rather than relying
        # on a particular temporary filename or mv implementation.
        with cache.open() as previous_record:
            result = self.run_wrapper("--sbx-refresh-version",
                                      FAKE_SBX_LS=self.name + " running\n",
                                      FAKE_SBX_VERSION="7.8.9\n")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(previous_record.read(), "0.1.0\n")
        self.assertEqual(cache.read_text(), "7.8.9\n")

    def test_failed_normal_launch_version_refresh_removes_stale_cache(self):
        cache = self.seed_cache("0.1.0\n")
        result = self.run_wrapper("hello", existing=True,
                                  FAKE_SBX_VERSION="banner not a version\n")
        self.assertFalse(cache.exists())
        # Whether startup continues or aborts on metadata failure is not part
        # of this contract; it must never advertise the stale cached version.
        self.assertEqual(result.stdout, "")

    def test_failed_refresh_ls_removes_stale_cache_without_creation(self):
        cache = self.seed_cache()
        result = self.run_wrapper("--sbx-refresh-version", FAKE_SBX_LS_STATUS="7")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.calls(), [["ls", "--no-input"]])
        self.assertFalse(cache.exists())


    def test_existing_sandbox_missing_shared_mounts_fails_before_pi_spawn(self):
        for mode in ([], ["--mode", "rpc"]):
            with self.subTest(mode=mode):
                self.log.unlink(missing_ok=True)
                result = self.run_wrapper(*mode, existing=True,
                                          MOCK_MOUNT_FAIL="1")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertIn("mount", result.stderr.lower())
                self.assertEqual(self.creations(), [])
                self.assertEqual(self.launches(), [])
                self.assertFalse(any("--version" in call for call in self.calls()))
                self.assertFalse(list((self.state / self.name).glob(".mount-check.*")))

    def test_package_commands_remain_first_without_injected_skill(self):
        for args in (["install", "npm:example"], ["remove", "npm:example"],
                     ["update"], ["list"], ["config"]):
            with self.subTest(args=args):
                result = self.run_wrapper(*args, existing=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                final = self.launches()[-1]
                self.assertEqual(final[0], "run")
                self.assertEqual(final[final.index("--") + 1:], args)


    def test_rpc_maps_host_skills_root_with_trailing_slash(self):
        skills = self.root / "shared skills"
        skills.mkdir()
        result = self.run_wrapper(
            "--mode", "rpc", "--no-skills", "--skill", str(skills) + "/",
            SBX_PI_SKILLS_DIR=str(skills), existing=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        final = self.launches()[-1]
        self.assertEqual(final.count("--skill"), 1)
        self.assert_option(final, "--skill", "/mnt/pi-host-skills")
        self.assertFalse(list((self.state / self.name).glob("resources.*")))

    def test_rpc_stages_relative_external_resources_outside_workspace(self):
        external = self.root / "outside resources"
        external.mkdir()
        instruction = external / "instructions.md"
        extension = external / "extension.ts"
        instruction.write_text("# External instructions\n")
        extension.write_text("export default () => {};\n")
        result = self.run_wrapper(
            "--mode", "rpc", "--append-system-prompt", "../outside resources/instructions.md",
            "--extension", "../outside resources/extension.ts",
            existing=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        final = self.launches()[-1]
        for flag, original in (("--append-system-prompt", instruction),
                               ("--extension", extension)):
            staged = Path(final[final.index(flag) + 1])
            self.assertTrue(staged.is_relative_to(self.state / self.name))
            self.assertEqual(staged.name, original.name)
            self.assertEqual(staged.read_bytes(), original.read_bytes())

    def test_rpc_rejects_recursive_resource_snapshot_containing_state(self):
        external = self.root / "external tree"
        external.mkdir()
        result = self.run_wrapper(
            "--mode", "rpc", "--extension", str(external),
            SBX_PI_STATE_DIR=str(external / "wrapper state"),
            existing=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("state", result.stderr.lower())
        self.assertEqual(self.launches(), [])
        self.assertFalse(list((external / "wrapper state" / self.name).glob("resources.*")))


    def test_require_existing_refuses_creation_without_local_side_effects(self):
        for mode in ([], ["--mode", "rpc"]):
            with self.subTest(mode=mode):
                self.log.unlink(missing_ok=True)
                cache = self.seed_cache()
                result = self.run_wrapper(*mode, SBX_PI_REQUIRE_EXISTING="1")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertEqual(self.calls(), [["ls", "--no-input"]])
                self.assertFalse(cache.exists())
                self.assertFalse(self.state.exists())
                self.assertFalse((self.home / ".agents").exists())
                self.assertFalse((self.root / "xdg-state").exists())

    def test_require_existing_allows_both_routes_to_existing_sandbox(self):
        for mode in ([], ["--mode", "rpc"]):
            with self.subTest(mode=mode):
                self.log.unlink(missing_ok=True)
                result = self.run_wrapper(
                    *mode, SBX_PI_REQUIRE_EXISTING="1",
                    existing=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.creations(), [])
                self.assertEqual(len(self.launches()), 1)
                self.assertEqual(self.launches()[0][0], "exec" if mode else "run")
                self.assertEqual((self.cache / (self.name + ".version")).read_text(), "1.2.3\n")


    def test_existing_sandbox_without_skills_source_record_fails_closed(self):
        for mode in ([], ["--mode", "rpc"]):
            with self.subTest(mode=mode):
                self.log.unlink(missing_ok=True)
                result = self.run_wrapper(*mode, FAKE_SBX_LS=self.name + " running\n")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertEqual(self.creations(), [])
                self.assertEqual(self.launches(), [])
                self.assertIn("record", result.stderr.lower())

    def test_existing_sandbox_rejects_changed_skills_source_after_creation(self):
        first = self.run_wrapper("hello")
        self.assertEqual(first.returncode, 0, first.stderr)
        source_record = self.state / self.name / ".skills-source"
        self.assertEqual(source_record.read_text(), str((self.home / ".agents" / "skills").resolve()) + "\n")
        self.log.unlink()
        changed = self.root / "different skills"
        changed.mkdir()
        result = self.run_wrapper("hello", SBX_PI_SKILLS_DIR=str(changed),
                                  FAKE_SBX_LS=self.name + " running\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.creations(), [])
        self.assertEqual(self.launches(), [])
        self.assertIn("skill", result.stderr.lower())

    def test_mount_preflight_requires_sandbox_write_visible_on_host(self):
        result = self.run_wrapper("--mode", "rpc", existing=True, MOCK_MOUNT_NO_WRITE="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.creations(), [])
        self.assertEqual(self.launches(), [])
        self.assertIn("mount", result.stderr.lower())
        self.assertFalse(list((self.state / self.name).glob(".mount-check.*")))

    def test_rpc_rejects_final_resource_symlink_to_ancestor_containing_state(self):
        ancestor = self.root / "external ancestor"
        ancestor.mkdir()
        secret = ancestor / "host-secret.txt"
        secret.write_text("This must never be copied into shared resources.\n")
        alias = self.cwd / "linked-resource"
        alias.symlink_to(ancestor, target_is_directory=True)
        state = ancestor / "wrapper state"
        result = self.run_wrapper("--mode", "rpc", "--extension", str(alias),
                                  SBX_PI_STATE_DIR=str(state), existing=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.launches(), [])
        self.assertIn("state", result.stderr.lower())
        self.assertFalse(list((state / self.name).glob("resources.*")))
        self.assertFalse(list(state.rglob(secret.name)))

    def test_rpc_directory_snapshot_preserves_nested_symlink_without_copying_target(self):
        resource = self.root / "external extension"
        resource.mkdir()
        entrypoint = resource / "extension.ts"
        entrypoint.write_text("export default () => {};\n")
        # This ancestor includes the wrapper state and a private host secret.
        # Dereferencing it during cp would recursively copy both into state.
        (self.root / "host-secret.txt").write_text("private\n")
        nested = resource / "ancestor"
        nested.symlink_to(self.root, target_is_directory=True)
        result = self.run_wrapper("--mode", "rpc", "--extension", str(resource), existing=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        final = self.launches()[-1]
        staged = Path(final[final.index("--extension") + 1])
        self.assertTrue(staged.is_relative_to(self.state / self.name))
        self.assertEqual((staged / entrypoint.name).read_bytes(), entrypoint.read_bytes())
        self.assertTrue((staged / nested.name).is_symlink())
        self.assertEqual(os.readlink(staged / nested.name), os.readlink(nested))
        self.assertEqual(sorted(p.name for p in staged.iterdir()), ["ancestor", "extension.ts"])

    def test_self_update_invalidates_cached_version_without_pre_update_refresh(self):
        cache = self.seed_cache("1.0.0\n")
        result = self.run_wrapper("update", existing=True, FAKE_SBX_VERSION="1.1.0\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(cache.exists())
        self.assertFalse(any("--version" in call for call in self.calls()))
        final = self.launches()[-1]
        self.assertEqual(final[final.index("--") + 1:], ["update"])

    def test_export_option_values_do_not_trigger_version_shortcut_or_rpc(self):
        for args in (["--export", "--version"], ["--export", "--mode", "rpc"]):
            with self.subTest(args=args):
                self.log.unlink(missing_ok=True)
                self.seed_cache("9.9.9\n")
                result = self.run_wrapper(*args, existing=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "")
                final = self.launches()[-1]
                self.assertEqual(final[0], "run")
                self.assertEqual(final[-len(args):], args)

    def test_rpc_preserves_version_like_export_value_without_offline_shortcut(self):
        args = ["--mode", "rpc", "--export", "--version"]
        protocol = '{"type":"get_state"}\n'
        self.seed_cache("9.9.9\n")
        result = self.run_wrapper(*args, existing=True, stdin=protocol)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, protocol)
        final = self.launches()[-1]
        self.assertEqual(final[0], "exec")
        self.assertEqual(final[-len(args):], args)


if __name__ == "__main__":
    unittest.main()
