"""JobScout UK - local dashboard (Python standard library only; no web framework).

Two scans from one dashboard:
  1. Find my jobs        -> ranked live vacancies Excel
  2. Sponsor companies   -> licensed sponsor employers in your sectors Excel

Double-click run.bat (source install) or JobScoutUK.exe (packaged build).
Opens http://127.0.0.1:7861 in your browser.
"""
import base64
import json
import os
import re
import sys
import threading
import time
import traceback
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from jobscout import pipeline, sectorscan
from jobscout.llm import DEFAULT_MODELS, quick_test
from jobscout.sources import test_reed, test_adzuna

if getattr(sys, "frozen", False):          # packaged .exe
    BASE = os.path.dirname(sys.executable)
else:
    BASE = os.path.dirname(os.path.abspath(__file__))

CONFIG_PATH = os.path.join(BASE, "config.json")
UPLOADS = os.path.join(BASE, "uploads")
OUTPUT = os.path.join(BASE, "output")
PORT = 7861

RUNS = {}  # run_id -> state dict

CFG_KEYS = ("provider", "model", "api_key", "reed_api_key", "adzuna_app_id", "adzuna_app_key",
            "location", "distance_miles", "days_back", "max_jobs", "letters_for_top",
            "portals", "extra_keywords", "max_companies")


class Prog:
    def __init__(self, state):
        self.state = state

    def log(self, msg):
        self.state["lines"].append(str(msg))

    def set(self, pct, stage=None):
        self.state["pct"] = int(max(self.state.get("pct", 0), min(100, pct)))
        if stage:
            self.state["stage"] = stage

    def summary(self, **kw):
        self.state["summary"] = kw


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


