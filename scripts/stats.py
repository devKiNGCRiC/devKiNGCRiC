"""Builds the live GitHub stats card for the profile README.

Runs inside GitHub Actions (see .github/workflows/stats.yml). Uses only the
Python standard library: it asks the GitHub GraphQL API for your public repos
and contributions, then draws an SVG in the same style as the rest of the
README and writes it to the path given on the command line.
"""
import base64, datetime, html, json, os, sys, urllib.request

LOGIN = os.environ.get("GH_LOGIN", "devKiNGCRiC")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
HIDE = {"HTML", "CSS", "SCSS", "Procfile", "Batchfile", "Shell"}  # markup / glue, not "real" languages

# palette (matches the other SVGs in /assets)
CARD, TILE, LINE = "#15141C", "#1C1B25", "#2B2936"
CREAM, MUTED, DIM = "#F5F1E8", "#A39DB3", "#6E6880"
LIME, PINK = "#C8FF3D", "#FF5BD6"

# fonts are pulled from jsDelivr and embedded, so the card looks the same everywhere
FONT_CDN = os.environ.get("FONT_CDN") or "https://cdn.jsdelivr.net/npm/@fontsource/{pkg}@5.3.0/files/{pkg}-latin-{w}-normal.woff2"
FONTS = [("Unbounded", "unbounded", 800), ("Bricolage Grotesque", "bricolage-grotesque", 600),
         ("JetBrains Mono", "jetbrains-mono", 500), ("JetBrains Mono", "jetbrains-mono", 700)]

