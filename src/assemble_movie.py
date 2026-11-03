"""Assemble the demo movie, driven by video_frames/caption_story.md.

The story file is the single source of the captions: every section maps to
its segment(s), section text is split into readable cues, and each cue stays
on screen long enough to read (minimum time plus a max reading speed). When
a section's footage is shorter than its captions need, the segment's last
frame freezes until the captions finish.

Intro is opening_textbook_prop.webp, outro is closing_parent_report_win.webp,
each with a slow push-in. Segments join with crossfades, plus a fade in
from black at the start and a fade out to black at the end.

Usage (from repo root, no server needed):
  .venv/Scripts/python.exe src/assemble_movie.py

Outputs video_frames/movie_cut3.mp4 (picture squeezed to 1280x720 with
a black caption band below, small white captions in the band) and
video_frames/movie_cut3.srt (same cues).
"""

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FR = os.path.join(ROOT, "video_frames")
FFMPEG = os.environ.get("FFMPEG",
                         r"C:\Users\horia\ffmpeg\ffmpeg-9.0.2-"
                         r"essentials_build\bin\ffmpeg.exe")
FFPROBE = os.path.join(os.path.dirname(FFMPEG), "ffprobe.exe")
STORY = os.path.join(FR, "caption_story.md")
OUT_MP4 = os.path.join(FR, "movie_cut3.mp4")
OUT_SRT = os.path.join(FR, "movie_cut3.srt")
OUT_ASS = os.path.join(FR, "movie_cut3.ass")

# (source, trim_head, story section index)
SEGMENTS = [
    ("STILL:opening_textbook_prop.webp", 0.0, 0),
    ("take1_home_load.webm", 4.5, 0),
    ("take2_setup_tour.webm", 2.0, 1),
    ("take3_stuck_redraw.webm", 2.0, 2),
    ("take4_tap_lake.webm", 2.0, 3),
    ("take5_bored_challenge.webm", 2.0, 4),
    ("take6_why_timeline.webm", 2.0, 5),
    ("take7_builder_volcanoes.webm", 2.0, 6),
    ("take8_private_toggle.webm", 2.0, 7),
    ("take9_parent_report.webm", 2.0, 8),
    ("STILL:closing_parent_report_win.webp", 0.0, 8),
]

STILL_SECONDS = 6.0
FPS = 30
W, H = 1280, 800
XFADE = 0.6  # crossfade seconds between segments
MIN_CUE = 1.6  # every caption stays up at least this long
CPS = 20.0  # captions assume at most this many chars per second


def probe(path):
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def read_story():
    text = open(STORY, encoding="utf-8").read()
    parts = re.split(r"^\*\*.+?\*\*\s*$", text, flags=re.M)
    sections = []
    for part in parts[1:]:
        lines = [ln.strip().strip("*").strip()
                 for ln in part.strip().splitlines()]
        body = " ".join(ln for ln in lines if ln)
        sections.append(re.sub(r"\s+", " ", body))
    return sections


def wrap(text, width=42):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + 1 + len(w) <= width:
            cur = (cur + " " + w).strip()
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return "\n".join(lines)


def split_cues(text, width=64):
    """Split into short cues: sentences first, then long ones on commas."""
    sents = re.split(r"(?<=[.!?]) +", text)
    chunks = []
    for s in sents:
        if len(s) <= width:
            chunks.append(s)
        else:
            for bit in re.split(r"(?<=[,:;]) +", s):
                if len(bit) <= width:
                    chunks.append(bit)
                else:
                    words, cur = bit.split(), ""
                    for w in words:
                        if len(cur) + 1 + len(w) <= width:
                            cur = (cur + " " + w).strip()
                        else:
                            chunks.append(cur)
                            cur = w
                    if cur:
                        chunks.append(cur)
    cues, cur = [], ""
    for ch in chunks:
        if len(cur) + 1 + len(ch) <= width:
            cur = (cur + " " + ch).strip()
        else:
            if cur:
                cues.append(cur)
            cur = ch
    if cur:
        cues.append(cur)
    return cues


def cues_for(text, a, span):
    """Fit cues inside span: each cue gets a readable duration, and the
    return value reports how much extra footage the section needs (0
    when the cues already fit, so no caption spills into the next part).
    """
    cues = split_cues(text)
    raw = [min(max(len(c) / CPS, MIN_CUE), 5.0) for c in cues]
    need = sum(raw)
    scale = 1.0 if need <= span else span / need
    durs = [max(d0 * scale, MIN_CUE) for d0 in raw]
    total = sum(durs)
    extra = total - span if total > span else 0.0
    # Spread leftover time as small pauses so the last cue lands at the
    # end of the span (e.g. over the outro still) instead of front-loading.
    gap = max(0.0, (span - total) / len(durs)) if durs else 0.0
    out, t = [], a
    for c, d in zip(cues, durs):
        out.append((t + 0.05, t + d - 0.05, wrap(c, 56)))
        t += d + gap
    return out, extra


