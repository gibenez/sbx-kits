# Orca → Pi skill propagation: discovery, invocation, files, and execution hosts

## Scope and answer

This report answers the **ordinary Orca UI, before the first message** requirement. It does not recommend a custom launcher or the alternate CLI launch discussed in the earlier investigation. Sandbox-autonomous skills must remain usable; host-installed skills may take precedence for Chat, but that precedence must actually be established, not assumed.

Evidence: Orca commit **`a91fc0a676e324b2630a78bdc6d885f513cc9d88`**, inspected at `/tmp/orca-investigation.r3tw7h`; installed **Pi 1.6.0** primary docs and distribution source at `/usr/local/share/npm-global/lib/node_modules/@earendil-works/pi-coding-agent/`. Pi references below are relative to that package, **not proof of the user's sandbox Pi version**. Read the existing investigation §§9–12 first; this report is standalone and narrows their conclusions. No implementation, npm execution, authentication, Pi launch, sandbox execution/provisioning, or live integration test was performed.

**Bottom line:** Orca's pre-session skill picker is a catalog, not an installer into Pi's environment. For Pi, selecting an ordinary skill inserts **`/skill:<name>`**; submitting sends that text through Pi RPC. Pi then resolves the name against **its own loaded skills**, reads its selected `SKILL.md`, and supplies the instructions to the model. Scripts run only if the model subsequently invokes a tool. Built-in Pi shell/file tools operate in Pi's execution environment, not in the renderer merely because the skill was selected there. [O1–O5, P1–P3]

There are real Orca installation/upload and linked-resource mechanisms, so **“Orca never copies skills” would be false**. But the inspected Pi picker → prompt path does **not** copy a selected host skill directory into an arbitrary wrapper-hidden Docker sandbox, attach its Markdown contents, or add a per-selection `--skill` flag. Installed host skills can supply a pre-message menu without being usable by sandbox Pi; those are two separate conditions. [O1–O8, O12–O16]

Two particularly important corrections:

1. The supported shared directory is **`.agents/skills` (plural)**. Neither this Orca Pi scanner nor Pi's inspected automatic discovery uses **`.agent/skills` (singular)** as a default root. [O6, P4]
2. In inspected Pi 1.6.0, **`--skill` does not imply override precedence over automatically loaded same-name skills**. CLI skill paths are appended after normal resolved skills; name collisions keep the first. Host precedence is an acceptable requirement, **not a stock property verified here**. [P5]

## 1. Three different places called “local”

| Layer | Responsibility | Which files are visible? |
| --- | --- | --- |
| **Renderer/client** | Shows menu, receives catalogs, edits composer, sends input. Can be on a laptop connected to another Orca runtime. | Its own filesystem is not automatically the agent's filesystem. |
| **Owning Orca execution runtime/host** | Scans skill files, resolves selected install destination, prepares instructions/resources, launches Pi command and transports RPC. For paired remote Orca this is the server. | That runtime's home/workspace and explicitly supported execution targets. |
| **Wrapper-hidden `sbx` sandbox** | If the configured Pi executable delegates there, the actual Pi process and its ordinary tools run there. | Sandbox image/private files plus the runtime's actual documented mounts. A host path passed in argv is not a file transfer. |

Orca's remote-server documentation explicitly puts projects, sessions, terminals, and agents on the server; the client supplies UI/input. The native Chat discovery context routes a pane to its owning runtime, not arbitrarily to whichever global host is selected. The server's `skills.discover` handler resolves its own project runtime/provider roots and directly invokes the scanner. A further `sbx` wrapper is **not** a paired Orca runtime registration; it introduces another boundary Orca's native scanner does not thereby learn to traverse. [O7–O10]

“SSH host” is also ambiguous:

- A **managed/paired Orca server reached over a remote connection** has its own runtime APIs and resources. Its native scanner and installer can work on its server filesystem.
- A legacy **`executionHostId` of kind `ssh`** is a distinct code path. This pinned source marks SSH repository skill sources as `remote-repo`, refuses discovery for SSH workspaces in the host resolver, and explicitly refuses SSH install destinations with `skill-install-ssh-relay-unavailable`, explaining that managed hosts install as paired runtimes. Do not turn generic SSH/SFTP support into a claim of skill synchronization. [O9–O11]

