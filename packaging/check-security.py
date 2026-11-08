#!/usr/bin/env python3
"""Säkerhetsroboten: väntar det säkerhetsrättningar som WenuyOS behöver göra något åt?

  packaging/check-security.py              text
  packaging/check-security.py --markdown   ärendetext (GitHub-arbetsflödet sakerhet.yml, varje dag)
  packaging/check-security.py --json       maskinläsbart

Kontrollerar
  1. Debians säkerhetsspårare (security-tracker.debian.org): sårbarheter i trixie som är RÄTTADE i en nyare version
     än den som finns i senaste WenuyOS-ISO:n (packaging/debian13-packages.tsv). Installerade datorer får rättningen
     själva (automatiska säkerhetsuppdateringar), men ISO:n behöver byggas om – nya installationer får annars den
     gamla versionen tills första uppdateringen. Allvarliga (high/critical) räknas för sig.
  2. Firefox i ISO:n (/opt, innan Mozillas apt-paket tar över) mot Mozillas senaste version.
  3. Öppna (ännu inte rättade) allvarliga sårbarheter i trixie för paket i WenuyOS – bara information: där
     väntar alla på Debian.
Utgång 1 = något behöver göras (ISO byggas om). Läser bara offentliga data; ingen nyckel, inget token.
"""
import functools, json, os, subprocess, sys, urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACKER = "https://security-tracker.debian.org/tracker/data/json"
FIREFOX = "https://product-details.mozilla.org/1.0/firefox_versions.json"
RELEASE = "trixie"
SERIOUS = ("high", "critical")


def vcmp(a, b):   # dpkg-versioner: -1, 0, 1
    for op, r in (("lt", -1), ("eq", 0)):
        if subprocess.run(["dpkg", "--compare-versions", a, op, b]).returncode == 0:
            return r
    return 1


LATEST_ISO = "https://api.github.com/repos/danielwoxne/New-wenuyos/releases?per_page=20"


def latest_iso_list():
    """Paketlistan från den senaste ISO:n som byggts på GitHub (release iso-…-debian13-…), om det finns någon."""
    try:
        for rel in fetch(LATEST_ISO):
            if not rel.get("tag_name", "").startswith("iso-") or "debian13" not in rel["tag_name"]:
                continue
            for a in rel.get("assets", []):
                if a["name"].endswith(".tsv"):
                    req = urllib.request.Request(a["browser_download_url"], headers={"User-Agent": "wenuyos-security-check"})
                    path = os.path.join(HERE, "packaging", ".iso-packages.tsv")
                    with urllib.request.urlopen(req, timeout=120) as r, open(path, "wb") as f:
                        f.write(r.read())
                    return path, rel["tag_name"]
    except (OSError, ValueError, KeyError):
        pass
    return None, None


def shipped(path=None):
    """källpaket → (version, [binärpaket]) ur ISO:ns paketlista (Package, Version, Source, SourceVersion)."""
    path = path or os.path.join(HERE, "packaging", "debian13-packages.tsv")
    src = {}
    firefox = None
    for line in open(path):
        f = line.rstrip("\n").split("\t")
        if len(f) < 4 or f[0].startswith("#"):
            if len(f) >= 2 and f[0] == "#firefox":
                firefox = f[1]
            continue
        pkg, ver, s, sver = f[:4]
        s = s or pkg
        if s.startswith("linux-signed"):   # den signerade kärnan spåras under källpaketet linux
            s = "linux"
        sver = sver or ver
        cur = src.get(s)
        if not cur or vcmp(sver, cur[0]) < 0:   # den äldsta versionen räknas
            src[s] = (sver, (cur[1] if cur else []) + [pkg])
        else:
            cur[1].append(pkg)
    return src, firefox


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "wenuyos-security-check"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


def check(tracker, src):
    fixable, open_serious = [], []
    for name, (ver, bins) in src.items():
        for cve, info in tracker.get(name, {}).items():
            rel = info.get("releases", {}).get(RELEASE)
            if not rel:
                continue
            urg = rel.get("urgency", "")
            if rel.get("status") == "resolved":
                fixed = rel.get("fixed_version", "")
                if fixed and fixed != "0" and vcmp(ver, fixed) < 0:
                    fixable.append({"source": name, "cve": cve, "shipped": ver, "fixed": fixed, "urgency": urg})
            elif rel.get("status") == "open" and urg in SERIOUS and not rel.get("nodsa"):
                open_serious.append({"source": name, "cve": cve, "urgency": urg})
    return fixable, open_serious


def main():
    md, js = "--markdown" in sys.argv, "--json" in sys.argv
    path, tag = latest_iso_list()
    src, ff = shipped(path)
    where = tag or "packaging/debian13-packages.tsv"
    tracker = fetch(TRACKER)
    fixable, open_serious = check(tracker, src)
    latest_ff = None
    try:
        latest_ff = fetch(FIREFOX).get("LATEST_FIREFOX_VERSION")
    except OSError:
        pass
    ff_old = bool(ff and latest_ff and vcmp(ff, latest_ff) < 0)
    serious = [x for x in fixable if x["urgency"] in SERIOUS]
    act = bool(fixable) or ff_old
    if js:
        print(json.dumps({"fixable": fixable, "open_serious": open_serious, "firefox": {"iso": ff, "latest": latest_ff}}, indent=1))
        return 1 if act else 0
    pkgs = sorted({x["source"] for x in fixable})
    if md:
        print(f"Säkerhetsroboten (varje dag) – underlag: Debians säkerhetsspårare och Mozilla; ISO:ns paket: {where}.\n")
        if fixable:
            print(f"**{len(fixable)} rättade sårbarheter ({len(serious)} allvarliga) finns i nyare versioner än i ISO:n** – "
                  "installerade datorer rättas av de automatiska säkerhetsuppdateringarna; **bygg om ISO:n** "
                  "(Actions → ISO) så att nya installationer också har dem.\n")
            print("| Källpaket | I ISO:n | Rättad i | Sårbarheter |\n|---|---|---|---|")
            for p in pkgs:
                rows = [x for x in fixable if x["source"] == p]
                cves = ", ".join(sorted(x["cve"] for x in rows)[:6]) + (" …" if len(rows) > 6 else "")
                print(f"| {p} | {rows[0]['shipped']} | {max((x['fixed'] for x in rows), key=functools.cmp_to_key(vcmp))} | {cves} |")
            print()
        if ff_old:
            print(f"**Firefox i ISO:n är {ff}, senaste är {latest_ff}** – bygg om ISO:n (installerade datorer "
                  "uppdateras via Mozillas förråd).\n")
        if open_serious:
            print(f"Information: {len(open_serious)} allvarliga sårbarheter i trixie väntar på rättning från Debian "
                  f"({', '.join(sorted({x['source'] for x in open_serious})[:10])}).\n")
        if not act:
            print("Inget att göra – ISO:n har alla rättningar som finns.")
    else:
        print(f"Rättade i nyare version än ISO:n: {len(fixable)} ({len(serious)} allvarliga) i {len(pkgs)} paket")
        for p in pkgs[:30]:
            print("  " + p)
        print(f"Firefox: ISO {ff or '?'}, senaste {latest_ff or '?'}" + (" – bygg om ISO:n" if ff_old else ""))
        print(f"Öppna allvarliga i trixie (väntar på Debian): {len(open_serious)}")
    return 1 if act else 0


if __name__ == "__main__":
    sys.exit(main())
