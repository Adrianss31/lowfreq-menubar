#!/usr/bin/env python3
"""Low-Freq Hunter · widget menu bar per macOS (SwiftBar).

File UNICO e autosufficiente: incorpora sia il renderer della barra (una
template image disegnata via osascript/Cocoa) sia la finestra di
configurazione (una piccola UI web servita in locale). Non servono altri
file: solo SwiftBar e Python 3.

INSTALLAZIONE
  1) brew install swiftbar          (una volta sola)
  2) metti questo file nella cartella plugin di SwiftBar e rendilo eseguibile:
         chmod +x lowfreq.10s.py
  3) apri SwiftBar → dal menu del widget scegli "configura…" e imposta
     l'indirizzo (e l'eventuale token) dei tuoi telefoni.

Il ".10s." nel nome = SwiftBar lo aggiorna ogni 10 secondi.
Interroga /api/state dei telefoni con l'app Low-Freq Hunter; la config sta in
~/.config/lowfreq-menubar.json (creata al primo avvio).
"""
import json, os, subprocess, sys, threading, webbrowser, urllib.request
from urllib.parse import urlsplit, urlunsplit, parse_qs
from http.server import BaseHTTPRequestHandler, HTTPServer

VERSION = "1.0.0"
CFG_PATH = os.path.expanduser("~/.config/lowfreq-menubar.json")
STATE_PATH = os.path.expanduser("~/.cache/lowfreq-menubar-state.json")
SUPPORT_DIR = os.path.expanduser("~/Library/Application Support/lowfreq-menubar")
RENDER_JS = os.path.join(SUPPORT_DIR, "render_bar.js")
SELF = os.path.realpath(__file__)
CONFIG_PORT = 8770

DEFAULT_CFG = {
    "dispositivi": [
        # bande: lista di id da mostrare nella barra (vuota = tutte le attive)
        {"nome": "telefono", "url": "", "token": "", "bande": []},
    ],
    "barra": {
        # "attive" = bande sopra soglia + dBFS · "dominante" = Hz dominante ·
        # "minima" = solo un simbolo
        "mostra": "attive",
        "max_bande_per_dispositivo": 3,
        "nome_dispositivo": True,
        "dbfs": True,
        "durata": False,
    },
    "menu": {
        "livelli_tutte_le_bande": True,
        "dominante": True,
        "batteria": True,
        "eventi_totali": True,
    },
    "notifiche": {
        "banda_attiva": False,
        "dispositivo_offline": False,
    },
    "timeout_s": 3,
}