The user-facing skill-sharing documentation still mentions selecting an SSH host. That is broader than the inspected implementation's refusal; for this pin the executable guard is stronger evidence of the route's actual availability. A real user's host type/build remains to be identified. [O11]

## 2. Normal UI, before a Pi child exists

A fresh normal UI Chat can be founded **at rest**, without starting Pi. Subscription and command-menu reads do not themselves acquire a Pi owner: founding commits the resting record, subscriptions explicitly do not start agents, and command reads return live/cached or optional at-rest data. [O21] Pi has no registered at-rest RPC command probe in this pin. Thus the ordinary pre-message menu can use **host filesystem discovery**, but cannot obtain a new private sandbox catalog merely by opening `/`. [O17]

The picker activates the skills hook, computes the pane's workspace/startup/pinned cwd and owning runtime, and calls `skills.discover`. Native cwd-targeted discovery scans with `repos: []`, so it is not a search across all registered projects. Pi's source profile admits its own roots plus shared owner-null roots. [O6–O9]

### Exact locations and installation destinations

| Path | Orca pre-session Pi scan | Pi 1.6.0 child discovery |
| --- | --- | --- |
| `~/.agents/skills/<name>/SKILL.md` | Shared host-home source. | Supported user Agent Skills root, in **Pi's** home. |
| `<cwd>/.agents/skills/<name>/SKILL.md` | Shared cwd/repository source for this scan. | Supported project root; Pi also searches ancestors up to repository root, trust-gated. |
| `~/.pi/agent/skills/<name>/SKILL.md` | Explicit, discovery-only **host-home Pi root**. | Default Pi user root; effective `<agentDir>/skills` can be changed by `PI_CODING_AGENT_DIR`. |
| `<cwd>/.pi/skills/...` | No corresponding Pi project entry in this source builder. | Supported Pi project resource root, trust-gated. |
| `~/.agent/skills` / `<cwd>/.agent/skills` | Not a supported default in this inspected scanner. | Not a supported default in the inspected discovery code/docs. An explicitly configured arbitrary path is different. |
| Other settings/package/explicit paths | Not a reproduction of Pi's full resource-loader algorithm. | Pi supports settings/package resources and repeatable `--skill`. Paths must exist for Pi. |

Sources: source construction [O6], Pi resource discovery/docs [P1, P4]. Do not infer that an ancestor-only skill Pi can find must be in Orca's cwd-only fallback scan.

**Orca's Skills installation UI is host-targeted, not sandbox-targeted.** It offers **Machine** (“This computer” or an available runtime), **Destination** (“Global skills” or “One workspace”), a workspace selector, agent choices, and an explicit WSL execution-environment choice when applicable. Selecting Pi uses the canonical root: global **`<selected runtime home>/.agents/skills`**, workspace **`<selected workspace>/.agents/skills`**. Pi's install-provider entry has null provider-specific path segments, so it does **not** default to `~/.pi/agent/skills`. The install resolves home/workspace identity on its authority, not by trusting an arbitrary client-side destination path. [O12–O13]

Changing the Pi command's environment or `PI_CODING_AGENT_DIR` does **not** relocate the scanner's hard-coded host `~/.pi/agent/skills` source. Conversely, Orca sets `PI_CODING_AGENT_DIR` for its Pi invocation; whether an `sbx` wrapper forwards/remaps that host value is unverified. Sandbox Pi can therefore have a different effective user-resource root from both the host scanner and the expected sandbox home. Home `.agents/skills` is a separate root. [O6, O18, P4]

## 3. Exact picker → prompt → Pi → tool chain

For an ordinary host-discovered skill called `research`:

