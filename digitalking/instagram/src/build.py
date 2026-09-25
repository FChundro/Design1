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

# ---------- Post 2: 3 free AI prompts ----------
def s2(n, total, inner):
    return f'<div style="position:absolute;inset:90px 90px 150px">{inner}</div>' + footer % f"{n}/{total}"

def prompt_slide(n, total, num, title, text):
    return s2(n, total, f"""
<div style="font-size:44px;font-weight:bold" class="gold">PROMPT {num}</div>
<div style="margin-top:24px;font-size:76px;font-weight:bold;line-height:1.1">{title}</div>
<div style="margin-top:50px;border-left:8px solid #E8B730;background:#1b1c22;border-radius:12px;padding:40px 44px;
 font-family:'DejaVu Sans Mono',monospace;font-size:38px;line-height:1.45;color:#e6e7ec">{text}</div>""")

render("prompts-01", s2(1, 6, f"""
<div style="width:150px">{CROWN}</div>
<div style="margin-top:70px;font-size:100px;font-weight:bold;line-height:1.05">3 AI prompts to find your <span class="gold">side hustle</span></div>
<div style="margin-top:60px;font-size:46px;color:#c9ccd6">Copy. Paste. Get paid ideas.</div>
<div style="position:absolute;bottom:0;font-size:38px" class="gold">Swipe &rarr;</div>"""))
render("prompts-02", prompt_slide(2, 6, 1, "Find the idea",
 "Give me 20 digital product ideas for [AUDIENCE] interested in [NICHE]. For each: the problem it solves, a price, and how hard it is to make (1-5)."))
render("prompts-03", prompt_slide(3, 6, 2, "Find the pain",
 "List the 25 biggest frustrations [AUDIENCE] have about [TOPIC], written in the exact words they would type in a comment."))
render("prompts-04", prompt_slide(4, 6, 3, "Write the promise",
 "Turn this idea into one sentence: Get [RESULT] in [TIME] without [PAIN]. Idea: [IDEA]. Give me 10 versions."))
render("prompts-05", s2(5, 6, """
<div style="font-size:84px;font-weight:bold;line-height:1.1">How to use them</div>
<div style="margin-top:60px;font-size:54px;line-height:1.55;color:#c9ccd6">
<span class="gold">1.</span> Replace the [BRACKETS]<br>
<span class="gold">2.</span> Run them in order<br>
<span class="gold">3.</span> Pick the idea that repeats<br>
<span class="gold">4.</span> Build it this weekend</div>"""))
render("prompts-06", s2(6, 6, f"""
<div style="width:170px">{CROWN}</div>
<div style="margin-top:60px;font-size:84px;font-weight:bold;line-height:1.12">These are 3 of my <span class="gold">75 prompts</span>.</div>
<div style="margin-top:70px;font-size:58px;line-height:1.4">Comment <span class="gold" style="font-weight:bold">KING</span><br>for the other 72.</div>
<div style="position:absolute;bottom:0;font-size:42px;color:#c9ccd6">Save this before you forget &darr;</div>"""))

# ---------- Post 3: Google reviews side hustle ----------
steps = [
 ("Pick 20 local businesses", "Restaurants, salons, garages with fewer than 50 Google reviews."),
 ("Offer a review system", "A QR code at the counter + a friendly message asking happy customers for a review."),
 ("Let AI write the messages", "WhatsApp, SMS and email templates in minutes."),
 ("Charge monthly", "$100 – $300 per business per month to run it."),
 ("Show the results", "More reviews means more customers. Screenshot the growth and get referrals."),
]
render("reviews-01", s2(1, 7, f"""
<div style="width:150px">{CROWN}</div>
<div style="margin-top:70px;font-size:96px;font-weight:bold;line-height:1.06">The <span class="gold">Google reviews</span> side hustle</div>
<div style="margin-top:60px;font-size:48px;color:#c9ccd6">5 steps. No experience needed.</div>
<div style="position:absolute;bottom:0;font-size:38px" class="gold">Swipe &rarr;</div>"""))
for i,(t,d) in enumerate(steps, start=2):
    render(f"reviews-{i:02d}", s2(i, 7, f"""
<div style="font-size:44px;font-weight:bold" class="gold">STEP {i-1}</div>
<div style="margin-top:30px;font-size:90px;font-weight:bold;line-height:1.08">{html.escape(t)}</div>
<div style="margin-top:50px;font-size:54px;color:#c9ccd6;line-height:1.35">{html.escape(d)}</div>"""))
render("reviews-07", s2(7, 7, f"""
<div style="font-size:60px;font-weight:bold;line-height:1.2">Rule #1: <span class="gold">only real customers.</span></div>
<div style="margin-top:30px;font-size:46px;color:#c9ccd6;line-height:1.35">Never fake or paid reviews. It breaks Google's rules.</div>
<div style="margin-top:90px;width:140px">{CROWN}</div>
<div style="margin-top:40px;font-size:62px;line-height:1.35">Want the AI message templates?<br>Comment <span class="gold" style="font-weight:bold">KING</span></div>"""))

