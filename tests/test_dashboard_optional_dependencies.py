"""The optional dashboard reports missing dependencies before building routes."""
import asyncio


def test_dashboard_reports_missing_deps_without_building_app(monkeypatch, isolated_config):
    from dashboard import server
    monkeypatch.setattr(server, '_DEPS_OK', False)
    monkeypatch.setattr(server, '_DEPS_ERROR', 'fastapi unavailable (test)')
    monkeypatch.setattr(server, '_local_ip', lambda: '127.0.0.1')
    monkeypatch.setattr(server.DashboardServer, '_build_app',
                        lambda self: (_ for _ in ()).throw(AssertionError('must not build')))
    dashboard = server.DashboardServer()
    assert dashboard.app is None
    asyncio.run(dashboard.serve())
    assert 'fastapi unavailable (test)' in dashboard._bind_error
