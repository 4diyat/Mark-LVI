from actions.browser_control import browser_control


class Player:
    def __init__(self, enabled=True):
        self.enabled, self.jobs = enabled, []

    def get_plugins(self):
        return [{'name': 'workspace_browser', 'valid': True, 'enabled': self.enabled}]

    def show_code_job(self, job):
        self.jobs.append(job)


def test_legacy_navigation_routes_to_internal_browser():
    player = Player()
    assert 'Requested the internal browser' in browser_control({'action': 'go_to', 'url': 'https://example.com'}, player=player)
    assert player.jobs == [{'kind': 'workspace_browser', 'url': 'https://example.com'}]
    browser_control({'action': 'search', 'query': 'a & b'}, player=player)
    assert 'a+%26+b' in player.jobs[-1]['url']


def test_browser_disabled_and_legacy_automation_fail_closed():
    player = Player(False)
    assert 'Enable' in browser_control({'action': 'go_to', 'url': 'https://example.com'}, player=player)
    assert not player.jobs
    assert 'unavailable' in browser_control({'action': 'click'}, player=player)
    assert 'HTTP or HTTPS' in browser_control({'action': 'go_to', 'url': 'file:///etc/passwd'}, player=player)
