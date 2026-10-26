"""Refresh the language bars and the contribution heatmap in README.md.

Reads public data only (GitHub REST API + the public contributions page) and
rewrites the text between the <!--L-->..<!--/L--> and <!--A-->..<!--/A--> markers
(markers sit mid-line so they never start a line inside the <pre> blocks).
Usage: python update_readme.py <github-user> [README.md]
"""
import datetime
import json
import os
import re
import sys
import urllib.request

USER = sys.argv[1]
PATH = sys.argv[2] if len(sys.argv) > 2 else "README.md"
BAR_WIDTH = 24
WEEKS = 48
LEVELS = "·░▒▓█"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "readme-updater"})
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com"):
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode()


def languages():
    repos = json.loads(get(f"https://api.github.com/users/{USER}/repos?per_page=100&type=owner"))
    totals = {}
    for repo in repos:
        if repo["fork"] or repo["name"].lower() == USER.lower():
            continue
        for lang, n in json.loads(get(repo["languages_url"])).items():
            totals[lang] = totals.get(lang, 0) + n
    total = sum(totals.values())
    ranked = sorted(totals.items(), key=lambda x: -x[1])
    rows = ranked[:6]
    rest = sum(n for _, n in ranked[6:])
    if rest:
        rows.append(("other", rest))
    lines = []
    for name, n in rows:
        pct = n * 100 / total
        filled = round(pct / 100 * BAR_WIDTH)
        lines.append(f"{name:<11}<b>{'█' * filled}</b>{'░' * (BAR_WIDTH - filled)} {pct:5.1f}%")
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


def replace(text, tag, body):
    pattern = re.compile(rf"(<!--{tag}-->).*?(<!--/{tag}-->)", re.S)
    if not pattern.search(text):
        sys.exit(f"marker {tag} not found")
    return pattern.sub(lambda m: f"{m.group(1)}{body}{m.group(2)}", text)


text = open(PATH, encoding="utf-8").read()
text = replace(text, "L", languages())
text = replace(text, "A", activity())
open(PATH, "w", encoding="utf-8").write(text)
