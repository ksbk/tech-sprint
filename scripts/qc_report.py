from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from techsprint.utils import ffmpeg
TECHSPRINT_DIR = ROOT / ".techsprint"
REPORT_PATH = ROOT / "docs" / "qc_report.md"


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True)


srt_time_re = re.compile(r"(\d+):(\d+):(\d+),(\d+)")


def parse_srt_time(t: str) -> float | None:
    m = srt_time_re.match(t.strip())
    if not m:
        return None
    h, mnt, s, ms = map(int, m.groups())
    return h * 3600 + mnt * 60 + s + ms / 1000.0


def analyze_srt(path: Path) -> dict:
    if not path.exists():
        return {
            "exists": False,
            "count": 0,
            "min_start": None,
            "max_end": None,
            "broken": True,
            "overlaps": 0,
        }
    text = path.read_text(encoding="utf-8", errors="ignore")
    blocks = [b for b in text.split("\n\n") if b.strip()]
    cues = []
    broken = False
    overlaps = 0
    last_end = -1.0
    for block in blocks:
        lines = [l for l in block.splitlines() if l.strip()]
        if len(lines) < 2:
            continue
        timing = lines[1] if "-->" in lines[1] else (lines[0] if "-->" in lines[0] else None)
        if not timing:
            broken = True
            continue
        parts = [p.strip() for p in timing.split("-->")]
        if len(parts) != 2:
            broken = True
            continue
        start = parse_srt_time(parts[0])
        end = parse_srt_time(parts[1])
        if start is None or end is None or end < start:
            broken = True
            continue
        cues.append((start, end))
        if start < last_end:
            overlaps += 1
        last_end = max(last_end, end)
    if not cues:
        return {
            "exists": True,
            "count": 0,
            "min_start": None,
            "max_end": None,
            "broken": True,
            "overlaps": overlaps,
        }
    min_start = min(s for s, _ in cues)
    max_end = max(e for _, e in cues)
    return {
        "exists": True,
        "count": len(cues),
        "min_start": min_start,
        "max_end": max_end,
        "broken": broken,
        "overlaps": overlaps,
    }


def parse_fps(rate: str | None) -> float | None:
    if not rate or rate == "0/0":
        return None
    try:
        num, den = rate.split("/")
        return float(num) / float(den)
    except Exception:
        return None