1. **Discovery:** owning Orca runtime reads the skill summary/path from disk and returns a catalog. This provides name/description/scope metadata, not a promise that the future Pi child can read the same file. [O6–O9]
2. **Selection:** Pi's profile specifies `/` plus `skill:`. The picker applies its suggestion and may retain a path on its skill chip; it does not load/copy the package at selection. The Pi invocation token is `/skill:research`. [O1]
3. **Submission:** ordinary text blocks become the RPC `{type: 'prompt', message: ...}`. For this route, no selected-skill Markdown expansion or package upload is performed by Orca. A path retained for UI metadata is not an instruction to mount it, a per-skill process cwd, or an alternate Pi name-resolution mechanism. [O1–O2]
4. **Pi resource resolution:** the Pi child has already loaded its skill inventory from its effective directories/settings/packages/explicit paths. It does **not** look up the menu's host file by virtue of receiving that name. [P4–P5]
5. **Explicit invocation:** Pi detects text **starting** `/skill:research`, finds that name in its loaded list, reads that skill's `filePath`, strips frontmatter, and constructs `<skill name="..." location="...">References are relative to <baseDir> ...</skill>`, followed by optional user arguments. Unknown names or file-read failures leave the original text; receiving the token is not proof that expansion succeeded. [P2]
6. **Model/tool action:** the model follows those instructions and may call `read`, `bash`, etc. A skill is not a new executable handler or guaranteed script invocation. The built-in shell tool spawns its shell with Pi/tool-context cwd and environment; file tools resolve paths against that environment's cwd. With actual Pi inside the sandbox, these ordinary tool operations happen there. [P1–P3]

**Autonomous use remains separate:** Pi advertises loaded skill names/descriptions/locations in its system prompt and the model can read an appropriate `SKILL.md` without any menu selection. `disable-model-invocation` affects that advertisement, not forced `/skill:name` use. Merely adding a second host-visible catalog need not remove private sandbox skills; disabling all defaults would, however, require deliberate reintroduction of any desired resources. [P1, P5]

### Once Pi is acquired

Pi RPC `get_commands` returns loaded skills as `skill:<name>`, source `skill`. Orca retains name/description/kind, **not Pi's `sourceInfo`/file location**. Its renderer can show a reported skill even without any matching host file. For Pi, once a reported command array exists (even an empty one), its session-reported skills become authoritative rather than a permanent union with host-scanned skills. [O3–O5, P6]

Consequences:

- A private sandbox skill can be usable autonomously and appear **after acquisition** without a host copy.
- A host skill can appear **before acquisition** yet disappear or resolve differently when Pi loads its own catalog.
- The same menu name can initially describe a host version and ultimately invoke a different same-name sandbox version. Host display ranking is not Pi duplicate precedence. [O4–O5, P5]

Orca schedules `get_commands` after opening the session and reading options; its adapter subsequently returns a cached startup catalog. Reopening/retrying the menu does not, in this adapter, itself rescan Pi's resource loader or reissue `get_commands`. Later-installed skills therefore have separate **host scan**, **Pi resource reload**, and **Orca command-cache refresh** concerns. This matters for preserving autonomous skills installed later inside the actual project sandbox. [O17, P6; earlier investigation §12.5]

## 4. Ordinary selection is not the same as launch injection or installation

| Mechanism | What actually crosses/changes | Does it make arbitrary host skills available in a hidden sandbox? |
| --- | --- | --- |
| Ordinary Pi menu pick | `/skill:name` text; optional UI path metadata. | **No automatic transfer.** Pi resolves its own loaded name. |
| Pi autonomous discovery | Pi reads its own resource files and advertises metadata to model. | No host scan or host file required, provided sandbox resources are loaded. |
| Orca Pi launch-injected resources | Visuals skill root and bot-linked skill root become repeatable `--skill <root>`; standing instructions use `--append-system-prompt <file>`. | Path arguments, not copies into `sbx`. Every path and symlink target must be readable there. |
| Bot linked skills | Orca scans linked projects on its host and maintains skill-directory symlinks in a bot resource folder; instructions can instead index unloaded skill paths. | This is real resource preparation, but not a generic selected-skill copier or host→sandbox transport. |
| Explicit Skills install/share/update | Downloads/extracts a verified package and places files in the chosen host/workspace; may use remote upload fallback. | Yes, files are installed on the chosen runtime. It still does not penetrate an unrelated private `sbx` filesystem. |

Launch resolution obtains `basis.visuals()` and `basis.linkedSkills()`, not “every item the host picker discovered.” Non-bot chats have no bot linked-skill root. Linked-project instructions/indexes are additional model guidance, not ordinary picker-time content injection. An instruction file can contain paths without making the target files readable. [O8, O14–O15]

