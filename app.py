"""
VideoForge Web  –  Streamlit Encoder UI
Run with:  streamlit run streamlit_app.py

NOTE: Browser-based video *playback* uses the HTML5 <video> tag (no OpenCV).
      The encoder pipeline still calls FFmpeg server-side.

Deploy free on:
  • Streamlit Community Cloud  → https://streamlit.io/cloud
  • Hugging Face Spaces        → https://huggingface.co/spaces  (Docker/Streamlit SDK)
  • Railway / Render           → add a start command: streamlit run streamlit_app.py --server.port $PORT
"""

import os
import sys
import subprocess
import tempfile
import time
import threading
import streamlit as st


# ─────────────────────────────────────────────────────────────────────────────
#  Page config  (must be the very first Streamlit call)
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="VideoForge",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────────────────────────────────────────────
#  CSS Theming
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;600&display=swap');

html, body, [class*="css"] {
    font-family: 'JetBrains Mono', 'Consolas', monospace;
    background-color: #0d0d12;
    color: #c8c8e0;
}
.stApp { background-color: #0d0d12; }

/* Title */
h1 { color: #8080ff; letter-spacing: 0.05em; }
h2, h3 { color: #9090c0; }

/* Buttons */
.stButton>button {
    background: #1a1a28;
    border: 1px solid #3a3a58;
    border-radius: 6px;
    color: #b0b0d8;
    font-family: 'JetBrains Mono', monospace;
    padding: 8px 20px;
    transition: border-color 0.2s;
}
.stButton>button:hover { border-color: #6060c0; }

/* Progress */
.stProgress>div>div { background: linear-gradient(90deg, #4040aa, #8080ff); border-radius: 4px; }

/* Upload */
.stFileUploader { border: 1px dashed #2a2a40; border-radius: 8px; }

/* Sliders */
.stSlider [data-baseweb="slider"] { padding: 0; }

/* Metric */
[data-testid="metric-container"] { background: #12121e; border: 1px solid #2a2a38; border-radius: 8px; padding: 12px; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────
def ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True, timeout=5)
        return True
    except Exception:
        return False


def probe_video(path: str) -> dict:
    """Return basic video metadata via ffprobe."""
    result = {"duration": 0.0, "width": 0, "height": 0, "fps": 0.0, "codec": "unknown"}
    try:
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_streams", "-show_format", path
        ]
        import json
        out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
        data = json.loads(out)
        result["duration"] = float(data.get("format", {}).get("duration", 0))
        for s in data.get("streams", []):
            if s.get("codec_type") == "video":
                result["width"]  = s.get("width",  0)
                result["height"] = s.get("height", 0)
                result["codec"]  = s.get("codec_name", "unknown")
                fps_str          = s.get("r_frame_rate", "0/1")
                try:
                    n, d = map(int, fps_str.split("/"))
                    result["fps"] = round(n / d, 2) if d else 0.0
                except Exception:
                    pass
                break
    except Exception:
        pass
    return result


def encode_video(
    input_path: str,
    output_path: str,
    codec: str,
    crf: int,
    progress_callback=None,
    total_duration: float = 0.0,
) -> tuple[bool, str]:
    codec_map = {
        "AVC (H.264)":  ("libx264",    ["-preset", "medium"]),
        "HEVC (H.265)": ("libx265",    ["-preset", "medium"]),
        "AV1":          ("libaom-av1", ["-cpu-used", "4", "-row-mt", "1"]),
    }
    lib, extra = codec_map.get(codec, ("libx264", ["-preset", "medium"]))

    cmd = (
        ["ffmpeg", "-y", "-i", input_path, "-c:v", lib, "-crf", str(crf)]
        + extra
        + ["-c:a", "copy", "-movflags", "+faststart", output_path]
    )

    try:
        proc = subprocess.Popen(
            cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL,
            text=True, bufsize=1
        )
        for line in proc.stderr:
            if progress_callback and "time=" in line and total_duration > 0:
                try:
                    time_str    = line.split("time=")[1].split(" ")[0]
                    h, m, s     = map(float, time_str.split(":"))
                    cur_sec     = h * 3600 + m * 60 + s
                    pct         = min(cur_sec / total_duration, 1.0)
                    progress_callback(pct)
                except Exception:
                    pass
        proc.wait()
        if proc.returncode == 0:
            return True, "Encoding complete!"
        return False, f"FFmpeg exited with code {proc.returncode}"
    except FileNotFoundError:
        return False, "FFmpeg not found. Install it and add to PATH."
    except Exception as e:
        return False, str(e)


# ─────────────────────────────────────────────────────────────────────────────
#  App UI
# ─────────────────────────────────────────────────────────────────────────────
def main():
    st.markdown("# 🎬 VideoForge")
    st.markdown("**Software encoder & player  –  H.264 / HEVC / AV1**")
    st.divider()

    # ── FFmpeg check ──
    if not ffmpeg_available():
        st.error(
            "⚠️  FFmpeg not found on this server.  \n"
            "Install it: `apt-get install ffmpeg` (Linux) or `brew install ffmpeg` (macOS)."
        )
        st.stop()

    # ── Upload ──
    st.subheader("① Upload Video")
    uploaded = st.file_uploader(
        "Supported formats: AVI, MP4, MKV, MOV, WebM, TS",
        type=["avi", "mp4", "mkv", "mov", "webm", "flv", "ts", "m4v"],
    )

    if not uploaded:
        st.info("Upload a video file to begin.")
        return

    # Save upload to temp file so FFmpeg can read it
    suffix = os.path.splitext(uploaded.name)[-1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded.read())
        input_path = tmp.name

    # ── Probe metadata ──
    meta = probe_video(input_path)

    st.subheader("② Preview & Metadata")
    col1, col2 = st.columns([3, 2])

    with col1:
        # HTML5 playback – browser decodes natively
        st.video(input_path)

    with col2:
        st.markdown("**File info**")
        c1, c2 = st.columns(2)
        c1.metric("Duration",   f"{meta['duration']:.1f}s")
        c2.metric("Resolution", f"{meta['width']}×{meta['height']}")
        c1.metric("FPS",        f"{meta['fps']}")
        c2.metric("Codec",      meta["codec"].upper())
        st.markdown(f"**Filename:** `{uploaded.name}`")
        size_mb = os.path.getsize(input_path) / (1024 * 1024)
        st.markdown(f"**Size:** `{size_mb:.2f} MB`")

    st.divider()

    # ── Encoder settings ──
    st.subheader("③ Encoder Settings")

    ecol1, ecol2, ecol3 = st.columns([2, 2, 3])
    with ecol1:
        codec = st.selectbox("Output Codec", ["AVC (H.264)", "HEVC (H.265)", "AV1"],
                             help="AV1 = best compression, slowest. H.264 = fast, wide compat.")
    with ecol2:
        crf = st.slider("Quality (CRF)", 0, 51, 23,
                        help="Lower = higher quality. 0 = lossless. 18–28 = typical range.")

    quality_map = {
        range(0, 1):   "🟢 Lossless",
        range(1, 19):  "🟢 High quality",
        range(19, 28): "🟡 Balanced",
        range(28, 40): "🟠 Compact",
        range(40, 52): "🔴 Low quality",
    }
    quality_label = next(
        (v for k, v in quality_map.items() if crf in k), "Balanced"
    )
    with ecol3:
        st.markdown(f"<br>**{quality_label}**  (CRF {crf})", unsafe_allow_html=True)

    st.divider()

    # ── Encode button ──
    st.subheader("④ Encode")
    if st.button("⚙  Start Encoding", type="primary"):
        out_suffix = ".mp4"
        out_path   = input_path.replace(suffix, f"_encoded{out_suffix}")

        progress_bar  = st.progress(0.0, text="Starting FFmpeg…")
        status_text   = st.empty()

        def update_progress(pct: float):
            progress_bar.progress(pct, text=f"Encoding… {pct*100:.1f}%")

        with st.spinner("Encoding in progress…"):
            ok, msg = encode_video(
                input_path, out_path, codec, crf,
                progress_callback=update_progress,
                total_duration=meta["duration"],
            )

        if ok:
            progress_bar.progress(1.0, text="✅ Done!")
            st.success(msg)

            out_size = os.path.getsize(out_path) / (1024 * 1024)
            ratio    = out_size / size_mb * 100 if size_mb else 0
            st.markdown(
                f"**Output size:** `{out_size:.2f} MB`  &nbsp;|&nbsp;  "
                f"**vs original:** `{ratio:.0f}%`"
            )

            with open(out_path, "rb") as f:
                st.download_button(
                    label      = "⬇  Download Encoded Video",
                    data       = f,
                    file_name  = f"encoded_{uploaded.name.rsplit('.', 1)[0]}.mp4",
                    mime       = "video/mp4",
                )
        else:
            progress_bar.empty()
            st.error(f"Encoding failed: {msg}")

        # Cleanup temp files
        for p in (input_path, out_path):
            try:
                os.unlink(p)
            except Exception:
                pass


if __name__ == "__main__":
    main()
