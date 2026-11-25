set -euo pipefail
while IFS='=' read -r k v; do
  case "$k" in
    HTTP_PROXY|HTTPS_PROXY|http_proxy|https_proxy) export "$k=$v" ;;
  esac
done < <(env; tr '\0' '\n' < /proc/1/environ 2>/dev/null)
for tool in python3 nft curl sha256sum tar; do
  command -v "$tool" >/dev/null || { echo "sbx-relay: required tool unavailable: $tool" >&2; exit 1; }
done
install -d -m 755 /usr/local/libexec
if [ ! -x /usr/local/libexec/gost-3.3.3 ]; then
  case "$(uname -m)" in
    aarch64|arm64) arch=arm64; checksum=4c704c92df6eeea8a3b08d0de4fd3c44343095a20136b3b6cf334f98d2f174ab ;;
    x86_64|amd64) arch=amd64; checksum=f4c1255dc892a7014c0ad6e5f1c3573108f7bea4403f04f21873406ab58aa666 ;;
    *) echo 'sbx-relay: unsupported architecture' >&2; exit 1 ;;
  esac
  download=$(mktemp -d /run/sbx-gost-download.XXXXXX)
  trap 'rm -rf "$download"' EXIT
  curl --fail --silent --show-error --location --retry 3 \
    "https://github.com/go-gost/gost/releases/download/v3.3.3/gost_3.3.3_linux_${arch}.tar.gz" \
    -o "$download/archive.tar.gz"
  printf '%s  %s\n' "$checksum" "$download/archive.tar.gz" | sha256sum --check --status
  tar -xzf "$download/archive.tar.gz" -C "$download" gost
  install -m 755 "$download/gost" /usr/local/libexec/gost-3.3.3
fi
cat << 'SBX_RELAY_PY' > /usr/local/libexec/sbx-docker-relay.py
#!/usr/bin/env python3
"""Bridge-network HTTP(S) routing through the mandatory inspection proxy.

No TLS termination. GOST sniffs HTTP Host/TLS SNI and CONNECTs upstream.
Host networking, non-web protocols, ECH and custom non-Docker bridges are not
covered. External bridge IPv6 HTTP(S) is rejected rather than routed directly.
"""
import fcntl
import ipaddress
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit

RUNTIME = Path('/run/sbx-docker-relay')
BINARY = '/usr/local/libexec/gost-3.3.3'
SCRIPT = '/usr/local/libexec/sbx-docker-relay.py'
TABLE = 'sbx_docker_relay'
PORT = 12345


