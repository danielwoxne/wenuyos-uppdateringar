#!/usr/bin/env python3
"""Har Ubuntu släppt nyare versioner av paket som WenuyOS byggt om? Då ska de byggas om (säkerhetsrättelser).

  packaging/check-ubuntu.py                 jämför out/apt/*.dsc med Ubuntu
  packaging/check-ubuntu.py --published     jämför det publicerade förrådet (apt-resolute) – används av GitHub-bevakningen
  packaging/check-ubuntu.py --markdown      utdata som ärendetext;  --list  bara "paket@kodnamn" för ombygge
Läser Ubuntus Sources-filer direkt (main + universe, <kodnamn>, -updates, -security). Utgång 1 = något behöver byggas om.
"""
import glob, io, lzma, os, re, subprocess, sys, urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVE = "http://archive.ubuntu.com/ubuntu"
PUBLISHED = "https://github.com/danielwoxne/wenuyos-uppdateringar/releases/download/apt-resolute/Sources"


def vcmp(a, b):   # dpkg-versioner: -1, 0, 1
    for op, r in (("lt", -1), ("eq", 0)):
        if subprocess.run(["dpkg", "--compare-versions", a, op, b]).returncode == 0: return r
    return 1


def sources_conf():
    out = {}
    for line in open(os.path.join(HERE, "packaging", "sources.conf")):
        line = line.split("#")[0].split()
        if len(line) == 2: out[line[0]] = line[1]
    return out


def stanzas(text):
    for block in text.split("\n\n"):
        p = re.search(r"^Package: (\S+)", block, re.M); v = re.search(r"^Version: (\S+)", block, re.M)
        if p and v: yield p.group(1), v.group(1)


CACHE = {}
def ubuntu_version(src, codename):
    best = None
    for suite in (codename, codename + "-updates", codename + "-security"):
        for comp in ("main", "universe"):
            url = f"{ARCHIVE}/dists/{suite}/{comp}/source/Sources.xz"
            if url not in CACHE:
                try: CACHE[url] = lzma.decompress(urllib.request.urlopen(url, timeout=120).read()).decode("utf-8", "replace")
                except Exception: CACHE[url] = ""
            for p, v in stanzas(CACHE[url]):
                if p == src and "wenuyos" not in v and (best is None or vcmp(v, best) > 0): best = v
    return best


def ours(published):
    vers = {}
    if published:
        txt = urllib.request.urlopen(PUBLISHED, timeout=60).read().decode()
        for p, v in stanzas(txt):
            if "+wenuyos" in v and (p not in vers or vcmp(v, vers[p]) > 0): vers[p] = v
    else:
        for dsc in glob.glob(os.path.join(HERE, "out", "apt", "*+wenuyos*.dsc")):
            t = open(dsc).read()
            p = re.search(r"^Source: (\S+)", t, re.M).group(1); v = re.search(r"^Version: (\S+)", t, re.M).group(1)
            if p not in vers or vcmp(v, vers[p]) > 0: vers[p] = v
    return vers


def main(a):
    conf, have = sources_conf(), ours("--published" in a)
    todo, rows = [], []
    for src, cn in conf.items():
        mine = have.get(src)
        up = ubuntu_version(src, cn)
        base = mine.split("+wenuyos")[0] if mine else None
        if not up:
            rows.append((src, cn, mine or "–", "?", "kunde inte läsa Ubuntu"))
        elif not mine or vcmp(up, base) > 0:
            todo.append(f"{src}@{cn}" if cn != "resolute" else src)
            rows.append((src, cn, mine or "–", up, "BYGG OM"))
        else:
            rows.append((src, cn, mine, up, "ok"))
    if "--list" in a:
        print(" ".join(todo))
    elif "--markdown" in a:
        print("Ubuntu har nyare versioner av paket som WenuyOS byggt om (ofta säkerhetsrättelser). Bygg om och publicera:\n")
        print("```\nsudo packaging/rebuild.sh\n```\n")
        print("| Källpaket | Följer | WenuyOS | Ubuntu | |\n|---|---|---|---|---|")
        for r in rows: print("| " + " | ".join(r) + " |")
        print("\nTills dess används Ubuntus nyare version på datorerna (den har högre versionsnummer) – utom de val "
              "som bara finns hos WenuyOS (Mesa 26.2, bara om användaren valt det).")
    else:
        for src, cn, mine, up, st in rows:
            print(f"{st:<9} {src:<16} WenuyOS {mine:<34} Ubuntu {cn}: {up}")
    return 1 if todo else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
