#!/usr/bin/env bash
# Run as your normal user; sudo is used only for installation.
set -euo pipefail

case "${SHELL##*/}" in
  zsh) rc="$HOME/.zshrc" ;;
  bash) rc="$HOME/.bashrc" ;;
  *) printf 'Unsupported login shell: %s (expected bash or zsh).\n' "${SHELL:-unknown}" >&2; exit 1 ;;
esac

# Do not source shell configuration: it may contain interactive commands.
existing="${SBX_PI_LLMAPI_DOMAIN:-}"
assignment='^[[:space:]]*(export[[:space:]]+)?SBX_PI_LLMAPI_DOMAIN='
if [[ -z "$existing" && -f "$rc" ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" =~ $assignment ]]; then
      value="${line#*=}"
      case "$value" in
        \"*\") value="${value#\"}"; value="${value%\"}" ;;
        \'*\') value="${value#\'}"; value="${value%\'}" ;;
      esac
      # Only literal domain values are accepted; never evaluate shell code.
      if [[ "$value" =~ ^[a-zA-Z0-9.-]+$ ]]; then existing="$value"; fi
    fi
  done < "$rc"
fi

if ! { exec 3<> /dev/tty; } 2>/dev/null; then
  printf 'Installation requires a terminal to ask for the LLM API domain.\n' >&2
  exit 1
fi
while :; do
  printf 'LLM API domain%s: ' "${existing:+ [$existing]}" >&3
  IFS= read -r domain <&3 || exit 1
  domain="${domain:-$existing}"
  if [[ "$domain" =~ ^[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?$ ]]; then break; fi
  printf 'Enter a hostname, without https://, a port, or a path.\n' >&3
done
exec 3>&-

tmp="$(mktemp)"
config_tmp="$(mktemp)"
trap 'rm -f "$tmp" "$config_tmp"' EXIT
curl -fsSL https://raw.githubusercontent.com/gibenez/sbx-kits/main/pi-dev/wrapper/pi -o "$tmp"
sudo install -m 755 "$tmp" /usr/local/bin/pi

# Replace previous assignments rather than adding conflicting exports on reinstall.
if [[ -e "$rc" ]]; then
  cp -p "$rc" "$rc.pi-sbx.bak"
  awk '!/^[[:space:]]*(export[[:space:]]+)?SBX_PI_LLMAPI_DOMAIN=/' "$rc" > "$config_tmp"
fi
printf '\nexport SBX_PI_LLMAPI_DOMAIN="%s"\n' "$domain" >> "$config_tmp"
# Preserve an existing startup file's permissions (and follow its symlink).
if [[ -e "$rc" ]]; then
  cp "$config_tmp" "$rc"
else
  install -m 600 "$config_tmp" "$rc"
fi
printf 'Installed /usr/local/bin/pi and saved SBX_PI_LLMAPI_DOMAIN in %s.\n' "$rc"
printf 'Run: source "%s"\nThen set your API key with: sbx secret set llmapi\n' "$rc"
