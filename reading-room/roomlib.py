"""Shared look and helpers for the shared-mcp reading rooms."""
import html
E = html.escape
CSS = """
:root{--ink:#11212e;--ink-soft:#3a4d5c;--paper:#f6f4ee;--card:#fff;--rule:#d9d2c4;--accent:#1d5b73;--accent-2:#7a5ca6;--warn:#9a5b1e;--ok:#0f5132;--code:#eef1f0;--shadow:0 1px 3px rgba(0,0,0,.08),0 8px 28px rgba(0,0,0,.06)}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.62 "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;-webkit-font-smoothing:antialiased}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.shell{display:grid;grid-template-columns:288px minmax(0,1fr);min-height:100vh}
nav.toc{position:sticky;top:0;align-self:start;height:100vh;overflow-y:auto;background:#10242f;color:#cfe0e6;padding:28px 22px;border-right:1px solid #0a1922}
nav.toc h1{font-size:15px;letter-spacing:.04em;text-transform:uppercase;color:#f6f4ee;margin:0 0 4px}
nav.toc .sub{font-size:12.5px;color:#8fb0bb;margin:0 0 22px;font-style:italic}
nav.toc ol{list-style:none;margin:0;padding:0}nav.toc li{margin:2px 0}
nav.toc a{display:block;color:#bcd2da;padding:5px 8px;border-radius:6px;font-size:13.5px;font-family:ui-sans-serif,system-ui,sans-serif}
nav.toc a:hover{background:#16323f;text-decoration:none;color:#fff}
nav.toc .grp{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:#5f8694;margin:18px 0 4px;font-family:ui-sans-serif,system-ui,sans-serif}
.wrap{max-width:1100px;padding:56px 64px 120px}
header.doc{border-bottom:2px solid var(--ink);padding-bottom:26px;margin-bottom:8px}
header.doc .kicker{font:600 12px/1 ui-sans-serif,system-ui,sans-serif;letter-spacing:.18em;text-transform:uppercase;color:var(--accent)}
header.doc h1{font-size:33px;line-height:1.18;margin:14px 0 10px;letter-spacing:-.01em}
header.doc .lede{font-size:17px;color:var(--ink-soft);margin:0}
.meta{display:flex;flex-wrap:wrap;gap:8px 22px;margin-top:18px;font:13px/1.4 ui-sans-serif,system-ui,sans-serif;color:var(--ink-soft)}.meta b{color:var(--ink);font-weight:600}
section{padding:38px 0 8px;border-top:1px solid var(--rule);margin-top:30px}section:first-of-type{border-top:none}
h2{font-size:24px;margin:0 0 4px;letter-spacing:-.01em}h2 .num{color:var(--accent);font-variant-numeric:tabular-nums;margin-right:10px}
h3{font-size:16.5px;margin:26px 0 6px}h4{font:600 13px/1 ui-sans-serif,system-ui,sans-serif;margin:18px 0 6px;color:var(--ink-soft)}
.role{font:600 11.5px/1 ui-sans-serif,system-ui,sans-serif;letter-spacing:.1em;text-transform:uppercase;color:var(--accent-2);margin:0 0 14px}
p{margin:12px 0}p.big{font-size:20px;line-height:1.5;border-left:4px solid var(--accent);padding:6px 0 6px 18px;margin:18px 0}p.small{font-size:13.5px;color:var(--ink-soft)}
code{background:var(--code);padding:.1em .42em;border-radius:4px;font:13.5px/1.5 ui-monospace,"SF Mono",Menlo,monospace}
pre{background:var(--code);padding:12px 14px;border-radius:8px;font:12.5px/1.5 ui-monospace,Menlo,monospace;overflow:auto}
figure{margin:26px 0;background:var(--card);border:1px solid var(--rule);border-radius:12px;box-shadow:var(--shadow);overflow:hidden}
figure .cap{display:flex;gap:10px;align-items:center;padding:13px 18px;border-bottom:1px solid var(--rule);background:#fbfaf6}
figure .cap .fno{font:700 12px/1 ui-sans-serif,system-ui,sans-serif;letter-spacing:.08em;color:var(--accent);white-space:nowrap}
figure .cap .ft{font:13.5px/1.4 ui-sans-serif,system-ui,sans-serif;color:var(--ink-soft)}
figure .svgbox{padding:18px}.svgbox svg{width:100%;height:auto;display:block}
table{width:100%;border-collapse:collapse;margin:14px 0;font:14px/1.45 ui-sans-serif,system-ui,sans-serif;background:var(--card);border:1px solid var(--rule);border-radius:10px;overflow:hidden}
th,td{padding:9px 12px;border-bottom:1px solid var(--rule);text-align:left;vertical-align:top}th{background:#fbfaf6;font-weight:600}
td.ok{color:var(--ok);font-weight:600}td.fail{color:var(--warn);font-weight:600}
footer{margin-top:60px;padding-top:18px;border-top:1px solid var(--rule);font:13px/1.5 ui-sans-serif,system-ui,sans-serif;color:var(--ink-soft)}
@media (max-width:900px){.shell{grid-template-columns:1fr}nav.toc{position:static;height:auto}.wrap{padding:28px 20px 80px}}
"""

def sec(id_, num, title, role, body):
    return f'<section id="{id_}"><h2><span class="num">{num}</span>{title}</h2><p class="role">{role}</p>{body}</section>'

def fig(n, cap, svg):
    return f'<figure><div class="cap"><span class="fno">FIG {n}</span><span class="ft">{cap}</span></div><div class="svgbox">{svg}</div></figure>'

def page(title, kicker, h1, lede, meta_html, nav_html, body, footer):
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>{CSS}</style></head><body><div class="shell">{nav_html}
<main><div class="wrap"><header class="doc"><div class="kicker">{kicker}</div><h1>{h1}</h1><p class="lede">{lede}</p><div class="meta">{meta_html}</div></header>
{body}
<footer>{footer}</footer></div></main></div></body></html>"""
