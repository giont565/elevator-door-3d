"""三菱電梯門機構 — 教育訓練影片自動錄製（解說描邊版）
每支：標題卡 → 解說模式 3D 動畫（發光描邊 + 底部字幕條 + 指標籤）
用法：
  python record_training.py --preview   # 每支抓 3 幀調鏡頭
  python record_training.py             # 全量錄製 + ffmpeg 合成
"""
import sys, shutil, subprocess, math
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent
HTML = ROOT / "mitsubishi.html"
OUT_DIR = Path.home() / "Desktop" / "電梯門機教學影片_v3"
OUT_DIR.mkdir(parents=True, exist_ok=True)
WORK = ROOT / "_rec"; WORK.mkdir(exist_ok=True)

W, H, FPS = 1280, 720, 24
TITLE_SEC = 2.6
FOOTER = "三菱電梯 門機構原理教學 — 廠務工程訓練用"
CREDIT = "TSMC PUSD 製作"

# 每支影片設定
SHOTS = [
  dict(file="1_乘場門開關門", title="乘場門（廳門）開關門",
       sub="乾淨開關門一輪：關 → 開 → 等 → 關 → 鎖",
       mode="cycle", iso="land", cam=[0.42,1.9,3.4], tgt=[0,1.55,0.0],
       t0=0.0, t1=16.5, anim=13.0),
  dict(file="2_車廂門開關門", title="車廂門（轎門）開關門",
       sub="門機馬達直驅連動皮帶，上下股各帶一扇轎門等速對開",
       mode="cycle", iso="car", cam=[0.42,1.95,3.45], tgt=[0,1.6,0.0],
       t0=0.0, t1=16.5, anim=13.0),
  dict(file="3_羽瓣連動特寫", title="活動羽瓣 × 門閉鎖器 連動特寫",
       sub="羽瓣夾住雙滾輪帶乘場門開關，到位後收回脫鉤上鎖",
       mode="cycle", iso="all", cam=[-1.1,2.55,1.05], tgt=[-0.18,2.26,-0.22],
       t0=0.0, t1=16.5, anim=14.0),
  dict(file="4_防夾安全示範", title="MBS 光幕 防夾安全示範",
       sub="關門中光束被遮斷 → 皮帶煞停反轉 → 重新開門",
       mode="curtain", iso="all", cam=[0.46,1.9,3.7], tgt=[0,1.5,0.0],
       t0=0.0, t1=16.5, anim=13.0),
  dict(file="5_鑰匙緊急開鎖", title="鑰匙緊急開鎖",
       sub="外門開關鑰匙 → 頂起引上棒 → 閉鎖器解鎖 → 手扒開外門",
       mode="key", iso="all", cam=[-0.9,2.15,0.95], tgt=[-0.12,2.05,-0.22],
       t0=0.0, t1=1.0, anim=11.0),
]

TITLE_HTML = """<!doctype html><html><head><meta charset=utf-8><style>
*{{margin:0;box-sizing:border-box}}
html,body{{width:{W}px;height:{H}px;background:#0a0807;overflow:hidden;
 font-family:'PingFang TC','Noto Sans TC',sans-serif}}
.wrap{{width:100%;height:100%;display:flex;flex-direction:column;justify-content:center;
 align-items:center;position:relative}}
.band{{width:100%;padding:60px 40px;background:#000;text-align:center}}
h1{{color:#fff;font-size:60px;font-weight:800;letter-spacing:2px;margin-bottom:22px}}
.sub{{color:#ffb02e;font-size:30px;font-weight:600;line-height:1.5}}
.foot{{position:absolute;bottom:46px;width:100%;text-align:center;color:#8b7d77;font-size:20px}}
.credit{{position:absolute;bottom:18px;width:100%;text-align:center;color:#5e544f;font-size:16px;letter-spacing:1px}}
</style></head><body><div class=wrap>
<div class=band><h1>{title}</h1><div class=sub>{sub}</div></div>
<div class=foot>{foot}</div><div class=credit>{credit}</div>
</div></body></html>"""


