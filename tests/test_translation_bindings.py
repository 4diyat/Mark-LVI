from core.i18n import active_locale, set_locale
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("translation_bindings_test", Path(__file__).resolve().parents[1] / "ui/localization.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
TranslationBindings = module.TranslationBindings


class Field:
    def __init__(self): self.value = ''
    def text(self): return self.value
    def setText(self, value): self.value = value


def test_live_translation_preserves_dynamic_content():
    old = active_locale()
    try:
        set_locale('en')
        static, dynamic = Field(), Field()
        translations = TranslationBindings()
        translations.text(static, 'creative.open')
        translations.text(dynamic, 'creative.unsaved', conditional=True)
        before = static.value
        dynamic.setText('/home/user/my-project.py')
        set_locale('id')
        translations.refresh()
        assert static.value != before
        assert dynamic.value == '/home/user/my-project.py'
        set_locale('en')
        translations.refresh()
        assert static.value == before
        assert dynamic.value == '/home/user/my-project.py'
    finally:
        set_locale(old)
