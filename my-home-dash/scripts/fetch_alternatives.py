"""Download the latest Windows release of open-source Adobe/Microsoft alternatives from GitHub.

Usage:  python scripts/fetch_alternatives.py [adobe|microsoft ...]

Files land in data/downloads/<category>/<repo-name>/ and a manifest is written to
data/downloads/manifest.json, which the /adobe and /microsoft pages read.
Set GITHUB_TOKEN to raise the API rate limit.
"""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "data" / "downloads"
MANIFEST = DEST / "manifest.json"

# (repo, replaces, description)
CATALOG = {
    "adobe": [
        ("shotcut/shotcut", "Premiere Pro", "Cross-platform video editor"),
        ("OpenShot/openshot-qt", "Premiere Pro", "Easy-to-use video editor"),
        ("olive-editor/olive", "Premiere Pro", "Node-based non-linear video editor"),
        ("darktable-org/darktable", "Lightroom", "RAW photo workflow and darkroom"),
        ("audacity/audacity", "Audition", "Multi-track audio editor and recorder"),
        ("obsproject/obs-studio", "Captivate / Media Encoder", "Screen recording and live streaming"),
        ("penpot/penpot", "XD / Illustrator", "Open-source design and prototyping"),
        ("aseprite/aseprite", "Animate (pixel art)", "Pixel art and animation editor"),
        ("pencil2d/pencil", "Animate", "2D hand-drawn animation"),
        ("synfig/synfig", "Animate / After Effects", "2D vector animation and compositing"),
        ("jamovi/jamovi", "Analytics (stats)", "Statistical spreadsheet"),
        ("ImageMagick/ImageMagick", "Photoshop (batch)", "Command-line image processing"),
        ("ShareX/ShareX", "Capture tools", "Screen capture and sharing"),
        ("sumatrapdfreader/sumatrapdf", "Acrobat Reader", "Lightweight PDF/eBook reader"),
        ("pdfarranger/pdfarranger", "Acrobat Pro", "Merge, split, rotate PDF pages"),
        ("Stirling-Tools/Stirling-PDF", "Acrobat Pro", "Self-hosted PDF toolkit"),
        ("KDE/kdenlive", "Premiere Pro", "KDE video editor (GitHub mirror)"),
        ("rawtherapee/rawtherapee", "Lightroom", "RAW image processor"),
        ("LibreSprite/LibreSprite", "Animate (pixel art)", "Sprite editor, Aseprite fork"),
        ("HandBrake/HandBrake", "Media Encoder", "Video transcoder"),
    ],
    "microsoft": [
        ("ONLYOFFICE/DesktopEditors", "Word / Excel / PowerPoint", "Office suite with MS format fidelity"),
        ("VSCodium/vscodium", "Visual Studio Code", "VS Code builds without telemetry"),
        ("laurent22/joplin", "OneNote", "Notes with sync and Markdown"),
        ("logseq/logseq", "OneNote", "Outliner knowledge base"),
        ("AppFlowy-IO/AppFlowy", "Notion / OneNote", "Open-source workspace"),
        ("zen-browser/desktop", "Edge", "Privacy-focused Firefox-based browser"),
        ("brave/brave-browser", "Edge", "Chromium-based privacy browser"),
        ("ungoogled-software/ungoogled-chromium-windows", "Edge", "De-Googled Chromium"),
        ("notepad-plus-plus/notepad-plus-plus", "Notepad", "Source code and text editor"),
        ("microsoft/PowerToys", "Windows utilities", "Official Microsoft power-user utilities"),
        ("keepassxreboot/keepassxc", "Authenticator / passwords", "Offline password manager"),
        ("Bitwarden/clients", "Password manager", "Password manager desktop client"),
        ("syncthing/syncthing", "OneDrive", "Continuous peer-to-peer file sync"),
        ("nextcloud-releases/desktop", "OneDrive", "Nextcloud sync client"),
        ("mattermost/desktop", "Teams", "Team chat desktop app"),
        ("element-hq/element-desktop", "Teams", "Matrix chat client"),
        ("signalapp/Signal-Desktop", "Teams / Skype", "Private messenger"),
        ("jitsi/jitsi-meet-electron", "Teams / Skype", "Video meetings"),
        ("mRemoteNG/mRemoteNG", "Remote Desktop Manager", "Multi-protocol remote connections"),
        ("PowerShell/PowerShell", "Windows PowerShell", "Cross-platform PowerShell (official)"),
        ("git-for-windows/git", "Visual Studio Team tooling", "Git for Windows"),
        ("DBeaver/dbeaver", "SQL Server Mgmt Studio", "Universal database client"),
        ("dbcli/mssql-cli", "SSMS (CLI)", "SQL Server command-line client"),
        ("beekeeper-studio/beekeeper-studio", "SSMS / Access", "SQL editor and database manager"),
        ("sqlitebrowser/sqlitebrowser", "Access", "Visual SQLite database tool"),
        ("TeamNewPipe/NewPipe", "(skip)", ""),
    ],
}
CATALOG["microsoft"] = [c for c in CATALOG["microsoft"] if c[1] != "(skip)"]

