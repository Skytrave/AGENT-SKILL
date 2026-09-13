---
name: B站视频下载
description: 下载 B 站（bilibili.com）视频为本地 mp4，并统一转码为 H.264 + AAC 手机通用格式。当用户说"下载B站视频""下B站""存这个BV""bilibili下载""把视频下下来"或给出 bilibili.com/video/BV 链接并要求下载时使用。支持单集与清晰度选择，自动合并音视频，自动兼容手机播放。
---

# B 站视频下载

## 适用场景
用户提供 B 站视频链接（含 `https://www.bilibili.com/video/BVxxxx` 或短链），要求下载为本地 mp4 文件。

## 关键前置（必读）
- **运行环境**：用隔离的 Python venv 执行脚本，不要污染系统环境。
  - 解释器：`C:\Users\sky\.workbuddy\binaries\python\envs\default\Scripts\python.exe`
  - 若该 venv 不存在，先创建：`C:\Users\sky\.workbuddy\binaries\python\versions\3.13.12\python.exe -m venv C:\Users\sky\.workbuddy\binaries\python\envs\default`
- **依赖自包含**：脚本会自动 `pip install yt-dlp` 与 `imageio-ffmpeg`，并把 ffmpeg 二进制缓存为 `ffmpeg.exe`，无需手动装 ffmpeg。
- **B 站是 DASH 分离流**：视频、音频是分开的，必须用 ffmpeg 合并。脚本已处理（yt-dlp 合并 + 分离分片兜底合并）。
- **stdout 可能不回显**：本环境 Bash 的 `rm`/`tail`/`cat`/`grep` 常缺失。脚本会把结果同时写入输出目录的 `download_result.txt`，用 Read 工具确认结果，不要依赖终端回显。
- **删除文件**用 Python（`os.remove`）或 PowerShell（`Remove-Item`），别用 Bash 的 `rm`。

## 步骤
### 1. 取出下载链接
从用户消息中提取完整 B 站 URL（保留 `?vd_source=` 等参数无妨，也可删掉）。

### 2. 运行下载脚本
在 Agent 工具里执行（用隔离 venv 的 python，**不要**在 Bash 里裸跑 `python`）：

```
<venv_python> <skill_dir>/download_bilibili.py "<B站URL>" --out <输出目录>
```

参数：
- `url`（必填）：视频链接
- `--out`：输出目录，默认 `./bilibili_downloads`
- `--quality`：清晰度，默认 `bv*+ba/b`（最佳视频+最佳音频）。需要限速/降清晰度可改 `bv[height<=720]+ba/b`
- `--cookies`：cookie 文件路径，仅当视频提示"需登录/版权限制"时才需要

### 3. 确认结果
读取 `<输出目录>/download_result.txt`：
- `OK|<完整路径>|<大小>MB` → 成功，用 present_files 展示该 mp4
- `ERROR|...` → 失败，按提示排查（多为网络/需要 cookies/链接失效）

### 4. 清理（可选）
成功后可删除 `download_result.txt` 及任何残留的 `*.f3*.mp4`/`*.f3*.m4a` 分片（正常情况下脚本已自动清理）。

## 格式统一（重要）
脚本在合并后会**自动把成品统一转码/封装为 H.264 + AAC 的 mp4**：
- 若 B 站源已是 H.264 + AAC（最常见），直接保留，不做重编码。
- 若源是 H.265/HEVC、AV1 等手机兼容性差的编码，**自动重编码为 H.264 + AAC**（文件体积可能变大，属正常）。
- 目的：保证下载到手机后任意播放器都能直接打开，避免"无法解析"。
- 无需在下载时额外操作，这是默认行为。

## 常见问题
- **只下到无声/无画面的分片**：说明 ffmpeg 未被 yt-dlp 识别，脚本的兜底合并会补上；若仍有问题检查 `~/.workbuddy/binaries/ffmpeg/ffmpeg.exe` 是否存在。
- **提示"会员/版权/地区限制"**：该视频需要登录态，让用户提供 cookies.txt（`--cookies` 传入）。
- **下载整个合集/ playlist**：默认已加 `--no-playlist` 只下当前单集；如要下整集去掉该参数并在 URL 用合集页。
- **手机打不开 / 无法解析**：旧版本可能下载到 HEVC/AV1 编码；升级后的 skill 已默认转 H.264+AAC，重新下载即可。若仍异常，检查文件是否完整。

## 产出
- 输出目录下的 `<视频标题>.mp4`（完整音视频，**已统一为 H.264+AAC 手机通用格式**）
- 用 present_files 把 mp4 展示给用户