QUERY = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    contributionsCollection {
      totalCommitContributions
      contributionCalendar { totalContributions }
    }
    repositories(first: 100, after: $cursor, ownerAffiliations: OWNER, privacy: PUBLIC, isFork: false) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes { languages(first: 20, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name color } } } }
    }
  }
}"""


def graphql(variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json", "User-Agent": "profile-stats"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if data.get("errors"):
        raise SystemExit(f"GitHub API error: {data['errors']}")
    return data["data"]["user"]


def fetch():
    """Returns (stats dict, list of (language, bytes, color)) for the user."""
    if os.environ.get("STATS_MOCK"):  # local testing without the API
        user_pages = [json.load(open(os.environ["STATS_MOCK"]))]
    else:
        user_pages, cursor = [], None
        while True:
            u = graphql({"login": LOGIN, "cursor": cursor})
            user_pages.append(u)
            info = u["repositories"]["pageInfo"]
            if not info["hasNextPage"]: break
            cursor = info["endCursor"]
    first = user_pages[0]
    langs = {}
    for page in user_pages:
        for repo in page["repositories"]["nodes"]:
            for e in repo["languages"]["edges"]:
                name = e["node"]["name"]
                if name in HIDE: continue
                size, color = langs.get(name, (0, e["node"]["color"] or MUTED))
                langs[name] = (size + e["size"], color)
    cc = first["contributionsCollection"]
    stats = {
        "contrib": cc["contributionCalendar"]["totalContributions"],
        "commits": cc["totalCommitContributions"],
        "repos": first["repositories"]["totalCount"],
        "langs": len(langs),
    }
    ranked = sorted(((n, s, c) for n, (s, c) in langs.items()), key=lambda t: -t[1])
    return stats, ranked


def font_css():
    css = []
    for fam, pkg, w in FONTS:
        try:
            with urllib.request.urlopen(FONT_CDN.format(pkg=pkg, w=w), timeout=30) as r:
                b64 = base64.b64encode(r.read()).decode()
            css.append(f"@font-face{{font-family:'{fam}';font-weight:{w};src:url(data:font/woff2;base64,{b64}) format('woff2');}}")
        except Exception as exc:  # a missing font should never break the card
            print(f"warning: could not load {fam} {w}: {exc}", file=sys.stderr)
    return "".join(css)


def text(x, y, s, fam, w, size, fill, anchor="start", spacing=None):
    fb = {"Unbounded": "Arial Black, sans-serif", "Bricolage Grotesque": "Segoe UI, Helvetica, sans-serif",
          "JetBrains Mono": "Consolas, Menlo, monospace"}[fam]
    ls = f' letter-spacing="{spacing}"' if spacing else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="\'{fam}\', {fb}" font-weight="{w}" font-size="{size}" '
            f'fill="{fill}" text-anchor="{anchor}"{ls}>{html.escape(str(s))}</text>')


def fmt(n):
    return f"{n/1000:.1f}k".replace(".0k", "k") if n >= 1000 else str(n)


def build(stats, ranked):
    W, H = 1000, 290
    p = [f'<rect x=".75" y=".75" width="{W-1.5}" height="{H-1.5}" rx="23.5" fill="{CARD}" stroke="{LINE}" stroke-width="1.5"/>']
    today = datetime.date.today().strftime("%d %b %Y")
    # left: stat tiles
    p.append(f'<circle class="pulse" cx="37" cy="44" r="5" fill="{LIME}"/>')
    p.append(text(50, 49, "LIVE STATS", "JetBrains Mono", 700, 12.5, LIME, spacing=2))
    tiles = [(stats["contrib"], "Contributions (past year)"), (stats["commits"], "Commits (past year)"),
             (stats["repos"], "Public repos"), (stats["langs"], "Languages used")]
    for i, (num, label) in enumerate(tiles):
        x, y = 32 + (i % 2) * 222, 72 + (i // 2) * 102
        p.append(f'<rect x="{x}" y="{y}" width="210" height="90" rx="16" fill="{TILE}" stroke="{LINE}"/>')
        p.append(text(x + 18, y + 50, fmt(num), "Unbounded", 800, 34, CREAM))
        p.append(text(x + 18, y + 74, label, "JetBrains Mono", 500, 11.5, MUTED))
    # right: top languages
    rx, rw = 512, 456
    p.append(f'<path d="M{rx-24} 36V254" stroke="{LINE}"/>')
    p.append(text(rx, 49, "TOP LANGUAGES", "JetBrains Mono", 700, 12.5, PINK, spacing=2))
    p.append(text(W - 32, 49, f"Updated {today}", "JetBrains Mono", 500, 11.5, DIM, anchor="end"))
    top = ranked[:6]
    total = sum(s for _, s, _ in top) or 1
    p.append(f'<clipPath id="bar"><rect x="{rx}" y="76" width="{rw}" height="14" rx="7"/></clipPath><g clip-path="url(#bar)">')
    x = rx
    for name, size, color in top:
        seg = rw * size / total
        p.append(f'<rect x="{x:.1f}" y="76" width="{seg + 0.5:.1f}" height="14" fill="{color}"/>')
        x += seg
    p.append("</g>")
    for i, (name, size, color) in enumerate(top):
        cx, cy = rx + (i % 2) * 236, 130 + (i // 2) * 44
        p.append(f'<circle cx="{cx + 7}" cy="{cy - 5}" r="7" fill="{color}"/>')
        p.append(text(cx + 24, cy, name, "Bricolage Grotesque", 600, 17, CREAM))
        p.append(text(cx + 214, cy, f"{100 * size / total:.1f}%", "JetBrains Mono", 500, 13, MUTED, anchor="end"))
    if not top:
        p.append(text(rx, 140, "No language data yet", "Bricolage Grotesque", 600, 17, MUTED))
    p.append(text(rx, 262, "Share of code across my public repos (HTML/CSS hidden)", "JetBrains Mono", 500, 11, DIM))
    style = (font_css() + "@keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}.pulse{animation:pulse 1.4s ease-in-out infinite}"
             "@media (prefers-reduced-motion: reduce){*{animation:none!important}}")
    summary = (f"GitHub stats: {stats['contrib']} contributions and {stats['commits']} commits in the past year, "
               f"{stats['repos']} public repos. Top languages: " +
               ", ".join(f"{n} {100*s/total:.0f}%" for n, s, _ in top) + ".")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" fill="none" role="img" '
            f'aria-label="{html.escape(summary)}"><title>{html.escape(summary)}</title><style>{style}</style>' + "".join(p) + "</svg>")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "dist/stats.svg"
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    stats, ranked = fetch()
    with open(out, "w") as fh:
        fh.write(build(stats, ranked))
    print(f"wrote {out}: {stats}, top={[(n, s) for n, s, _ in ranked[:6]]}")
