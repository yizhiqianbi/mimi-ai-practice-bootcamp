#!/usr/bin/env python3
"""口播成片：一份 口播.json → 配音、字幕、竖版成片、封面、剪映草稿素材。

用法：
    python talkvideo.py voice   口播.json     # 逐句配音（录音/ 里有同名文件就用录音）
    python talkvideo.py check   口播.json     # 自查：时长、五段、钩子、禁用词、出处、字幕长度、版面溢出
    python talkvideo.py preview 口播.json     # 每个镜头一张图 + 一张总览，先看版面
    python talkvideo.py render  口播.json     # 成片 mp4、封面、字幕、剪映草稿素材

需要：Python 3.9+、ffmpeg；pip install playwright edge-tts && python -m playwright install chromium
口播.json 里的文件路径都相对 口播.json 所在的文件夹。产出写到同一文件夹的 产出/。
"""
import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEGS = ["钩子", "冲突", "证据", "转折", "行动"]
BANNED = ["最", "第一", "100%", "全网", "顶级", "唯一", "国家级", "绝对", "首选", "极致"]
W, H, FPS = 1080, 1920, 30
SAFE_BOTTOM = 1360


def plain(s):
    return re.sub(r"[\[\]]", "", s)


def die(msg):
    print("✗ " + msg)
    sys.exit(1)


def need_ffmpeg():
    for exe in ("ffmpeg", "ffprobe"):
        if not shutil.which(exe):
            die(f"找不到 {exe}。Windows：winget install Gyan.FFmpeg；Mac：brew install ffmpeg")


def load(path):
    path = Path(path).resolve()
    spec = json.loads(path.read_text(encoding="utf-8"))
    spec["_base"] = path.parent
    spec["_out"] = path.parent / spec.get("out", "产出")
    spec.setdefault("name", path.stem)
    ids = [s["id"] for s in spec["sentences"]]
    if len(ids) != len(set(ids)):
        die("sentences 里有重复的 id")
    for s in spec["sentences"]:
        if s["seg"] not in SEGS:
            die(f"{s['id']} 的 seg 只能是 {'/'.join(SEGS)}")
        if s["scene"] not in spec["scenes"]:
            die(f"{s['id']} 用的镜头 {s['scene']} 不在 scenes 里")
    return spec


def files_in(spec):
    """所有镜头和品牌里引用的文件（相对路径）。"""
    out = []
    br = spec.get("brand", {})
    for k in ("logo", "font_file"):
        if br.get(k):
            out.append(br[k])
    for sc in spec["scenes"].values():
        for b in sc.get("blocks", []):
            for k in ("src", "image"):
                if b.get(k):
                    out.append(b[k])
            for s in b.get("srcs", []):
                out.append(s if isinstance(s, str) else s["src"])
            for it in b.get("items", []):
                if isinstance(it, dict) and it.get("src"):
                    out.append(it["src"])
    if spec.get("bgm", {}).get("src"):
        out.append(spec["bgm"]["src"])
    return out


def resolved(spec):
    """给浏览器用的副本：相对路径换成 file:// 地址。"""
    base = spec["_base"]
    url = lambda p: (base / p).resolve().as_uri()
    s = json.loads(json.dumps({k: v for k, v in spec.items() if not k.startswith("_")}))
    br = s.get("brand", {})
    for k in ("logo", "font_file"):
        if br.get(k):
            br[k] = url(br[k])
    for sc in s["scenes"].values():
        for b in sc.get("blocks", []):
            for k in ("src", "image"):
                if b.get(k):
                    b[k] = url(b[k])
            if "srcs" in b:
                b["srcs"] = [url(x) if isinstance(x, str) else {**x, "src": url(x["src"])} for x in b["srcs"]]
            for it in b.get("items", []):
                if isinstance(it, dict) and it.get("src"):
                    it["src"] = url(it["src"])
    return s


def probe(f):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "csv=p=0", str(f)]).strip())


def voice_file(spec, sid):
    for d in (spec["_base"] / "录音", spec["_out"] / "配音"):
        for ext in (".m4a", ".mp3", ".wav"):
            f = d / (sid + ext)
            if f.exists() and f.stat().st_size > 1000:
                return f
    return None


