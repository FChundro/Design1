import subprocess, pathlib, html
ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
JOBS = []
CROWN = '''<svg viewBox="0 0 120 90" xmlns="http://www.w3.org/2000/svg"><path d="M8 78 L14 24 L40 50 L60 10 L80 50 L106 24 L112 78 Z" fill="#E8B730"/><rect x="8" y="80" width="104" height="9" rx="3" fill="#E8B730"/><circle cx="14" cy="22" r="7" fill="#E8B730"/><circle cx="60" cy="9" r="7" fill="#E8B730"/><circle cx="106" cy="22" r="7" fill="#E8B730"/></svg>'''
BASE = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
*{box-sizing:border-box;margin:0}
body{width:%(w)dpx;height:%(h)dpx;background:#0f1014;color:#fff;font-family:"DejaVu Sans","Liberation Sans",sans-serif;overflow:hidden;position:relative}
.gold{color:#E8B730}
</style></head><body>%(body)s</body></html>"""

def render(name, body, w=1080, h=1350):
    f = SRC / f"{name}.html"
    f.write_text(BASE % dict(w=w, h=h, body=body))
    JOBS.append((f.as_uri(), str(ROOT / (name + ".png")), w, h))

# Profile picture (1080x1080, safe inside a circle)
render("profile-picture", f"""
<div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;
 background:radial-gradient(circle at 50% 45%,#23242b 0%,#0f1014 70%)">
 <div style="width:430px">{CROWN}</div>
 <div style="margin-top:40px;font-size:118px;font-weight:bold;letter-spacing:14px" class="gold">DK</div>
</div>""", 1080, 1080)

footer = '<div style="position:absolute;bottom:56px;left:90px;right:90px;display:flex;justify-content:space-between;font-size:30px;color:#8a8d98"><span>@digitalking.io</span><span>%s</span></div>'
def slide(n, inner):
    return f'<div style="position:absolute;inset:90px 90px 150px">{inner}</div>' + footer % (f"{n}/8")

items = [
 ("Prompt pack", "Sell AI prompts for a niche you know.", "$9 – $29"),
 ("Checklist / cheat sheet", "One page that solves one problem.", "$5 – $9"),
 ("Template pack", "Captions, budgets, client emails.", "$9 – $29"),
 ("Mini ebook", "A 15-page how-to guide.", "$19 – $39"),
 ("Notion or Canva templates", "Planners, trackers, social posts.", "$9 – $49"),
]

render("carousel-01", slide(1, f"""
<div style="width:150px">{CROWN}</div>
<div style="margin-top:70px;font-size:104px;font-weight:bold;line-height:1.05">5 digital products you can make <span class="gold">this weekend</span></div>
<div style="margin-top:60px;font-size:46px;color:#c9ccd6">…with AI doing most of the work.</div>
<div style="position:absolute;bottom:0;font-size:38px" class="gold">Swipe &rarr;</div>"""))

for i, (t, d, p) in enumerate(items, start=2):
    render(f"carousel-{i:02d}", slide(i, f"""
<div style="font-size:250px;font-weight:bold;line-height:1" class="gold">{i-1}</div>
<div style="margin-top:50px;font-size:92px;font-weight:bold;line-height:1.08">{html.escape(t)}</div>
<div style="margin-top:44px;font-size:52px;color:#c9ccd6;line-height:1.3">{html.escape(d)}</div>
<div style="position:absolute;bottom:0;display:inline-block;border:4px solid #E8B730;border-radius:60px;padding:22px 48px;font-size:54px;font-weight:bold" class="gold">{p}</div>"""))

render("carousel-07", slide(7, """
<div style="font-size:88px;font-weight:bold;line-height:1.1">The secret?</div>
<div style="margin-top:60px;font-size:60px;line-height:1.35;color:#c9ccd6">AI writes the first draft.<br>You add your experience.</div>
<div style="margin-top:80px;font-size:84px;font-weight:bold;line-height:1.1" class="gold">Done in 48 hours.</div>"""))

render("carousel-08", slide(8, f"""
<div style="width:170px">{CROWN}</div>
<div style="margin-top:60px;font-size:84px;font-weight:bold;line-height:1.12">Want my <span class="gold">75 AI prompts</span> to build yours?</div>
<div style="margin-top:70px;font-size:58px;line-height:1.4">Comment <span class="gold" style="font-weight:bold">KING</span><br>and I'll send them to you.</div>
<div style="position:absolute;bottom:0;font-size:42px;color:#c9ccd6">Save this for later &darr;</div>"""))
import json
(SRC / "jobs.json").write_text(json.dumps(JOBS))
subprocess.run(["node", str(SRC / "shoot.js")], check=True)
print("ok")
