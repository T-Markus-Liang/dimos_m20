from __future__ import annotations

from unittest.mock import Mock

from dimos.core.coordination import python_worker


def test_non_parent_worker_uses_psutil_wait(monkeypatch) -> None:
    process = Mock()
    process._parent_pid = 100
    process.pid = 200
    remote_process = Mock()
    monkeypatch.setattr(python_worker.os, "getpid", lambda: 101)
    monkeypatch.setattr(python_worker.psutil, "Process", lambda _pid: remote_process)

    assert python_worker._wait_for_process_exit(process, timeout=0.5)
    remote_process.wait.assert_called_once_with(timeout=0.5)
    process.join.assert_not_called()


def test_parent_worker_keeps_multiprocessing_join(monkeypatch) -> None:
    process = Mock()
    process._parent_pid = 100
    process.is_alive.return_value = False
    monkeypatch.setattr(python_worker.os, "getpid", lambda: 100)

    assert python_worker._wait_for_process_exit(process, timeout=0.5)
    process.join.assert_called_once_with(timeout=0.5)
