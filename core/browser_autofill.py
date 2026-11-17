"""Build a same-origin, manually approved, non-submitting login fill script."""
import json
from core.browser_url import https_origin


def fill_script(origin, username, password):
    if https_origin(origin) != origin or not isinstance(username, str) or not isinstance(password, str):
        raise ValueError('Invalid fill request')
    params = json.dumps([origin, username, password], ensure_ascii=True)
    return '''(() => {
      const [origin, username, password] = PARAMS;
      if (location.origin !== origin) return 'origin_changed';
      const visible = el => {
        if (el.disabled || el.readOnly || !el.isConnected || !el.getClientRects().length) return false;
        const rect = el.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0 || rect.right <= 0 || rect.bottom <= 0 ||
            rect.left >= innerWidth || rect.top >= innerHeight) return false;
        for (let n=el; n && n.nodeType===1; n=n.parentElement) {
          const s=getComputedStyle(n);
          if (s.visibility !== 'visible' || s.display === 'none' || Number(s.opacity) === 0) return false;
        }
        return true;
      };
      const passwords = Array.from(document.querySelectorAll('input[type="password"]')).filter(visible);
      if (passwords.length !== 1) return 'no_form';
      const pass=passwords[0], form=pass.form;
      const valid=() => form && pass.isConnected && pass.form===form && location.origin===origin &&
        form.method.toLowerCase()==='post' && new URL(form.action || location.href, location.href).origin===origin;
      if (!valid()) return 'no_form';
      const candidates=Array.from(form.querySelectorAll('input')).filter(el => visible(el) &&
        (el.autocomplete==='username' || el.type==='email' || el.type==='text'));
      const preferred=candidates.filter(el => el.autocomplete==='username');
      const names=preferred.length ? preferred : candidates;
      if (names.length !== 1) return 'no_form';
      const user=names[0], setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;
      setter.call(user, username);
      user.dispatchEvent(new Event('input',{bubbles:true}));
      user.dispatchEvent(new Event('change',{bubbles:true}));
      if (!valid() || !visible(user) || user.form!==form || !visible(pass)) return 'origin_changed';
      setter.call(pass,password);
      pass.dispatchEvent(new Event('input',{bubbles:true}));
      pass.dispatchEvent(new Event('change',{bubbles:true}));
      return 'filled';
    })()'''.replace('PARAMS', params, 1)
