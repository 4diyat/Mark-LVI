"""Run QR login JavaScript against a fake DOM, without browser or network."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("success", [True, False])
def test_fragment_is_cleared_before_qr_post_and_not_sent_as_url(success):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed; real-browser validation remains separate")
    html = (ROOT / "dashboard/static/login.html").read_text(encoding="utf-8")
    script = re.search(r'<script nonce="__NONCE__">(.*?)</script>', html, re.S)
    assert script is not None
    harness = r'''
const vm = require('vm');
const input = JSON.parse(process.argv[1]);
const nodes = {};
const node = id => nodes[id] ||= {
  value: '', style: {}, textContent: '', classList: {remove(){}, add(){}},
  addEventListener(){}, focus(){},
};
const stored = {};
const calls = [];
const location = {hash:'#key=abc23456', pathname:'/login', replace(path){calls.push(['replace',path]);}};
const history = {replaceState(_a, _b, path){calls.push(['clear',path]); location.hash='';}};
const storage = prefix => ({getItem(k){return stored[prefix+k] || null;},
                            setItem(k,v){stored[prefix+k]=v;}, removeItem(k){delete stored[prefix+k];}});
const fetch = async (url, opts) => {
  calls.push(['fetch', url, opts.body, location.hash]);
  return {json: async () => input.success
    ? {ok:true, token:'SESSION', device_token:'DEVICE'}
    : {ok:false, error:'Invalid or expired key'}};
};
const context = {URLSearchParams, location, history, fetch,
  document:{getElementById:node}, sessionStorage:storage('s:'), localStorage:storage('l:')};
vm.runInNewContext(input.script, context);
setImmediate(() => console.log(JSON.stringify({calls, stored, error:node('err').textContent})));
'''
    data = json.dumps({"script": script.group(1), "success": success})
    output = subprocess.run([node, "-e", harness, data], check=True,
                            capture_output=True, text=True, timeout=5)
    result = json.loads(output.stdout)
    assert result["calls"][0] == ["clear", "/login"]
    assert result["calls"][1] == ["fetch", "/api/qr-login", '{"key":"abc23456"}', ""]
    if success:
        assert result["stored"] == {"s:jarvis_key": "ABC23456", "s:jarvis_token": "SESSION",
                                    "l:jarvis_device_token": "DEVICE"}
        assert result["calls"][2] == ["replace", "/"]
    else:
        assert not result["stored"]
        assert result["error"] == "Invalid or expired key"
        assert len(result["calls"]) == 2
