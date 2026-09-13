#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
B 站视频下载器（自包含）

依赖：
  - yt-dlp        : 解析并下载 B 站视频
  - imageio-ffmpeg: 提供静态 ffmpeg 二进制（B 站为 DASH 分离流，需 ffmpeg 合并音视频）

特性：
  - 自动安装缺失依赖（写入当前 Python 环境）
  - 自动定位/缓存 ffmpeg 二进制，确保 yt-dlp 能合并音视频
  - 若 yt-dlp 未能合并（ffmpeg 未识别），自动兜底合并分离的 .f3xxx.mp4/.m4a 分片
  - 输出目录默认为 ./bilibili_downloads，可用 --out 指定

用法：
  python download_bilibili.py "<B站视频URL>" [--out 目录] [--quality "bv*+ba/b"] [--cookies 路径]
"""

import argparse
import glob
import os
import shutil
import subprocess
import sys

# ---------------------------------------------------------------------------
# 依赖与 ffmpeg 准备
# ---------------------------------------------------------------------------

def ensure_deps():
    """确保 yt-dlp 与 imageio-ffmpeg 已安装，并返回 ffmpeg 可执行文件路径。"""
    py = sys.executable

    # 1) 安装/校验 yt-dlp
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        print("[setup] 安装 yt-dlp ...")
        subprocess.run([py, "-m", "pip", "install", "-q", "--upgrade", "yt-dlp"], check=True)

    # 2) 安装/校验 imageio-ffmpeg
    try:
        import imageio_ffmpeg
    except ImportError:
        print("[setup] 安装 imageio-ffmpeg ...")
        subprocess.run([py, "-m", "pip", "install", "-q", "imageio-ffmpeg"], check=True)
        import imageio_ffmpeg  # 重新导入

    # 3) 把 ffmpeg 二进制缓存为 ffmpeg.exe（yt-dlp 只认 ffmpeg/ffprobe 命名）
    src = imageio_ffmpeg.get_ffmpeg_exe()  # 形如 ffmpeg-win-x86_64-vX.X.exe
    cache_dir = os.path.join(os.path.expanduser("~"), ".workbuddy", "binaries", "ffmpeg")
    os.makedirs(cache_dir, exist_ok=True)
    dst = os.path.join(cache_dir, "ffmpeg.exe")
    if (not os.path.exists(dst)) or (os.path.getmtime(dst) < os.path.getmtime(src)):
        shutil.copy(src, dst)
        print(f"[setup] ffmpeg 已缓存: {dst}")
    else:
        print(f"[setup] ffmpeg 已存在: {dst}")
    return dst


# ---------------------------------------------------------------------------
# 下载与合并
# ---------------------------------------------------------------------------

def get_expected_path(url, out_dir):
    """预取视频标题，确定性推导最终文件名（兼容多视频共存目录与重复下载）。"""
    try:
        r = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--no-playlist", "--print", "%(title)s", url],
            capture_output=True, text=True, timeout=90,
        )
        title = r.stdout.strip().splitlines()[0] if r.stdout.strip() else ""
    except Exception:
        title = ""
    if title:
        return os.path.join(out_dir, title + ".mp4")
    return None


def download(url, out_dir, quality, cookies):
    os.makedirs(out_dir, exist_ok=True)
    before = set(os.listdir(out_dir))  # 基线快照：用于事后定位本次下载的成品
    ffmpeg_exe = ensure_deps()
    ffmpeg_dir = os.path.dirname(ffmpeg_exe)

    # 预取标题，确定性地推导最终文件名（避免目录已有其他视频 / 重复下载时被误判）
    expected = get_expected_path(url, out_dir)

    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--ffmpeg-location", ffmpeg_dir,
        "--merge-output-format", "mp4",
        "--no-playlist",
        "-f", quality,
        "-o", os.path.join(out_dir, "%(title)s.%(ext)s"),
    ]
    if cookies:
        cmd += ["--cookies", cookies]
    cmd += [url]

    print("[download] 命令:", " ".join(cmd))
    rc = subprocess.run(cmd).returncode
    if rc != 0:
        raise RuntimeError(f"yt-dlp 返回非零退出码: {rc}")

    # yt-dlp 若成功合并，会直接产出 <title>.mp4 并清理分片；
    # 若因 ffmpeg 未识别而只下了分离分片，则在此兜底合并。
    parts_v = sorted(glob.glob(os.path.join(out_dir, "*.f3*.mp4")))
    parts_a = sorted(glob.glob(os.path.join(out_dir, "*.f3*.m4a")))

    if parts_v and parts_a:
        print("[merge] 检测到分离分片，执行兜底合并 ...")
        title = os.path.basename(parts_v[0]).split(".f3")[0]
        out_mp4 = os.path.join(out_dir, title + ".mp4")
        mcmd = [ffmpeg_exe, "-y", "-i", parts_v[0], "-i", parts_a[0], "-c", "copy", out_mp4]
        subprocess.run(mcmd, check=True)
        for p in parts_v + parts_a:
            os.remove(p)

    # 优先用"预期文件名"定位成品（确定性，兼容重复下载与多视频共存目录）
    if expected and os.path.exists(expected):
        return expected
    # 其次用"下载前后目录快照差集"
    created = [os.path.join(out_dir, f) for f in os.listdir(out_dir)
               if f not in before and f.lower().endswith(".mp4")]
    if not created:
        all_mp4 = glob.glob(os.path.join(out_dir, "*.mp4"))
        if not all_mp4:
            raise RuntimeError("未生成任何 mp4 文件，下载可能失败")
        created = [max(all_mp4, key=os.path.getsize)]  # 兜底：快照异常时退回体积最大者
    return created[0]


# ---------------------------------------------------------------------------
# 格式统一：确保产出为 H.264 + AAC（手机通用）
# ---------------------------------------------------------------------------

def probe_codec(path, ffmpeg_exe):
    """探测视频/音频编码，返回 (video_codec_lower, audio_codec_lower)。"""
    r = subprocess.run([ffmpeg_exe, "-i", path], capture_output=True, text=True)
    o = r.stderr
    vcodec = ""
    acodec = ""
    for l in o.splitlines():
        if "Video:" in l:
            vcodec = l.split("Video:")[1].split("(")[0].strip().lower()
        elif "Audio:" in l:
            acodec = l.split("Audio:")[1].split("(")[0].strip().lower()
    return vcodec, acodec


def ensure_h264_aac(path, ffmpeg_exe):
    """确保视频最终为 H.264 + AAC（手机通用）。

    - 已是 H.264 + AAC：原样返回，不做任何处理。
    - 否则：用 ffmpeg 重编码为 H.264(libx264) + AAC，先写临时文件，校验通过后才替换原文件。
    返回最终文件路径。
    """
    v, a = probe_codec(path, ffmpeg_exe)
    is_h264 = ("h264" in v) or ("avc" in v)
    is_aac = "aac" in a
    if is_h264 and is_aac:
        print(f"[transcode] 已是 H.264+AAC，跳过: {os.path.basename(path)}")
        return path

    print(f"[transcode] 检测到 {v or 'NA'}/{a or 'NA'}，转码为 H.264+AAC ...")
    tmp = path + ".tmp_h264.mp4"
    # 视频：非 H.264 才重编码，已是则直接 copy；音频同理（非 AAC 才重编码）
    vcmd = (["-c:v", "libx264", "-crf", "20", "-preset", "medium", "-pix_fmt", "yuv420p"]
            if not is_h264 else ["-c:v", "copy"])
    acmd = (["-c:a", "aac", "-b:a", "128k"] if not is_aac else ["-c:a", "copy"])
    cmd = [ffmpeg_exe, "-y", "-i", path] + vcmd + acmd + ["-movflags", "+faststart", tmp]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(tmp):
        print("[transcode][WARN] 转码失败，保留原文件:", file=sys.stderr)
        if os.path.exists(tmp):
            os.remove(tmp)
        return path
    # 校验产物编码
    nv, na = probe_codec(tmp, ffmpeg_exe)
    if (not ("h264" in nv or "avc" in nv)) or ("aac" not in na):
        print("[transcode][WARN] 产物编码校验未通过，保留原文件", file=sys.stderr)
        if os.path.exists(tmp):
            os.remove(tmp)
        return path
    os.replace(tmp, path)
    return path


def main():
    ap = argparse.ArgumentParser(description="B 站视频下载器")
    ap.add_argument("url", help="B 站视频 URL（支持带 ?vd_source= 等参数）")
    ap.add_argument("--out", default="./bilibili_downloads", help="输出目录（默认 ./bilibili_downloads）")
    ap.add_argument("--quality", default="bv*+ba/b",
                    help='清晰度选择，默认 "bv*+ba/b"（最佳视频+最佳音频）；可改为 "bv[height<=720]+ba/b" 等')
    ap.add_argument("--cookies", default=None, help="cookie 文件路径（部分受限视频需要登录态）")
    args = ap.parse_args()

    try:
        final = download(args.url, args.out, args.quality, args.cookies)
        ffmpeg_exe = ensure_deps()
        final = ensure_h264_aac(final, ffmpeg_exe)
        size_mb = os.path.getsize(final) / 1024 / 1024
        msg = f"OK|{final}|{size_mb:.1f}MB"
        print("[result]", msg)
        # 额外写一份结果文件，便于在 stdout 不回显的环境里确认
        with open(os.path.join(args.out, "download_result.txt"), "w", encoding="utf-8") as fh:
            fh.write(msg + "\n")
    except Exception as e:
        print("[ERROR]", repr(e), file=sys.stderr)
        with open(os.path.join(args.out, "download_result.txt"), "w", encoding="utf-8") as fh:
            fh.write("ERROR|" + repr(e) + "\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