# ─────────────────────────────────────────────────────────────────────────────
#  Sorgente del renderer della barra (JXA/Cocoa). Scritto in SUPPORT_DIR al
#  primo avvio e invocato con `osascript -l JavaScript`.
# ─────────────────────────────────────────────────────────────────────────────
RENDER_JS_SRC = r'''#!/usr/bin/osascript -l JavaScript
// Renderer della barra per il widget Low-Freq Hunter.
// Riceve un JSON con i dispositivi e disegna una template image PNG @2x
// (nera con alpha: macOS la ricolora da solo, bianca o nera, per qualunque
// sfondo della menu bar). Stampa il PNG in base64 su stdout.
ObjC.import('Cocoa');

function run(argv) {
  const m = JSON.parse(argv[0]);
  const H = 18, PAD = 2, BASE = 3.2;

  const fBand  = $.NSFont.monospacedDigitSystemFontOfSizeWeight(11, 0.23);
  const fBandB = $.NSFont.monospacedDigitSystemFontOfSizeWeight(11, 0.4);
  const fUnit  = $.NSFont.systemFontOfSizeWeight(7.5, 0.23);
  const fLevel = $.NSFont.monospacedDigitSystemFontOfSizeWeight(10, 0.0);
  const fName  = $.NSFont.systemFontOfSizeWeight(8, 0.3);
  const ink = a => $.NSColor.colorWithCalibratedWhiteAlpha(0, a);
  const PILL_H = 14, PILL_PAD = 5;

  function attr(text, font, alpha, kern) {
    const d = $.NSMutableDictionary.alloc.init;
    d.setObjectForKey(font, $('NSFont'));
    d.setObjectForKey(ink(alpha), $('NSColor'));
    if (kern) d.setObjectForKey($(kern), $('NSKern'));
    const s = $(String(text));
    return { s: s, a: d, f: font, w: s.sizeWithAttributes(d).width };
  }

  const items = [];
  const gap = w => items.push({ k: 'gap', w: w });
  const txt = (t, f, a, k) => { const o = attr(t, f, a, k); items.push({ k: 't', o: o, w: o.w }); };
  const dot = over => items.push({ k: 'dot', over: over, w: 6 });

  items.push({ k: 'icon', w: 10 });
  gap(7);
  m.devs.forEach((dev, di) => {
    if (di > 0) { gap(8); items.push({ k: 'sep', w: 1 }); gap(8); }
    if (dev.name) { txt(dev.name, fName, 0.5, 0.6); gap(5); }
    if (dev.state === 'off')  { txt('offline', fName, 0.55, 0.4); return; }
    if (dev.state === 'stop') { txt('fermo',   fName, 0.55, 0.4); return; }
    if (!dev.bands.length) { dot(!!dev.idle_over); return; }
    dev.bands.forEach((b, bi) => {
      if (bi > 0) gap(9);
      if (b.over) {
        const fr = attr(b.label, fBandB, 1.0), hz = attr('Hz', fUnit, 1.0);
        items.push({ k: 'pill', fr: fr, hz: hz, w: PILL_PAD * 2 + fr.w + 1.5 + hz.w });
      } else {
        txt(b.label, fBand, 0.95);
        gap(1.5);
        txt('Hz', fUnit, 0.5);
      }
      if (b.level != null) { gap(4); txt(b.level, fLevel, 0.55); }
    });
  });

  const W = Math.ceil(items.reduce((a, i) => a + i.w, 0) + PAD * 2);

  const rep = $.NSBitmapImageRep.alloc
    .initWithBitmapDataPlanesPixelsWidePixelsHighBitsPerSampleSamplesPerPixelHasAlphaIsPlanarColorSpaceNameBytesPerRowBitsPerPixel(
      null, W * 2, H * 2, 8, 4, true, false, $.NSCalibratedRGBColorSpace, 0, 0);
  rep.setSize($.NSMakeSize(W, H));
  $.NSGraphicsContext.saveGraphicsState;
  $.NSGraphicsContext.setCurrentContext($.NSGraphicsContext.graphicsContextWithBitmapImageRep(rep));

  let x = PAD;
  for (const it of items) {
    if (it.k === 'gap') { x += it.w; continue; }
    if (it.k === 'sep') {
      ink(0.22).set;
      $.NSBezierPath.fillRect($.NSMakeRect(x, (H - 9) / 2, 1, 9));
    } else if (it.k === 'icon') {
      ink(0.9).set;
      const hs = [5, 9, 6.5], bw = 2, g = 1.4, cy = BASE + 3.6;
      hs.forEach((bh, i) => {
        $.NSBezierPath.bezierPathWithRoundedRectXRadiusYRadius(
          $.NSMakeRect(x + i * (bw + g), cy - bh / 2, bw, bh), 1, 1).fill;
      });
    } else if (it.k === 'dot') {
      const cy = BASE + 3.6, r = $.NSMakeRect(x, cy - 3, 6, 6);
      if (it.over) { ink(0.95).set; $.NSBezierPath.bezierPathWithOvalInRect(r).fill; }
      else {
        ink(0.42).set;
        const p = $.NSBezierPath.bezierPathWithOvalInRect($.NSMakeRect(x + 0.5, cy - 2.5, 5, 5));
        p.lineWidth = 1; p.stroke;
      }
    } else if (it.k === 'pill') {
      const cy = BASE + 4;
      ink(0.95).set;
      $.NSBezierPath.bezierPathWithRoundedRectXRadiusYRadius(
        $.NSMakeRect(x, cy - PILL_H / 2, it.w, PILL_H), PILL_H / 2, PILL_H / 2).fill;
      const ctx = $.NSGraphicsContext.currentContext;
      ctx.compositingOperation = 8;   // DestinationOut: il testo buca la pill
      it.fr.s.drawAtPointWithAttributes($.NSMakePoint(x + PILL_PAD, BASE + it.fr.f.descender), it.fr.a);
      it.hz.s.drawAtPointWithAttributes($.NSMakePoint(x + PILL_PAD + it.fr.w + 1.5, BASE + it.hz.f.descender), it.hz.a);
      ctx.compositingOperation = 2;   // SourceOver
    } else if (it.k === 't') {
      it.o.s.drawAtPointWithAttributes($.NSMakePoint(x, BASE + it.o.f.descender), it.o.a);
    }
    x += it.w;
  }

  $.NSGraphicsContext.restoreGraphicsState;
  const png = rep.representationUsingTypeProperties(4, $.NSDictionary.dictionary);
  return png.base64EncodedStringWithOptions(0).js;
}
'''