# ---------- voice ----------
def cmd_voice(spec):
    need_ffmpeg()
    v = spec.get("voice", {})
    name, rate = v.get("name", "zh-CN-YunyangNeural"), v.get("rate", "+8%")
    todo = [s for s in spec["sentences"] if not voice_file(spec, s["id"])]
    if todo:
        try:
            import edge_tts
        except ImportError:
            die("没装 edge-tts：pip install edge-tts。不想用合成配音，就把每句录成 录音/句子id.m4a")
        d = spec["_out"] / "配音"
        d.mkdir(parents=True, exist_ok=True)
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")

        async def run():
            for s in todo:
                text = s.get("say") or re.sub(r"[\[\]]", "", s["text"])
                await edge_tts.Communicate(text, name, rate=rate, proxy=proxy).save(str(d / (s["id"] + ".mp3")))
                print(f"  配音 {s['id']}：{text}")
        asyncio.run(run())
    tot = 0
    for s in spec["sentences"]:
        f = voice_file(spec, s["id"])
        d = probe(f)
        tot += d
        print(f"  {s['id']:>4} {s['seg']} {d:5.2f}s  {'录音' if f.parent.name == '录音' else '合成'}")
    print(f"✓ 配音齐了，纯人声 {tot:.1f} 秒")


# ---------- timeline ----------
def lat_w(p):
    core = re.sub(r"[\[\] ]", "", p)
    lat = re.findall(r"[A-Za-z0-9.\-]", core)
    return max(2, len(core) - len(lat) + 0.45 * len(lat))


def cjk_len(p):
    core = re.sub(r"[\[\] ]", "", p)
    return len(core) - len(re.findall(r"[A-Za-z0-9.\-]", core)) + len(re.findall(r"[A-Za-z0-9.\-]+", core))


def chunks(text):
    parts = [p for p in re.split(r"[，；：。！？,;:!?]", text) if p.strip()]
    parts = [q for p in parts for q in (re.split(r"、", p) if cjk_len(p) > 16 else [p]) if q.strip()]
    return [p.strip() for p in parts]


def timeline(spec):
    beats, t, prev = [], 0.25, None
    for s in spec["sentences"]:
        f = voice_file(spec, s["id"])
        if not f:
            die(f"{s['id']} 还没有配音，先跑 voice")
        if prev is not None:
            t += 0.45 if s["seg"] != prev else 0.28
        d = probe(f)
        parts = chunks(s["text"])
        w = [lat_w(p) for p in parts]
        c, ch = t, []
        for p, wi in zip(parts, w):
            dd = d * wi / sum(w)
            ch.append({"s": round(c, 3), "e": round(c + dd, 3), "txt": p})
            c += dd
        beats.append({"id": s["id"], "seg": s["seg"], "scene": s["scene"], "s": round(t, 3), "e": round(t + d, 3), "ch": ch})
        t += d
        prev = s["seg"]
    T = round(t + spec.get("end_hold", 2.6), 2)
    scenes = []
    for b in beats:
        if scenes and scenes[-1]["k"] == b["scene"]:
            continue
        if any(x["k"] == b["scene"] for x in scenes):
            die(f"镜头 {b['scene']} 被不相邻的句子重复使用；换一个镜头名")
        scenes.append({"k": b["scene"], "s": round(max(0, b["s"] - 0.18), 3) if scenes else 0})
    for i, s in enumerate(scenes):
        s["e"] = scenes[i + 1]["s"] if i + 1 < len(scenes) else T
    return {"T": T, "beats": beats, "scenes": scenes}


def srt(tl):
    def ts(x):
        ms = int(round(x * 1000))
        return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"
    out, n = [], 0
    for b in tl["beats"]:
        for c in b["ch"]:
            n += 1
            out.append(f"{n}\n{ts(c['s'])} --> {ts(c['e'])}\n{plain(c['txt'])}\n")
    return "\n".join(out), n


# ---------- browser ----------
def browser():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        die("没装 playwright：pip install playwright && python -m playwright install chromium")
    return sync_playwright()


def open_stage(p, spec, tl):
    br = p.chromium.launch()
    pg = br.new_page(viewport={"width": W, "height": H})
    pg.goto((HERE / "stage.html").as_uri())
    pg.evaluate("a=>setup(a[0],a[1])", [resolved(spec), tl])
    pg.evaluate("""async()=>{await document.fonts.ready;
      await Promise.all([...document.images].map(i=>i.complete?0:new Promise(r=>{i.onload=i.onerror=r})))}""")
    return br, pg