def analyze_audio_vol(path: Path) -> dict | None:
    if not shutil.which("ffmpeg"):
        return None
    cmd = ["ffmpeg", "-v", "info", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"]
    proc = run(cmd)
    if proc.returncode != 0:
        return None
    out = proc.stderr
    mean = None
    maxv = None
    for line in out.splitlines():
        if "mean_volume" in line:
            try:
                mean = float(line.split(":")[-1].strip().replace(" dB", ""))
            except Exception:
                pass
        if "max_volume" in line:
            try:
                maxv = float(line.split(":")[-1].strip().replace(" dB", ""))
            except Exception:
                pass
    return {"mean_volume_db": mean, "max_volume_db": maxv}


def size_ok(size: int) -> bool:
    return size > 50_000


def main() -> int:
    mp4s = sorted(
        TECHSPRINT_DIR.glob("*/final.mp4"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:3]
    issues = []
    results = []

    for mp4 in mp4s:
        run_dir = mp4.parent
        srt = run_dir / "captions.srt"
        srt_info = analyze_srt(srt)

        size = mp4.stat().st_size
        probe = ffmpeg.probe_duration(mp4)
        duration = probe
        vcodec = pix_fmt = None
        width = height = fps = None
        audio_present = False

        if shutil.which("ffprobe"):
            proc = run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_format",
                    "-show_streams",
                    "-of",
                    "json",
                    str(mp4),
                ]
            )
            if proc.returncode == 0:
                data = json.loads(proc.stdout)
                duration = float(data.get("format", {}).get("duration") or 0.0) or None
                for st in data.get("streams", []):
                    if st.get("codec_type") == "video":
                        width = st.get("width")
                        height = st.get("height")
                        vcodec = st.get("codec_name")
                        pix_fmt = st.get("pix_fmt")
                        fps = parse_fps(st.get("avg_frame_rate") or st.get("r_frame_rate"))
                    if st.get("codec_type") == "audio":
                        audio_present = True

        vol = analyze_audio_vol(mp4)
        loudnorm = None
        try:
            loudnorm = ffmpeg.probe_loudnorm(mp4)
        except Exception:
            loudnorm = None

        subtitle_coverage = None
        if duration and srt_info["min_start"] is not None and srt_info["max_end"] is not None:
            span = srt_info["max_end"] - srt_info["min_start"]
            subtitle_coverage = span / duration if duration > 0 else None

        tmp_dir = run_dir / "tmp"
        tmp_ok = True
        if tmp_dir.exists():
            tmp_files = list(tmp_dir.rglob("*"))
            tmp_ok = len([p for p in tmp_files if p.is_file()]) == 0

        results.append(
            {
                "run_id": run_dir.name,
                "size_bytes": size,
                "duration": duration,
                "width": width,
                "height": height,
                "fps": fps,
                "vcodec": vcodec,
                "pix_fmt": pix_fmt,
                "audio_present": audio_present,
                "vol": vol,
                "srt": srt_info,
                "subtitle_coverage": subtitle_coverage,
                "tmp_clean": tmp_ok,
                "loudnorm": loudnorm,
            }
        )

        if size == 0 or not size_ok(size):
            issues.append(f"{run_dir.name}: final.mp4 size suspicious ({size} bytes)")
        if duration is not None and duration <= 1.0:
            issues.append(f"{run_dir.name}: duration too short ({duration:.2f}s)")
        if vcodec and vcodec != "h264":
            issues.append(f"{run_dir.name}: non-h264 video codec ({vcodec})")
        if pix_fmt and pix_fmt != "yuv420p":
            issues.append(f"{run_dir.name}: non-yuv420p pixel format ({pix_fmt})")
        if not audio_present:
            issues.append(f"{run_dir.name}: no audio stream")

        if loudnorm:
            try:
                out_i = float(loudnorm.get("output_i"))
                out_tp = float(loudnorm.get("output_tp"))
                out_lra = float(loudnorm.get("output_lra"))
                if not (-18 <= out_i <= -14):
                    issues.append(f"{run_dir.name}: loudness out of range ({out_i} LUFS)")
                if out_tp > -1.5:
                    issues.append(f"{run_dir.name}: true peak too high ({out_tp} dBTP)")
                if out_lra > 20:
                    issues.append(f"{run_dir.name}: high LRA ({out_lra} LU)")
            except Exception:
                issues.append(f"{run_dir.name}: loudnorm parse incomplete")
        else:
            issues.append(f"{run_dir.name}: loudnorm unavailable")

        if not srt_info["exists"]:
            issues.append(f"{run_dir.name}: captions.srt missing")
        else:
            if srt_info["count"] < 2:
                issues.append(f"{run_dir.name}: too few subtitle cues ({srt_info['count']})")
            if srt_info["broken"]:
                issues.append(f"{run_dir.name}: subtitle timestamps malformed or non-monotonic")
            if subtitle_coverage is not None and subtitle_coverage < 0.6:
                issues.append(f"{run_dir.name}: subtitle coverage low ({subtitle_coverage:.0%})")
        if not tmp_ok:
            issues.append(f"{run_dir.name}: tmp directory contains files")

    lines = []
    lines.append("# QC Report")
    lines.append("")
    lines.append(f"Runs analyzed: {len(results)}")
    lines.append("")
    lines.append("| run_id | duration_s | resolution | fps | audio | mean_vol_db | max_vol_db | loudnorm_out_i | loudnorm_out_tp | loudnorm_out_lra | subtitles | coverage | size_bytes |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in results:
        duration = f"{r['duration']:.2f}" if r["duration"] is not None else "n/a"
        resolution = f"{r['width']}x{r['height']}" if r["width"] and r["height"] else "n/a"
        fps = f"{r['fps']:.2f}" if r["fps"] else "n/a"
        audio = "yes" if r["audio_present"] else "no"
        mean_vol = r["vol"]["mean_volume_db"] if r["vol"] else None
        max_vol = r["vol"]["max_volume_db"] if r["vol"] else None
        mean_vol = f"{mean_vol:.1f}" if mean_vol is not None else "n/a"
        max_vol = f"{max_vol:.1f}" if max_vol is not None else "n/a"
        loud = r["loudnorm"] or {}
        out_i = loud.get("output_i")
        out_tp = loud.get("output_tp")
        out_lra = loud.get("output_lra")
        out_i = f"{float(out_i):.1f}" if out_i is not None else "n/a"
        out_tp = f"{float(out_tp):.1f}" if out_tp is not None else "n/a"
        out_lra = f"{float(out_lra):.1f}" if out_lra is not None else "n/a"
        subs = f"{r['srt']['count']} cues" if r["srt"]["exists"] else "missing"
        coverage = r["subtitle_coverage"]
        coverage = f"{coverage:.0%}" if coverage is not None else "n/a"
        lines.append(
            f"| {r['run_id']} | {duration} | {resolution} | {fps} | {audio} | {mean_vol} | "
            f"{max_vol} | {out_i} | {out_tp} | {out_lra} | {subs} | {coverage} | "
            f"{r['size_bytes']} |"
        )

    lines.append("")
    lines.append("## Issues & Recommendations")
    if issues:
        for issue in issues:
            lines.append(f"- {issue}")
        lines.append("")
        lines.append("Suggested fixes:")
        lines.append("- Ensure demo background is generated via ffmpeg helpers when missing or invalid.")
        lines.append("- Keep ComposeService using ffmpeg helpers to enforce h264/yuv420p output settings.")
        lines.append("- If loudness is low, consider adding optional loudnorm/volume filters in ffmpeg helpers.")
        lines.append("- Ensure subtitles are written with valid, monotonic timestamps and cover most of the audio duration.")
        lines.append("- Keep tmp outputs scoped to each run directory and clean when appropriate.")
    else:
        lines.append("- No issues detected.")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:12]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
