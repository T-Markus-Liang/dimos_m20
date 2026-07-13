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

from dimos.utils.viewer_urls import ViewerHost, format_viewer_access_hints


def test_format_viewer_access_hints_for_loopback() -> None:
    text = format_viewer_access_hints(listen_host="127.0.0.1")

    assert "Remote access disabled" in text
    assert "http://127.0.0.1:7779" in text
    assert "http://127.0.0.1:9878/?url=rerun%2Bhttp%3A%2F%2F127.0.0.1%3A9877%2Fproxy" in text
    assert "ws://127.0.0.1:3030/ws" in text


def test_format_viewer_access_hints_for_wildcard(monkeypatch) -> None:
    monkeypatch.setattr(
        "dimos.utils.viewer_urls.local_ipv4_hosts",
        lambda: [ViewerHost("192.168.1.20", "wlan0"), ViewerHost("10.0.0.5", "eth0")],
    )

    text = format_viewer_access_hints(listen_host="0.0.0.0")

    assert "Services are bound to all interfaces" in text
    assert "http://192.168.1.20:7779" in text
    assert "http://192.168.1.20:9878/?url=rerun%2Bhttp%3A%2F%2F192.168.1.20%3A9877%2Fproxy" in text
    assert "rerun+http://10.0.0.5:9877/proxy" in text
