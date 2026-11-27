# pi-dev

Quick install on the host (requires `sbx`, `curl`, and `sudo`):

```bash
curl -fsSL https://raw.githubusercontent.com/gibenez/sbx-kits/main/pi-dev/install.sh | bash
```

The installer asks for your LLM API domain, offering the existing environment value (or a literal value already in your shell configuration) as the default. It detects your login shell via `$SHELL` and saves `SBX_PI_LLMAPI_DOMAIN` in `~/.zshrc` or `~/.bashrc`, backing up an existing file to the same path with `.pi-sbx.bak` appended. Open a new shell or run the printed `source` command, set your API key with `sbx secret set llmapi`, then run `pi` from your project directory. If your orchestrator does not load your shell configuration, set the variable in its environment too. This installs the published wrapper and uses the published remote kit.

To update an installed wrapper that already supports the command, run this from a terminal:

```bash
pi --sbx-update
```

This reruns the published installer above: it prompts for your LLM API domain and uses `sudo` to replace `/usr/local/bin/pi`. It does not start a sandbox or update Pi inside one. If you installed the wrapper to a different path manually, replace that copy manually; this command still installs to `/usr/local/bin/pi`. For an older wrapper without this command, use the quick-install command above once.

A sandbox development kit for the Pi terminal coding agent, with:

- Generic LLM API support (API key only, no OAuth).
- Host-managed skills shared read-only with the sandbox.
- The `pi-subagents-lite` extension for lightweight subagents with isolated sessions, tools, and models.

## Install and configure the host wrapper

Install `sbx` on the execution host, clone this repository, and install the wrapper as `pi` somewhere on that host's `PATH`:

```bash
mkdir -p "$HOME/.local/bin"
install -m 755 /absolute/path/to/sbx-kits/pi-dev/wrapper/pi "$HOME/.local/bin/pi"
export PATH="$HOME/.local/bin:$PATH"

sbx secret set llmapi
export SBX_PI_LLMAPI_DOMAIN="your.llmapi.domain"
# Until these changes are published, use this checkout's kit:
# From this repository's root:
export SBX_PI_KIT="$PWD/pi-dev"
```

Persist the exports in your shell configuration or set them in the environment that launches your orchestrator. Use the wrapper's absolute path as the Pi executable if the orchestrator does not inherit your shell's `PATH`. The wrapper is a host program; it invokes the actual Pi inside the sandbox.

`SBX_PI_KIT` defaults to the published remote kit, `git+https://github.com/gibenez/sbx-kits.git#dir=pi-dev`. **Changing this checkout does not change that published kit.** Point `SBX_PI_KIT` at this local `pi-dev` directory until the updated kit is published. Existing sandboxes are not recreated or migrated just because this value changes.

Configuration:

| Variable | Purpose |
| --- | --- |
| `SBX_PI_KIT` | Kit reference used when creating a sandbox; defaults to the remote Git reference above. |
| `SBX_PI_LLMAPI_DOMAIN` | LLM API domain supplied as the kit's `llmapi_domain` argument. Set before creating a sandbox. |
| `SBX_PI_SKILLS_DIR` | Optional host skill root; defaults to `$HOME/.agents/skills`. Custom locations must also be discoverable by your host UI if you need a pre-session skill picker. |
| `SBX_PI_VERSION_CACHE_DIR` | Optional version-cache directory; defaults to `${XDG_CACHE_HOME:-$HOME/.cache}/pi-sbx/versions`. Separate from session/resource state. |
| `SBX_PI_STATE_DIR` | Optional state root; defaults to `${XDG_STATE_HOME:-$HOME/.local/state}/pi-sbx`. Its per-sandbox `NAME` directory is shared read-write at the same absolute path for mount records and staged resources. Older wrappers also stored RPC sessions here; those files are left untouched. |
| `SBX_PI_SANDBOX_NAME` | Optional sandbox-name override, useful for selecting a known sandbox identity. It does not mount a different current directory into an existing sandbox. |
| `SBX_PI_REQUIRE_EXISTING` | Set to `1` to forbid provisioning during normal launches. Used by the opt-in live smoke test. |
| `PI_CODING_AGENT_DIR` | Host Pi account root used to locate discoverable sessions; defaults to `$HOME/.pi/agent`. Must be absolute and match the account root Orca scans. Only the current project's session bucket is mounted; sandbox Pi still uses its private `/home/agent/.pi/agent` for config/auth. |

