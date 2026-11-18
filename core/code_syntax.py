"""Small bounded syntax colouring lexer for Python and JavaScript editor lines."""
import keyword
import re

_JS = frozenset('async await break case catch class const continue debugger default delete do else export extends false finally for from function get if import in instanceof let new null of return set static super switch this throw true try typeof undefined var void while yield'.split())
_PREFIX = r'''(?P<string>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)'''
_SUFFIX = r"(?P<number>\b\d+(?:\.\d+)?\b)|(?P<word>\b[A-Za-z_$][\w$]*\b)"
_TOKENS = {lang: re.compile(_PREFIX + '|(?P<comment>' + comment + ')|' + _SUFFIX)
           for lang, comment in (('python', r'\#.*'), ('javascript', r'//.*'))}


def language_for_path(path):
    suffix = (path or '').rsplit('.', 1)[-1].lower() if '.' in (path or '') else ''
    return 'python' if suffix == 'py' else 'javascript' if suffix in ('js', 'mjs', 'cjs') else 'text'


def spans(text, language):
    """Return UTF-16 ranges for Qt; plaintext and unusually long lines stay plain."""
    if language not in ('python', 'javascript') or len(text) > 20_000:
        return []
    result = []
    last_pos = offset = 0
    for match in _TOKENS[language].finditer(text):
        offset += len(text[last_pos:match.start()].encode('utf-16-le')) // 2
        start = offset
        length = len(match.group().encode('utf-16-le')) // 2
        offset += length
        last_pos = match.end()
        kind = match.lastgroup
        token = match.group()
        if kind == 'word':
            words = keyword.kwlist if language == 'python' else _JS
            if token not in words:
                continue
            kind = 'keyword'
        result.append((start, length, kind))
    return result
