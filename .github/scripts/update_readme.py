"""Refresh the language bars and the contribution heatmap in README.md.

Reads public data only (GitHub REST API + the public contributions page) and
rewrites the text between the <!--L--> and <!--P--> markers (languages, project tree
with the newest repos) and draws the heatmap into assets/activity.svg. Repos are grouped by topic: "ai-assisted" and
"college"; any other repo is "own". Language bars are split: repos written by me vs. "ai-assisted" ones.
(markers sit mid-line so they never start a line inside the <pre> blocks).
Usage: python update_readme.py <github-user> [README.md]
"""
import datetime
import html
import json
import os
import re
import sys
import textwrap
import urllib.request

USER = sys.argv[1]
PATH = sys.argv[2] if len(sys.argv) > 2 else "README.md"
BAR_WIDTH = 24
WEEKS = 48
SVG_PATH = os.path.join(os.path.dirname(os.path.abspath(PATH)), "assets", "activity.svg")
SVG_WIDTH, SVG_HEIGHT, SVG_CELL = 372, 112, 6.8
NAVY, GREEN, MUTED = "#0a192f", "#3DDC97", "#8892b0"
SHADES = ["#112240", "#1b4d44", "#24785d", "#2fa977", "#3DDC97"]
AI_TOPIC = "ai-assisted"
GROUPS = ["own", "college", AI_TOPIC]
DESC_WIDTH = 32
DESC_LINES = 1
MAX_REPOS = 5
TOP_LANGS = 5


def repos():
    data = json.loads(get(f"https://api.github.com/users/{USER}/repos?per_page=100&type=owner"))
    return [r for r in data if not r["fork"] and r["name"].lower() != USER.lower()]


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "readme-updater"})
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com"):
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode()


def bars(selected, top):
    totals = {}
    for repo in selected:
        for lang, n in json.loads(get(repo["languages_url"])).items():
            totals[lang] = totals.get(lang, 0) + n
    total = sum(totals.values())
    if not total:
        return ["(none yet)"]
    ranked = sorted(totals.items(), key=lambda x: -x[1])
    rows = ranked[:top]
    rest = sum(n for _, n in ranked[top:])
    if rest:
        rows.append(("other", rest))
    lines = []
    for name, n in rows:
        pct = n * 100 / total
        filled = round(pct / 100 * BAR_WIDTH)
        lines.append(f"{name:<11}<b>{'█' * filled}</b>{'░' * (BAR_WIDTH - filled)} {pct:5.1f}%")
    return lines


def languages():
    all_repos = repos()
    mine = [r for r in all_repos if AI_TOPIC not in r["topics"]]
    ai = [r for r in all_repos if AI_TOPIC in r["topics"]]
    lines = ["(written by me)"] + bars(mine, TOP_LANGS) + [f"({AI_TOPIC})"] + bars(ai, TOP_LANGS)
    return "\n" + "\n".join(lines)