This is why the accurate claim is **“ordinary Pi selection sends a name, not a skill package”**, not “Orca never copies/synchronizes any skills or injects any instructions.”

## 5. Remote execution: catalog RPC, real file transport, and limits

### Paired Orca runtime discovery is remote filesystem discovery

For a remote runtime target, the global Skills client calls runtime RPC `skills.discover`; it does not forward the client's entire local inventory/WSL project target. The Chat picker uses pane ownership and can send that runtime its cwd/worktree identity. The **remote handler** resolves its execution context and calls `discoverSkillsOnTarget`; the native branch performs `discoverSkills` on the server. The native scanner uses filesystem canonicalization/stat/read operations there. Result metadata returns to the renderer. This is remote discovery, **not synchronization of the client's skill directory onto the server**. [O7–O10]

### Explicit install can transfer bytes

The inspected remote install flow is precise:

1. Client-side install orchestration calls the selected runtime's **`skills.install`** (or `skills.installBundle`) with a **download grant** and package identity. [O16]
2. On that runtime, the registered method invokes `runtime.installSharedSkillRequest`; its install ingress calls `downloadSkillPackageGrant` with a temporary directory under **that runtime's state directory**, validates the archive identity, then installs to its resolved destination. The ordinary path therefore downloads on the selected runtime, **not first into the client's installed skills tree**. [O9, O13, O16]
3. If the direct operation fails with the classified download-unavailable errors and the target advertises upload capability, fallback **downloads the archive on the client-side orchestrator**, then calls **`skills.beginUpload` → `skills.uploadChunk` (offset + base64 bytes) → `skills.commitUpload`** on the remote runtime. It then retries install using **`ingress: {kind: 'staged-upload', uploadId}`**, and cleans up through **`skills.cancelUpload`**. These are concrete file-transfer endpoints, not just metadata. Bundles have the analogous path. [O16]
4. Upload handlers stage and validate a package for explicit installation; they do not implement a watched mirror of all existing local skill roots. `skills.share` is also an explicit publishing operation, and the handler rejects publishing through a paired client; it says to run it on the machine storing the skills. [O9, O16]

### Other filesystem APIs exist, but are not a skill propagation contract

The runtime also registers `files.read`, `files.readChunk`, `files.readDir`, `files.browseServerDir`, `files.write`, `files.writeBase64`, `files.writeBase64Chunk`, `files.commitUpload`, and workspace-scoped create/copy/rename operations. Mutation calls delegate to the runtime's file explorer service with explicit SSH/host identity fences where applicable. These are real remote filesystem capabilities; their existence does **not** show that a Pi menu pick calls them, that `files.copy` means a cross-host recursive sync, or that any automatically bridges a hidden Docker filesystem. [O19]

**Bounded negative:** searching the skill discovery/install/upload/transfer RPC catalog, remote host paths, and Pi picker/launch flow found no separate automatic client↔execution-host mirror of arbitrary user skill directories, and no picker-triggered transfer into `sbx`. Explicit package install/upload, bot local symlink maintenance, bundled resource installation, and generic file APIs are positive mechanisms and should not be erased by a universal “no-copy” claim. Other agent-specific managed-home/hook configuration code is not evidence of a Pi skill mirror. [O9, O14–O16, O19]

Thus an ordinary remote Orca session works by **having the skills/resources on its execution runtime** (or explicitly installing them there), with the UI receiving a remote catalog. Being connected over SSH does not by itself propagate the laptop's existing skills; raw legacy SSH targets have the additional refusals above.

## 6. Skill text versus scripts, executables, and dependencies

A successful Markdown read proves only **instruction availability**. It does not prove that any bundled script, referenced binary, package manager, browser, credential, network permission, or runtime exists where tools run. Pi's own skill docs recommend bundled relative paths and declaring runtime dependencies. [P1]

For example, if a loaded skill says `scripts/extract.sh`, the model is told references are relative to the skill directory. It should use that base path (or explicitly `cd` there); selecting the skill does **not** change the session's cwd to that directory. The shell tool ordinarily starts in Pi/tool-context cwd. If instructions say `/Users/alice/.agents/skills/pdf/scripts/extract.sh`, that remains that absolute pathname as interpreted **inside the sandbox**—not an implicit request to execute on Alice's host. [P2–P3]