def ensure_render_js():
    """Scrive il renderer in SUPPORT_DIR se manca o è cambiato."""
    try:
        if open(RENDER_JS, encoding="utf-8").read() == RENDER_JS_SRC:
            return
    except Exception:
        pass
    os.makedirs(SUPPORT_DIR, exist_ok=True)
    with open(RENDER_JS, "w", encoding="utf-8") as f:
        f.write(RENDER_JS_SRC)


# ─────────────────────────────────────────────────────────────────────────────
#  Helper condivisi
# ─────────────────────────────────────────────────────────────────────────────
def load_cfg():
    if not os.path.exists(CFG_PATH):
        os.makedirs(os.path.dirname(CFG_PATH), exist_ok=True)
        with open(CFG_PATH, "w") as f:
            json.dump(DEFAULT_CFG, f, indent=2, ensure_ascii=False)
        return json.loads(json.dumps(DEFAULT_CFG)), True
    with open(CFG_PATH) as f:
        user = json.load(f)
    cfg = json.loads(json.dumps(DEFAULT_CFG))
    for k, v in user.items():
        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k].update(v)
        else:
            cfg[k] = v
    for d in cfg.get("dispositivi", []):
        d.setdefault("bande", [])
        d.setdefault("token", "")
    return cfg, False


def parse_url(url, token):
    """(base_url_senza_query, token). Tollera un url con il token dentro
    (…/?k=TOKEN), come quello copiato dalla dashboard."""
    parts = urlsplit(url or "")
    token = (token or "").strip()
    if not token:
        q = parse_qs(parts.query)
        if q.get("k"):
            token = q["k"][0]
    base = urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))
    return base, token


def parse_dev(dev):
    return parse_url(dev.get("url", ""), dev.get("token", ""))


def fetch_state(dev, timeout):
    base, token = parse_dev(dev)
    if not base:
        raise ValueError("url vuoto")
    url = base + "/api/state" + ("?k=" + token if token else "")
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def fmt_dur(s):
    s = max(0, int(s))
    if s >= 3600:
        return f"{s//3600}h{(s%3600)//60:02d}"
    if s >= 60:
        return f"{s//60}m"
    return f"{s}s"


def band_label(st, bid):
    if bid == "V":
        return "Vibr"
    for b in (st.get("cfg", {}).get("bands") or []):
        if b["id"] == bid:
            return b["label"].replace(" ", "")
    return bid


def fmt_lvl(v):
    return "−" + str(abs(int(round(v))))


