"""Refresh the language bars and the contribution heatmap in README.md.

Reads public data only (GitHub REST API + the public contributions page) and
rewrites the text between the <!--L-->, <!--A--> and <!--P--> markers
(languages, activity, project tree with the newest repos). Repos are grouped by topic: "ai-assisted" and
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
LEVELS = "·░▒▓█"
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
    html = get(f"https://github.com/users/{USER}/contributions")
    cells = sorted(set(re.findall(r'data-date="([\d-]+)"[^>]*data-level="(\d)"', html)))[-WEEKS * 7:]
    counts = {}
    for m in re.finditer(r'data-date="([\d-]+)"[^>]*>.*?</td>\s*<tool-tip[^>]*>(\d+|No) contributions?', html, re.S):
        counts[m.group(1)] = 0 if m.group(2) == "No" else int(m.group(2))
    pad = (datetime.date.fromisoformat(cells[0][0]).weekday() + 1) % 7
    cols = (len(cells) + pad + 6) // 7
    grid = [[" "] * cols for _ in range(7)]
    for i, (_, level) in enumerate(cells):
        c, r = divmod(i + pad, 7)
        grid[r][c] = LEVELS[int(level)]
    header, last = [" "] * cols, None
    for c in range(cols):
        idx = c * 7 - pad
        if idx < 0:
            continue
        month = datetime.date.fromisoformat(cells[idx][0]).strftime("%b")
        if month != last and c + 3 <= cols and all(x == " " for x in header[max(c - 1, 0):c + 3]):
            header[c:c + 3] = list(month)
            last = month
    labels = ["   ", "Mon", "   ", "Wed", "   ", "Fri", "   "]
    rows = ["    " + "".join(header)] + [labels[r] + " " + "".join(grid[r]) for r in range(7)]
    total = sum(counts.get(d, 0) for d, _ in cells)
    return f"{total} in {WEEKS} weeks\n" + "\n".join(rows)


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
text = replace(text, "A", activity())
text = replace(text, "P", projects())
open(PATH, "w", encoding="utf-8").write(text)
