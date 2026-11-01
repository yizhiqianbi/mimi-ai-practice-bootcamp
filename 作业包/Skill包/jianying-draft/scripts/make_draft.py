#!/usr/bin/env python3
"""按剪辑表生成一个剪映专业版草稿（基于 pyJianYingDraft）。

用法：
    pip install pyJianYingDraft
    python make_draft.py 产出/日期_剪辑表_v1.json            # 写进本机剪映草稿目录
    python make_draft.py 产出/日期_剪辑表_v1.json --check    # 只检查剪辑表，不生成
    python make_draft.py 剪辑表.json --drafts <剪映草稿目录>   # 草稿目录自动找不到时手动指定

剪辑表里的文件路径都相对剪辑表所在的文件夹。生成前先完全退出剪映。
镜头可以是图片或视频（字段 image 或 media）；视频镜头用 source_start 指定从原视频第几秒开始截。
"""
import argparse
import json
import os
import platform
import shutil
import sys
from pathlib import Path


def default_drafts_dir():
    home = Path.home()
    if platform.system() == "Windows":
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        candidates = [local / "JianyingPro" / "User Data" / "Projects" / "com.lveditor.draft"]
    elif platform.system() == "Darwin":
        candidates = [home / "Movies" / "JianyingPro" / "User Data" / "Projects" / "com.lveditor.draft"]
    else:
        candidates = []
    for p in candidates:
        if p.is_dir():
            return p
    return None


def load_plan(path):
    plan = json.loads(path.read_text(encoding="utf-8"))
    base = path.parent
    problems = []

    def need(rel, what):
        p = (base / rel).resolve()
        if not p.exists():
            problems.append(f"{what}找不到：{rel}")
        return p

    shots = plan.get("shots", [])
    if not shots:
        problems.append("shots 为空")
    t = 0.0
    for i, s in enumerate(shots, 1):
        s["_path"] = need(s.get("media") or s["image"], f"第 {i} 个镜头的画面")
        if abs(s["start"] - t) > 1e-6:
            problems.append(f"第 {i} 个镜头从 {s['start']} 秒开始，上一个镜头到 {t} 秒结束，中间有空档或重叠")
        if s["end"] <= s["start"]:
            problems.append(f"第 {i} 个镜头的结束时间不晚于开始时间")
        t = s["end"]
    plan["_total"] = t
    for key, what in (("srt", "字幕"), ("voice", "口播录音")):
        if plan.get(key):
            plan["_" + key] = need(plan[key], what)
    if plan.get("bgm"):
        plan["bgm"]["_path"] = need(plan["bgm"]["path"], "BGM")
    return plan, problems


