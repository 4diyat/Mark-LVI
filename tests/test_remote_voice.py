"""Remote microphone relay, independently of devices and cloud services."""
import ast
import asyncio
import subprocess
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def get_relay():
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "JarvisLive")
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in {"_queue_mic_frame", "_queue_audio_end"}]
    nodes += [n for n in cls.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "_relay_phone_audio"]
    ns = {"asyncio": asyncio, "time": time}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "main.py", "exec"), ns)
    return ns["_relay_phone_audio"]


def test_phone_stream_wakes_and_ends_queued_after_audio():
    async def check():
        q, out = asyncio.Queue(), asyncio.Queue()
        wakes = []
        obj = SimpleNamespace(_dashboard=SimpleNamespace(_phone_audio_queue=q), out_queue=out,
            _phone_active=False, _speaking_lock=threading.Lock(), _is_speaking=False,
            _wake_enabled=True, _awake=False, ui=SimpleNamespace(muted=False))
        def wake(reason):
            wakes.append(reason)
            obj._awake = True
        obj.wake = wake
        task = asyncio.create_task(get_relay()(obj))
        await q.put({"data": b"old", "mime_type": "audio/pcm", "received_at": time.monotonic() - 3})
        await q.put({"data": b"ab", "mime_type": "audio/pcm", "received_at": time.monotonic()})
        await q.put({"phone_audio_end": True})
        await asyncio.sleep(.02)
        assert out.get_nowait() == {"data": b"ab", "mime_type": "audio/pcm"}
        assert out.get_nowait() == {"audio_stream_end": True}
        assert out.empty() and wakes == ["remote microphone"] and not obj._phone_active
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(check())


@pytest.mark.parametrize("muted,speaking", [(True, False), (False, True)])
def test_muted_or_speaking_never_forwards_or_wakes(muted, speaking):
    async def check():
        q, out = asyncio.Queue(), asyncio.Queue()
        messages = []
        async def broadcast(message):
            messages.append(message)
        obj = SimpleNamespace(_dashboard=SimpleNamespace(_phone_audio_queue=q, broadcast=broadcast), out_queue=out,
            _phone_active=False, _speaking_lock=threading.Lock(), _is_speaking=speaking,
            _wake_enabled=True, _awake=False, ui=SimpleNamespace(muted=muted),
            wake=lambda **_: pytest.fail("should not wake"))
        task = asyncio.create_task(get_relay()(obj))
        await q.put({"data": b"ab", "mime_type": "audio/pcm"})
        await q.put({"phone_audio_end": True})
        await asyncio.sleep(.02)
        assert out.empty() and not obj._phone_active
        assert bool(messages) == muted
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(check())


def test_browser_audio_resampling_and_processing_graph(tmp_path):
    import shutil
    if not shutil.which("node"):
        pytest.skip("node not available")
    html = (ROOT / "dashboard/static/app.html").read_text(encoding="utf-8")
    script = html[html.index('    function _pcmResampler'):html.index('    function _showVoiceSetup')]
    js = script + '''
const resample = _pcmResampler(44100); let n = 0;
for (let i = 0; i < 44100 / 100; i++) n += resample(new Float32Array(100)).length;
if (n !== 16000) throw Error('bad sample count ' + n);
'''
    subprocess.run(["node", "-e", js], check=True, timeout=10)
    assert "node.connect(silent)" in html and "silent.gain.value = 0" in html
    assert "window.isSecureContext" in html and "_flushVoice()" in html