MAX_BYTES = 1_500_000_000
BAD = re.compile(r"(arm64|aarch64|armv7|linux|mac|darwin|osx|android|\.deb|\.rpm|\.dmg|\.appimage|"
                 r"\.sig|\.asc|sha256|\.sha|\.txt|\.json|\.yml|\.blockmap|symbols|source|"
                 r"debug|pdb|portable-?(?:no|min)|\.apk|\.snap|\.flatpak|\.tar\.|ios|wsl)", re.I)
GOOD_EXT = (".exe", ".msi", ".msix", ".zip", ".7z")


def api(url):
    headers = {"User-Agent": "my-home-dash", "Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
        return json.load(r)


def score(asset):
    n = asset["name"].lower()
    if BAD.search(n) or not n.endswith(GOOD_EXT):
        return -1
    s = 0
    if "win" in n:
        s += 3
    if re.search(r"x64|x86[_-]64|amd64|win64|64", n):
        s += 3
    if n.endswith((".exe", ".msi")):
        s += 2
    if "setup" in n or "install" in n:
        s += 1
    if n.endswith(".zip") and "win" not in n:
        s -= 2
    return s


def pick(release):
    ranked = sorted(((score(a), a) for a in release.get("assets", [])), key=lambda t: -t[0])
    ranked = [t for t in ranked if t[0] >= 2 and t[1]["size"] <= MAX_BYTES]
    return ranked[0][1] if ranked else None


def download(url, path):
    tmp = path.with_suffix(path.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "my-home-dash"})
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    tmp.replace(path)


def main(categories):
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    for cat in categories:
        entries = []
        for repo, replaces, desc in CATALOG[cat]:
            name = repo.split("/")[1]
            entry = {"repo": repo, "name": name, "replaces": replaces, "description": desc,
                     "repo_url": f"https://github.com/{repo}",
                     "releases_url": f"https://github.com/{repo}/releases/latest",
                     "status": "pending"}
            try:
                rel = api(f"https://api.github.com/repos/{repo}/releases/latest")
                entry["version"] = rel.get("tag_name")
                asset = pick(rel)
                if not asset:
                    entry["status"] = "no-windows-asset"
                else:
                    folder = DEST / cat / name
                    folder.mkdir(parents=True, exist_ok=True)
                    target = folder / asset["name"]
                    if not (target.exists() and target.stat().st_size == asset["size"]):
                        print(f"[{cat}] {repo} -> {asset['name']} ({asset['size']/1e6:.0f} MB)", flush=True)
                        download(asset["browser_download_url"], target)
                    entry.update(status="downloaded", file=f"{cat}/{name}/{asset['name']}",
                                 size=asset["size"])
            except Exception as exc:  # keep going; record the failure
                entry["status"] = f"error: {exc}"
                print(f"[{cat}] {repo} FAILED: {exc}", flush=True)
            entries.append(entry)
        manifest[cat] = {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                         "items": entries}
        DEST.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    cats = [a for a in sys.argv[1:] if a in CATALOG] or list(CATALOG)
    main(cats)
