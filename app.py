"""
VideoForge Web  –  Encoder + VMAF Quality Analytics
Run:  streamlit run streamlit_app.py

Deploy:
  Streamlit Community Cloud → add packages.txt containing just:  ffmpeg
  HF Spaces (Streamlit SDK) → same packages.txt trick
"""

import os, json, subprocess, tempfile, time, re
import streamlit as st

# ── Page config (must be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title="VideoForge · Encoder & Quality Analytics",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Light theme CSS ───────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'IBM Plex Sans', sans-serif;
    background-color: #f4f6fb;
    color: #1a1a2e;
}
.stApp { background-color: #f4f6fb; }

/* Header */
.vf-header {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 60%, #0f3460 100%);
    border-radius: 14px;
    padding: 28px 36px 24px;
    margin-bottom: 24px;
    color: white;
}
.vf-header h1 { color: white; font-size: 1.9rem; font-weight: 600; margin: 0; letter-spacing: -0.02em; }
.vf-header p  { color: #a8b8cc; margin: 4px 0 0; font-size: 0.9rem; }
.vf-badge {
    display: inline-block;
    background: rgba(255,255,255,0.12);
    border: 1px solid rgba(255,255,255,0.2);
    border-radius: 20px; padding: 2px 10px;
    font-size: 0.74rem; color: #c4d4e8;
    margin-right: 5px; margin-top: 10px;
}

/* Section labels */
.vf-label {
    font-size: 0.68rem; font-weight: 700;
    letter-spacing: 0.12em; text-transform: uppercase;
    color: #7888aa; margin-bottom: 8px; margin-top: 4px;
}

/* Metric cards */
[data-testid="metric-container"] {
    background: white; border: 1px solid #e2e6f0;
    border-radius: 10px; padding: 14px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}

/* Buttons */
.stButton > button {
    background: #1a1a2e; color: white; border: none;
    border-radius: 8px; padding: 10px 22px;
    font-family: 'IBM Plex Sans', sans-serif;
    font-weight: 500; transition: opacity 0.18s;
}
.stButton > button:hover { opacity:0.83; color:white; }

/* Progress */
.stProgress > div > div {
    background: linear-gradient(90deg, #0f3460, #2e86de);
    border-radius: 4px;
}

/* Comparison table */
.cmp-table { width:100%; border-collapse:collapse; font-size:0.85rem; margin-top:8px; }
.cmp-table th {
    background:#eef1f8; color:#5a6480; font-weight:600;
    padding:10px 13px; text-align:left;
    border-bottom:2px solid #dde2ee;
    white-space: nowrap;
}
.cmp-table td {
    padding:10px 13px; border-bottom:1px solid #f0f2f8;
    color:#1a1a2e; font-family:'IBM Plex Mono', monospace;
    white-space: nowrap;
}
.cmp-table tr:last-child td { border-bottom:none; }
.cmp-table tr:hover td { background:#fafbff; }
.best-val { color:#1b7f3a; font-weight:600; }
.w-badge { background:#e6f5eb; color:#1b7f3a; border-radius:4px; padding:1px 6px; font-size:0.7rem; font-weight:700; margin-left:4px; }

/* Codec chips */
.chip-avc  { background:#e3f0fd; color:#1053a0; border:1px solid #b8d8f8; border-radius:5px; padding:1px 9px; font-size:0.78rem; font-weight:600; }
.chip-hevc { background:#f3e5f5; color:#6a1b9a; border:1px solid #dbb8ea; border-radius:5px; padding:1px 9px; font-size:0.78rem; font-weight:600; }
.chip-av1  { background:#e6f5eb; color:#206f34; border:1px solid #b4dcbe; border-radius:5px; padding:1px 9px; font-size:0.78rem; font-weight:600; }

/* VMAF colour */
.q-exc { color:#1b7f3a; font-weight:600; }
.q-gd  { color:#1565c0; font-weight:600; }
.q-ok  { color:#c07000; font-weight:600; }
.q-bad { color:#c0392b; font-weight:600; }

/* Source ref bar */
.src-bar {
    background:#eef1fb; border-radius:8px;
    padding:10px 16px; font-size:0.82rem;
    color:#3a4060; margin-top:12px;
    border-left:3px solid #2e86de;
}

/* Insight card */
.insight-note {
    background:#fffbe6; border:1px solid #ffe08a;
    border-radius:8px; padding:12px 16px;
    font-size:0.84rem; color:#6a4f00; margin-top:12px;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    gap:3px; background:#eaecf5;
    border-radius:9px; padding:3px;
}
.stTabs [data-baseweb="tab"] { border-radius:7px; padding:5px 16px; font-size:0.86rem; }
.stTabs [aria-selected="true"] { background:white !important; box-shadow:0 1px 4px rgba(0,0,0,0.09); }

label { font-weight:500; color:#383d58; font-size:0.87rem; }
.stAlert { border-radius:9px; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  Backend
# ══════════════════════════════════════════════════════════════════════════════

def ffmpeg_ok() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True, timeout=5)
        return True
    except Exception:
        return False


def vmaf_ok() -> bool:
    try:
        out = subprocess.check_output(["ffmpeg", "-filters"], stderr=subprocess.STDOUT,
                                      text=True, timeout=10)
        return "libvmaf" in out
    except Exception:
        return False


def probe(path: str) -> dict:
    r = {"duration": 0.0, "width": 0, "height": 0, "fps": 0.0,
         "codec": "unknown", "bitrate_kbps": 0}
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_streams", "-show_format", path],
            text=True, stderr=subprocess.DEVNULL)
        d   = json.loads(out)
        fmt = d.get("format", {})
        r["duration"]     = float(fmt.get("duration", 0))
        r["bitrate_kbps"] = int(fmt.get("bit_rate", 0)) // 1000
        for s in d.get("streams", []):
            if s.get("codec_type") == "video":
                r["width"]  = s.get("width",  0)
                r["height"] = s.get("height", 0)
                r["codec"]  = s.get("codec_name", "unknown")
                try:
                    n, dn = map(int, s.get("r_frame_rate","0/1").split("/"))
                    r["fps"] = round(n/dn, 2) if dn else 0.0
                except Exception:
                    pass
                break
    except Exception:
        pass
    return r


def encode(input_path, output_path, codec, crf, progress_cb=None, duration=0.0):
    """Returns (ok, msg, fflog, encode_seconds)."""
    cmap = {
        "AVC (H.264)":  ("libx264",    ["-preset", "fast"]),
        "HEVC (H.265)": ("libx265",    ["-preset", "fast"]),
        "AV1":          ("libaom-av1", ["-cpu-used","8","-tile-columns","2",
                                        "-threads","4","-usage","realtime"]),
    }
    lib, extra = cmap.get(codec, ("libx264",["-preset","fast"]))
    cmd = (["ffmpeg","-y","-i",input_path,"-c:v",lib,"-crf",str(crf)]
           + extra + ["-c:a","copy","-movflags","+faststart",output_path])
    lines = []; t0 = time.time()
    try:
        proc = subprocess.Popen(cmd, stderr=subprocess.PIPE,
                                stdout=subprocess.DEVNULL, text=True, bufsize=1)
        for line in proc.stderr:
            lines.append(line.rstrip())
            if progress_cb and "time=" in line and duration > 0:
                try:
                    ts = line.split("time=")[1].split(" ")[0]
                    h, m, s = map(float, ts.split(":"))
                    progress_cb(min((h*3600+m*60+s)/duration, 1.0))
                except Exception:
                    pass
        proc.wait()
        elapsed = time.time() - t0
        log = "\n".join(lines[-40:])
        if proc.returncode == 0:
            return True, "Done!", log, elapsed
        hints = {-6:"OOM (SIGABRT) — AV1 needs 1-4 GB RAM. Use H.264 on free tiers.",
                 -9:"OOM (SIGKILL) — use H.264 or a smaller file.",
                 -11:"Segfault — corrupted input or codec bug.",
                 1:"FFmpeg error — see log."}
        return False, hints.get(proc.returncode, f"FFmpeg exit {proc.returncode}"), log, elapsed
    except FileNotFoundError:
        return False, "FFmpeg not found. Add to PATH.", "", 0.0
    except Exception as e:
        return False, str(e), "\n".join(lines), time.time()-t0


def quality_metrics(ref: str, dist: str, do_vmaf: bool) -> dict:
    """Compute PSNR, SSIM and optionally VMAF via FFmpeg."""
    res = {"psnr": None, "ssim": None, "vmaf": None}

    # ── PSNR + SSIM ──
    try:
        cmd = ["ffmpeg","-y","-i",dist,"-i",ref,
               "-filter_complex","[0:v][1:v]psnr[po];[0:v][1:v]ssim[so]",
               "-map","[po]","-map","[so]","-f","null","-"]
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT,
                                      text=True, timeout=180)
        for line in out.splitlines():
            # PSNR line looks like: "PSNR y:44.12 u:... average:44.12 min:... max:..."
            if re.search(r"PSNR", line, re.I):
                m = re.search(r"average[:\s]+([0-9.]+|inf)", line, re.I)
                if m:
                    v = m.group(1)
                    res["psnr"] = 100.0 if v == "inf" else round(float(v), 3)
            # SSIM line: "SSIM Y:0.99... All:0.9923 (22.16)"
            if re.search(r"SSIM", line, re.I):
                m = re.search(r"All[:\s]+([0-9.]+)", line, re.I)
                if m:
                    res["ssim"] = round(float(m.group(1)), 5)
    except Exception:
        pass

    # ── VMAF ──
    if do_vmaf:
        try:
            vf = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
            vf.close()
            cmd = ["ffmpeg","-y","-i",dist,"-i",ref,
                   "-filter_complex",
                   f"[0:v][1:v]libvmaf=log_fmt=json:log_path={vf.name}",
                   "-f","null","-"]
            subprocess.run(cmd, capture_output=True, timeout=300, check=True)
            with open(vf.name) as f:
                vdata = json.load(f)
            score = (vdata.get("pooled_metrics",{}).get("vmaf",{}).get("mean")
                     or vdata.get("VMAF score")
                     or vdata.get("aggregate",{}).get("VMAF_score"))
            if score is not None:
                res["vmaf"] = round(float(score), 2)
            os.unlink(vf.name)
        except Exception:
            pass
    return res


def vmaf_display(v):
    if v is None: return "—", ""
    if v >= 93:   return f"{v:.1f} · Excellent", "q-exc"
    if v >= 80:   return f"{v:.1f} · Good",      "q-gd"
    if v >= 60:   return f"{v:.1f} · Fair",       "q-ok"
    return               f"{v:.1f} · Poor",       "q-bad"


def psnr_display(v):
    if v is None: return "—"
    tag = "Excellent" if v>=50 else "Good" if v>=40 else "Acceptable" if v>=30 else "Poor"
    return f"{v:.2f} dB · {tag}"


# ══════════════════════════════════════════════════════════════════════════════
#  Session state
# ══════════════════════════════════════════════════════════════════════════════
for k, v in {"results":[],"inp":None,"meta":None,"sz":0.0,"name":""}.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ══════════════════════════════════════════════════════════════════════════════
#  Page
# ══════════════════════════════════════════════════════════════════════════════

# Header
st.markdown("""
<div class="vf-header">
  <h1>🎬 VideoForge</h1>
  <p>Encode, compare, and quantify — H.264 vs HEVC vs AV1 with VMAF quality scoring</p>
  <span class="vf-badge">AVC H.264</span><span class="vf-badge">HEVC H.265</span>
  <span class="vf-badge">AV1</span><span class="vf-badge">VMAF</span>
  <span class="vf-badge">PSNR</span><span class="vf-badge">SSIM</span>
</div>""", unsafe_allow_html=True)

if not ffmpeg_ok():
    st.error("FFmpeg not found. Add `ffmpeg` to packages.txt and redeploy.")
    st.stop()

HAS_VMAF = vmaf_ok()

# ① Upload
st.markdown('<div class="vf-label">① Source Video</div>', unsafe_allow_html=True)
uploaded = st.file_uploader("Drop video here", type=["avi","mp4","mkv","mov","webm","flv","ts","m4v"],
                             label_visibility="collapsed")
if not uploaded:
    st.info("Upload a video to start encoding and quality analysis.")
    st.stop()

suf = os.path.splitext(uploaded.name)[-1].lower()
if st.session_state.name != uploaded.name:
    with tempfile.NamedTemporaryFile(delete=False, suffix=suf) as tmp:
        tmp.write(uploaded.read())
        st.session_state.inp  = tmp.name
    st.session_state.meta    = probe(st.session_state.inp)
    st.session_state.sz      = os.path.getsize(st.session_state.inp) / (1024*1024)
    st.session_state.name    = uploaded.name
    st.session_state.results = []

meta    = st.session_state.meta
sz_mb   = st.session_state.sz
inp     = st.session_state.inp

# Source preview + metadata
col_v, col_m = st.columns([3, 2], gap="large")
with col_v:
    st.video(inp)
with col_m:
    st.markdown("**Source file info**")
    r1, r2 = st.columns(2)
    r1.metric("Duration",     f"{meta['duration']:.1f} s")
    r2.metric("Resolution",   f"{meta['width']}×{meta['height']}")
    r1.metric("Frame rate",   f"{meta['fps']} fps")
    r2.metric("Bitrate",      f"{meta['bitrate_kbps']} kbps")
    r1.metric("File size",    f"{sz_mb:.2f} MB")
    r2.metric("Source codec", meta["codec"].upper())

st.divider()

# ② Settings
st.markdown('<div class="vf-label">② Encoder Settings</div>', unsafe_allow_html=True)
s1, s2, s3, s4 = st.columns([2, 2, 1, 2])
with s1:
    codec = st.selectbox("Codec", ["AVC (H.264)", "HEVC (H.265)", "AV1"],
                         help="H.264 = fastest. HEVC = ~40% smaller. AV1 = best compression, high RAM.")
with s2:
    crf = st.slider("CRF (quality)", 0, 51, 23,
                    help="Lower = better quality. 0 lossless · 18 visually lossless · 23 balanced · 28+ compact")
with s3:
    do_vmaf  = st.checkbox("VMAF", value=HAS_VMAF, disabled=not HAS_VMAF,
                            help="Perceptual quality score 0–100. Needs libvmaf in FFmpeg.")
    do_psnr  = st.checkbox("PSNR/SSIM", value=True)
with s4:
    ql = next(v for r,v in [
        (range(0,1),"🟢 Lossless"),(range(1,19),"🟢 High quality"),
        (range(19,29),"🟡 Balanced"),(range(29,40),"🟠 Compact"),(range(40,52),"🔴 Low quality")
    ] if crf in r)
    st.markdown(f"<br><b>{ql}</b><br><small style='color:#7888aa'>CRF {crf}</small>",
                unsafe_allow_html=True)

if codec == "AV1":
    st.warning("⚠️  AV1 needs 1–4 GB RAM. May crash on free cloud tiers (exit code -6). "
               "Works fine locally. Use H.264/HEVC for cloud deployment.")

# ③ Encode + Clear
st.markdown('<div class="vf-label" style="margin-top:6px">③ Run Encode</div>', unsafe_allow_html=True)
b1, b2, _ = st.columns([1.4, 1, 5])
go    = b1.button("⚙ Encode", type="primary", use_container_width=True)
clear = b2.button("🗑 Clear", use_container_width=True)
if clear:
    st.session_state.results = []
    st.rerun()

if go:
    out_path = inp.replace(suf, f"_{codec.split()[0].lower()}_crf{crf}.mp4")
    bar = st.progress(0.0, text=f"Starting {codec}…")

    with st.spinner(f"Encoding {codec} CRF {crf}…"):
        ok, msg, fflog, enc_t = encode(
            inp, out_path, codec, crf,
            progress_cb=lambda p: bar.progress(p, text=f"Encoding {codec}… {p*100:.0f}%"),
            duration=meta["duration"],
        )

    if not ok:
        bar.empty()
        st.error(f"❌ {msg}")
        if fflog:
            with st.expander("FFmpeg log"):
                st.code(fflog, language="bash")
    else:
        bar.progress(1.0, text="✅ Encode done — computing quality metrics…")
        out_meta  = probe(out_path)
        out_sz    = os.path.getsize(out_path) / (1024*1024)
        saved_pct = (1 - out_sz/sz_mb)*100 if sz_mb else 0

        qual = {"psnr":None,"ssim":None,"vmaf":None}
        if do_psnr or (do_vmaf and HAS_VMAF):
            with st.spinner("Analysing quality (PSNR/SSIM/VMAF)…"):
                qual = quality_metrics(inp, out_path, do_vmaf and HAS_VMAF)

        st.session_state.results.append({
            "codec": codec, "crf": crf,
            "size_mb": out_sz, "bitrate": out_meta["bitrate_kbps"],
            "enc_time": enc_t, "saved": saved_pct,
            "cr": sz_mb/out_sz if out_sz else 0,
            "psnr": qual["psnr"], "ssim": qual["ssim"], "vmaf": qual["vmaf"],
            "path": out_path,
        })
        bar.empty()
        q_str = f" · VMAF {qual['vmaf']:.1f}" if qual["vmaf"] else \
                f" · PSNR {qual['psnr']:.2f} dB" if qual["psnr"] else ""
        st.success(f"✅ {codec} CRF {crf}  ·  {out_sz:.2f} MB  ·  saved {saved_pct:.1f}%  ·  {enc_t:.1f}s{q_str}")

# ══════════════════════════════════════════════════════════════════════════════
#  Results dashboard
# ══════════════════════════════════════════════════════════════════════════════
results = st.session_state.results
if not results:
    st.caption("Results and charts appear here after encoding.")
    st.stop()

st.divider()
st.markdown('<div class="vf-label">④ Analytics Dashboard</div>', unsafe_allow_html=True)

tab_tbl, tab_chart, tab_dl = st.tabs(["📋 Comparison Table", "📈 Charts & Insights", "⬇ Downloads"])

# ── Table ─────────────────────────────────────────────────────────────────────
with tab_tbl:
    best_sz  = min(r["size_mb"]  for r in results)
    best_cr  = max(r["cr"]       for r in results)
    best_spd = min(r["enc_time"] for r in results)
    best_vm  = max((r["vmaf"]  or 0) for r in results) if any(r["vmaf"]  for r in results) else None
    best_pn  = max((r["psnr"]  or 0) for r in results) if any(r["psnr"]  for r in results) else None
    best_ss  = max((r["ssim"]  or 0) for r in results) if any(r["ssim"]  for r in results) else None

    def best_mark(val, best, fmt="{}", higher_better=False):
        if val is None or best is None: return "—"
        is_best = (val == best)
        s = fmt.format(val)
        if is_best:
            return f'<span class="best-val">{s} <span class="w-badge">BEST</span></span>'
        return s

    rows_html = ""
    for r in results:
        cs = r["codec"].split()[0]
        chip_cls = {"AVC":"chip-avc","HEVC":"chip-hevc","AV1":"chip-av1"}.get(cs,"")
        tag = f'<span class="{chip_cls}">{cs}</span>'

        vmaf_txt, vmaf_cls = vmaf_display(r["vmaf"])
        vmaf_cell = f'<span class="{vmaf_cls}">{vmaf_txt}</span>'
        if r["vmaf"] and best_vm and r["vmaf"] == best_vm and len(results)>1:
            vmaf_cell += ' <span class="w-badge">BEST</span>'

        rows_html += f"""<tr>
          <td>{tag}</td>
          <td style="font-family:'IBM Plex Mono'">{r['crf']}</td>
          <td>{best_mark(r['size_mb'], best_sz, "{:.2f} MB")}</td>
          <td>{r['bitrate']} kbps</td>
          <td>{best_mark(r['cr'], best_cr, "{:.2f}×", True)}</td>
          <td>{r['saved']:.1f}%</td>
          <td>{best_mark(r['enc_time'], best_spd, "{:.1f}s")}</td>
          <td>{vmaf_cell}</td>
          <td>{psnr_display(r['psnr'])}</td>
          <td>{"%.5f" % r['ssim'] if r['ssim'] else "—"}</td>
        </tr>"""

    st.markdown(f"""
    <table class="cmp-table">
      <thead><tr>
        <th>Codec</th><th>CRF</th><th>File Size</th><th>Bitrate</th>
        <th>Comp. Ratio</th><th>Saved</th><th>Encode Time</th>
        <th>VMAF ↑</th><th>PSNR ↑</th><th>SSIM ↑</th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
    <div class="src-bar">
      <b>Source (original):</b> &nbsp;
      {meta['codec'].upper()} &nbsp;·&nbsp; {sz_mb:.2f} MB &nbsp;·&nbsp;
      {meta['bitrate_kbps']} kbps &nbsp;·&nbsp;
      {meta['width']}×{meta['height']} &nbsp;·&nbsp; {meta['fps']} fps
    </div>
    """, unsafe_allow_html=True)

    st.caption("VMAF 93+ = Excellent · 80–93 = Good · 60–80 = Fair · <60 = Poor. "
               "PSNR 40+ dB = Good. SSIM closer to 1.0 = better. BEST = winner in that column.")

# ── Charts ────────────────────────────────────────────────────────────────────
with tab_chart:
    import pandas as pd

    df = pd.DataFrame([{
        "Codec":             r["codec"],
        "File Size (MB)":    round(r["size_mb"], 3),
        "Bitrate (kbps)":    r["bitrate"],
        "Encode Time (s)":   round(r["enc_time"], 2),
        "Space Saved (%)":   round(r["saved"], 1),
        "Comp. Ratio":       round(r["cr"], 2),
        "VMAF":              r["vmaf"],
        "PSNR (dB)":         round(r["psnr"], 2) if r["psnr"] else None,
        "SSIM":              round(r["ssim"], 5) if r["ssim"] else None,
    } for r in results])

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("**File size — encoded vs original (MB)**")
        size_df = pd.DataFrame(
            [{"Codec":"Original","File Size (MB)":round(sz_mb,3)}]
            + [{"Codec":r["codec"],"File Size (MB)":round(r["size_mb"],3)} for r in results]
        ).set_index("Codec")
        st.bar_chart(size_df, color="#2e86de", use_container_width=True)

        st.markdown("**Encode time (seconds)**")
        st.bar_chart(df.set_index("Codec")[["Encode Time (s)"]], color="#e67e22", use_container_width=True)

    with c2:
        st.markdown("**Bitrate — encoded vs original (kbps)**")
        brate_df = pd.DataFrame(
            [{"Codec":"Original","Bitrate (kbps)":meta["bitrate_kbps"]}]
            + [{"Codec":r["codec"],"Bitrate (kbps)":r["bitrate"]} for r in results]
        ).set_index("Codec")
        st.bar_chart(brate_df, color="#6c5ce7", use_container_width=True)

        st.markdown("**Space saved vs original (%)**")
        st.bar_chart(df.set_index("Codec")[["Space Saved (%)"]], color="#00a878", use_container_width=True)

    # Quality metrics
    q_available = [c for c in ["VMAF","PSNR (dB)","SSIM"] if df[c].notna().any()]
    if q_available:
        st.markdown("**Quality metrics comparison**")
        qdf = df.set_index("Codec")[q_available].dropna(how="all")
        st.bar_chart(qdf, use_container_width=True)
        st.caption("VMAF/PSNR/SSIM are on different scales. All higher = better.")

    # ── Insights ──
    if len(results) > 1:
        st.markdown("---")
        st.markdown("**Summary insights**")
        smallest = min(results, key=lambda r: r["size_mb"])
        fastest  = min(results, key=lambda r: r["enc_time"])
        most_saved = max(results, key=lambda r: r["saved"])
        best_qual  = max(results, key=lambda r: (r["vmaf"] or 0) + (r["psnr"] or 0)/5)

        i1, i2, i3, i4 = st.columns(4)
        i1.metric("Smallest file",   smallest["codec"].split()[0],
                  f"{smallest['size_mb']:.2f} MB")
        i2.metric("Fastest encode",  fastest["codec"].split()[0],
                  f"{fastest['enc_time']:.1f}s")
        i3.metric("Most compressed", most_saved["codec"].split()[0],
                  f"{most_saved['saved']:.1f}% saved")
        bq_val = (f"VMAF {best_qual['vmaf']:.1f}" if best_qual["vmaf"]
                  else f"PSNR {best_qual['psnr']:.1f} dB" if best_qual["psnr"] else "—")
        i4.metric("Best quality",    best_qual["codec"].split()[0], bq_val)

        # Efficiency note
        if len(results) >= 2:
            # Best quality-per-MB
            eff = max(results, key=lambda r: ((r["vmaf"] or 0) / r["size_mb"]) if r["size_mb"] else 0)
            if eff["vmaf"]:
                st.markdown(
                    f'<div class="insight-note">💡 <b>{eff["codec"]}</b> offers the best '
                    f'quality-per-MB ratio (VMAF {eff["vmaf"]:.1f} at {eff["size_mb"]:.2f} MB). '
                    f'Ideal if you want the best perceptual quality for the smallest file.</div>',
                    unsafe_allow_html=True
                )

# ── Downloads ─────────────────────────────────────────────────────────────────
with tab_dl:
    for r in results:
        cs = r["codec"].split()[0]
        dl_c, info_c = st.columns([2, 5])
        with dl_c:
            try:
                with open(r["path"], "rb") as f:
                    st.download_button(
                        label=f"⬇ {cs}  CRF {r['crf']}",
                        data=f,
                        file_name=f"videoforge_{cs.lower()}_crf{r['crf']}.mp4",
                        mime="video/mp4",
                        use_container_width=True,
                        key=f"dl_{cs}_{r['crf']}_{id(r)}",
                    )
            except FileNotFoundError:
                st.caption("⚠ Temp file expired — re-encode to download again.")
        with info_c:
            vm = f" · VMAF {r['vmaf']:.1f}" if r["vmaf"] else ""
            pn = f" · PSNR {r['psnr']:.2f} dB" if r["psnr"] else ""
            st.caption(f"{r['size_mb']:.2f} MB · {r['bitrate']} kbps · "
                       f"saved {r['saved']:.1f}% · encoded in {r['enc_time']:.1f}s{vm}{pn}")
    st.caption("⚠ Files live in server temp storage — download immediately after encoding.")
