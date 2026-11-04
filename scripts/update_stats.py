"""Generate a self-contained SVG from public GitHub data (Python stdlib only)."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from html import escape
import json
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
USERNAME = os.environ.get("PROFILE_USERNAME", "yelle233")
# Organization projects explicitly selected for this profile; never sum an entire org.
EXTRA_STAR_REPOS = ("QDU-VRobot/qdu26_sentry_navigation",)
if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", USERNAME):
    raise ValueError("Invalid GitHub username")


def api(path):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "github-profile-stats",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token := os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    for attempt in range(3):
        try:
            request = Request(f"https://api.github.com{path}", headers=headers)
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
        except (URLError, TimeoutError):
            if attempt == 2:
                raise
        time.sleep(2 ** attempt)


def star_repositories(owned_repos, extra_names):
    """Count each public repository once, including selected organization projects."""
    unique = {
        repo["full_name"].casefold(): repo
        for repo in owned_repos
        if not repo.get("private", False)
    }
    for name in extra_names:
        if name.casefold() in unique:
            continue
        repo = api(f"/repos/{name}")
        if repo.get("private", False):
            raise ValueError(f"Star statistics require a public repository: {name}")
        unique[repo["full_name"].casefold()] = repo
    return list(unique.values())


def generate():
    user = api(f"/users/{USERNAME}")
    repos = []
    page = 1
    while True:
        batch = api(f"/users/{USERNAME}/repos?type=owner&per_page=100&page={page}")
        repos.extend(repo for repo in batch if not repo.get("private", False))
        if len(batch) < 100:
            break
        page += 1

    originals = [repo for repo in repos if not repo["fork"]]
    languages = Counter()
    with ThreadPoolExecutor(max_workers=4) as pool:
        paths = [f"/repos/{repo['full_name']}/languages" for repo in originals]
        for result in pool.map(api, paths):
            languages.update(result)
    total = sum(languages.values())
    ordered = languages.most_common()
    shown = ordered[:4]
    if len(ordered) > 4:
        shown.append(("Other", sum(size for _, size in ordered[4:])))

    palette = {"Java": "#fbbf24", "C++": "#a78bfa", "Python": "#22d3ee", "HTML": "#fb7185", "C": "#60a5fa", "Fortran": "#fb923c", "Other": "#94a3b8"}
    fallback = ["#fbbf24", "#a78bfa", "#22d3ee", "#fb7185", "#94a3b8"]
    star_repos = star_repositories(repos, EXTRA_STAR_REPOS)
    stars = sum(repo["stargazers_count"] for repo in star_repos)
    personal_stars = sum(repo["stargazers_count"] for repo in repos)
    extra_stars = stars - personal_stars
    date = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    svg = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="360" viewBox="0 0 1200 360" role="img" aria-labelledby="title desc">
  <title id="title">{escape(USERNAME)} · GitHub at a glance</title>
  <desc id="desc">{len(repos)} personal public repositories, {stars} stars across personal repositories and selected organization projects ({personal_stars} personal + {extra_stars} organization), {user['followers']} followers. Organization stars belong to the whole project. Languages by bytes in personal non-fork public repositories only. Updated {date}, UTC+8.</desc>
  <rect x="1" y="1" width="1198" height="358" rx="22" fill="#15182b" stroke="#34314e"/>
  <g font-family="Segoe UI, Microsoft YaHei, sans-serif">
    <text x="38" y="48" fill="#ddd6fe" font-size="18" font-weight="700">GitHub 一瞥</text>
    <text x="1162" y="47" text-anchor="end" fill="#929bb7" font-size="12" letter-spacing="1.5">PUBLIC WORK / {escape(USERNAME.upper())}</text>
    <line x1="38" y1="70" x2="1162" y2="70" stroke="#30334a"/>
    <line x1="590" y1="94" x2="590" y2="293" stroke="#30334a"/>
    <text x="38" y="111" fill="#929bb7" font-size="12" letter-spacing="2">SMALL IDEAS, REAL PROJECTS</text>''']
    for x, number, label, color in [
        (38, len(repos), "个人公开仓库", "#c4b5fd"),
        (224, stars, "项目获星", "#f9a8d4"),
        (410, user["followers"], "关注者", "#67e8f9"),
    ]:
        svg.append(f'<text x="{x}" y="193" fill="{color}" font-size="55" font-weight="700">{number}</text><text x="{x}" y="227" fill="#cbd5e1" font-size="16">{label}</text>')
    svg.append(f'<text x="38" y="283" fill="#929bb7" font-size="14">个人仓库 {personal_stars} 星 + 组织项目 {extra_stars} 星</text>')
    svg.append('<text x="628" y="111" fill="#929bb7" font-size="12" letter-spacing="2">LANGUAGES / BY CODE SIZE</text>')
    svg.append('<rect x="628" y="134" width="534" height="12" rx="6" fill="#30334a"/>')
    cursor = 628.0
    for index, (language, size) in enumerate(shown):
        color = palette.get(language, fallback[index])
        width = 534 * size / total
        svg.append(f'<rect x="{cursor:.2f}" y="134" width="{width:.2f}" height="12" fill="{color}"/>')
        cursor += width
        x = 635 + (index % 2) * 275
        y = 183 + (index // 2) * 42
        svg.append(f'<circle cx="{x}" cy="{y - 5}" r="5" fill="{color}"/><text x="{x + 15}" y="{y}" fill="#e2e8f0" font-size="15">{escape(language)} <tspan fill="#929bb7">{size / total:.1%}</tspan></text>')
    if not total:
        svg.append('<text x="628" y="190" fill="#929bb7" font-size="15">暂无公开语言数据</text>')
    svg.append(f'<line x1="38" y1="309" x2="1162" y2="309" stroke="#30334a"/><text x="38" y="337" fill="#929bb7" font-size="12">获星含列明的组织项目 · 语言仅统计个人非 fork 仓库</text><text x="1162" y="337" text-anchor="end" fill="#929bb7" font-size="12">Updated {date} · UTC+8</text></g></svg>')
    target = ROOT / "assets" / "stats.svg"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text("\n".join(svg) + "\n", encoding="utf-8")
    temporary.replace(target)
    print(f"Updated public stats: {len(repos)} repositories, {stars} stars, {user['followers']} followers.")
    print(f"Star breakdown: {personal_stars} personal + {extra_stars} selected organization project stars.")
    for repo in sorted(star_repos, key=lambda item: item["full_name"].casefold()):
        print(f"  {repo['full_name']}: {repo['stargazers_count']}")


if __name__ == "__main__":
    generate()
