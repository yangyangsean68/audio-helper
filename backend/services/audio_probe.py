import json
import math
import os
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from config import settings
from errors import AppError

STAGE = "upload"


@dataclass(frozen=True)
class ProbeResult:
    container: str
    codec: str
    duration_sec: float


def _windows_path_dirs() -> list[Path]:
    dirs: list[Path] = []
    try:
        import winreg

        for hive, subkey in (
            (winreg.HKEY_CURRENT_USER, r"Environment"),
            (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        ):
            try:
                with winreg.OpenKey(hive, subkey) as key:
                    value, _ = winreg.QueryValueEx(key, "Path")
            except OSError:
                continue
            for item in str(value).split(";"):
                item = item.strip()
                if item:
                    dirs.append(Path(os.path.expandvars(item)))
    except ImportError:
        pass
    return dirs


@lru_cache(maxsize=1)
def _ffprobe_executable() -> str | None:
    found = shutil.which("ffprobe") or shutil.which("ffprobe.exe")
    if found:
        return found
    candidates: list[Path] = []
    for directory in _windows_path_dirs():
        candidates.append(directory / "ffprobe.exe")
        candidates.append(directory / "ffprobe")
    local_app = os.environ.get("LOCALAPPDATA", "")
    if local_app:
        winget = Path(local_app) / "Microsoft" / "WinGet" / "Packages"
        candidates.extend(winget.glob("Gyan.FFmpeg*/ffmpeg-*/bin/ffprobe.exe"))
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


def _parse_duration(value: object) -> float | None:
    if value in (None, "", "N/A", "n/a", "nan"):
        return None
    try:
        duration = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(duration) or duration <= 0:
        return None
    return duration


def _run_ffprobe(args: list[str]) -> dict:
    ffprobe = _ffprobe_executable()
    if not ffprobe:
        raise AppError(
            502,
            "AUDIO_PROBE_UNAVAILABLE",
            "无法校验音频：未找到 ffprobe。请安装 FFmpeg 并将其 bin 目录加入 PATH。",
            STAGE,
        )
    try:
        completed = subprocess.run(
            [ffprobe, *args],
            capture_output=True,
            text=True,
            timeout=settings.ffprobe_timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AppError(
            504,
            "UPSTREAM_TIMEOUT",
            "音频校验超时，请稍后重试。",
            STAGE,
        ) from exc
    except OSError as exc:
        raise AppError(
            502,
            "AUDIO_PROBE_UNAVAILABLE",
            "无法校验音频：调用 ffprobe 失败。",
            STAGE,
        ) from exc

    if completed.returncode != 0:
        raise AppError(
            415,
            "AUDIO_UNSUPPORTED_TYPE",
            "不支持该录音格式。请使用支持 WebM/Opus 的浏览器重新录音。",
            STAGE,
        )
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise AppError(
            415,
            "AUDIO_UNSUPPORTED_TYPE",
            "不支持该录音格式。请使用支持 WebM/Opus 的浏览器重新录音。",
            STAGE,
        ) from exc
    if not isinstance(payload, dict):
        raise AppError(
            415,
            "AUDIO_UNSUPPORTED_TYPE",
            "不支持该录音格式。请使用支持 WebM/Opus 的浏览器重新录音。",
            STAGE,
        )
    return payload


def _duration_from_packets(path: Path) -> float | None:
    payload = _run_ffprobe(
        [
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "packet=pts_time,duration_time",
            "-of",
            "json",
            str(path),
        ]
    )
    packets = payload.get("packets") or []
    samples: list[tuple[float, float]] = []
    for packet in packets:
        if not isinstance(packet, dict):
            continue
        pts = _parse_duration(packet.get("pts_time"))
        if pts is None:
            continue
        packet_duration = _parse_duration(packet.get("duration_time")) or 0.0
        samples.append((pts, packet_duration))
    if not samples:
        return None
    first_pts = samples[0][0]
    last_pts, last_duration = samples[-1]
    duration = last_pts + last_duration - first_pts
    return duration if duration > 0 else None


def probe_audio(path: Path) -> ProbeResult:
    payload = _run_ffprobe(
        [
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
    )
    format_info = payload.get("format") or {}
    format_name = str(format_info.get("format_name") or "")
    containers = {item.strip().lower() for item in format_name.split(",") if item.strip()}
    if "webm" not in containers:
        raise AppError(
            415,
            "AUDIO_UNSUPPORTED_TYPE",
            "不支持该录音格式。请使用支持 WebM/Opus 的浏览器重新录音。",
            STAGE,
        )

    audio_stream = None
    for stream in payload.get("streams") or []:
        if isinstance(stream, dict) and stream.get("codec_type") == "audio":
            audio_stream = stream
            break
    if audio_stream is None:
        raise AppError(
            415,
            "AUDIO_UNSUPPORTED_TYPE",
            "不支持该录音格式。请使用支持 WebM/Opus 的浏览器重新录音。",
            STAGE,
        )

    codec = str(audio_stream.get("codec_name") or "").lower()
    if codec != "opus":
        raise AppError(
            415,
            "AUDIO_UNSUPPORTED_TYPE",
            "不支持该录音格式。请使用支持 WebM/Opus 的浏览器重新录音。",
            STAGE,
        )

    duration = _parse_duration(format_info.get("duration"))
    if duration is None:
        duration = _parse_duration(audio_stream.get("duration"))
    if duration is None:
        duration = _duration_from_packets(path)
    if duration is None:
        raise AppError(
            422,
            "AUDIO_DURATION_INVALID",
            "无法确认录音时长，请重新录音。",
            STAGE,
        )

    return ProbeResult(container="webm", codec=codec, duration_sec=duration)