# ---------- check ----------
def cmd_check(spec, quiet=False):
    need_ffmpeg()
    errs, warns = [], []
    for f in files_in(spec):
        if not (spec["_base"] / f).exists():
            errs.append(f"找不到文件：{f}")
    if errs:
        for e in errs:
            print("✗ " + e)
        sys.exit(1)
    tl = timeline(spec)
    T = tl["T"]
    segs = [b["seg"] for b in tl["beats"]]
    order = [s for i, s in enumerate(segs) if i == 0 or segs[i - 1] != s]
    if order != SEGS:
        errs.append(f"五段顺序不对：{' → '.join(order)}（应为 {' → '.join(SEGS)}）")
    if not 55 <= T <= 65:
        errs.append(f"总长 {T:.1f} 秒，不在 55–65 秒（加减一句，或调 voice.rate）")
    hook = [b for b in tl["beats"] if b["seg"] == "钩子"]
    if hook and hook[-1]["e"] > 3.6:
        errs.append(f"钩子读完要 {hook[-1]['e']:.1f} 秒，超过 3 秒；砍短")
    act = [s for s in spec["sentences"] if s["seg"] == "行动"]
    if len(act) > 2:
        warns.append(f"行动段有 {len(act)} 句；结尾只给一个动作")
    for s in spec["sentences"]:
        txt = re.sub(r"[\[\]]", "", s["text"]) + (s.get("say") or "")
        for w in BANNED:
            if w in txt and w not in s.get("allow", []):
                (warns if s["seg"] == "冲突" else errs).append(
                    f"{s['id']} 有「{w}」（广告法）：{plain(s['text'])}" +
                    ("；说的是客户处境可以在 allow 里放行" if s["seg"] == "冲突" else ""))
        if s["seg"] in ("证据", "转折") and not s.get("src"):
            errs.append(f"{s['id']} 是{s['seg']}段，没写 src（出处）")
        if re.search(r"\d", s["text"]) and not s.get("say"):
            warns.append(f"{s['id']} 有数字但没写 say（读法），合成配音可能读错：{plain(s['text'])}")
    for b in tl["beats"]:
        for c in b["ch"]:
            core = re.sub(r"[\[\]]", "", c["txt"])
            if not re.fullmatch(r"[\x00-\x7F]+", core) and cjk_len(c["txt"]) > 16:
                errs.append(f"{b['id']} 的字幕「{core}」超过 16 字；在稿子里加逗号断开")
    with browser() as p:
        br, pg = open_stage(p, spec, tl)
        for o in pg.evaluate("overflow()"):
            if o["bottom"] > SAFE_BOTTOM:
                errs.append(f"镜头 {o['k']} 内容到了 y={o['bottom']}，会压住字幕（上限 {SAFE_BOTTOM}）；删版块或调小 size/h")
        br.close()
    spec["_out"].mkdir(parents=True, exist_ok=True)
    text, n = srt(tl)
    (spec["_out"] / f"{spec['name']}_字幕.srt").write_text(text, encoding="utf-8")
    if not quiet or errs or warns:
        print(f"总长 {T:.1f} 秒｜{len(spec['sentences'])} 句｜{len(tl['scenes'])} 个镜头｜{n} 条字幕")
        for b in SEGS:
            bs = [x for x in tl["beats"] if x["seg"] == b]
            if bs:
                print(f"  {b} {bs[0]['s']:5.1f}–{bs[-1]['e']:5.1f}s")
        for e in errs:
            print("✗ " + e)
        for w in warns:
            print("! " + w)
    if errs:
        sys.exit(1)
    print("✓ 自查通过" + (f"（{len(warns)} 条提醒）" if warns else ""))
    return tl