# ─────────────────────────────────────────────────────────────────────────────
#  Rendering della barra
# ─────────────────────────────────────────────────────────────────────────────
def build_bar_model(results, bar):
    devs = []
    for dev, st in results:
        name = dev["nome"][:3].upper() if bar["nome_dispositivo"] else ""
        d = {"name": name, "state": "ok", "bands": [], "idle_over": False}
        if st is None:
            d["state"] = "off"
        elif not st.get("running"):
            d["state"] = "stop"
        else:
            sel = set(dev.get("bande") or [])
            act = st.get("activeBands") or {}
            lv = st.get("levels") or {}

            def mk(bid, over):
                v = lv.get(bid)
                return {"label": band_label(st, bid).replace("Hz", "").strip(),
                        "over": over,
                        "level": fmt_lvl(v) if bar["dbfs"] and v is not None else None}

            if bar["mostra"] == "minima":
                d["idle_over"] = bool(act)
            elif sel:
                order = [b["id"] for b in (st.get("cfg", {}).get("bands") or [])]
                if st.get("cfg", {}).get("vibEnabled"):
                    order.append("V")
                ids = [b for b in order if b in sel] or sorted(sel)
                d["bands"] = [mk(b, b in act) for b in ids[: bar["max_bande_per_dispositivo"]]]
            else:
                items = sorted(act.items(), key=lambda kv: -(lv.get(kv[0], -999) or -999))
                d["bands"] = [mk(b, True) for b, _ in items[: bar["max_bande_per_dispositivo"]]]
                d["idle_over"] = bool(act)
        devs.append(d)
    return {"devs": devs}


def render_bar_image(model):
    ensure_render_js()
    r = subprocess.run(["osascript", "-l", "JavaScript", RENDER_JS, json.dumps(model)],
                       capture_output=True, text=True, timeout=8)
    b64 = r.stdout.strip()
    if r.returncode != 0 or len(b64) < 100:
        raise RuntimeError(r.stderr.strip() or "render vuoto")
    return b64


def bar_fallback_text(results, bar):
    """Riga di testo se il rendering immagine fallisce."""
    segs = []
    for dev, st in results:
        name = dev["nome"] if bar["nome_dispositivo"] else ""
        if st is None:
            segs.append(f"{name} ⚠︎".strip()); continue
        if not st.get("running"):
            segs.append(f"{name} ▢".strip()); continue
        act = st.get("activeBands") or {}
        lv = st.get("levels") or {}
        sel = set(dev.get("bande") or [])
        ids = [b for b in (sel or act)]
        parts = []
        for bid in ids[: bar["max_bande_per_dispositivo"]]:
            mark = "●" if bid in act else "◦"
            v = lv.get(bid)
            parts.append(f"{mark}{band_label(st, bid)}" + (f" {v:.0f}" if v is not None else ""))
        segs.append(f"{name} {' '.join(parts)}".strip() if parts else f"{name} ◦".strip())
    return "♪ " + " · ".join(segs)


def notify(title, body):
    subprocess.run(["osascript", "-e",
                    f'display notification "{body}" with title "{title}"'],
                   capture_output=True)