For a shared installation to work reliably:

- Share the **whole skill directory/package**, including `scripts/`, `references/`, assets, and required supporting files, not only `SKILL.md`. A name/description catalog or copied Markdown body is insufficient for bundled-file use. [P1]
- Inspect symlinks. A host skill directory that is a link into an npm/git/package cache outside the mount can be readable on the host but broken inside the sandbox. Orca's scanner canonicalizes files; Pi and bot-link loading also resolve links. Mounting only a directory of links does not export their targets. [O14, O20, P5]
- Mounting a skill's files does not install its interpreter or binaries. Shell/Python/Node executables and libraries must be available to sandbox tools; host `node_modules`/native executables can be OS/architecture/ABI-specific. Read-only mounts also cannot support scripts that write alongside themselves. These are execution prerequisites, not behavior promised by the picker. [P1–P3]
- A skill may instruct the agent to install dependencies when needed, but success still depends on sandbox network/permission policy and package availability; selecting it is not automatic dependency provisioning. The local kit explicitly installs skills separately from its runtime/dependency policy. [K1]

### What the documented `sbx` mounts establish—and do not

The checked-in wrapper creates a sandbox with **`"$PWD" /var/folders/_j`**. Docker's documented positional paths are shared directories: the first is the primary workspace/initial agent cwd; an additional bare path is shared at its same absolute path by default. These two arguments are **not a source/target pair**, and do not establish sharing arbitrary host home, Pi account, Orca application-data, skill-cache, or bot-link directories. [K1, D1]

Consequently host `<actual shared project>/.agents/skills` can be a single authoritative host-backed tree discoverable by the UI and readable by sandbox Pi, conditional on mounts/permissions/trust/cwd. That is bind sharing, **not copying at skill selection**. A global host root outside the mounts is not exposed merely because Orca scanned it. Additional mounts take host sources; the reviewed documentation does not turn private sandbox image/home files into a reverse-exported host discovery tree. Do not assume that reattaching an existing sandbox changes its mounts. [D1; existing investigation §§11–12]

Same-absolute-path mounting can preserve embedded paths; a different mount target requires corresponding path handling. JSONL RPC and `--skill` provide no general namespace translation. Actual mount contents, symlink targets, `HOME`, `PI_CODING_AGENT_DIR`, and cwd remain live-test facts, not inferred successes. [O8, O18, P3–P5, D1]

## 7. Duplicate names: host precedence is not automatic

Pi 1.6.0's ordinary CLI path is verifiable without running Pi:

1. `dist/main.js:637,689–699` resolves parsed `--skill` paths and passes them as **`additionalSkillPaths`** to its resource loader.
2. `dist/core/resource-loader.js:385–445` obtains resolved package/automatic enabled skills, then builds `skillPaths` as **`mergePaths([...cliEnabledSkills, ...enabledSkills], additionalSkillPaths)`** (unless `--no-skills`). Here `cliEnabledSkills` refers to skill resources from CLI **extension/package sources**, not the parsed `--skill` array.
3. `mergePaths` at `803–816` preserves first path order, canonicalizes/deduplicates paths; `updateSkillsFromPaths` at `645–656` invokes `loadSkills(... includeDefaults: false)` with that ordered list.
4. `dist/core/skills.js:324–350,369–386` keeps the **first name**, emits a collision diagnostic naming winner/loser for a later different file, and silently skips the same resolved file loaded through a link.

Therefore an automatic sandbox skill can beat a later host **`--skill`** namesake. Earlier explicit paths do not become higher priority simply because their argv spelling says `--skill`. Two host/sandbox files with the same name are not retained as independently addressable `/skill:name` versions. [P5]

`--no-skills` still permits explicitly supplied skills, but using it unconditionally would suppress normal automatic sandbox resource discovery—the very autonomy the user wants preserved. This report does not propose that as a solution. Establishing Chat-only host precedence while retaining autonomous sandbox discovery needs a deliberate, version-verified loading policy; the menu's ranking and host install target do not supply that policy. [P5, P7]