def activity():
    page = get(f"https://github.com/users/{USER}/contributions")
    cells = sorted(set(re.findall(r'data-date="([\d-]+)"[^>]*data-level="(\d)"', page)))[-WEEKS * 7:]
    counts = {}
    for m in re.finditer(r'data-date="([\d-]+)"[^>]*>.*?</td>\s*<tool-tip[^>]*>(\d+|No) contributions?', page, re.S):
        counts[m.group(1)] = 0 if m.group(2) == "No" else int(m.group(2))
    pad = (datetime.date.fromisoformat(cells[0][0]).weekday() + 1) % 7
    cols = (len(cells) + pad + 6) // 7
    total = sum(counts.get(d, 0) for d, _ in cells)
    left, top, size = 30, 40, SVG_CELL - 1.4
    x = lambda c: left + c * SVG_CELL
    y = lambda r: top + r * SVG_CELL
    font = 'font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"'
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_WIDTH}" height="{SVG_HEIGHT}" '
        f'viewBox="0 0 {SVG_WIDTH} {SVG_HEIGHT}" role="img" aria-label="{total} contributions in {WEEKS} weeks">',
        f'<rect width="{SVG_WIDTH}" height="{SVG_HEIGHT}" rx="8" fill="{NAVY}"/>',
        f'<text x="{left}" y="18" {font} font-size="11" fill="{GREEN}" font-weight="bold">{total} contributions</text>',
        f'<text x="{SVG_WIDTH - 10}" y="18" {font} font-size="10" fill="{MUTED}" text-anchor="end">last {WEEKS} weeks</text>',
    ]
    last_label = -9
    for c in range(cols):
        idx = c * 7 - pad
        if idx < 0 or idx >= len(cells):
            continue
        day = datetime.date.fromisoformat(cells[idx][0])
        if (c == 0 or day.day <= 7) and c - last_label >= 4 and c + 3 <= cols:
            out.append(f'<text x="{x(c):.1f}" y="{top - 6}" {font} font-size="9" fill="{MUTED}">{day.strftime("%b")}</text>')
            last_label = c
    for r, name in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        out.append(f'<text x="8" y="{y(r) + size - 0.5:.1f}" {font} font-size="8" fill="{MUTED}">{name}</text>')
    for i, (date, level) in enumerate(cells):
        c, r = divmod(i + pad, 7)
        n = counts.get(date, 0)
        out.append(f'<rect x="{x(c):.1f}" y="{y(r):.1f}" width="{size:.1f}" height="{size:.1f}" rx="1.2" '
                   f'fill="{SHADES[int(level)]}"><title>{date}: {n}</title></rect>')
    ly = y(7) + 6
    lx = SVG_WIDTH - 10 - 5 * SVG_CELL - 26
    out.append(f'<text x="{lx - 4}" y="{ly + size - 0.5:.1f}" {font} font-size="8" fill="{MUTED}" text-anchor="end">less</text>')
    for k, shade in enumerate(SHADES):
        out.append(f'<rect x="{lx + k * SVG_CELL:.1f}" y="{ly}" width="{size:.1f}" height="{size:.1f}" rx="1.2" fill="{shade}"/>')
    out.append(f'<text x="{lx + 5 * SVG_CELL + 3:.1f}" y="{ly + size - 0.5:.1f}" {font} font-size="8" fill="{MUTED}">more</text>')
    out.append("</svg>")
    with open(SVG_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


def projects():
    groups = {g: [] for g in GROUPS}
    newest = sorted(repos(), key=lambda r: r["created_at"], reverse=True)[:MAX_REPOS]
    for repo in newest:
        group = next((g for g in GROUPS[1:] if g in repo["topics"]), "own")
        groups[group].append(repo)
    groups = {g: rs for g, rs in groups.items() if rs}
    lines = []
    for gi, (group, rs) in enumerate(groups.items()):
        last_group = gi == len(groups) - 1
        lines.append(("└── " if last_group else "├── ") + f"{group}/")
        pad = "    " if last_group else "│   "
        for ri, repo in enumerate(rs):
            last = ri == len(rs) - 1
            url = f"https://github.com/{USER}/{repo['name']}"
            lines.append(f'{pad}{"└── " if last else "├── "}<a href="{url}">{repo["name"]}</a>')
            desc = textwrap.wrap(repo["description"] or "", DESC_WIDTH)
            if len(desc) > DESC_LINES:
                desc = desc[:DESC_LINES]
                desc[-1] = desc[-1][:DESC_WIDTH - 1].rstrip(" ,.") + "…"
            lines += [pad + ("    " if last else "│   ") + html.escape(d) for d in desc]
    return "\n" + "\n".join(lines)


def replace(text, tag, body):
    pattern = re.compile(rf"(<!--{tag}-->).*?(<!--/{tag}-->)", re.S)
    if not pattern.search(text):
        sys.exit(f"marker {tag} not found")
    return pattern.sub(lambda m: f"{m.group(1)}{body}{m.group(2)}", text)


text = open(PATH, encoding="utf-8").read()
text = replace(text, "L", languages())
activity()
text = replace(text, "P", projects())
open(PATH, "w", encoding="utf-8").write(text)