# ─────────────────────────────────────────────────────────────────────────────
#  Plugin (output per SwiftBar)
# ─────────────────────────────────────────────────────────────────────────────
def main():
    cfg, created = load_cfg()
    bar, menu, notif = cfg["barra"], cfg["menu"], cfg["notifiche"]

    try:
        with open(STATE_PATH) as f:
            prev = json.load(f)
    except Exception:
        prev = {}
    cur_mem = {}

    results = []
    for dev in cfg["dispositivi"]:
        try:
            results.append((dev, fetch_state(dev, cfg["timeout_s"])))
        except Exception:
            results.append((dev, None))

    # riga nella barra: immagine template (adattiva); testo come fallback
    try:
        print(f"| templateImage={render_bar_image(build_bar_model(results, bar))}")
    except Exception:
        print(bar_fallback_text(results, bar) + " | font=Menlo-Bold size=13")
    print("---")

    if created:
        print("Benvenuto in Low-Freq Hunter menu bar | color=#c07000")
        print(f"Configura i tuoi telefoni | shell={SELF} param1=--config terminal=false refresh=true")
        print("(imposta indirizzo e token, poi scegli le bande)")
        print("---")

    for dev, st in results:
        print(f"{dev['nome'].upper()} | font=Menlo-Bold size=12 refresh=true")
        if st is None:
            print("✕ non raggiungibile | color=#dc2626 refresh=true")
            if notif["dispositivo_offline"] and prev.get(dev["nome"], {}).get("ok", True):
                notify("Low-Freq Hunter", f"{dev['nome']}: telefono non raggiungibile")
            cur_mem[dev["nome"]] = {"ok": False, "act": []}
            print("---"); continue

        now_s = st.get("now", 0) / 1000
        mode = ("● REC" if st.get("mode") == "rec" else "solo ascolto") if st.get("running") else "fermo"
        extra = []
        if menu["batteria"] and st.get("batteryPct") is not None:
            extra.append(f"batt {st['batteryPct']}%")
        if menu["eventi_totali"]:
            extra.append(f"{st.get('eventsCount', 0)} eventi")
        print(f"{mode}{' · ' + ' · '.join(extra) if extra else ''} | font=Menlo size=12 refresh=true")

        act = st.get("activeBands") or {}
        lv = st.get("levels") or {}
        for b in (st.get("cfg", {}).get("bands") or []):
            bid, v = b["id"], lv.get(b["id"])
            on = bid in act
            if not on and not menu["livelli_tutte_le_bande"]:
                continue
            mark = "●" if on else "○"
            dur = f"  da {fmt_dur(now_s - act[bid])}" if on else ""
            vtxt = f"{v:6.1f}" if v is not None else "     —"
            c = " color=#dc2626" if on else ""
            print(f"{mark} {b['label']:>7} {vtxt} dBFS  (soglia {b['thr']}){dur} | font=Menlo size=12{c} refresh=true")
        if menu["dominante"] and st.get("running") and st.get("domHz") is not None:
            print(f"dominante {st['domHz']:.1f} Hz | font=Menlo size=12 color=#10a37f refresh=true")
        base, token = parse_dev(dev)
        dash = base + "/" + ("?k=" + token if token else "")
        if base:
            print(f"apri dashboard | href={dash}")

        if notif["banda_attiva"]:
            prev_act = set(prev.get(dev["nome"], {}).get("act", []))
            for bid in act:
                if bid not in prev_act:
                    v = lv.get(bid)
                    notify(f"LFH · {dev['nome']}",
                           f"{band_label(st, bid)} sopra soglia"
                           + (f" ({v:.1f} dBFS)" if v is not None else ""))
        cur_mem[dev["nome"]] = {"ok": True, "act": list(act)}
        print("---")

    print(f"configura… | shell={SELF} param1=--config terminal=false refresh=true")
    print("aggiorna | refresh=true")
    print(f"Low-Freq Hunter menu bar v{VERSION} | font=Menlo size=10 color=#8a8a96")

    try:
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        with open(STATE_PATH, "w") as f:
            json.dump(cur_mem, f)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
#  UI di configurazione (server locale + pagina web) — avviata con `--config`
# ─────────────────────────────────────────────────────────────────────────────
def probe(url, token, timeout):
    base, tok = parse_url(url, token)
    if not base:
        raise ValueError("url vuoto")
    u = base + "/api/state" + ("?k=" + tok if tok else "")
    with urllib.request.urlopen(u, timeout=timeout) as r:
        st = json.load(r)
    bands = [{"id": b["id"], "label": b.get("label", b["id"]), "thr": b.get("thr")}
             for b in (st.get("cfg", {}).get("bands") or [])]
    if st.get("cfg", {}).get("vibEnabled"):
        bands.append({"id": "V", "label": "Vibraz.", "thr": st["cfg"].get("vibThr")})
    return {"running": st.get("running"), "mode": st.get("mode"),
            "batt": st.get("batteryPct"), "bands": bands}