# ---------- preview ----------
def stills(spec, tl, d, sheet=True):
    d.mkdir(parents=True, exist_ok=True)
    for f in d.glob("*.png"):
        f.unlink()
    files = []
    with browser() as p:
        br, pg = open_stage(p, spec, tl)
        for i, s in enumerate(tl["scenes"]):
            te = s["e"] - 0.2 if i < len(tl["scenes"]) - 1 else tl["T"] - 0.1
            pg.evaluate(f"render({te},true)")
            seg = next(b["seg"] for b in tl["beats"] if b["scene"] == s["k"])
            f = d / f"{i + 1:02}_{seg}_{s['k']}.png"
            pg.screenshot(path=str(f))
            files.append((f, s))
        cv = spec.get("cover", "")
        m = re.match(r"(\w+)@([\d.]+)", cv)
        b = next((x for x in tl["beats"] if m and x["id"] == m.group(1)), tl["beats"][0])
        pg.evaluate(f"render({b['s'] + (b['e'] - b['s']) * (float(m.group(2)) if m else 0.5)},true)")
        pg.screenshot(path=str(spec["_out"] / f"{spec['name']}_封面.png"))
        br.close()
    if sheet:
        try:
            from PIL import Image
            cols, tw, th = 6, 270, 480
            rows = (len(files) + cols - 1) // cols
            im = Image.new("RGB", (cols * tw, rows * th), "white")
            for i, (f, _) in enumerate(files):
                im.paste(Image.open(f).convert("RGB").resize((tw, th)), ((i % cols) * tw, (i // cols) * th))
            im.save(spec["_out"] / f"{spec['name']}_镜头总览.jpg", quality=88)
        except ImportError:
            pass
    return files


def cmd_preview(spec):
    tl = cmd_check(spec, quiet=True)
    files = stills(spec, tl, spec["_out"] / f"{spec['name']}_剪映" / "剪辑画面")
    print(f"✓ {len(files)} 张镜头图：产出/{spec['name']}_剪映/剪辑画面/；总览：产出/{spec['name']}_镜头总览.jpg；封面：产出/{spec['name']}_封面.png")


# ---------- render ----------
def worker(spec_path, k, K, tlp, outp):
    spec = load(spec_path)
    tl = json.loads(Path(tlp).read_text(encoding="utf-8"))
    N = int(tl["T"] * FPS)
    a, b = N * k // K, N * (k + 1) // K
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(FPS), "-i", "-",
                           "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p", outp], stdin=subprocess.PIPE)
    with browser() as p:
        br, pg = open_stage(p, spec, tl)
        for f in range(a, b):
            pg.evaluate(f"render({f / FPS})")
            ff.stdin.write(pg.screenshot(type="jpeg", quality=93))
        br.close()
    ff.stdin.close()
    ff.wait()


def mix(spec, tl, tmp):
    T = tl["T"]
    ins, fl = [], []
    for i, b in enumerate(tl["beats"]):
        ins += ["-i", str(voice_file(spec, b["id"]))]
        ms = int(b["s"] * 1000)
        fl.append(f"[{i}:a]aresample=48000,adelay={ms}|{ms}[v{i}]")
    n = len(tl["beats"])
    vo = "".join(f"[v{i}]" for i in range(n)) + \
        f"amix=inputs={n}:normalize=0:duration=longest,apad=whole_dur={T},loudnorm=I=-16:TP=-2:LRA=9,aresample=48000"
    voice_out = tmp / "口播.m4a"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *ins, "-filter_complex", ";".join(fl + [vo + f",atrim=0:{T}[a]"]),
                    "-map", "[a]", "-c:a", "aac", "-b:a", "160k", "-ac", "2", str(voice_out)], check=True)
    bg = spec.get("bgm")
    if not bg:
        return voice_out, voice_out, None
    src = spec["_base"] / bg["src"]
    L = probe(src)
    r = L / T
    bgm = tmp / "bgm.wav"
    if bg.get("fit", "stretch") == "stretch" and 0.7 <= r <= 1.35:
        af = f"atempo={r:.5f}"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vn", "-af", af, "-ar", "48000", "-ac", "2",
                        "-c:a", "pcm_s16le", str(bgm)], check=True)
    else:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "-1", "-i", str(src), "-vn", "-t", str(T + 1),
                        "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(bgm)], check=True)
    lufs = bg.get("lufs", -29)
    final = tmp / "mix.m4a"
    fl2 = fl + [vo + "[voice]",
                f"[{n}:a]apad=whole_dur={T},atrim=0:{T},loudnorm=I={lufs}:TP=-9,aresample=48000,afade=t=out:st={T - 1.2}:d=1.2[bgm]",
                f"[voice][bgm]amix=inputs=2:normalize=0:duration=longest,alimiter=limit=0.89,apad=whole_dur={T},atrim=0:{T}[a]"]
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *ins, "-i", str(bgm), "-filter_complex", ";".join(fl2),
                    "-map", "[a]", "-c:a", "aac", "-b:a", "192k", "-ac", "2", str(final)], check=True)
    bgm_m4a = tmp / "bgm.m4a"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(bgm), "-af", "loudnorm=I=-16:TP=-2", "-c:a", "aac",
                    "-b:a", "160k", str(bgm_m4a)], check=True)
    return final, voice_out, (bgm_m4a, lufs + 16)