## 8. Implications for the requested normal-UI workflow

The source supports the following separation, **not a completed integration**:

- **Before first message:** host/runtime-visible `.agents/skills` or the scanner's Pi-home root can supply ordinary UI fallback entries. No custom launcher is required to obtain that **host catalog**. [O6–O7, O17]
- **At invocation:** those skills must also be loaded/readable by the actual sandbox Pi under the intended names. Pre-session visibility alone does not transport or register them. A mounted shared project tree is a documented possible bridge; private host-home files are not implicitly shared. [P2, P4–P5, K1, D1]
- **Autonomy:** sandbox-only skills can remain Pi resources and be selected by the model even without host UI visibility. They become UI-reported skills after successful acquisition/catalog read. Preserving private autonomous skills does not magically make their names visible in a new at-rest host menu. [P1, P6, O3–O5]
- **Precedence:** accepting host priority removes a policy objection, not the need to enforce it. Inspected `--skill` ordering does not enforce it. [P5]
- **Ordinary remote Orca:** install/discover on the actual execution runtime. Do not confuse the renderer's home, a paired server's home, legacy SSH inventory, and a nested `sbx` sandbox's home. [O7–O13]

### Unresolved facts / smallest future live checks (not performed)

1. Actual Orca and sandbox Pi versions; whether the remote host is paired-runtime or legacy SSH; effective Pi executable, cwd, home, agentDir, trust state and configured skill sources.
2. Inspect explicit existing sandbox mounts and a harmless skill directory's full resolved symlink closure. Can both host and sandbox read the same Markdown **and** supporting script at the intended absolute paths? Do not dump environments/credentials or create a sandbox for this check.
3. Before a first message, record the host `skills.discover` result and the exact `/skill:name` token. After successful acquisition, compare Pi `get_commands` and collision diagnostics. A menu row is not proof of the selected file version.
4. In a controlled existing test environment, use harmless same-name marker skills to confirm actual version precedence, then a harmless tool command to verify cwd/interpreter/path and execution location. Do not infer tool success from prompt expansion alone.
5. For later autonomous installations, identify whether they write the shared project tree or private sandbox home; separately verify Pi reload and Orca cached catalog lifecycle. No tested UI-only forced Pi refresh was established.

## Primary-source reference index

All **O** links are fixed to the inspected Orca commit. **P** references are local installed primary docs/source; they intentionally do not link an unverified upstream release tag. **D** is the Docker documentation pinned during the earlier investigation.