def build(plan, drafts_dir):
    import pyJianYingDraft as jy
    from pyJianYingDraft import (ClipSettings, KeyframeProperty, TextStyle, TrackType,
                                 TransitionType, trange_seconds)

    w, h = plan.get("canvas", [1080, 1920])
    folder = jy.DraftFolder(str(drafts_dir))
    script = folder.create_draft(plan["name"], w, h, plan.get("fps", 30))
    draft_dir = Path(drafts_dir) / plan["name"]

    mat_dir = draft_dir / "materials"
    mat_dir.mkdir()

    def stage(src):
        dst = mat_dir / src.name
        if not dst.exists():
            shutil.copy2(src, dst)
        return str(dst)

    script.append_track(jy.TrackSpec(TrackType.video, "画面"))
    trans = plan.get("transition")
    shots = plan["shots"]
    for i, s in enumerate(shots):
        src = None
        if "source_start" in s:
            src = trange_seconds(s["source_start"], duration=s["end"] - s["start"])
        seg = jy.VideoSegment(stage(s["_path"]), trange_seconds(s["start"], end=s["end"]), source_timerange=src)
        z0, z1 = s.get("zoom", [1.0, 1.0])
        if z0 != 1.0 or z1 != 1.0:
            seg.add_keyframe(KeyframeProperty.uniform_scale, 0, z0)
            seg.add_keyframe(KeyframeProperty.uniform_scale, seg.duration, z1)
        if trans and i < len(shots) - 1:
            seg.add_transition(TransitionType.from_name(trans))
        script.add_segment(seg, "画面")

    if plan.get("titles"):
        script.append_track(jy.TrackSpec(TrackType.text, "标题"))
        for t in plan["titles"]:
            seg = jy.TextSegment(t["text"], trange_seconds(t["start"], end=t["end"]),
                                 style=TextStyle(size=t.get("size", 12), bold=True, align=1,
                                                 color=tuple(t.get("color", [1, 1, 1]))),
                                 clip_settings=ClipSettings(transform_y=t.get("y", 0.6)))
            script.add_segment(seg, "标题")

    if plan.get("_srt"):
        st = plan.get("subtitle_style", {})
        script.import_srt(stage(plan["_srt"]), "字幕",
                          text_style=TextStyle(size=st.get("size", 7), bold=True, align=1, auto_wrapping=True,
                                               color=tuple(st.get("color", [1, 1, 1]))),
                          clip_settings=ClipSettings(transform_y=st.get("y", -0.6)))

    total = plan["_total"]
    if plan.get("_voice"):
        script.append_track(jy.TrackSpec(TrackType.audio, "口播"))
        mat = jy.AudioMaterial(stage(plan["_voice"]))
        dur = min(mat.duration / 1e6, total)
        script.add_segment(jy.AudioSegment(mat, trange_seconds(0, duration=dur),
                                           volume=10 ** (plan.get("voice_db", 0) / 20)), "口播")

    if plan.get("bgm"):
        b = plan["bgm"]
        script.append_track(jy.TrackSpec(TrackType.audio, "BGM"))
        mat = jy.AudioMaterial(stage(b["_path"]))
        length = mat.duration / 1e6
        vol = 10 ** (b.get("db", -20) / 20)
        t = 0.0
        last = None
        while t < total - 1e-3:
            d = min(length, total - t)
            last = jy.AudioSegment(mat, trange_seconds(t, duration=d),
                                   source_timerange=trange_seconds(0, duration=d), volume=vol)
            script.add_segment(last, "BGM")
            t += d
        if last is not None:
            last.add_fade("0s", "2s")

    script.save()
    return draft_dir


def main():
    ap = argparse.ArgumentParser(description="按剪辑表生成剪映专业版草稿")
    ap.add_argument("plan", help="剪辑表 JSON")
    ap.add_argument("--drafts", help="剪映草稿目录（剪映 → 全局设置 → 草稿位置）")
    ap.add_argument("--check", action="store_true", help="只检查剪辑表，不生成草稿")
    a = ap.parse_args()

    plan_path = Path(a.plan).resolve()
    plan, problems = load_plan(plan_path)
    print(f"剪辑表：{plan_path.name}｜{len(plan['shots'])} 个镜头｜总长 {plan['_total']:.1f} 秒")
    print(f"字幕：{'有' if plan.get('_srt') else '无'}｜口播：{'有' if plan.get('_voice') else '无（只有画面和字幕）'}｜BGM：{'有' if plan.get('bgm') else '无'}")
    if problems:
        print("剪辑表有问题，先改好再生成：")
        for p in problems:
            print("  - " + p)
        sys.exit(1)
    if a.check:
        print("检查通过")
        return

    drafts = Path(a.drafts) if a.drafts else default_drafts_dir()
    if not drafts or not drafts.is_dir():
        print("找不到剪映草稿目录，用 --drafts 指定（剪映 → 全局设置 → 草稿位置）")
        sys.exit(1)
    if (drafts / plan["name"]).exists():
        print(f"草稿「{plan['name']}」已存在，不覆盖。把剪辑表里的 name 改成新版本号再跑")
        sys.exit(1)

    draft_dir = build(plan, drafts)
    print(f"已生成草稿：{draft_dir}")
    print("打开剪映，在草稿列表里找到它（看不到就重启剪映）。检查一遍后点「导出」")


if __name__ == "__main__":
    main()
