# Copyright 2026 Dimensional Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Viewer URL helpers for LAN-accessible DimOS visualization endpoints."""

from __future__ import annotations

from dataclasses import dataclass
import socket
import subprocess
from urllib.parse import quote


WILDCARD_HOSTS = {"0.0.0.0", "::", ""}
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
SKIP_IFACE_PREFIXES = ("br-", "docker", "lo", "tap", "tun", "veth")


@dataclass(frozen=True)
class ViewerHost:
    host: str
    iface: str = ""


def _ip_addr_hosts() -> list[ViewerHost]:
    try:
        result = subprocess.run(
            ["ip", "-o", "-4", "addr", "show", "up", "scope", "global"],
            capture_output=True,
            check=False,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []

    hosts: list[ViewerHost] = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        iface = parts[1]
        if iface.startswith(SKIP_IFACE_PREFIXES):
            continue
        host = parts[3].split("/", 1)[0]
        hosts.append(ViewerHost(host=host, iface=iface))
    return hosts


def _hostname_hosts() -> list[ViewerHost]:
    hosts: list[ViewerHost] = []
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, family=socket.AF_INET)
    except socket.gaierror:
        return hosts

    for info in infos:
        host = info[4][0]
        if host.startswith("127."):
            continue
        hosts.append(ViewerHost(host=host, iface="hostname"))
    return hosts


def local_ipv4_hosts() -> list[ViewerHost]:
    """Return reachable non-loopback IPv4 addresses, preferring real NICs."""
    seen: set[str] = set()
    hosts: list[ViewerHost] = []
    for candidate in [*_ip_addr_hosts(), *_hostname_hosts()]:
        if candidate.host in seen:
            continue
        seen.add(candidate.host)
        hosts.append(candidate)
    return hosts


def viewer_hosts_for_listen_host(listen_host: str) -> list[ViewerHost]:
    if listen_host in WILDCARD_HOSTS:
        hosts = local_ipv4_hosts()
        return hosts or [ViewerHost("127.0.0.1", "loopback")]
    return [ViewerHost(listen_host, "loopback" if listen_host in LOOPBACK_HOSTS else "configured")]


def format_viewer_access_hints(
    *,
    listen_host: str,
    dashboard_port: int = 7779,
    rerun_grpc_port: int = 9877,
    rerun_web_port: int = 9878,
    rerun_ws_port: int = 3030,
) -> str:
    """Format LAN/local viewer URLs for fixed DimOS visualization ports."""
    hosts = viewer_hosts_for_listen_host(listen_host)
    lines = ["", "Viewer access:"]
    if listen_host in LOOPBACK_HOSTS:
        lines.append("  Remote access disabled; services are bound to localhost.")
    elif listen_host in WILDCARD_HOSTS:
        lines.append("  Services are bound to all interfaces.")
    else:
        lines.append(f"  Services are bound to {listen_host}.")

    for item in hosts:
        suffix = f"  # {item.iface}" if item.iface else ""
        lines.append(f"  Web dashboard: http://{item.host}:{dashboard_port}{suffix}")
        rerun_url = quote(f"rerun+http://{item.host}:{rerun_grpc_port}/proxy", safe="")
        lines.append(f"  Web Rerun:     http://{item.host}:{rerun_web_port}/?url={rerun_url}")
        lines.append(
            "  Rerun viewer:  "
            f"dimos-viewer --connect rerun+http://{item.host}:{rerun_grpc_port}/proxy "
            f"--ws-url ws://{item.host}:{rerun_ws_port}/ws"
        )
    return "\n".join(lines)