def stamp(t):
    ms = int(round((t - int(t)) * 1000))
    s = int(t) % 60
    m = (int(t) // 60) % 60
    h = int(t) // 3600
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def ass_stamp(t):
    cs = int(round((t - int(t)) * 100))
    s = int(t) % 60
    m = (int(t) // 60) % 60
    h = int(t) // 3600
    return "%d:%02d:%02d.%02d" % (h, m, s, cs)


def ass_text(text):
    return text.replace("\\", "\\\\").replace("{", "\\{").replace(
        "}", "\\}").replace("\n", "\\N")


def ass_header():
    # PlayRes matches the final frame (1280x800) so FontSize is in
    # real pixels. Bar is 80px tall; 22px keeps two lines inside it
    # with a small bottom margin (bottom-aligned via Alignment 2).
    return (
        "[Script Info]\nScriptType: v4.00+\n"
        "PlayResX: 1280\nPlayResY: 800\nWrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\nYCbCr Matrix: TV.709\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, "
        "PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, "
        "Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding\n"
        "Style: Caption,Arial,22,&H00FFFFFF,&H000019FF,&H80000000,"
        "&H80000000,0,0,0,0,100,100,0,0,1,1,0,2,40,40,8,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, "
        "MarginL, MarginR, MarginV, Effect, Text\n"
    )


def main():
    if not os.path.isfile(FFMPEG):
        sys.exit("ffmpeg not found: " + FFMPEG)
    sections = read_story()
    print("story sections: %d" % len(sections), flush=True)

    names = [f[6:] if f.startswith("STILL:") else f
             for f, _t, _s in SEGMENTS]
    for n in names:
        if not os.path.isfile(os.path.join(FR, n)):
            sys.exit("missing input: " + n)

    # Base durations, then freeze last frames so captions stay readable.
    durs = []
    for fname, trim, _sec in SEGMENTS:
        if fname.startswith("STILL:"):
            durs.append(STILL_SECONDS)
        else:
            durs.append(probe(os.path.join(FR, fname)) - trim)

    # Intro choreography: the opening still eases in for ~20s and only
    # crossfades to the home take when the last intro caption appears
    # ("So I built something that can."). Earlier cues play over the
    # still; the last cue plays over the home take, which is tail-trimmed
    # to that cue so no footage spills into the next section.
    TAIL = {}
    intro_keys = [k for k, (_f, _t, s) in enumerate(SEGMENTS) if s == 0]
    chunks = split_cues(sections[0])
    drawn = [min(max(len(c) / CPS, MIN_CUE), 5.0) for c in chunks]
    need_head = sum(drawn[:-1])
    D = max(20.0, need_head + XFADE + 0.2)
    r = D - XFADE  # transition starts here = last cue starts here
    gap9 = (r - need_head) / max(len(drawn) - 1, 1)
    intro_cues, t = [], 0.0
    for c, d in zip(chunks[:-1], drawn[:-1]):
        intro_cues.append((t + 0.05, t + d - 0.05, wrap(c, 56)))
        t += d + gap9
    d_last = drawn[-1]
    intro_cues.append((r + 0.05, r + d_last - 0.05,
                       wrap(chunks[-1], 56)))
    U_take = d_last + 0.5 + XFADE
    durs[intro_keys[0]] = D
    durs[intro_keys[-1]] = U_take
    TAIL[SEGMENTS[intro_keys[-1]][0]] = U_take

    # Caption cues per section, fitted inside the section span so no
    # caption spills into the next part. A section's captions must end
    # where the next section starts (the crossfade), so every section
    # but the last gets span minus XFADE. Extend the section's last
    # segment only when even minimum-time cues do not fit.
    def usable(sec):
        keys = [k for k, (_f, _t, s) in enumerate(SEGMENTS) if s == sec]
        # Footage occupancy minus the crossfade into the next section:
        # one XFADE per internal join plus one for the outgoing join,
        # except the last section which plays to the end.
        span = sum(durs[k] for k in keys) - len(keys) * XFADE
        if sec == len(sections) - 1:
            span += XFADE
        return keys, span

    srt, idx = [], 1
    all_cues = []
    for sec in range(len(sections)):
        if sec == 0:
            continue  # intro is choreographed exactly above
        keys, span = usable(sec)
        for _ in range(50):
            _cues, extra = cues_for(sections[sec], 0.0, span)
            if extra <= 0.01:
                break
            durs[keys[-1]] += extra
            span += extra

    # Place cues on the timeline (xfade overlaps shift sections earlier).
    starts = [0.0]
    for k in range(1, len(SEGMENTS)):
        starts.append(starts[-1] + durs[k - 1] - XFADE)
    for sec in range(len(sections)):
        keys, span = usable(sec)
        a = starts[keys[0]]
        if sec == 0:
            cues = [(s0 + a, s1 + a, tx) for s0, s1, tx in intro_cues]
        else:
            cues, _extra = cues_for(sections[sec], a, span)
            if cues and cues[-1][1] > a + span:
                s0, _s1, tx = cues[-1]
                cues[-1] = (s0, a + span, tx)
        for s0, s1, text in cues:
            srt += [str(idx), "%s --> %s" % (stamp(s0), stamp(s1)),
                    text, ""]
            idx += 1
            all_cues.append((s0, s1, text))
    with open(OUT_SRT, "w", encoding="utf-8") as f:
        f.write("\n".join(srt))
    with open(OUT_ASS, "w", encoding="utf-8") as f:
        f.write(ass_header())
        for s0, s1, text in all_cues:
            f.write("Dialogue: 0,%s,%s,Caption,,0,0,0,,%s\n" % (
                ass_stamp(s0), ass_stamp(s1), ass_text(text)))

    cmd = [FFMPEG, "-hide_banner", "-y"]
    for fname, _trim, _sec in SEGMENTS:
        if fname.startswith("STILL:"):
            cmd += ["-i", os.path.join(FR, fname[6:])]
        else:
            cmd += ["-i", os.path.join(FR, fname)]
    parts = []
    for k, (fname, trim, _sec) in enumerate(SEGMENTS):
        tag = "s%d" % k
        # Freeze extension: stills lengthen the push-in, takes hold the
        # last frame for the extra time captions need to be readable.
        if fname.startswith("STILL:"):
            frames = int(round(durs[k] * FPS))
            rate = 0.05 / max(frames, 1)
            parts.append(
                "[{k}:v]scale=2560:-2,zoompan=z='min(zoom+{rt},1.05)':"
                "d={d}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                "s={w}x{h}:fps={fps},format=yuv420p[{t}]".format(
                    k=k, rt=rate, d=frames, w=W, h=H, fps=FPS,
                    t=tag))
        else:
            raw = probe(os.path.join(FR, fname)) - trim
            tpad = ""
            if fname in TAIL and trim + TAIL[fname] < raw:
                end = trim + TAIL[fname]
                parts.append(
                    "[{k}:v]trim=start={tr}:end={end},"
                    "setpts=PTS-STARTPTS,fps={fps},"
                    "scale={w}:{h},format=yuv420p[{t}]".format(
                        k=k, tr=trim, end=end, fps=FPS, w=W, h=H,
                        t=tag))
                continue
            if durs[k] > raw:
                tpad = ",tpad=stop_mode=clone:stop_duration=%.2f" % (
                    durs[k] - raw)
            parts.append(
                "[{k}:v]trim=start={tr},setpts=PTS-STARTPTS,fps={fps},"
                "scale={w}:{h}{tp},format=yuv420p[{t}]".format(
                    k=k, tr=trim, fps=FPS, w=W, h=H, tp=tpad, t=tag))
    # Crossfade chain: each join overlaps by XFADE seconds.
    cur, cur_dur = "s0", durs[0]
    for k in range(1, len(SEGMENTS)):
        off = cur_dur - XFADE
        parts.append(
            "[{a}][s{k}]xfade=transition=fade:duration={xf}:"
            "offset={off:.2f}[v{k}]".format(
                a=cur, k=k, xf=XFADE, off=off))
        cur_dur = cur_dur + durs[k] - XFADE
        cur = "v%d" % k
    total = cur_dur
    sp = OUT_ASS.replace("\\", "/").replace(":", "\\:")
    bar_h = H // 10
    parts.append(
        "[{c}]fade=t=in:st=0:d=1,fade=t=out:st={end:.2f}:d=1,"
        "scale={w}:{ch},pad={w}:{h}:0:0,"
        "subtitles='{sp}',"
        "format=yuv420p[v]".format(
            c=cur, end=total - 1, w=W, ch=H - bar_h, h=H,
            sp=sp))
    cmd += ["-filter_complex", ";".join(parts),
            "-map", "[v]", "-t", "%.2f" % total,
            "-c:v", "libx264", "-crf", "20", "-preset", "medium",
            "-pix_fmt", "yuv420p", "-movflags", "faststart", "-an",
            OUT_MP4]
    print("total: %.1fs, cues: %d" % (total, idx - 1), flush=True)
    subprocess.run(cmd, check=True)
    print("wrote movie_cut3.mp4 + movie_cut3.srt + movie_cut3.ass")


if __name__ == "__main__":
    main()