def serve():
    lock = (RUNTIME / 'supervisor.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return
    stopping = False
    child = None

    def stop(signum, frame):
        nonlocal stopping
        stopping = True
        if child is not None and child.poll() is None:
            child.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while not stopping:
        child = subprocess.Popen([BINARY, '-C', str(RUNTIME / 'config.yaml')])
        child.wait()
        if not stopping:
            # Routing rules deliberately remain installed during recovery.
            time.sleep(1)


def rules(gateway, proxy_addresses, proxy_port):
    return f'''table inet {TABLE} {{
    chain listener_access {{
        iifname "lo" return
        iifname "docker0" return
        iifname "br-*" return
        reject with tcp reset
    }}
    chain input {{
        type filter hook input priority -10; policy accept;
        ip daddr {gateway} tcp dport {PORT} jump listener_access
    }}
    chain route_web {{
        ip daddr {{ {', '.join(proxy_addresses)} }} tcp dport {proxy_port} return
        fib daddr type local return
        fib daddr oifname "docker0" return
        fib daddr oifname "br-*" return
        tcp dport {{ 80, 443 }} counter dnat ip to {gateway}:{PORT}
    }}
    chain prerouting {{
        type nat hook prerouting priority -110; policy accept;
        meta nfproto ipv4 iifname "docker0" jump route_web
        meta nfproto ipv4 iifname "br-*" jump route_web
    }}
    chain unsupported_ipv6 {{
        oifname "docker0" return
        oifname "br-*" return
        tcp dport {{ 80, 443 }} reject with tcp reset
    }}
    chain forward {{
        type filter hook forward priority -10; policy accept;
        meta nfproto ipv6 iifname "docker0" jump unsupported_ipv6
        meta nfproto ipv6 iifname "br-*" jump unsupported_ipv6
    }}
}}
'''


def configure():
    if os.geteuid() != 0:
        raise RuntimeError('root/network administration privileges required')
    # This routing layer only supports a single unauthenticated HTTP proxy.
    # Preserve the existing adapters for explicit proxy clients and CA trust.
    hp = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')
    hsp = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy') or hp
    if not hp or hp != hsp:
        raise RuntimeError('HTTP(S) must use the same mandatory proxy')
    proxy = urlsplit(hp)
    if (proxy.scheme != 'http' or not proxy.hostname or not proxy.port
            or proxy.username or proxy.password or proxy.path not in ('', '/')
            or proxy.query or proxy.fragment):
        raise RuntimeError('unsupported proxy endpoint; explicit integration required')
    network = json.loads(subprocess.check_output(
        ['docker', 'network', 'inspect', 'bridge'], text=True))[0]
    gateway = str(ipaddress.IPv4Address(network['IPAM']['Config'][0]['Gateway']))
    proxy_addresses = sorted({str(ipaddress.IPv4Address(item[4][0])) for item in
                              socket.getaddrinfo(proxy.hostname, proxy.port, socket.AF_INET, socket.SOCK_STREAM)})
    config = {
        'log': {'level': 'fatal'},
        'services': [{'name': 'docker-web', 'addr': f'{gateway}:{PORT}',
                      'handler': {'type': 'red', 'chain': 'inspection',
                                  'metadata': {'sniffing': True, 'sniffing.timeout': '5s',
                                               'sniffing.fallback': False}},
                      'listener': {'type': 'red'}}],
        'chains': [{'name': 'inspection', 'hops': [{'name': 'mandatory', 'nodes': [
            {'name': 'inspection', 'addr': proxy.netloc,
             'connector': {'type': 'http'}, 'dialer': {'type': 'tcp'}}]}]}]
    }
    RUNTIME.mkdir(mode=0o700, exist_ok=True)
    if RUNTIME.is_symlink():
        raise RuntimeError('runtime-directory symlink refused')
    RUNTIME.chmod(0o700)
    os.umask(0o077)
    setup_lock = (RUNTIME / 'setup.lock').open('a')
    fcntl.flock(setup_lock, fcntl.LOCK_EX)
    config_path = RUNTIME / 'config.yaml'
    encoded = json.dumps(config, sort_keys=True)
    # Refuse endpoint changes under an existing supervisor instead of leaving
    # a live process silently using an old proxy configuration.
    if config_path.exists() and config_path.read_text() != encoded:
        raise RuntimeError('relay configuration changed; stop supervisor before reconfiguration')
    config_path.write_text(encoded)
    log = (RUNTIME / 'supervisor.log').open('ab')
    supervisor = subprocess.Popen([sys.executable, SCRIPT, '--serve'],
                                 stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                 start_new_session=True)
    ready = False
    for _ in range(100):
        try:
            with socket.create_connection((gateway, PORT), timeout=0.2):
                ready = True
                break
        except OSError:
            time.sleep(0.1)
    if not ready:
        raise RuntimeError('relay failed to listen; inspect protected supervisor log')
    # Replace only our own table in ONE atomic nft transaction. Do not flush
    # Docker's tables; keep existing routing intact if validation/install fails.
    present = subprocess.run(['nft', 'list', 'table', 'inet', TABLE],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    batch = (f'delete table inet {TABLE}\n' if present else '') + rules(gateway, proxy_addresses, proxy.port)
    for args in [['nft', '--check', '--file', '-'], ['nft', '--file', '-']]:
        result = subprocess.run(args, input=batch, text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError('network-rule validation/install failed; existing rules preserved')
    print('sbx-relay: bridge IPv4 HTTP(S) routing active; external bridge IPv6 HTTP(S) rejected')


if __name__ == '__main__':
    try:
        if sys.argv[1:] == ['--serve']:
            serve()
        elif not sys.argv[1:]:
            configure()
        else:
            raise RuntimeError('invalid invocation')
    except Exception:
        # Do not expose proxy endpoints, environment values, or subprocess output.
        print('sbx-relay: setup/supervision failed; inspect configuration without exposing credentials', file=sys.stderr)
        sys.exit(1)
SBX_RELAY_PY
chmod 755 /usr/local/libexec/sbx-docker-relay.py
python3 /usr/local/libexec/sbx-docker-relay.py