## Install skills once, on the host

The canonical global skill store is **`~/.agents/skills`** (plural `agents`). New sandboxes no longer run skill installers or maintain private kit-installed skill copies. The unrelated `pi-subagents-lite` extension is still installed inside the sandbox.

Run these optional installers **on the host**, not inside Pi's sandbox, to install the collections previously installed by the kit:

```bash
# Requires host Node/npm, curl, and jq. Inspect upstream sources before running.
npx -y skills@latest add mattpocock/skills -g -y $(curl -s https://raw.githubusercontent.com/mattpocock/skills/main/.claude-plugin/plugin.json | jq -r '.skills[] | split("/") | last' | xargs -n1 printf -- '-s %s ')
npx -y skills@latest add https://github.com/only-cli/oc -g -y --skill web-browsing-cli
npx -y skills@latest add https://github.com/microsoft/playwright-cli -g -y --skill playwright-cli
```

Check that each intended skill's full directory, including `SKILL.md`, scripts, references, and assets, is present under the canonical host root. Do not assume an installer-specific agent symlink elsewhere is the authoritative copy.

The wrapper creates the host skill directory if missing during a normal launch, then shares it into newly created sandboxes as `HOST_ROOT:/mnt/pi-host-skills:ro`. It supplies `--skill /mnt/pi-host-skills` for both TUI and RPC sessions unless `--no-skills` (or `-ns`) was requested. Package/auth subcommands retain their original command-first argv without injected resource flags. New kits also include `~/.pi/agent/settings.json` with `{"skills":["/mnt/pi-host-skills"]}` so Pi launched directly inside the sandbox, including subagents using its normal settings, can discover the shared root. Pi's loader deduplicates the repeated path. Normal Pi skill discovery remains enabled: project skills and other Pi defaults are not disabled. A read-only mount is not an update/synchronization job; manage these skills on the host. Restart/reload Pi as appropriate after host changes; a host UI's cached catalog may need its own refresh or a new Pi session.

Important boundaries:

- Mounting files does **not** install their runtime dependencies. Skills may require interpreters, binaries, libraries, browsers, credentials, or network permissions inside the sandbox. The Playwright skill describes installing its CLI on first use; that is not a guarantee of browser or runtime availability.
- Symlink targets must also be visible inside the sandbox. Links into an unmounted host cache will be broken. Absolute paths embedded in skills must make sense inside the sandbox too.
- The sandbox cannot update the shared read-only store. Scripts that write beside themselves need a separate writable working/output directory.
- Host UI discovery and sandbox Pi discovery are distinct. Seeing a skill in a pre-session host picker does not prove sandbox loading or script execution works. On a paired/remote UI, the relevant host is the execution runtime, not necessarily the laptop displaying the UI.
- Duplicate skill names are not a supported override mechanism. Adding `--skill` does not guarantee host priority over an existing same-name sandbox/project skill.

