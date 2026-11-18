"""Bounded read-only browser requests crossing from worker to Qt.

The page is untrusted and may contain private data. The Qt side must obtain
per-request consent, validate the active tab again, and wrap returned text
before sending it to a model. A timeout cancels an outstanding request.
"""
import json
import threading

MAX_TEXT = 8000

# Main-frame DOM only; do not export input values, form contents, editable
# regions, frames, scripts or hidden content. This is not a privacy guarantee:
# ordinary visible text can itself contain sensitive information.
READ_SCRIPT = r'''(() => {
  try {
    if (location.href !== EXPECTED_URL || !document.body) return null;
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node, result = '', visited = 0;
    while ((node = walker.nextNode()) && visited++ < 20000 && result.length < 8000) {
      let el = node.parentElement, blocked = false;
      for (let p = el; p; p = p.parentElement) {
        if (p.matches('form,input,textarea,select,option,script,style,noscript,iframe,[contenteditable]:not([contenteditable="false"])') || p.hidden) {
          blocked = true; break;
        }
        const css = getComputedStyle(p);
        if (css.display === 'none' || css.visibility !== 'visible' || Number(css.opacity) === 0) {
          blocked = true; break;
        }
      }
      if (blocked) continue;
      const value = (node.nodeValue || '').trim();
      if (value) result += value + '\n';
    }
    return result.slice(0, 8000);
  } catch (_) { return null; }
})()'''


def read_script(url):
    """Bind a script to the exact approved document, safely escaping the URL."""
    from core.browser_url import validate_browser_url
    return READ_SCRIPT.replace("EXPECTED_URL", json.dumps(validate_browser_url(url), ensure_ascii=True), 1)


def scope_allows(url, scope):
    """Recognize a tightly scoped trusted page without trusting page contents."""
    from urllib.parse import urlsplit
    from core.browser_url import validate_browser_url
    try:
        parsed = urlsplit(validate_browser_url(url))
        if scope == 'any':
            return True
        if scope == 'google_flights':
            return (parsed.scheme.lower() == 'https' and parsed.hostname in ('google.com', 'www.google.com')
                    and parsed.port in (None, 443)
                    and (parsed.path == '/travel/flights' or parsed.path.startswith('/travel/flights/')))
    except ValueError:
        pass
    return False


class BrowserReadRequest:
    def __init__(self, scope='any'):
        if scope not in ('any', 'google_flights'):
            raise ValueError('Unsupported browser read scope.')
        self.scope = scope
        self._lock = threading.Lock()
        self._done = threading.Event()
        self._cancelled = False
        self._claimed = False
        self._result = None

    def claim(self):
        with self._lock:
            if self._cancelled or self._claimed:
                return False
            self._claimed = True
            return True

    def active(self):
        with self._lock:
            return not self._cancelled and not self._done.is_set()

    def finish(self, result):
        with self._lock:
            if self._cancelled or self._done.is_set():
                return False
            self._result = result
            self._done.set()
            return True

    def wait(self, timeout):
        if self._done.wait(timeout):
            return self._result
        with self._lock:
            if self._done.is_set():
                return self._result
            self._cancelled = True
        return {'ok': False, 'message': 'Browser read timed out and was cancelled.'}
