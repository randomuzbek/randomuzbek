#!/usr/bin/env python3
"""Build metrics.svg from ALL repositories, private included.

Third-party card services only see public repos (and most of them are down or
paywalled anyway), so this renders the card locally from the GitHub GraphQL API
using a token that can see everything. Run it with `gh` authenticated:

    python3 .github/metrics/generate.py
"""
import json, subprocess, collections, html

USER = "randomuzbek"
BG, FG, DIM, ACCENT = "#0d1117", "#c9d1d9", "#8b949e", "#1f6feb"
PALETTE = ["#1f6feb", "#6e56cf", "#3fb950", "#d29922", "#db6d28",
           "#f778ba", "#39c5cf", "#a371f7", "#7d8590"]


def gql(query):
    out = subprocess.check_output(["gh", "api", "graphql", "-f", "query=" + query])
    return json.loads(out)["data"]


def collect():
    d = gql("""{viewer{id login followers{totalCount}
      repositories(first:100,ownerAffiliations:OWNER,isFork:false){totalCount nodes{
        name isPrivate stargazerCount
        languages(first:20,orderBy:{field:SIZE,direction:DESC}){edges{size node{name}}}}}}}""")["viewer"]
    repos = d["repositories"]["nodes"]
    uid = d["id"]

    langs = collections.Counter()
    for r in repos:
        for e in r["languages"]["edges"]:
            langs[e["node"]["name"]] += e["size"]

    # commit totals need one history() call per repo — batch them
    commits = 0
    names = [r["name"] for r in repos]
    for i in range(0, len(names), 15):
        frag = " ".join(
            f'r{j}: repository(owner:"{USER}",name:"{n}")'
            f'{{defaultBranchRef{{target{{... on Commit{{history{{totalCount}}}}}}}}}}'
            for j, n in enumerate(names[i:i + 15]))
        for v in gql("{" + frag + "}").values():
            ref = (v or {}).get("defaultBranchRef") or {}
            commits += ((ref.get("target") or {}).get("history") or {}).get("totalCount", 0)

    return {
        "commits": commits,
        "repos": d["repositories"]["totalCount"],
        "private": sum(1 for r in repos if r["isPrivate"]),
        "langs": langs,
    }


def bar(langs, x, y, w, top=8):
    total = sum(langs.values())
    rows = langs.most_common(top)
    rest = total - sum(v for _, v in rows)
    if rest > 0:
        rows.append(("Other", rest))

    seg, cx = [], x
    for i, (_, v) in enumerate(rows):
        sw = w * v / total
        seg.append(f'<rect x="{cx:.1f}" y="{y}" width="{sw:.1f}" height="10" '
                   f'fill="{PALETTE[i % len(PALETTE)]}"/>')
        cx += sw

    leg, lx, ly = [], x, y + 30
    for i, (name, v) in enumerate(rows):
        if i and i % 3 == 0:
            lx, ly = x, ly + 22
        c = PALETTE[i % len(PALETTE)]
        leg.append(f'<circle cx="{lx + 5}" cy="{ly - 4}" r="5" fill="{c}"/>'
                   f'<text x="{lx + 17}" y="{ly}" fill="{FG}" font-size="13">'
                   f'{html.escape(name)} <tspan fill="{DIM}">{100 * v / total:.1f}%</tspan></text>')
        lx += 200
    return f'<g><clipPath id="r"><rect x="{x}" y="{y}" width="{w}" height="10" rx="5"/></clipPath>' \
           f'<g clip-path="url(#r)">{"".join(seg)}</g>{"".join(leg)}</g>'


def tile(x, y, value, label):
    return (f'<text x="{x}" y="{y}" fill="{ACCENT}" font-size="30" font-weight="700">{value}</text>'
            f'<text x="{x}" y="{y + 20}" fill="{DIM}" font-size="12" '
            f'letter-spacing="1.2">{label}</text>')


def render(m):
    W, H = 760, 250
    tiles = "".join(tile(30 + i * 185, 92, v, l) for i, (v, l) in enumerate([
        (f'{m["commits"]:,}', "COMMITS"),
        (m["repos"], "REPOSITORIES"),
        (m["private"], "PRIVATE"),
        (len(m["langs"]), "LANGUAGES"),
    ]))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}"
  font-family="ui-monospace,SFMono-Regular,'JetBrains Mono',Consolas,monospace">
  <rect width="{W}" height="{H}" rx="10" fill="{BG}" stroke="#30363d"/>
  <text x="30" y="42" fill="{FG}" font-size="15" font-weight="700">All repositories</text>
  <text x="160" y="42" fill="{DIM}" font-size="13">public + private</text>
  <line x1="30" y1="56" x2="{W - 30}" y2="56" stroke="#30363d"/>
  {tiles}
  <text x="30" y="158" fill="{DIM}" font-size="12" letter-spacing="1.2">LANGUAGES BY SIZE</text>
  {bar(m["langs"], 30, 170, W - 60)}
</svg>'''


if __name__ == "__main__":
    metrics = collect()
    # A token that cannot see the account's repositories (CI's default
    # GITHUB_TOKEN, for one) yields a card reading 0 repos / 0 commits and
    # silently replaces a good one. Refuse to write that.
    if metrics["repos"] < 2 or metrics["commits"] < 1:
        raise SystemExit(
            f"refusing to write metrics.svg: token sees only {metrics['repos']} "
            f"repo(s) / {metrics['commits']} commit(s) — needs a PAT with repo scope")
    with open("metrics.svg", "w") as f:
        f.write(render(metrics))
    print({k: v for k, v in metrics.items() if k != "langs"})