def render_titlecard(page, shot, path):
    html = TITLE_HTML.format(W=W, H=H, title=shot["title"], sub=shot["sub"],
                             foot=FOOTER, credit=CREDIT)
    f = WORK / "title.html"; f.write_text(html, encoding="utf-8")
    page.goto(f"file://{f.resolve()}")
    page.wait_for_timeout(300)
    page.screenshot(path=str(path))


def setup_shot(page, shot):
    page.goto(f"file://{HTML.resolve()}")
    page.wait_for_timeout(4500)
    page.evaluate("window.__pause()")
    if shot["mode"] == "curtain":
        page.evaluate("document.getElementById('btnSafety').click()")
        page.wait_for_timeout(400)
    elif shot["mode"] == "key":
        page.evaluate("document.getElementById('btnKey').click()")
        page.wait_for_timeout(400)
    page.evaluate(f"window.__setISO('{shot['iso']}')")
    page.evaluate("window.__narrate(true)")
    page.evaluate(f"window.__setCam({shot['cam']},{shot['tgt']})")
    page.wait_for_timeout(500)


def scrub(page, shot, i, n):
    frac = i / max(1, n - 1)
    if shot["mode"] == "key":
        page.evaluate(f"window.__setKeyDemo({frac})")
    else:
        t = shot["t0"] + (shot["t1"] - shot["t0"]) * frac
        page.evaluate(f"window.__setT({t})")
    # 固定鏡頭，避免位移；只重設一次即可，但保險每幀重貼
    page.evaluate(f"window.__setCam({shot['cam']},{shot['tgt']})")


def record_shot(page, shot, preview=False):
    fdir = WORK / shot["file"]
    if fdir.exists():
        shutil.rmtree(fdir)
    fdir.mkdir()
    setup_shot(page, shot)
    if preview:
        for i, frac in enumerate([0.05, 0.5, 0.95]):
            scrub(page, shot, int(frac * 100), 101)
            page.wait_for_timeout(350)
            page.screenshot(path=str(fdir / f"prev_{i}.png"))
        print(f"  preview frames → {fdir}")
        return None
    # 標題卡
    title_png = fdir / "title.png"
    render_titlecard(page, shot, title_png)
    # 重新載入場景（render_titlecard 換了頁面）
    setup_shot(page, shot)
    n_anim = int(shot["anim"] * FPS)
    n_title = int(TITLE_SEC * FPS)
    idx = 0
    for _ in range(n_title):
        shutil.copy(title_png, fdir / f"f{idx:04d}.png"); idx += 1
    for i in range(n_anim):
        scrub(page, shot, i, n_anim)
        page.wait_for_timeout(60)
        page.screenshot(path=str(fdir / f"f{idx:04d}.png")); idx += 1
    # ffmpeg 合成
    out = OUT_DIR / f"{shot['file']}.mp4"
    cmd = ["ffmpeg", "-y", "-framerate", str(FPS), "-i", str(fdir / "f%04d.png"),
           "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "20",
           "-preset", "medium", "-movflags", "+faststart", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not out.exists() or out.stat().st_size < 50_000:
        print(f"  ❌ ffmpeg 失敗 {shot['file']}\n{r.stderr[-1500:]}")
        return None
    print(f"  ✓ {out.name}  {out.stat().st_size/1024/1024:.1f} MB  ({idx} frames)")
    return out


def main():
    preview = "--preview" in sys.argv
    only = [a for a in sys.argv[1:] if not a.startswith("--")]
    shots = [s for s in SHOTS if (not only or s["file"] in only or s["file"][0] in only)]
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--allow-file-access-from-files"])
        pg = b.new_page(viewport={"width": W, "height": H})
        pg.on("pageerror", lambda e: print("  [pageerror]", e))
        for s in shots:
            print(f"▶ {s['file']} ({'preview' if preview else 'full'})")
            record_shot(pg, s, preview)
        b.close()
    print("完成。輸出：", OUT_DIR)


if __name__ == "__main__":
    main()