def test_browser_worklet_stream_is_connected_silent_and_stops_tracks():
    import shutil
    if not shutil.which("node"):
        pytest.skip("node not available")
    html = (ROOT / "dashboard/static/app.html").read_text(encoding="utf-8")
    source = html[html.index('    const micBtn  ='):html.index('\n  </script>')]
    setup = r'''
let sent = [], tracksStopped = 0, connections = [], nodes = [];
const micBtnFake = {innerHTML: '', title: '', classList: {add() {}, remove() {}}, addEventListener() {}, setAttribute() {}};
const document = {getElementById: () => micBtnFake, addEventListener() {}};
const window = {isSecureContext: true, addEventListener() {}};
const navigator = {mediaDevices: {getUserMedia: async () => ({getTracks: () => [{stop: () => tracksStopped++}]})}};
const location = {protocol: 'https:', host: 'example.test'};
const _authToken = 'fake'; const feed = {}; const sys = () => {}; const toast = () => {}; const wake = micBtnFake; const doSend = () => {}; const doWake = () => {};
const URL = {createObjectURL: () => 'blob:test', revokeObjectURL: () => {}};
class FakeNode { constructor(name) {this.name=name;} connect(other) {connections.push([this.name, other.name]);} disconnect() {} }
class AudioWorkletNode extends FakeNode { constructor() {super('worklet'); this.port={}; nodes.push(this);} }
class AudioContext { constructor() {this.sampleRate=16000; this.state='running'; this.destination=new FakeNode('destination'); this.audioWorklet={addModule: async () => {}};} createMediaStreamSource() {return new FakeNode('source');} createGain() {const n=new FakeNode('gain'); n.gain={value: 1}; return n;} close() {} }
class WebSocket { static OPEN = 1; constructor(url) {this.url=url; this.readyState=1; this.bufferedAmount=0; globalThis.testSocket=this;} send(data) {sent.push(typeof data === 'string' ? data : data.byteLength);} close() {this.readyState=3;} }
'''
    test = r'''
(async () => {
 _pttHeld = true;
 await doMic();
 globalThis.testSocket.onopen();
 if (sent.length !== 1 || JSON.parse(sent[0]).type !== 'auth' || JSON.parse(sent[0]).token !== 'fake') throw Error('auth not sent first');
 if (globalThis.testSocket.url.includes('fake') || globalThis.testSocket.url.includes('?')) throw Error('token in URL');
 if (connections.length) throw Error('audio started before authentication');
 sent = [];
 await globalThis.testSocket.onmessage({data:JSON.stringify({type:'auth_ok'})});
 if (!connections.some(x => x[0] === 'worklet' && x[1] === 'gain')) throw Error('not connected');
 if (!connections.some(x => x[0] === 'gain' && x[1] === 'destination')) throw Error('no destination');
 for (let i=0; i<9; i++) nodes[0].port.onmessage({data:new Float32Array(128)});
 _stopVoice();
 if (sent.join(',') !== '2048,256') throw Error('audio or final flush missing ' + sent);
 if (tracksStopped !== 1) throw Error('microphone track not stopped');
})().catch(e => {console.error(e); process.exit(1)});
'''
    subprocess.run(["node", "-e", setup + source + test], check=True, timeout=10)


def test_ptt_release_during_permission_and_remote_speaker_playback():
    import shutil
    if not shutil.which("node"):
        pytest.skip("node not available")
    html = (ROOT / "dashboard/static/app.html").read_text(encoding="utf-8")
    source = html[html.index('    const micBtn  ='):html.index('\n  </script>')]
    setup = r'''
let tracksStopped=0, deferred, schedules=[], sockets=[];
const buttons = {};
function makeButton() {return {innerHTML:'', title:'', events:{}, classList:{add(){},remove(){}}, addEventListener(name, fn){this.events[name]=fn;}, setAttribute(){}};}
const document = {getElementById:(id)=>buttons[id] || (buttons[id]=makeButton()), addEventListener(){}};
const window = {isSecureContext:true, addEventListener(){}};
const navigator = {mediaDevices:{getUserMedia:()=>new Promise(r=>deferred=r)}};
const location = {protocol:'https:',host:'test'}; const _authToken='fake'; const feed={}; const sys=()=>{}; const toast=()=>{}; const wake=document.getElementById('wake'); const doSend=()=>{}; const doWake=()=>{};
class AudioContext {
 constructor(){this.state='running';this.currentTime=1;this.destination={};}
 createBuffer(ch,n,rate){let arr=new Float32Array(n);return {duration:n/rate,getChannelData:()=>arr};}
 createBufferSource(){return {connect(){},start(t){schedules.push(t)}};}
 close(){return Promise.resolve();}
}
class WebSocket {static OPEN=1; constructor(url){this.url=url;this.readyState=1;sockets.push(this);} send(data){this.sent=data;} close(){this.readyState=3;}}
'''
    run = r'''
(async()=>{
 buttons['mic-btn'].events.pointerdown({button:0,preventDefault(){}});
 buttons['mic-btn'].events.pointerup({preventDefault(){}});
 deferred({getTracks:()=>[{stop:()=>tracksStopped++}]});
 await new Promise(r=>setTimeout(r,0));
 if (tracksStopped!==1 || sockets.length!==0) throw Error('mic remained open after release');
 await buttons['speaker-btn'].events.click();
 if(sockets.length!==1 || !sockets[0].url.includes('/ws/phone-playback')) throw Error('no opt-in socket');
 sockets[0].onopen();
 if (JSON.parse(sockets[0].sent).type !== 'auth') throw Error('missing auth');
 sockets[0].onmessage({data:JSON.stringify({type:'auth_ok'})});
 sockets[0].onmessage({data:new Int16Array([0,100,-100]).buffer});
 if(schedules.length!==1) throw Error('audio not scheduled');
 toggleRemotePlayback();
 if(sockets[0].readyState!==3) throw Error('playback did not stop');
})().catch(e=>{console.error(e);process.exit(1)});
'''
    subprocess.run(["node", "-e", setup + source + run], check=True, timeout=10)