The fixed target is intentional: `sbx` documents that additional mount targets must be absolute POSIX paths, distinct from the primary workspace and reserved skills paths (with additional restrictions in clone mode). `/mnt/pi-host-skills` is an ordinary additional target rather than a default agent skills directory. This explicit bind of your existing host store is separate from `sbx`'s built-in `--skills` facility/shared skill store; configuring one does not migrate or populate the other. See [Docker's multiple-workspace mount documentation](https://docs.docker.com/ai/sandboxes/usage/#multiple-workspaces). Mount acceptance and actual resource discovery still need verification with your installed versions.

### Existing sandbox migration is explicit

The wrapper does **not** delete existing skills, uninstall packages, rewrite existing mounts, or recreate sandboxes automatically. An older sandbox may retain its private installed skills and lack both `/mnt/pi-host-skills` and the same-path per-sandbox state mount. **Existing sandboxes require explicit migration before relying on shared skills, staged resources, or host-readable RPC sessions.** Merely reattaching one does not retrofit either mount or the new kit settings. Normal startup refuses a sandbox without the wrapper's `.skills-source` and `.sessions-dir` records in shared state. It verifies the configured paths still match those records, checks the skills target is an actual read-only Linux mount, and checks that temporary markers in both state and the session bucket are readable and writable from both sides. **Sandboxes created by the earlier shared-state wrapper also need migration:** they lack the additional host Pi session-bucket mount. No kit/image change is required solely for this additional mount, but changing the installed wrapper cannot retrofit it.

Before migrating, inspect and back up the existing sandbox's skills and other state. Manually reconcile any desired private skills into the host's canonical tree, resolve same-name conflicts, and check supporting files and symlinks. Then explicitly create a fresh sandbox through the updated wrapper with the updated local/published kit. For example, use `SBX_PI_SANDBOX_NAME=pi-project-shared pi` from the project to leave the old sandbox intact while validating the new one. Merely editing a mount record does not migrate a sandbox. For normal Orca launches, eventually migrate the default sandbox name or supply the matching workspace-specific override; do not globally point every project at the temporary test sandbox. Only remove old private copies or old sandboxes after verifying the shared versions and preserving any needed sessions/state. No automated deletion is provided.

#### Preserve earlier conversations

Stop active chats/TUIs before copying transcripts, and back up sandbox-private state before replacing any sandbox. Earlier RPC transcripts remain under `${SBX_PI_STATE_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/pi-sbx}/OLD_NAME/sessions/`; older TUI transcripts remain inside the old sandbox under `/home/agent/.pi/agent/sessions/` (normally in encoded cwd buckets).

After explicitly creating the replacement through this wrapper, read its `.sessions-dir` record to find the new host bucket. Copy only the desired project's `.jsonl` transcripts there, retaining filenames, never overwriting a different existing transcript, and keeping the originals/backups. Inspect each transcript's session-header `cwd` to select the right project; do not copy every sandbox's files into one bucket. For TUI transcripts, export them from the old sandbox first using your installed `sbx` tooling. Do not copy sandbox auth/settings or make the whole host account writable in the sandbox. This wrapper does not perform historical imports automatically.

Orca can then discover those copies in its history scan. Already-open Orca tabs may still point at the original path; keep the original files/state until those tabs are closed and the imported sessions have been verified. Avoid continuing both copies of the same session independently.

## Launch Pi

From the project directory:

```bash
pi                  # Native interactive TUI
pi --mode rpc       # JSONL RPC for a host orchestrator
pi --print "Summarize this project"  # One-shot generation, without a PTY
```

The primary shared workspace is the current directory. Sandbox names default to `pi-` plus a sanitized basename of that directory; use `SBX_PI_SANDBOX_NAME` to select a known identity or avoid basename collisions. `/var/folders/_j` is included as an extra mount only when that host directory exists; it is not a destination for the project mount. Workspace, skill, and state paths must not contain colons because the mount syntax uses them as separators.

Metadata/provisioning calls use `--no-input` and closed stdin so they cannot consume queued RPC requests or prompt for setup interactively. Final native interactive launch uses `sbx run --workdir "$PWD"` to preserve the TUI route. RPC and explicit `--print`/`-p` generation use `sbx exec -i --workdir "$PWD"` without `-t`, so neither requests a PTY. This includes Orca's auto-naming invocation (`--print --no-session --no-tools --no-skills --no-context-files --mode text`), whose prompt arrives through stdin. The wrapper forwards stdin, stdout, stderr, and exit status without filtering generated text. `--mode text` alone does not force print mode and retains the native TUI route; literal `--print` values and arguments after `--` do not change routing. Because exec does not automatically source the persistent environment, its command runs Bash, sources `/etc/sandbox-persistent.sh` if readable with setup output redirected to stderr, then uses `exec pi` with the prepared arguments. Version refresh uses that same bootstrap. Both launch routes explicitly set `PI_CODING_AGENT_DIR=/home/agent/.pi/agent`; the host account directory is not forwarded.

An RPC or explicit print invocation from the host home directory refuses to create a missing sandbox, avoiding a context-free background invocation accidentally provisioning one with the entire home as its workspace. It can still attach to an existing selected sandbox. This guard does not apply to native TUI launches; launch those from the intended project directory.

One-shot print calls do not receive the shared session-directory option or resource rewriting below. In particular, Orca's `--no-session` auto-naming calls do not persist a naming conversation. Print transport itself only requires a wrapper update; the shared history mount described below requires explicit migration of existing sandboxes.

### Shared session history and explicit RPC launch resources

Orca Chat's `/resume [search]` opens Orca's Agent Session History, not Pi's TUI picker. Orca discovers Pi transcripts by scanning the host Pi sessions root, with encoded cwd buckets for workspace filtering. A host-readable session at an arbitrary path is not automatically discoverable.

On creation, the wrapper mounts only the current project's real session bucket read-write at the same resolved absolute host path:

```text
${PI_CODING_AGENT_DIR:-$HOME/.pi/agent}/sessions/--encoded-project-path--/
```

The encoding matches Pi: strip the first leading slash from cwd, replace slash/backslash/colon with `-`, and wrap in `--`. Both native TUI and RPC launches receive `--session-dir` pointing to this bucket. Their lead-session transcripts therefore share the same host-visible, Orca-discoverable storage. This does not redirect independently launched Pi processes or subagents that choose their own storage. Only this bucket is exposed, not host auth/config or all projects' history. The bucket must not be a symlink: Orca's directory walker skips symlink entries.

The host account root must agree with the environment/configuration of the Orca execution runtime doing the scan; this may be a remote host rather than the UI laptop. Switching workspace/account on an existing sandbox is refused because it cannot retarget the existing mount. An explicit `--session-dir` is passed unchanged in both routes and must already be sandbox-visible; custom directories opt out of the default discovery layout.

The wrapper also mounts `SBX_PI_STATE_DIR/NAME` read-write for mount records and staged resources, separately from transcripts.

For RPC only, the wrapper processes explicit `--extension`/`-e`, `--skill`, `--prompt-template`, `--theme`, `--system-prompt`, and `--append-system-prompt` arguments:

- Paths under the canonical host skill root are translated to `/mnt/pi-host-skills`.
- Existing paths in the workspace or shared per-sandbox state are passed through.
- Other existing host files/directories are copied into a per-launch resources directory under the shared state mount, and the argument is rewritten to that snapshot. The requested root's symlink is resolved, but links within copied directories are preserved, not recursively dereferenced. A resource containing the state directory is rejected to prevent recursive copying.
- Nonexistent host paths and inline values are passed unchanged; that does not make an otherwise unmounted sandbox path available.

This is **scoped delivery of explicit RPC launch arguments**, not automatic skill-picker propagation or a live mirror of all host resources. Snapshots do not track subsequent host edits. A single extension file's sibling imports, dependencies outside a copied directory, absolute embedded paths, and required runtimes are not inferred or staged automatically. Native TUI launch does not perform this resource staging. Both host session buckets and wrapper state (including older transcripts and resource snapshots) are sensitive application data; inspect them before any manual cleanup.

Host bridge environment variables, socket access, and dynamic integration dependencies are not generally forwarded or solved by this wrapper. These remain live integration blockers to check, alongside stdin/stdout fidelity, EOF/cancellation, terminal behavior, skill loading, and script execution. Setup/probe diagnostics belong on stderr, not JSONL stdout. No live `sbx`/Orca compatibility test has been performed here.

### Version probes and cache

Every normal launch except the potentially self-updating `pi update` command, after sandbox creation if needed and before handing off to Pi, obtains the installed sandbox Pi version using the actual `pi --version` through `sbx exec` and records it on the host. A wrapper invocation of `pi --version` reads the cache immediately: it does not call `sbx`, create/start a sandbox, or query npm/the network. If no applicable cached installed version is known, it exits nonzero with a diagnostic on stderr instead of inventing a version.

The cache can become stale after a manual in-sandbox Pi upgrade or sandbox replacement/removal outside this wrapper. Refresh it through a normal wrapper launch, or use the maintenance commands:

```bash
pi --sbx-refresh-version  # Existing sandbox only: read actual Pi version, cache, print
pi --sbx-clear-version    # Offline: invalidate the selected cached version
```

Each maintenance command must be the sole argument. Cache-only `--version` (or `-v`) also works after built-in prefix options such as `--approve`; option values and arguments after `--` are not mistaken for version requests. Normal session startup attempts a fresh version read; if it fails, the old cached version is invalidated, a warning goes to stderr, and launch continues without version metadata. `pi update` invalidates the cache instead of recording a version immediately before it might change. Refresh explicitly or launch a new session afterward.

Use the same project directory or `SBX_PI_SANDBOX_NAME` override to select the intended sandbox. Refresh does not create a missing sandbox, but `sbx exec` may start a stopped one. A plain `--version` probe never creates even the host skill directory. Do not treat an npm registry `latest` response as the installed sandbox version. A cached version is not proof that RPC or skills work with your installed Pi, `sbx`, and orchestrator versions.

## Orca model picker before the first message

Set Orca’s Pi **Command** to the updated wrapper’s absolute path, with no prefix arguments. When Orca runs `--mode rpc --no-session` from the host home directory, the wrapper answers `get_state` and `get_available_models` itself. It never calls `sbx` on this route, rejects prompts, and doesn’t need host Pi or any new mount. Workspace chats still run real Pi in their normal sandboxes.

The catalog is read from `files/home/.pi/agent/models.json` under `SBX_PI_KIT`. The published kit uses GitHub `main`; a public GitHub kit with `#ref=...&dir=...` uses the specified revision and directory. A local kit directory is read directly. The GitHub route requires host `python3` and `curl` on Orca’s PATH (a local kit only needs `python3`). GitHub catalogs are cached for one hour under `${XDG_CACHE_HOME:-$HOME/.cache}/pi-sbx/catalogs`; if a refresh fails, the last valid catalog for that URL is used. Only picker fields are returned and cached, not credentials, endpoints, or headers.

The picker shows what the kit declares, not whether a particular existing sandbox has those models or working credentials. Once a chat acquires Pi, its live model list comes from the sandbox. This route does not change `pi --version` or claim a sandbox Pi version.

On this kit's Anthropic Messages route, Pi sends a token budget for the Qwen thinking levels, not a named provider effort. The Qwen entries request up to 32,768 total output tokens so Pi's 16,384-token `high` thinking budget leaves room for the answer. The gateway may enforce a lower limit.

## Validation

Run the offline regression suite from this repository's root:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s pi-dev/tests -v
bash -n pi-dev/wrapper/pi
```

The suite uses fake `sbx` executables and local protocol stubs: it never creates a real sandbox, invokes a package manager, or proves Orca compatibility.

After explicitly creating/migrating a test sandbox using the updated wrapper and local kit, run the opt-in live check:

```bash
python3 pi-dev/tests/smoke_rpc.py \
  --project /absolute/path/to/project \
  --sandbox pi-project-shared \
  --expect-skill research
```

Replace the sandbox and skill names with ones you actually prepared. This invokes the wrapper with `SBX_PI_REQUIRE_EXISTING=1`, sends only `get_state` and `get_commands`, checks the expected skill and a host-visible session parent, then checks EOF shutdown. **It may start the existing sandbox, execute its startup adapters, load extensions, and write state, but it never provisions a missing sandbox or sends a model prompt.** It uses `--offline` to suppress Pi's automatic network activity; extensions/startup hooks are independent. A session file need not exist before the first message, so the check verifies its parent, not a fabricated transcript. Potentially sensitive subprocess diagnostics are not echoed. For detailed failures, inspect the direct wrapper invocation locally and redact secrets before sharing logs.

Finally verify in your installed Orca:

1. Configure Pi's Command to the installed wrapper's absolute path, with the intended wrapper environment. Use the normal New Chat UI, not a custom launcher.
2. Before sending any message, open the skill picker and confirm a host skill appears.
3. Send a trusted skill request; verify it reads `/mnt/pi-host-skills` and runs any supporting scripts inside the sandbox with the required dependencies.
4. In a fresh Pi chat, open the model picker before sending a message. Confirm it shows the kit’s models, and that no home-directory sandbox was created. Confirm version probes still complete promptly.
5. Send a message in Chat, close it, and use `/resume` from another chat in the same workspace; confirm the saved conversation appears and continues. Create a native TUI session through the wrapper and verify it also appears. Verify imported older transcripts separately. Test stdin EOF, SIGTERM, and absence of orphaned sandbox Pi processes. The smoke check's local exit alone does not prove remote cleanup.

No live `sbx` or Orca check was run in the implementation environment because `sbx` was unavailable. macOS Bash 3 compatibility is intended but was not executed here. Source investigations and pinned references are in [research/orca-chat-investigation.md](research/orca-chat-investigation.md) and [research/orca-skill-propagation.md](research/orca-skill-propagation.md).
