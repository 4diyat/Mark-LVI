"""Run generated JavaScript against fake pages; no browser or network needed."""
import json
import shutil
import subprocess

import pytest

from core.browser_autofill import fill_script


@pytest.mark.skipif(not shutil.which('node'), reason='node not installed')
@pytest.mark.parametrize('scenario,expected', [('good', 'filled'), ('wrong', 'origin_changed'),
    ('get', 'no_form'), ('external', 'no_form'), ('hidden', 'no_form'), ('navigate', 'origin_changed')])
def test_fill_only_visible_same_origin_post_form(scenario, expected):
    code = fill_script('https://example.com', 'alice";globalThis.injected=true;//', 'secret"value')
    harness = r'''
const scenario=SCENARIO;
const location={origin:scenario==='wrong'?'https://evil.test':'https://example.com',href:'https://example.com/login'};
const innerWidth=1000,innerHeight=800;
class HTMLInputElement {constructor(type){this.type=type;this.autocomplete='';this.isConnected=true;this.nodeType=1;this._v='';}
get value(){return this._v} set value(v){this._v=v} getClientRects(){return scenario==='hidden'?[]:[1]}
getBoundingClientRect(){return {width:10,height:10,left:0,top:0,right:10,bottom:10}}
dispatchEvent(){if(scenario==='navigate' && this.type==='text')location.origin='https://evil.test'}}
class Event{constructor(type,options){this.type=type}}
const getComputedStyle=()=>({visibility:'visible',display:'block',opacity:'1'});
const user=new HTMLInputElement('text'), pass=new HTMLInputElement('password');
const form={method:scenario==='get'?'get':'post',action:scenario==='external'?'https://evil.test':'https://example.com',querySelectorAll(){return [user,pass]}};
user.form=pass.form=form;
const document={querySelectorAll(){return [pass]}};
const result=SCRIPT;
if(result!==EXPECTED)throw Error(result);
if(scenario!=='good' && pass.value)throw Error('secret leaked');
if(scenario==='good' && (user.value!==USER || pass.value!==PASSWORD))throw Error('bad fill');
if(globalThis.injected)throw Error('script injection');
'''
    for marker, value in [('SCENARIO', json.dumps(scenario)), ('SCRIPT', code), ('EXPECTED', json.dumps(expected)),
                          ('USER', json.dumps('alice";globalThis.injected=true;//')), ('PASSWORD', json.dumps('secret"value'))]:
        harness = harness.replace(marker, value, 1)
    # Cold Node startup on shared Windows runners can exceed ten seconds.
    # The bound still turns a genuinely stuck process into a test failure.
    subprocess.run(['node', '-e', harness], check=True, timeout=45)