CONFIG_HTML = r"""<!DOCTYPE html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Config · Low-Freq Hunter menu bar</title><style>
:root{--bg:#0a0a0c;--surface:#141418;--surface2:#1c1c22;--border:#2a2a30;
--text:#e8e8ee;--dim:#8a8a96;--faint:#5a5a64;--accent:#00d4aa;--rec:#ff4455;--amber:#ffaa00}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:ui-monospace,Menlo,monospace;
font-size:13px;padding:18px;max-width:820px;margin:0 auto}
h1{font-size:16px;letter-spacing:2px;margin-bottom:4px}
.sub{color:var(--dim);font-size:11px;margin-bottom:16px}
.panel{background:var(--surface);border:1px solid var(--border);padding:14px;margin-bottom:12px}
.caps{font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:var(--dim);margin-bottom:8px}
.dev{border:1px solid var(--border);padding:12px;margin-bottom:10px;background:var(--surface2)}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:5px 0}
label{color:var(--dim)}
input[type=text]{background:var(--bg);color:var(--text);border:1px solid var(--border);
font-family:inherit;font-size:12px;padding:6px 8px}
input.nome{width:130px}input.url{flex:1;min-width:220px}
input[type=number]{background:var(--bg);color:var(--text);border:1px solid var(--border);
font-family:inherit;font-size:12px;padding:4px 6px;width:56px}
select{background:var(--surface2);color:var(--text);border:1px solid var(--border);
font-family:inherit;font-size:12px;padding:5px 8px}
button{background:var(--surface2);color:var(--text);border:1px solid var(--border);
font-family:inherit;font-size:12px;letter-spacing:1px;padding:8px 14px;cursor:pointer}
button:hover{border-color:var(--accent)}
button.primary{color:var(--accent);border-color:var(--accent)}
button.danger{color:var(--rec);border-color:transparent;padding:4px 8px}
.chip{display:inline-block;padding:4px 10px;border:1px solid var(--border);font-size:12px;
cursor:pointer;user-select:none;background:var(--bg)}
.chip.on{outline:1px solid var(--accent);color:var(--accent)}
.chip.off{opacity:.45}
.chk{display:flex;align-items:center;gap:6px;cursor:pointer}
.bands{display:flex;gap:6px;flex-wrap:wrap;margin-top:4px}
.probe{font-size:11px;color:var(--faint);margin-top:4px}
.probe.ok{color:var(--accent)}.probe.err{color:var(--rec)}
#toast{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);background:#000d;
border:1px solid var(--accent);color:var(--accent);padding:10px 18px;display:none}
.hint{color:var(--faint);font-size:11px}
</style></head><body>
<h1>LOW-FREQ HUNTER · menu bar</h1>
<div class="sub">configurazione del widget macOS — <span id="cfgpath"></span></div>

<div class="panel"><div class="caps">Dispositivi</div>
<div id="devs"></div>
<button id="adddev">+ aggiungi dispositivo</button>
<div class="hint" style="margin-top:8px">l'url è quello della dashboard del telefono; il token si estrae da solo se è dentro l'url.<br>
le bande selezionate vengono <b>sorvegliate sempre</b> nella barra, con i dBFS, anche sotto soglia (badge pieno = sopra soglia).
nessuna selezionata = mostra solo le bande che superano la soglia.</div>
</div>

<div class="panel"><div class="caps">Barra</div>
<div class="row"><label>mostra</label>
<select id="b_mostra">
<option value="attive">bande sopra soglia + dBFS</option>
<option value="dominante">frequenza dominante</option>
<option value="minima">solo simbolo</option></select>
<label>max bande</label><input type="number" id="b_max" min="1" max="8"></div>
<div class="row">
<label class="chk"><input type="checkbox" id="b_nome"> nome dispositivo</label>
<label class="chk"><input type="checkbox" id="b_dbfs"> dBFS</label>
<label class="chk"><input type="checkbox" id="b_dur"> durata (da quanto attiva)</label></div>
</div>

<div class="panel"><div class="caps">Menu a tendina</div>
<div class="row">
<label class="chk"><input type="checkbox" id="m_all"> livelli di tutte le bande</label>
<label class="chk"><input type="checkbox" id="m_dom"> dominante</label>
<label class="chk"><input type="checkbox" id="m_batt"> batteria</label>
<label class="chk"><input type="checkbox" id="m_ev"> eventi totali</label></div>
</div>

<div class="panel"><div class="caps">Notifiche macOS</div>
<div class="row">
<label class="chk"><input type="checkbox" id="n_band"> quando una banda supera la soglia</label>
<label class="chk"><input type="checkbox" id="n_off"> quando un dispositivo è offline</label></div>
</div>

<div class="row"><button class="primary" id="save">salva</button>
<button id="reload">ricarica</button>
<span class="hint">dopo il salvataggio clicca "aggiorna" nel menu del widget</span></div>
<div id="toast"></div>

<script>
let cfg=null;
const $=id=>document.getElementById(id);
async function j(u,o){const r=await fetch(u,o);if(!r.ok)throw new Error(await r.text());return r.json();}
function toast(t,err){const e=$('toast');e.textContent=t;e.style.display='block';
e.style.borderColor=e.style.color=err?'#ff4455':'#00d4aa';setTimeout(()=>e.style.display='none',2600);}

function devHTML(d,i){return `<div class="dev" data-i="${i}">
<div class="row"><label>nome</label><input type="text" class="nome" data-f="nome" value="${d.nome||''}">
<label>url</label><input type="text" class="url" data-f="url" value="${d.url||''}" placeholder="http://192.168.1.x:8765/?k=...">
<button class="danger" data-del="${i}">rimuovi</button></div>
<div class="probe" data-probe="${i}">bande: —</div>
<div class="bands" data-bands="${i}"></div></div>`;}

function render(){
  $('devs').innerHTML=cfg.dispositivi.map(devHTML).join('');
  cfg.dispositivi.forEach((d,i)=>renderBands(i,null));
  $('b_mostra').value=cfg.barra.mostra;
  $('b_max').value=cfg.barra.max_bande_per_dispositivo;
  $('b_nome').checked=cfg.barra.nome_dispositivo;
  $('b_dbfs').checked=cfg.barra.dbfs;
  $('b_dur').checked=cfg.barra.durata;
  $('m_all').checked=cfg.menu.livelli_tutte_le_bande;
  $('m_dom').checked=cfg.menu.dominante;
  $('m_batt').checked=cfg.menu.batteria;
  $('m_ev').checked=cfg.menu.eventi_totali;
  $('n_band').checked=cfg.notifiche.banda_attiva;
  $('n_off').checked=cfg.notifiche.dispositivo_offline;
  cfg.dispositivi.forEach((d,i)=>probe(i));
}
function renderBands(i,bands){
  const d=cfg.dispositivi[i], box=document.querySelector(`[data-bands="${i}"]`);
  if(!box) return;
  if(!bands){ box.innerHTML = (d.bande||[]).length
    ? '<span class="hint">selezionate: '+d.bande.join(', ')+'</span>' : ''; return; }
  const sel=new Set(d.bande||[]);
  box.innerHTML = bands.map(b=>
    `<span class="chip ${sel.has(b.id)?'on':'off'}" data-band="${i}:${b.id}">${b.label}</span>`).join('')
    || '<span class="hint">nessuna banda configurata sul dispositivo</span>';
}
async function probe(i){
  const d=cfg.dispositivi[i], p=document.querySelector(`[data-probe="${i}"]`);
  if(!d.url){ p.className='probe'; p.textContent='bande: inserisci un url'; return; }
  p.className='probe'; p.textContent='bande: interrogo il dispositivo…';
  try{
    const r=await j('/api/probe?i='+i);
    p.className='probe ok';
    p.textContent=`${r.running?(r.mode==='rec'?'● REC':'in ascolto'):'fermo'}`+
      (r.batt!=null?` · batt ${r.batt}%`:'')+` · ${r.bands.length} bande`;
    renderBands(i,r.bands);
  }catch(e){ p.className='probe err'; p.textContent='bande: non raggiungibile (controlla url/rete)'; renderBands(i,null); }
}

$('devs').addEventListener('input',e=>{
  const dev=e.target.closest('.dev'); if(!dev) return;
  const i=+dev.dataset.i, f=e.target.dataset.f; if(!f) return;
  cfg.dispositivi[i][f]=e.target.value;
});
$('devs').addEventListener('change',e=>{
  if(e.target.dataset.f==='url'){ const i=+e.target.closest('.dev').dataset.i; probe(i); }
});
$('devs').addEventListener('click',e=>{
  if(e.target.dataset.del!=null){ cfg.dispositivi.splice(+e.target.dataset.del,1); render(); }
  else if(e.target.dataset.band){
    const [i,id]=e.target.dataset.band.split(':'); const d=cfg.dispositivi[+i];
    const s=new Set(d.bande||[]); s.has(id)?s.delete(id):s.add(id); d.bande=[...s];
    e.target.classList.toggle('on'); e.target.classList.toggle('off');
  }
});
$('adddev').onclick=()=>{ cfg.dispositivi.push({nome:'nuovo',url:'',token:'',bande:[]}); render(); };
$('reload').onclick=async()=>{ cfg=await j('/api/config'); render(); toast('ricaricata'); };
$('save').onclick=async()=>{
  cfg.barra.mostra=$('b_mostra').value;
  cfg.barra.max_bande_per_dispositivo=Math.max(1,+$('b_max').value||3);
  cfg.barra.nome_dispositivo=$('b_nome').checked;
  cfg.barra.dbfs=$('b_dbfs').checked; cfg.barra.durata=$('b_dur').checked;
  cfg.menu.livelli_tutte_le_bande=$('m_all').checked; cfg.menu.dominante=$('m_dom').checked;
  cfg.menu.batteria=$('m_batt').checked; cfg.menu.eventi_totali=$('m_ev').checked;
  cfg.notifiche.banda_attiva=$('n_band').checked; cfg.notifiche.dispositivo_offline=$('n_off').checked;
  try{ await j('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cfg)});
    toast('salvato ✓ — clicca "aggiorna" nel menu del widget');
  }catch(e){ toast('errore nel salvataggio: '+e.message,true); }
};
(async()=>{ $('cfgpath').textContent=CFGPATH; cfg=await j('/api/config'); render(); })();
</script></body></html>"""