# ---------- Post 4: 10 Reel hooks ----------
hooks = ["Stop scrolling if you want to [RESULT].", "Nobody is talking about this [TOOL].",
 "The lazy way to [RESULT].", "Do this before you [COMMON ACTION].", "I tested [X] for 30 days.",
 "This one prompt replaced my [TOOL].", "If I had to start from zero today…", "You're doing [TASK] wrong.",
 "Steal my exact [TEMPLATE].", "Save this before it's gone."]
render("hooks-01", s2(1, 5, f"""
<div style="width:150px">{CROWN}</div>
<div style="margin-top:70px;font-size:104px;font-weight:bold;line-height:1.05"><span class="gold">10 hooks</span> that stop the scroll</div>
<div style="margin-top:60px;font-size:46px;color:#c9ccd6">Fill in the blanks. Use them today.</div>
<div style="position:absolute;bottom:0;font-size:38px" class="gold">Swipe &rarr;</div>"""))
for page,(a,b) in enumerate([(0,4),(4,7),(7,10)], start=2):
    rows="".join(f'<div style="margin-bottom:46px;font-size:54px;line-height:1.3"><span class="gold" style="font-weight:bold">{k+1}.</span> {html.escape(hooks[k])}</div>' for k in range(a,b))
    render(f"hooks-{page:02d}", s2(page, 5, rows))
render("hooks-05", s2(5, 5, f"""
<div style="width:170px">{CROWN}</div>
<div style="margin-top:60px;font-size:84px;font-weight:bold;line-height:1.12">Want all <span class="gold">30 hooks</span> + 75 AI prompts?</div>
<div style="margin-top:70px;font-size:58px;line-height:1.4">Comment <span class="gold" style="font-weight:bold">KING</span></div>
<div style="position:absolute;bottom:0;font-size:42px;color:#c9ccd6">Save + share with a creator friend &darr;</div>"""))


# ---------- Gumroad store images ----------
render("gumroad-cover", f"""
<div style="position:absolute;inset:0;display:flex;align-items:center;padding:0 90px;gap:70px;
 background:radial-gradient(circle at 20% 50%,#23242b 0%,#0f1014 65%)">
 <div style="width:230px;flex:none">{CROWN}</div>
 <div>
  <div style="font-size:30px;letter-spacing:6px" class="gold">DIGITAL KINGS</div>
  <div style="margin-top:18px;font-size:92px;font-weight:bold;line-height:1.02">The AI <span class="gold">Income</span> Kit</div>
  <div style="margin-top:28px;font-size:36px;color:#c9ccd6;line-height:1.35">75 AI prompts &middot; 7-day launch plan &middot; 30 viral hooks</div>
 </div>
</div>""", 1280, 720)
render("gumroad-thumbnail", f"""
<div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;
 background:radial-gradient(circle at 50% 40%,#23242b 0%,#0f1014 70%)">
 <div style="width:170px">{CROWN}</div>
 <div style="margin-top:34px;font-size:64px;font-weight:bold;line-height:1.05">AI <span class="gold">Income</span><br>Kit</div>
 <div style="margin-top:22px;font-size:26px;color:#c9ccd6">75 prompts to make money online</div>
</div>""", 600, 600)
import json
(SRC / "jobs.json").write_text(json.dumps(JOBS))
subprocess.run(["node", str(SRC / "shoot.js")], check=True)
print("ok")