def test_remote_playback_continues_when_no_local_speakers():
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "JarvisLive")
    node = next(n for n in cls.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "_play_audio")
    def no_speaker(**kwargs):
        raise OSError("no audio device")
    namespace = {"asyncio": asyncio, "sd": SimpleNamespace(RawOutputStream=no_speaker),
                 "audio_devices": SimpleNamespace(resolve=lambda *_: None),
                 "get_output_device": lambda: "", "RECEIVE_SAMPLE_RATE": 24000,
                 "CHANNELS": 1, "CHUNK_SIZE": 1024, "_TAIL_MARGIN": .1,
                 "np": SimpleNamespace(frombuffer=lambda *_a, **_k: (_ for _ in ()).throw(ValueError())),
                 "time": time}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "main.py", "exec"), namespace)
    async def check():
        output, logs = [], []
        queue = asyncio.Queue()
        obj = SimpleNamespace(audio_in_queue=queue, _out_latency=.1, _dashboard=SimpleNamespace(
            publish_audio=output.append), ui=SimpleNamespace(write_log=logs.append),
            set_speaking=lambda _: None, _turn_done_event=None)
        task = asyncio.create_task(namespace["_play_audio"](obj))
        await queue.put(b"\x01\x00" * 1200)
        await asyncio.sleep(.02)
        assert output == [b"\x01\x00" * 1200]
        assert any("remote audio can still play" in msg for msg in logs)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(check())


def test_feed_socket_sends_auth_first_and_shows_connected_only_after_ack():
    import shutil
    if not shutil.which("node"):
        pytest.skip("node not available")
    html = (ROOT / "dashboard/static/app.html").read_text(encoding="utf-8")
    source = html[html.index('    const feed  ='):html.index('    function setStatus(s)')]
    setup = r'''
let calls=[];
const nodes={};
const document={getElementById(id){return nodes[id] ||= {textContent:'',
  classList:{add(x){calls.push(['class',id,x]);},remove(){} }};}};
const location={protocol:'https:',host:'test.local'}; const _authToken='SECRET';
const sys=()=>{}; const toast=()=>{}; const append=()=>{}; const setStatus=()=>{}; const _onFileReceived=()=>{};
class WebSocket {constructor(url){this.url=url;globalThis.socket=this;} send(m){calls.push(['send',m]);}}
'''
    run = r'''
socket.onopen();
if(socket.url !== 'wss://test.local/ws') throw Error('credential in url');
if(calls.length!==1) throw Error('connected before ack');
const auth=JSON.parse(calls[0][1]);
if(auth.type !== 'auth' || auth.token !== 'SECRET') throw Error('bad auth');
socket.onmessage({data:JSON.stringify({type:'auth_ok'})});
if(nodes['connection-text'].textContent !== 'Connected') throw Error('not connected after ack');
'''
    subprocess.run(["node", "-e", setup + source + run], check=True, timeout=10)
    for endpoint in ("/ws?token=", "/ws/phone-audio?token=", "/ws/phone-playback?token="):
        assert endpoint not in html
