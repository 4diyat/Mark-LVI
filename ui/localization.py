"""Small, explicit bindings for translating live Qt controls without rebuilding them."""
from core.i18n import label


class TranslationBindings:
    def __init__(self):
        self._bindings = []

    def bind(self, getter, setter, key, *, conditional=False):
        """Translate now and on refresh; conditional fields retain changed data."""
        text = label(key)
        setter(text)
        self._bindings.append([getter, setter, key, text, conditional])

    def refresh(self):
        for binding in self._bindings:
            getter, setter, key, previous, conditional = binding
            if conditional and getter() != previous:
                continue
            text = label(key)
            setter(text)
            binding[3] = text

    def text(self, widget, key, *, conditional=False):
        self.bind(widget.text, widget.setText, key, conditional=conditional)
        return widget

    def placeholder(self, widget, key):
        self.bind(widget.placeholderText, widget.setPlaceholderText, key)

    def title(self, widget, key):
        self.bind(widget.windowTitle, widget.setWindowTitle, key)

    def tab(self, tabs, index, key):
        self.bind(lambda: tabs.tabText(index), lambda text: tabs.setTabText(index, text), key)

    def choice(self, combo, index, key):
        self.bind(lambda: combo.itemText(index), lambda text: combo.setItemText(index, text), key)