- **O1 — Pi token/profile and picker selection:** [`native-chat-agent-profiles.ts:84–89`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/shared/native-chat/input/commands/native-chat-agent-profiles.ts#L84-L89); [`use-native-chat-picker-state.ts:219–232`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/renderer/src/components/native-chat/composer/pickers/use-native-chat-picker-state.ts#L219-L232); [`native-chat-composer-autocomplete.ts:184–198`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/shared/native-chat/input/composer/native-chat-composer-autocomplete.ts#L184-L198).
- **O2 — Prompt wire construction:** [`rpc-prompt.ts:95–156`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/main/pi/rpc/prompts/rpc-prompt.ts#L95-L156).
- **O3 — Pi command adapter drops skill path metadata:** [`rpc-options.ts:20–28,200–220`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/main/pi/rpc/options/rpc-options.ts#L200-L220).
- **O4 — Reported commands determine Pi availability:** [`native-chat-skill-visibility.ts:38–46`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/shared/native-chat/input/commands/native-chat-skill-visibility.ts#L38-L46).
- **O5 — Scan enrichment versus reported skill rows:** [`native-chat-picker-items.ts:178–242`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/shared/native-chat/input/composer/native-chat-picker-items.ts#L178-L242).
- **O6 — Exact host discovery roots and filtering:** [`skill-discovery-sources.ts:123–260`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/main/skills/discovery/skill-discovery-sources.ts#L123-L260); [`native-chat-skill-visibility.ts:14–35`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/shared/native-chat/input/commands/native-chat-skill-visibility.ts#L14-L35).
- **O7 — Picker runtime/context and discover call:** [`native-chat-skill-discovery-context.ts:110–176`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/renderer/src/components/native-chat/composer/pickers/native-chat-skill-discovery-context.ts#L110-L176); [`use-native-chat-skills.ts:211–235`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/renderer/src/components/native-chat/composer/pickers/use-native-chat-skills.ts#L211-L235); [`runtime-skills-client.ts:23–43`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/renderer/src/runtime/skills/configuration/runtime-skills-client.ts#L23-L43).
- **O8 — Pi launch resources and path arguments:** [`rpc-launch-resolution.ts:202–215,247`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/main/pi/rpc/launch/rpc-launch-resolution.ts#L202-L215); [`rpc-launch.ts:176–201`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/main/pi/rpc/launch/rpc-launch.ts#L176-L201).
- **O9 — Actual server skill handlers:** [`skills.ts:49–110`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/main/runtime/rpc/methods/skills/skills.ts#L49-L110), [`:140–164`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/main/runtime/rpc/methods/skills/skills.ts#L140-L164), [`:200–315`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/main/runtime/rpc/methods/skills/skills.ts#L200-L315); [`skill-discovery-target.ts:162–218`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/main/skills/discovery/skill-discovery-target.ts#L162-L218).
- **O10 — First-party remote architecture:** [`remote-servers.mdx:8–44`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/docs/site/content/docs/remote-servers.mdx#L8-L44).
- **O11 — Legacy SSH limits and documentation discrepancy:** [`skill-remote-repo-sources.ts:10–38`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/main/skills/discovery/skill-remote-repo-sources.ts#L10-L38); [`runtime-skill-install-commands.ts:39,63–70`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/main/runtime/integrations/skill/runtime-skill-install-commands.ts#L63-L70); [`cli/skills.mdx:94`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/docs/site/content/docs/cli/skills.mdx#L94).
- **O12 — Install UI and Pi canonical destination:** [`SkillInstallTargetFields.tsx:60–170`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/renderer/src/components/skills/installation/SkillInstallTargetFields.tsx#L60-L170); [`skill-install-providers.ts:164–169`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/shared/skills/installation/skill-install-providers.ts#L164-L169); [`skill-provider-destinations.ts:21–64`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/main/skills/providers/skill-provider-destinations.ts#L21-L64); [`skill-install-paths.ts`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/main/skills/install/skill-install-paths.ts).
- **O13 — Host install authority, ingress and destination:** [`runtime-skill-install-authority.ts:103–165`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/main/runtime/integrations/skill/runtime-skill-install-authority.ts#L103-L165); [`skill-install-destinations.ts:46–101`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/main/skills/install/skill-install-destinations.ts#L46-L101); [`skill-install-request.ts:44–135`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/main/skills/install/skill-install-request.ts#L44-L135).
- **O14 — Bot linked directory symlink maintenance:** [`bot-skill-projects.ts:126–158,211–238`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/main/bots/bot-skill-projects.ts#L126-L158); [`native-chat-skill-roots.ts:24–39,44–109`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/main/native-chat/native-chat-skill-roots.ts#L24-L109).
- **O15 — Optional bot resources and visuals:** [`structured-agent-launch-composition.ts:55–95`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/main/runtime/agent-session/launch/structured-agent-launch-composition.ts#L55-L95); [`native-chat-visuals-delivery.ts:34–66`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/main/native-chat/conversation-files/native-chat-visuals-delivery.ts#L34-L66).
- **O16 — Remote direct install and actual fallback byte transport:** [`skill-remote-installation.ts:39–60,82–99,116–278`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/main/skills/runtime-transfer/skill-remote-installation.ts#L116-L278); [`skill-client-mediated-transfer.ts:61–181`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/main/skills/runtime-transfer/skill-client-mediated-transfer.ts#L61-L181).
- **O17 — Startup/cached catalog and lack of Pi at-rest provider:** [`rpc-session-startup.ts:96–165`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/main/pi/rpc/rpc-session-startup.ts#L96-L165); [`rpc-session-adapter.ts:206–208`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/main/pi/rpc/rpc-session-adapter.ts#L206-L208); [`rpc-runtime-registration.ts:15–56`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/main/pi/rpc-runtime-registration.ts#L15-L56). At-rest UI founding and subscribe trace with primary-source links is in [earlier investigation §12.1 and A1–A7](orca-chat-investigation.md#121-what-actually-starts-pi-before-a-message).
- **O18 — Orca's host Pi account-dir selection/launch env:** [`rpc-runtime-metadata.ts:40–44`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/main/pi/rpc-runtime-metadata.ts#L40-L44); [`rpc-launch-resolution.ts:125–136`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/main/pi/rpc/launch/rpc-launch-resolution.ts#L125-L136).
- **O19 — General runtime file APIs:** [`files.ts:100–107,175–213`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/main/runtime/rpc/methods/files/files.ts#L175-L213); [`files-mutation-methods.ts:54–149,164–198`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/main/runtime/rpc/methods/files/files-mutation-methods.ts#L54-L198).
- **O20 — Native scanner reads/canonicalizes host files:** [`skill-native-discovery.ts:115–138`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/main/skills/discovery/skill-native-discovery.ts#L115-L138).
- **O21 — Ordinary UI resting creation and passive reads:** [`structured-agent-session-create-handler.ts:94–126`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/main/runtime/rpc/methods/structured-sessions/creation/structured-agent-session-create-handler.ts#L94-L126); [`structured-agent-session-create-founding.ts:112–126`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/main/native-chat/agent-session-wire/acquisition/structured-agent-session-create-founding.ts#L112-L126); [`structured-agent-session-subscribe-method.ts:18–45`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/main/runtime/rpc/methods/structured-sessions/subscriptions/structured-agent-session-subscribe-method.ts#L18-L45); [`structured-agent-session-command-reads.ts:5–48`](https://github.com/stablyai/orca/blob/a91fc0a676e324b2630a78bdc6d885f513cc9d88/src/main/native-chat/agent-session-wire/options/structured-agent-session-command-reads.ts#L5-L48).
- **P1 — Skill semantics, bundled files, model discovery, paths, dependencies:** `docs/skills.md:1–63,79–93`; `dist/core/skills.js:278–300`.
- **P2 — Exact `/skill:` expansion:** `dist/core/agent-session.js:1820–1842` (queued expansion also at `1852`).
- **P3 — Built-in execution and path resolution:** `dist/core/tools/bash.js:60–81,159–182,198,283`; `dist/core/tools/path-utils.js:36–45`; `dist/core/tools/read.js` uses `resolveReadPath` / `resolveReadPathAsync`. Extensions/custom tool operations can alter execution; this report describes the inspected built-in default, not every extension/MCP server.
- **P4 — Effective resource roots and trust:** `dist/config.js:489–515`; `dist/core/package-manager.js:763–780,2174–2239`; `docs/skills.md:57–65`.
- **P5 — CLI path mapping, ordered merge, first-name wins:** `dist/main.js:637,689–699`; `dist/core/resource-loader.js:385–450,645–656,803–816`; `dist/core/skills.js:316–401`; `docs/skills.md:83–85`.
- **P6 — RPC skill command inventory:** `dist/modes/rpc/rpc-mode.js:554–580`; no reload command handler at `582–584`. Detailed reload boundaries are separately traced in the earlier investigation §12.5.
- **P7 — Explicit skills with disabled defaults:** `docs/cli.md:202–205`; `dist/core/resource-loader.js:441–445`.
- **K1 — Actual local wrapper/kit (read-only):** [`../wrapper/pi`](../wrapper/pi); [`../spec.yaml`](../spec.yaml). No change was made.
- **D1 — Docker Sandboxes workspace sharing:** [`usage.md:123–136`](https://github.com/docker/docs/blob/77d9d8c048d0743a0e9d4bc3878a87106c66e495/content/manuals/ai/sandboxes/usage.md#L123-L136), [`:170–175`](https://github.com/docker/docs/blob/77d9d8c048d0743a0e9d4bc3878a87106c66e495/content/manuals/ai/sandboxes/usage.md#L170-L175), [`:378–401`](https://github.com/docker/docs/blob/77d9d8c048d0743a0e9d4bc3878a87106c66e495/content/manuals/ai/sandboxes/usage.md#L378-L401). Limits/environment and existing-sandbox behavior are documented with further primary references in the earlier investigation §§11–12; this report does not assert new live mount/env facts.