def cmd_render(spec, spec_path, workers):
    tl = cmd_check(spec, quiet=True)
    out = spec["_out"]
    tmp = out / f".{spec['name']}_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    tlp = tmp / "tl.json"
    tlp.write_text(json.dumps(tl, ensure_ascii=False), encoding="utf-8")
    K = max(1, min(workers, os.cpu_count() or 4))
    print(f"渲染 {tl['T']:.1f} 秒 × {FPS}fps，{K} 个进程……")
    ps = [subprocess.Popen([sys.executable, __file__, "_worker", str(spec_path), str(k), str(K), str(tlp), str(tmp / f"p{k:02}.mp4")])
          for k in range(K)]
    if any(p.wait() for p in ps):
        die("有渲染进程失败，看上面的报错")
    (tmp / "parts.txt").write_text("".join(f"file 'p{k:02}.mp4'\n" for k in range(K)), encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(tmp / "parts.txt"),
                    "-c", "copy", str(tmp / "v.mp4")], check=True)
    final, voice_out, bgm = mix(spec, tl, tmp)
    mp4 = out / f"{spec['name']}.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(tmp / "v.mp4"), "-i", str(final), "-map", "0:v", "-map", "1:a",
                    "-c", "copy", "-movflags", "+faststart", str(mp4)], check=True)
    # 剪映草稿素材：同一份时间线，每个镜头一张图
    jd = out / f"{spec['name']}_剪映"
    files = stills(spec, tl, jd / "剪辑画面", sheet=True)
    text, n = srt(tl)
    (jd / "字幕.srt").write_text(text, encoding="utf-8")
    shutil.copy(voice_out, jd / "口播.m4a")
    plan = {"name": spec["name"], "canvas": [W, H], "fps": FPS,
            "shots": [{"image": f"剪辑画面/{f.name}", "start": s["s"], "end": s["e"], "zoom": [1.0, 1.04]} for f, s in files],
            "srt": "字幕.srt", "subtitle_style": {"size": 9, "color": [0.07, 0.07, 0.08], "y": -0.5},
            "voice": "口播.m4a", "voice_db": 0}
    if bgm:
        shutil.copy(bgm[0], jd / "bgm.m4a")
        plan["bgm"] = {"path": "bgm.m4a", "db": round(bgm[1])}
    (jd / "剪辑表.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    shutil.rmtree(tmp, ignore_errors=True)
    mb = mp4.stat().st_size / 1e6
    print(f"✓ 成片：产出/{mp4.name}（{tl['T']:.1f} 秒，{mb:.1f} MB）")
    print(f"✓ 封面：产出/{spec['name']}_封面.png；字幕：产出/{spec['name']}_字幕.srt")
    print(f"✓ 剪映草稿素材：产出/{jd.name}/（{len(files)} 个镜头、{n} 条字幕）→ 用 jianying-draft 的 make_draft.py 生成草稿")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "_worker":
        worker(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5], sys.argv[6])
        return
    ap = argparse.ArgumentParser(description="口播成片")
    ap.add_argument("cmd", choices=["voice", "check", "preview", "render"])
    ap.add_argument("spec", help="口播.json")
    ap.add_argument("--workers", type=int, default=8, help="渲染进程数（默认 8）")
    a = ap.parse_args()
    spec = load(a.spec)
    {"voice": lambda: cmd_voice(spec), "check": lambda: cmd_check(spec), "preview": lambda: cmd_preview(spec),
     "render": lambda: cmd_render(spec, Path(a.spec).resolve(), a.workers)}[a.cmd]()


if __name__ == "__main__":
    main()
