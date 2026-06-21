#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUT_HTML = ROOT / "banner_70x100cm.html"

ORIGINAL_W_PX = 1587
ORIGINAL_H_PX = 2245
PX_TO_MM = 25.4 / 96
TARGET_W_MM = 700
TARGET_H_MM = 1000


def read_logo(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8").strip()


def replace_last(text: str, old: str, new: str) -> str:
    index = text.rfind(old)
    if index == -1:
        raise ValueError(f"Could not find final marker: {old!r}")
    return text[:index] + new + text[index + len(old):]


eru_logo = "data:image/png;base64," + read_logo("assets/eru_logo.b64.txt")
vs_logo = "data:image/png;base64," + read_logo("assets/vs_logo.b64.txt")

html = (ROOT / "banner.template.html").read_text(encoding="utf-8")
html = html.replace("__ERU_LOGO__", eru_logo).replace("__VS_LOGO__", vs_logo)
html = html.replace(
    "<title>VisionSafe 360 Banner 100x70cm</title>",
    "<title>VisionSafe 360 Banner 70x100cm</title>",
)

print_css = f"""
  @page{{size:{TARGET_W_MM}mm {TARGET_H_MM}mm;margin:0;}}
  html,body{{width:{TARGET_W_MM}mm;height:{TARGET_H_MM}mm;margin:0!important;padding:0!important;background:#000;}}
  body{{overflow:hidden;}}
  .print-sheet{{
    position:relative;
    width:{TARGET_W_MM}mm;
    height:{TARGET_H_MM}mm;
    overflow:hidden;
    background:#000;
  }}
  .print-sheet > .page{{
    transform-origin:0 0;
    transform:scale({TARGET_W_MM / (ORIGINAL_W_PX * PX_TO_MM):.8f},{TARGET_H_MM / (ORIGINAL_H_PX * PX_TO_MM):.8f});
  }}
  .brand .o{{
    background:none!important;
    -webkit-background-clip:initial!important;
    background-clip:initial!important;
    -webkit-text-fill-color:var(--orange2)!important;
    color:var(--orange2)!important;
    text-shadow:0 0 40px rgba(255,106,0,.35);
  }}
  .team-grid .m .name{{color:#D7DBE0;font-weight:650;white-space:nowrap;}}
  .sup .srow .v{{color:#D7DBE0;font-weight:650;}}
"""
html = html.replace("</style>", print_css + "</style>", 1)
html = html.replace("<body>\n<div class=\"page\">", "<body>\n<div class=\"print-sheet\">\n<div class=\"page\">", 1)
html = replace_last(html, "</div>\n</body>", "</div>\n</div>\n</body>")

team_markup = """<div class="team-grid">
                <div class="m"><span class="n">01</span><span class="name">Hisham Mohamed</span><span class="d"></span></div>
                <div class="m"><span class="n">02</span><span class="name">Mohamed Soltan</span><span class="d"></span></div>
                <div class="m"><span class="n">03</span><span class="name">Raneem Mohamed</span><span class="d"></span></div>
                <div class="m"><span class="n">04</span><span class="name">John Amin</span><span class="d"></span></div>
                <div class="m"><span class="n">05</span><span class="name">Shams Elden Mohammed</span><span class="d"></span></div>
              </div>"""
html = html.replace(
    """<div class="team-grid">
                <div class="m"><span class="n">01</span><span class="d"></span></div>
                <div class="m"><span class="n">02</span><span class="d"></span></div>
                <div class="m"><span class="n">03</span><span class="d"></span></div>
                <div class="m"><span class="n">04</span><span class="d"></span></div>
                <div class="m"><span class="n">05</span><span class="d"></span></div>
              </div>""",
    team_markup,
)

html = html.replace(
    """<div class="srow"><span class="k">Name</span><span class="v"></span></div>
              <div class="srow"><span class="k">Title</span><span class="v"></span></div>""",
    """<div class="srow"><span class="k">Supervisor</span><span class="v">Dr. Amr Ibrahim</span></div>
              <div class="srow"><span class="k">Supervisor</span><span class="v">Eng. Aya Adel</span></div>""",
)

OUT_HTML.write_text(html, encoding="utf-8")
print(f"wrote {OUT_HTML.name}")
