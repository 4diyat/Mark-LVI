"""Bounded background file search and truthful search states."""
from __future__ import annotations

import threading
import time

from ui.panel_target import PanelTarget


def _poll_until(view, predicate):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        view.poll_search()
        if predicate():
            return
        threading.Event().wait(0.005)
    raise AssertionError(f"search timed out: {view.search_status} {view.hits}")


def test_search_runs_off_caller_thread_and_discards_old_result(monkeypatch):
    from ui import pages_people
    entered, release = threading.Event(), threading.Event()
    calls = []
    owner = threading.get_ident()
    def search(query, *, cancel):
        calls.append((query, threading.get_ident()))
        if query == 'old':
            entered.set()
            assert release.wait(2)
        return [query + '.txt']
    monkeypatch.setattr(pages_people, 'find_files', search)
    view = PanelTarget()
    assert view.start_search('old')
    assert entered.wait(1)
    assert view.search_status == 'searching'
    assert view.start_search('middle')
    assert view.start_search('new')
    release.set()
    _poll_until(view, lambda: view.search_status == 'done')
    assert view.hits == ('new.txt',)
    assert [q for q, _ in calls] == ['old', 'new']
    assert all(thread_id != owner for _, thread_id in calls)


def test_search_failure_and_invalid_query_do_not_claim_no_results(monkeypatch):
    from ui import pages_people
    def fail(query, *, cancel):
        raise OSError('permission denied')
    monkeypatch.setattr(pages_people, 'find_files', fail)
    view = PanelTarget()
    assert view.start_search('valid')
    _poll_until(view, lambda: view.search_status == 'error')
    assert view.hits == ()
    assert not view.start_search('ab')
    assert view.search_status == 'invalid'
    assert view.hits == ()


def test_search_cancellation_ignores_running_result(monkeypatch):
    from ui import pages_people
    entered, release = threading.Event(), threading.Event()
    def search(query, *, cancel):
        entered.set()
        assert release.wait(2)
        return ['stale.txt']
    monkeypatch.setattr(pages_people, 'find_files', search)
    view = PanelTarget()
    view.start_search('valid')
    assert entered.wait(1)
    view.cancel_search()
    release.set()
    _poll_until(view, lambda: not view.search_worker_running)
    assert view.search_status == 'idle'
    assert view.hits == ()


def test_find_files_checks_real_roots_and_can_cancel(tmp_path, monkeypatch):
    from pathlib import Path
    from ui.pages_people import find_files
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    docs = tmp_path / 'Documents'
    docs.mkdir()
    (docs / 'report-final.txt').write_text('test')
    (docs / 'other.txt').write_text('test')
    assert find_files('report') == [str(docs / 'report-final.txt')]
    assert find_files('report', cancel=lambda: True) == []


def test_find_files_reports_walk_failures(tmp_path, monkeypatch):
    import os
    from pathlib import Path
    import pytest
    from ui.pages_people import find_files
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    (tmp_path / 'Documents').mkdir()
    def broken_walk(root, onerror):
        onerror(PermissionError('denied'))
        yield from ()
    monkeypatch.setattr(os, 'walk', broken_walk)
    with pytest.raises(PermissionError):
        find_files('report')


def test_thread_start_failure_leaves_search_in_error_and_can_retry(monkeypatch):
    from ui import pages_people
    real_thread = threading.Thread
    class BrokenThread:
        def __init__(self, **kwargs):
            pass
        def start(self):
            raise RuntimeError('cannot start')
    monkeypatch.setattr(threading, 'Thread', BrokenThread)
    view = PanelTarget()
    assert not view.start_search('valid')
    assert view.search_status == 'error'
    assert not view.search_worker_running
    monkeypatch.setattr(threading, 'Thread', real_thread)
    monkeypatch.setattr(pages_people, 'find_files', lambda query, *, cancel: [])
    assert view.start_search('valid')
    _poll_until(view, lambda: view.search_status == 'done')
    assert view.hits == ()