def start_run(body):
    run_id = uuid.uuid4().hex[:12]
    mode = body.get("mode") or "jobs"
    state = {"pct": 0, "stage": "Starting", "lines": [], "done": False, "mode": mode,
             "error": None, "summary": None, "file": None, "t0": time.time()}
    RUNS[run_id] = state
    prog = Prog(state)

    os.makedirs(UPLOADS, exist_ok=True)
    fname = re.sub(r"[^A-Za-z0-9_.-]", "_", body.get("filename") or "resume.pdf")
    ext = os.path.splitext(fname)[1].lower() or ".pdf"
    cv_path = os.path.join(UPLOADS, f"{run_id}{ext}")
    with open(cv_path, "wb") as f:
        f.write(base64.b64decode(body.get("data_b64") or ""))

    if body.get("remember"):
        save_config({k: body.get(k, "") for k in CFG_KEYS})

    params = {
        "resume_path": cv_path,
        "provider": body.get("provider", "Gemini"),
        "api_key": (body.get("api_key") or "").strip(),
        "model": (body.get("model") or "").strip(),
        "reed_api_key": (body.get("reed_api_key") or "").strip(),
        "adzuna_app_id": (body.get("adzuna_app_id") or "").strip(),
        "adzuna_app_key": (body.get("adzuna_app_key") or "").strip(),
        "location": (body.get("location") or "London").strip(),
        "distance_miles": body.get("distance_miles") or 15,
        "days_back": body.get("days_back") or 7,
        "max_jobs": body.get("max_jobs") or 60,
        "letters_for_top": body.get("letters_for_top") or 8,
        "extra_titles": body.get("extra_titles") or "",
        "portals": body.get("portals") or ["reed", "adzuna", "indeed", "linkedin"],
        "extra_keywords": body.get("extra_keywords") or "",
        "max_companies": body.get("max_companies") or 60,
        "demo": body.get("provider") == "Demo (offline)",
        "out_dir": OUTPUT,
    }

    def work():
        try:
            if mode == "sponsors":
                out = sectorscan.run_scan(params, prog.log, prog)
            else:
                out = pipeline.run(params, prog.log, prog)
            state["file"] = out
        except Exception as e:
            state["error"] = f"{type(e).__name__}: {e}"
            prog.log("ERROR - " + state["error"])
            prog.log(traceback.format_exc(limit=2))
        finally:
            state["done"] = True

    threading.Thread(target=work, daemon=True).start()
    return run_id


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > 30 * 1024 * 1024:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return {}

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            data = INDEX_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif u.path == "/api/config":
            cfg = load_config()
            cfg.setdefault("provider", "Gemini")
            cfg.setdefault("model", DEFAULT_MODELS["Gemini"])
            self._json(cfg)
        elif u.path == "/api/status":
            rid = (parse_qs(u.query).get("id") or [""])[0]
            st = RUNS.get(rid)
            if not st:
                self._json({"error": "unknown run id"}, 404)
                return
            payload = {k: st[k] for k in ("pct", "stage", "lines", "done", "error", "summary", "mode")}
            payload["fname"] = os.path.basename(st["file"]) if st.get("file") else ""
            self._json(payload)
        elif u.path == "/api/download":
            rid = (parse_qs(u.query).get("id") or [""])[0]
            st = RUNS.get(rid)
            if not st or not st.get("file") or not os.path.exists(st["file"]):
                self._json({"error": "file not ready"}, 404)
                return
            with open(st["file"], "rb") as f:
                data = f.read()
            name = os.path.basename(st["file"])
            self.send_response(200)
            self.send_header("Content-Type",
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Content-Disposition", f'attachment; filename="{name}"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        body = self._body()
        if u.path == "/api/start":
            if not body.get("data_b64"):
                self._json({"error": "No CV uploaded"}, 400)
                return
            try:
                rid = start_run(body)
                self._json({"id": rid})
            except Exception as e:
                self._json({"error": f"{type(e).__name__}: {e}"}, 500)
        elif u.path == "/api/test":
            svc = body.get("service")
            if svc == "llm":
                ok, msg = quick_test(body.get("provider", ""), (body.get("api_key") or "").strip(),
                                     (body.get("model") or "").strip())
            elif svc == "reed":
                ok, msg = test_reed((body.get("reed_api_key") or "").strip())
            elif svc == "adzuna":
                ok, msg = test_adzuna((body.get("adzuna_app_id") or "").strip(),
                                      (body.get("adzuna_app_key") or "").strip())
            else:
                ok, msg = False, "unknown service"
            self._json({"ok": ok, "msg": msg})
        elif u.path == "/api/config":
            save_config(body)
            self._json({"ok": True})
        else:
            self._json({"error": "not found"}, 404)


INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>JobScout UK</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root{--dark:#1F4E5F;--teal:#2A7F8E;--bg:#F4F7F8;--card:#fff;--line:#E3E9EC;
--green:#1E7B45;--greenbg:#E8F4EA;--amber:#8A6100;--amberbg:#FFF1CC;--grey:#555;--greybg:#ECECEC;--red:#B00020}
*{box-sizing:border-box}body{margin:0;font-family:Arial,Helvetica,sans-serif;background:var(--bg);color:#222}
header{background:var(--dark);color:#fff;padding:18px 28px}
header h1{margin:0;font-size:22px}header p{margin:4px 0 0;font-size:13px;opacity:.85}
main{max-width:1180px;margin:22px auto;padding:0 16px;display:grid;grid-template-columns:440px 1fr;gap:18px}
@media(max-width:900px){main{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin-bottom:16px}
.card h2{margin:0 0 10px;font-size:15px;color:var(--dark)}
label{display:block;font-size:12px;color:#444;margin:10px 0 4px;font-weight:bold}
input,select{width:100%;padding:8px 10px;border:1px solid #C8D2D7;border-radius:6px;font-size:13px;font-family:inherit}
input[type=file]{padding:6px;background:#FAFCFC}
input[type=checkbox]{width:auto;margin-right:7px;transform:scale(1.15)}
.row{display:flex;gap:10px}.row>div{flex:1}
button{background:var(--teal);color:#fff;border:0;border-radius:6px;padding:9px 14px;font-size:13px;cursor:pointer}
button:hover{filter:brightness(1.08)}button:disabled{background:#9BB4BB;cursor:default}
.big{width:100%;padding:13px;font-size:15px;font-weight:bold;background:var(--dark);margin-top:12px}
.big2{width:100%;padding:13px;font-size:15px;font-weight:bold;background:var(--teal);margin-top:8px}
.test{background:#fff;color:var(--teal);border:1px solid var(--teal);padding:7px 12px;margin-top:8px}
.pill{display:inline-block;margin:8px 0 0 8px;padding:5px 10px;border-radius:20px;font-size:12px;vertical-align:middle}
.ok{background:var(--greenbg);color:var(--green)}.bad{background:#FBE7EA;color:var(--red)}
a{color:var(--teal)}small.hint{display:block;color:#667;margin-top:4px;font-size:11px;line-height:1.5}
.portal{display:flex;align-items:flex-start;padding:7px 9px;border:1px solid var(--line);border-radius:8px;margin-top:7px;background:#FBFDFD}
.portal div{font-size:12.5px}.portal b{display:block;font-size:13px}
.rec{color:var(--green);font-weight:bold;font-size:11px}
details{margin-top:12px}summary{cursor:pointer;font-size:13px;color:var(--dark);font-weight:bold}
#barwrap{background:#E2EAED;border-radius:8px;height:26px;overflow:hidden;margin:10px 0 6px;display:none}
#bar{height:100%;width:0;background:linear-gradient(90deg,var(--teal),#3FA796);transition:width .5s;
display:flex;align-items:center;justify-content:flex-end;color:#fff;font-size:12px;padding-right:8px;min-width:36px}
#stage{font-size:13px;color:var(--dark);font-weight:bold;min-height:18px}
#log{background:#10262D;color:#CFE7DC;font-family:Consolas,monospace;font-size:12px;border-radius:8px;
padding:12px;height:300px;overflow-y:auto;white-space:pre-wrap;display:none;margin-top:10px}
#cards{display:none;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:14px}
.stat{border-radius:10px;padding:14px;text-align:center}
.stat .n{font-size:30px;font-weight:bold;line-height:1.1}.stat .t{font-size:11.5px;margin-top:4px}
#livecount{display:none;margin-top:10px;font-size:13px;color:var(--dark);background:var(--greenbg);
border-radius:8px;padding:10px;font-weight:bold}
#err{display:none;background:#FBE7EA;color:var(--red);border-radius:8px;padding:12px;font-size:13px;margin-top:12px}
#dl{width:100%;margin-top:12px;background:#B9C8CD;border:0;color:#fff;padding:13px;border-radius:6px;
font-weight:bold;font-size:15px;cursor:default}
#dl.ready{background:var(--green);cursor:pointer}
.placeholder{color:#889;font-size:13px;text-align:center;padding:50px 20px;line-height:1.7}
</style>
</head>
<body>
<header><h1>JobScout UK</h1>
<p>One dashboard, two scans: ranked live vacancies, and licensed sponsor companies in your sectors &mdash; each as one Excel.</p></header>
<main>
<div><!-- LEFT -->
  <div class="card"><h2>1 &middot; Your CV</h2>
    <input type="file" id="cv" accept=".pdf,.docx,.doc,.txt,.md" style="display:none">
    <button style="width:100%;padding:12px;font-size:14px" onclick="document.getElementById('cv').click()">&#128194;&nbsp; Browse my computer&hellip; (PDF or Word)</button>
    <div id="cvname" style="font-size:12.5px;color:#1E7B45;font-weight:bold;margin-top:8px;display:none"></div>
    <small class="hint">PDF or Word (.docx). Nothing leaves your computer except the searches and AI calls you configure below.</small>
  </div>
  <div class="card"><h2>2 &middot; Your AI (the brain)</h2>
    <label>Provider</label>
    <select id="provider">
      <option>Gemini</option><option>OpenAI</option><option>Claude</option><option>Demo (offline)</option>
    </select>
    <label>API key</label>
    <input type="password" id="api_key" placeholder="Paste your key here">
    <small class="hint" id="keyhint"></small>
    <label>Model</label>
    <input type="text" id="model">
    <button class="test" onclick="testLLM()">Test connection</button><span id="llm_pill"></span>
  </div>
  <div class="card"><h2>3 &middot; Job portals to search</h2>
    <div class="portal"><input type="checkbox" id="p_reed" checked>
      <div><b>Reed <span class="rec">&#10003; recommended</span></b>Official API, best UK perm coverage. Needs the free key below.</div></div>
    <div class="portal"><input type="checkbox" id="p_adzuna" checked>
      <div><b>Adzuna <span class="rec">&#10003; recommended</span></b>Aggregates most UK boards (incl. much of Totaljobs/CWJobs inventory). Needs the free keys below.</div></div>
    <div class="portal"><input type="checkbox" id="p_indeed" checked>
      <div><b>Indeed <span class="rec">&#10003; recommended</span></b>Biggest UK volume, no key needed (public listings).</div></div>
    <div class="portal"><input type="checkbox" id="p_linkedin" checked>
      <div><b>LinkedIn</b> Best-effort: public listings only, no key, no login &mdash; can return few rows some runs (rate limits). Keep ticked; it fails safe.</div></div>
    <label style="margin-top:12px">Reed API key</label>
    <input type="password" id="reed_api_key">
    <small class="hint">Get it free: <a href="https://www.reed.co.uk/developers/jobseeker" target="_blank">reed.co.uk/developers/jobseeker</a> &rarr; register &rarr; key is shown on screen.</small>
    <button class="test" onclick="testSvc('reed')">Test Reed</button><span id="reed_pill"></span>
    <div class="row" style="margin-top:10px">
      <div><label>Adzuna App ID</label><input type="text" id="adzuna_app_id"></div>
      <div><label>Adzuna App Key</label><input type="password" id="adzuna_app_key"></div>
    </div>
    <small class="hint">Get both free: <a href="https://developer.adzuna.com/" target="_blank">developer.adzuna.com</a> &rarr; sign up &rarr; "Add app" &rarr; ID + key are shown.</small>
    <button class="test" onclick="testSvc('adzuna')">Test Adzuna</button><span id="adzuna_pill"></span>
    <details><summary>Search settings</summary>
      <div class="row"><div><label>Location</label><input id="location" value="London"></div>
        <div><label>Radius (miles)</label><input id="distance_miles" type="number" value="15" min="5" max="50"></div></div>
      <div class="row"><div><label>Posted within (days)</label><input id="days_back" type="number" value="7" min="1" max="28"></div>
        <div><label>Max jobs</label><input id="max_jobs" type="number" value="60" min="20" max="200"></div></div>
      <label>Cover letters for top N</label><input id="letters_for_top" type="number" value="8" min="3" max="20">
      <label>Extra search titles (optional, comma-separated)</label>
      <input id="extra_titles" placeholder="e.g. Head of IT, ERP Programme Manager">
      <label>Sponsor scan &mdash; extra sector keywords (optional)</label>
      <input id="extra_keywords" placeholder="e.g. retrofit, decarbonisation, proptech">
      <label>Sponsor scan &mdash; max companies</label>
      <input id="max_companies" type="number" value="60" min="20" max="150">
    </details>
    <label style="margin-top:12px"><input type="checkbox" id="remember" checked> Remember my settings &amp; keys on this computer</label>
  </div>
  <button class="big" id="runjobs" onclick="run('jobs')">&#9654;&nbsp; Find my jobs (ranked + letters)</button>
  <button class="big2" id="runsponsors" onclick="run('sponsors')">&#127970;&nbsp; Sponsor companies scan (even without adverts)</button>
</div>
<div><!-- RIGHT -->
  <div class="card" style="min-height:560px"><h2>Progress</h2>
    <div id="stage"></div>
    <div id="barwrap"><div id="bar">0%</div></div>
    <div id="cards">
      <div class="stat" style="background:var(--greenbg);color:var(--green)"><div class="n" id="n_high">0</div><div class="t" id="t_high">CLOSE MATCH</div></div>
      <div class="stat" style="background:var(--amberbg);color:var(--amber)"><div class="n" id="n_med">0</div><div class="t" id="t_med">MID MATCH</div></div>
      <div class="stat" style="background:var(--greybg);color:var(--grey)"><div class="n" id="n_low">0</div><div class="t" id="t_low">LOW MATCH</div></div>
      <div class="stat" style="background:#E3EEF1;color:var(--dark)"><div class="n" id="n_tot">0</div><div class="t">TOTAL</div></div>
    </div>
    <div id="livecount"></div>
    <button id="dl" disabled onclick="saveExcel()">&#11015;&nbsp; Save Excel report&hellip; (enabled when ready)</button>
    <div id="err"></div>
    <div id="log"></div>
    <div class="placeholder" id="ph"><b>Two buttons, two Excels:</b><br>
    &#9654; <b>Find my jobs</b> &mdash; live vacancies from your ticked portals, ranked High/Medium/Low for your CV, with email + cover-letter drafts.<br>
    &#127970; <b>Sponsor companies scan</b> &mdash; licensed Skilled-Worker sponsors in your sectors (energy, retrofit, property...), even if they have no advert today, with licence type and live-jobs check.<br><br>
    First time? Choose provider &ldquo;Demo (offline)&rdquo; and press either button &mdash; no keys needed.</div>
  </div>
</div>
</main>
<script>
const $=id=>document.getElementById(id);
const DEFAULTS={"Gemini":"gemini-2.5-flash","OpenAI":"gpt-4o-mini","Claude":"claude-haiku-4-5","Demo (offline)":""};
const KEYLINKS={"Gemini":'Where to get it: <a href="https://aistudio.google.com/apikey" target="_blank">aistudio.google.com/apikey</a> &rarr; sign in with Google &rarr; "Create API key" &rarr; copy it here. Free.',
"OpenAI":'Where to get it (ChatGPT models): <a href="https://platform.openai.com/api-keys" target="_blank">platform.openai.com/api-keys</a> &rarr; "Create new secret key" &rarr; copy it here. Needs billing set up &mdash; a ChatGPT Plus subscription is NOT enough. ~10-40p per run.',
"Claude":'Where to get it: <a href="https://console.anthropic.com/" target="_blank">console.anthropic.com</a> &rarr; API keys &rarr; "Create key" &rarr; copy it here. ~10-40p per run.',
"Demo (offline)":"No key needed - instant test run on bundled sample data."};
const PORTAL_IDS={reed:"p_reed",adzuna:"p_adzuna",indeed:"p_indeed",linkedin:"p_linkedin"};
function syncProvider(){const p=$("provider").value;$("model").value=DEFAULTS[p]??"";$("keyhint").innerHTML=KEYLINKS[p];
  $("api_key").disabled=(p==="Demo (offline)");}
$("provider").addEventListener("change",syncProvider);
fetch("/api/config").then(r=>r.json()).then(c=>{
  for(const k of ["provider","model","api_key","reed_api_key","adzuna_app_id","adzuna_app_key","location","distance_miles","days_back","max_jobs","letters_for_top","extra_keywords","max_companies"])
    if(c[k]!==undefined&&c[k]!==""&&$(k))$(k).value=c[k];
  if(Array.isArray(c.portals))for(const p in PORTAL_IDS)$(PORTAL_IDS[p]).checked=c.portals.includes(p);
  $("keyhint").innerHTML=KEYLINKS[$("provider").value];
  if(!c.model)$("model").value=DEFAULTS[$("provider").value];
});
function pill(id,ok,msg){$(id).className="pill "+(ok?"ok":"bad");$(id).textContent=(ok?"✓ ":"✗ ")+msg;}
async function testLLM(){pill("llm_pill",true,"testing...");
  const r=await fetch("/api/test",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({service:"llm",provider:$("provider").value,api_key:$("api_key").value,model:$("model").value})});
  const d=await r.json();pill("llm_pill",d.ok,d.msg);}
async function testSvc(s){pill(s+"_pill",true,"testing...");
  const r=await fetch("/api/test",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({service:s,reed_api_key:$("reed_api_key").value,
      adzuna_app_id:$("adzuna_app_id").value,adzuna_app_key:$("adzuna_app_key").value})});
  const d=await r.json();pill(s+"_pill",d.ok,d.msg);}
const LABELS={jobs:["CLOSE MATCH (apply this week)","MID MATCH (tailor CV first)","LOW MATCH (skip for now)"],
sponsors:["STRONG FIT (contact first)","POSSIBLE FIT","WEAK FIT"]};
let timer=null,doneId=null,doneName="JobScout.xlsx";
$("cv").addEventListener("change",()=>{const f=$("cv").files[0];
  if(f){$("cvname").textContent="✓ "+f.name;$("cvname").style.display="block";}});
async function saveExcel(){
  if(!doneId)return;
  const url="/api/download?id="+doneId;
  try{
    if(window.showSaveFilePicker){
      const h=await window.showSaveFilePicker({suggestedName:doneName,
        types:[{description:"Excel workbook",accept:{"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":[".xlsx"]}}]});
      const resp=await fetch(url);const w=await h.createWritable();
      await w.write(await resp.blob());await w.close();
      $("dl").textContent="✅ Saved - click to save another copy";return;
    }
  }catch(e){if(e&&e.name==="AbortError")return;}
  const a=document.createElement("a");a.href=url;a.download=doneName;
  document.body.appendChild(a);a.click();a.remove();
}
function run(mode){
  const f=$("cv").files[0];
  if(!f){alert("Please choose your CV file first (step 1).");return;}
  if($("provider").value!=="Demo (offline)"&&!$("api_key").value.trim()){
    alert("Paste your "+$("provider").value+" API key (step 2), or choose 'Demo (offline)' to try without keys.");return;}
  const portals=Object.keys(PORTAL_IDS).filter(p=>$(PORTAL_IDS[p]).checked);
  if(mode==="jobs"&&portals.length===0){alert("Tick at least one job portal (step 3).");return;}
  const rd=new FileReader();
  rd.onload=async()=>{
    const b64=rd.result.split(",")[1];
    const body={mode:mode,filename:f.name,data_b64:b64,remember:$("remember").checked,portals:portals};
    for(const k of ["provider","model","api_key","reed_api_key","adzuna_app_id","adzuna_app_key","location","distance_miles","days_back","max_jobs","letters_for_top","extra_titles","extra_keywords","max_companies"])
      body[k]=$(k).value;
    $("runjobs").disabled=true;$("runsponsors").disabled=true;
    $("ph").style.display="none";$("err").style.display="none";$("livecount").style.display="none";
    $("cards").style.display="none";doneId=null;
    $("dl").disabled=true;$("dl").className="";$("dl").innerHTML="&#11015;&nbsp; Save Excel report&hellip; (enabled when ready)";
    $("barwrap").style.display="block";$("log").style.display="block";$("log").textContent="";
    $("t_high").textContent=LABELS[mode][0];$("t_med").textContent=LABELS[mode][1];$("t_low").textContent=LABELS[mode][2];
    const r=await fetch("/api/start",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
    const d=await r.json();
    if(d.error){showErr(d.error);return;}
    timer=setInterval(()=>poll(d.id),900);
  };
  rd.readAsDataURL(f);
}
async function poll(id){
  const r=await fetch("/api/status?id="+id);const s=await r.json();
  if(s.error&&!s.lines){showErr(s.error);clearInterval(timer);return;}
  $("bar").style.width=s.pct+"%";$("bar").textContent=s.pct+"%";
  $("stage").textContent=s.stage?("⏳ "+s.stage):"";
  $("log").textContent=(s.lines||[]).join("\n");$("log").scrollTop=$("log").scrollHeight;
  if(s.done){clearInterval(timer);$("runjobs").disabled=false;$("runsponsors").disabled=false;
    if(s.error){showErr(s.error);return;}
    $("stage").textContent="✅ Done - your report is ready";
    if(s.summary){$("n_high").textContent=s.summary.high;$("n_med").textContent=s.summary.medium;
      $("n_low").textContent=s.summary.low;$("n_tot").textContent=s.summary.total;
      $("cards").style.display="grid";
      if(s.mode==="sponsors"&&s.summary.live!==undefined){
        $("livecount").textContent="🟢 "+s.summary.live+" of these companies are advertising jobs RIGHT NOW - they are flagged in the Excel";
        $("livecount").style.display="block";}}
    doneId=id;doneName=s.fname||"JobScout.xlsx";
    $("dl").disabled=false;$("dl").className="ready";
    $("dl").innerHTML="&#11015;&nbsp; Save Excel report&hellip; (choose where to save)";}
}
function showErr(e){$("err").style.display="block";$("err").textContent="Something went wrong: "+e;
  $("runjobs").disabled=false;$("runsponsors").disabled=false;clearInterval(timer);}
syncProvider();
</script>
</body>
</html>"""


def main():
    os.makedirs(OUTPUT, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}"
    print("=" * 56)
    print("  JobScout UK is running.")
    print(f"  If your browser did not open, go to: {url}")
    print("  Keep this window open. Close it to quit.")
    print("=" * 56)
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
