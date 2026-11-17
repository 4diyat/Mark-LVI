"""Exercise authenticated download JavaScript without a real browser/network."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("status", [200, 401, 500, 0])
def test_download_uses_header_and_cleans_blob_url(status):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed; actual browser validation is separate")
    html = (ROOT / "dashboard/static/app.html").read_text(encoding="utf-8")
    auth = html[html.index("    function _authHeader()"):html.index("    // ── AES-256")]
    js = html[html.index("    async function _downloadFile("):html.index("    // ── File upload")]
    harness = r'''
const vm = require('vm');
const input = JSON.parse(process.argv[1]);
const calls = [];
let button, link;
const URL = {createObjectURL(_blob){calls.push(['blob']); return 'blob:temporary';},
             revokeObjectURL(url){calls.push(['revoke', url]);}};
const document = {
  createElement(kind){
    const el = {kind, addEventListener(event, f){this.handler=f;},
      click(){calls.push(['click', this.href, this.download]);},
      remove(){calls.push(['remove']);}};
    if (kind === 'button') button = el; else link = el;
    return el;
  },
  body:{appendChild(el){calls.push(['append', el.kind]);}}
};
const container = {appendChild(el){calls.push(['button', el.textContent]);}};
const fetch = async (url, opts) => {
  calls.push(['fetch',url,opts.headers.Authorization]);
  if (!input.status) throw new Error('offline');
  return {ok: input.status===200, status:input.status,
          blob:async()=>({data:'fixture'})};
};
const context = {document, URL, fetch, toast:msg=>calls.push(['toast',msg]),
  setTimeout:(fn, ms)=>{calls.push(['timeout', ms]); fn();}, container};
vm.runInNewContext("const _authToken='SECRET_TOKEN';\n" + input.auth + input.script +
  "\n_downloadButton(container, 'notes <x>&.txt', 'Download');", context);
button.handler();
setImmediate(() => console.log(JSON.stringify({calls, buttonType:button.type})));
'''
    data = json.dumps({"auth": auth, "script": js, "status": status})
    result = subprocess.run([node, "-e", harness, data], check=True,
                            capture_output=True, text=True, timeout=5)
    value = json.loads(result.stdout)
    assert value["buttonType"] == "button"
    assert value["calls"][1] == ["fetch", "/uploads/notes%20%3Cx%3E%26.txt", "Bearer SECRET_TOKEN"]
    if status == 200:
        assert ["click", "blob:temporary", "notes <x>&.txt"] in value["calls"]
        assert ["timeout", 60000] in value["calls"]
        assert ["revoke", "blob:temporary"] in value["calls"]
        assert ["remove"] in value["calls"]
    else:
        assert any(call[0] == "toast" for call in value["calls"])
        assert not any(call[0] in ("blob", "click") for call in value["calls"])
