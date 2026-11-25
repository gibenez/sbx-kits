#!/usr/bin/env python3
"""Opt-in live RPC check against an explicitly named, existing sandbox.

No prompt is sent. The wrapper may start the sandbox and its startup adapters,
load extensions, and create session/resource state. No sandbox is provisioned.
This verifies the wrapper/Pi pipe, not Orca's UI or remote-process cleanup.
"""

import argparse
import json
import os
from pathlib import Path
import selectors
import subprocess
import tempfile
import time


def check_rpc(wrapper, project, sandbox, expected_skill, timeout):
    env = dict(os.environ, SBX_PI_SANDBOX_NAME=sandbox, SBX_PI_REQUIRE_EXISTING="1")
    command = [str(wrapper), "--mode", "rpc", "--offline"]
    responses = {}
    deadline = time.monotonic() + timeout
    # Do not echo potentially sensitive extension/config diagnostics. This
    # unnamed temporary file is discarded on exit and cannot fill a stderr pipe.
    with tempfile.TemporaryFile() as diagnostics:
        process = subprocess.Popen(
            command, cwd=project, env=env, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=diagnostics,
        )
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                for name in ("get_state", "get_commands"):
                    process.stdin.write(json.dumps({"id": name, "type": name}).encode() + b"\n")
                process.stdin.flush()
                pending = b""
                while len(responses) < 2:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise RuntimeError("timed out waiting for RPC state/commands")
                    if not selector.select(remaining):
                        continue
                    chunk = os.read(process.stdout.fileno(), 65536)
                    if not chunk:
                        raise RuntimeError("wrapper exited before RPC discovery completed; check its configuration and mounts")
                    pending += chunk
                    if len(pending) > 8 * 1024 * 1024:
                        raise RuntimeError("RPC record exceeded smoke-test size limit")
                    while b"\n" in pending:
                        line, pending = pending.split(b"\n", 1)
                        try:
                            record = json.loads(line)
                        except (ValueError, UnicodeError):
                            raise RuntimeError("non-JSON data on RPC stdout") from None
                        if not isinstance(record, dict):
                            raise RuntimeError("non-object JSON on RPC stdout")
                        if record.get("type") != "response" or record.get("id") not in ("get_state", "get_commands"):
                            continue
                        if record.get("success") is not True:
                            raise RuntimeError("Pi rejected an RPC discovery request")
                        responses[record["id"]] = record.get("data", {})
            commands = responses["get_commands"].get("commands", [])
            skills = {entry.get("name") for entry in commands if entry.get("source") == "skill"}
            if expected_skill and "skill:" + expected_skill not in skills:
                raise RuntimeError("expected skill is absent from Pi's loaded RPC inventory")
            session = responses["get_state"].get("sessionFile")
            if not session or not Path(session).is_absolute() or not Path(session).parent.is_dir():
                raise RuntimeError("Pi did not return a session location with a host-visible parent directory")
            process.stdin.close()
            # Drain during orderly EOF shutdown so stdout backpressure cannot
            # cause a false timeout. No records are printed or model prompts sent.
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise RuntimeError("EOF shutdown timed out; verify remote Pi lifecycle")
                    if selector.select(remaining):
                        if not os.read(process.stdout.fileno(), 65536):
                            break
            status = process.wait(timeout=max(0.1, deadline - time.monotonic()))
            if status:
                raise RuntimeError("wrapper exited nonzero after EOF")
            print("PASS: RPC state and commands received without a prompt; %d skills loaded; EOF shutdown completed." % len(skills))
            print("Still verify Orca UI discovery, script dependencies, SIGTERM, and absence of orphaned sandbox processes.")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            process.stdout.close()
            if not process.stdin.closed:
                process.stdin.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wrapper", type=Path, default=Path(__file__).resolve().parents[1] / "wrapper" / "pi")
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--sandbox", required=True, help="explicit existing sandbox; never provisioned")
    parser.add_argument("--expect-skill", help="skill name without the skill: prefix")
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    try:
        check_rpc(args.wrapper.resolve(), args.project.resolve(), args.sandbox, args.expect_skill, args.timeout)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        parser.exit(1, "FAIL: %s\n" % error)


if __name__ == "__main__":
    main()
