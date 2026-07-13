from __future__ import annotations

import threading
import time
from unittest.mock import Mock

from dimos.core.rpc_client import RpcCall, wait_for_stop_rpc_cleanup


def test_stop_does_not_wait_for_rpc_client_cleanup() -> None:
    cleanup_started = threading.Event()
    release_cleanup = threading.Event()

    def stop_client() -> None:
        cleanup_started.set()
        release_cleanup.wait(timeout=1.0)

    rpc = Mock()
    stop = RpcCall(None, rpc, "stop", "ExampleModule", [], stop_client)

    started = time.monotonic()
    stop()
    elapsed = time.monotonic() - started

    assert elapsed < 0.1
    rpc.call_nowait.assert_called_once_with("ExampleModule/stop", ((), {}))
    assert cleanup_started.wait(timeout=0.5)
    release_cleanup.set()
    assert wait_for_stop_rpc_cleanup(timeout=0.5)
    assert not any(t.name == "ExampleModule-stop-rpc-cleanup" for t in threading.enumerate())