def run_config_ui():
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json"):
            b = body.encode() if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            if self.path == "/" or self.path.startswith("/index"):
                self._send(200, CONFIG_HTML.replace("CFGPATH", json.dumps(CFG_PATH)),
                           "text/html; charset=utf-8")
            elif self.path == "/api/config":
                self._send(200, json.dumps(load_cfg()[0]))
            elif self.path.startswith("/api/probe"):
                i = int(parse_qs(urlsplit(self.path).query).get("i", ["-1"])[0])
                cfg = load_cfg()[0]
                try:
                    d = cfg["dispositivi"][i]
                    self._send(200, json.dumps(probe(d["url"], d.get("token", ""), cfg.get("timeout_s", 3))))
                except Exception as e:
                    self._send(502, json.dumps({"error": str(e)}))
            else:
                self._send(404, "{}")

        def do_POST(self):
            if self.path == "/api/config":
                n = int(self.headers.get("Content-Length", 0))
                try:
                    cfg = json.loads(self.rfile.read(n))
                    os.makedirs(os.path.dirname(CFG_PATH), exist_ok=True)
                    with open(CFG_PATH, "w") as f:
                        json.dump(cfg, f, indent=2, ensure_ascii=False)
                    self._send(200, json.dumps({"ok": True}))
                except Exception as e:
                    self._send(400, json.dumps({"error": str(e)}))
            else:
                self._send(404, "{}")

    try:
        srv = HTTPServer(("127.0.0.1", CONFIG_PORT), H)
    except OSError:
        webbrowser.open(f"http://127.0.0.1:{CONFIG_PORT}/")   # già in esecuzione
        return
    threading.Timer(0.4, lambda: webbrowser.open(f"http://127.0.0.1:{CONFIG_PORT}/")).start()
    print(f"Config UI su http://127.0.0.1:{CONFIG_PORT}/  (Ctrl-C per chiudere)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    if "--config" in sys.argv:
        run_config_ui()
    else:
        main()
