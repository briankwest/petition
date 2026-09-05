"""Per-letter response tokens for the records portal.

    python -m toolkit.letters.tokens issue               # mint a token for every letter that lacks one
    python -m toolkit.letters.tokens issue --reissue 3   # retire letter 3's token and mint a new one
    python -m toolkit.letters.tokens list                # letters and issue dates; never the tokens themselves
    python -m toolkit.letters.tokens verify TOKEN        # which letter a token belongs to

A token is 32 characters from a 32-symbol alphabet (no 0/O/1/I), 160 bits, printed in the letter as the URL
petition.mcalester.net/r/XXXX-XXXX-... and encoded compactly in its QR code. The plain tokens live only in
config/tokens.local.json (git-ignored, like the signature) and on the mailed paper. data/records/tokens.json
carries each token's SHA-256 with its letter number, slug and issue date and is committed, so the site can
recognise a token without ever holding one and git shows when each was issued or retired.
"""
from __future__ import annotations
import argparse, hashlib, json, re, secrets, sys
from datetime import date
from pathlib import Path
from toolkit import ROOT
from .data import SLUGS

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
LENGTH = 32
PORTAL = "https://petition.mcalester.net/r/"
LOCAL = ROOT / "config" / "tokens.local.json"
PUBLIC = ROOT / "data" / "records" / "tokens.json"


def mint() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))


def normalize(token: str) -> str:
    """Uppercase, hyphens and spaces dropped: what a clerk types from the letter must match what the QR carries."""
    return re.sub(r"[^A-Z2-9]", "", (token or "").upper())


def digest(token: str) -> str:
    return hashlib.sha256(normalize(token).encode()).hexdigest()


def display(token: str) -> str:
    t = normalize(token)
    return "-".join(t[i:i + 4] for i in range(0, len(t), 4))


def url(token: str, pretty: bool = False) -> str:
    return PORTAL + (display(token) if pretty else normalize(token))


def load_local(path: Path | None = None) -> dict[int, dict]:
    path = path or LOCAL                       # resolved at call time so tests can point the module elsewhere
    if not path.exists():
        return {}
    return {int(k): v for k, v in json.loads(path.read_text()).items()}


def load_public(path: Path | None = None) -> dict:
    path = path or PUBLIC
    if not path.exists():
        return {"portal": PORTAL, "letters": {}}
    return json.loads(path.read_text())


def issue(reissue: list[int] | None = None, local: Path | None = None, public: Path | None = None, today: date | None = None) -> list[int]:
    """Mint tokens for letters that have none (or that are listed for reissue). Returns the letter numbers minted."""
    local, public, today = local or LOCAL, public or PUBLIC, today or date.today()
    mine, pub = load_local(local), load_public(public)
    pub.setdefault("portal", PORTAL); pub.setdefault("letters", {})
    minted = []
    for n in sorted(SLUGS):
        if n in mine and n not in (reissue or []):
            continue
        if n in mine:                                            # retire the old one on the public side
            old = pub["letters"].get(str(n), {})
            retired = old.get("retired", []) + [dict(sha256=old.get("sha256"), issued=old.get("issued"), retired=today.isoformat())]
        else:
            retired = pub["letters"].get(str(n), {}).get("retired", [])
        t = mint()
        mine[n] = dict(slug=SLUGS[n], token=t, issued=today.isoformat())
        pub["letters"][str(n)] = dict(slug=SLUGS[n], sha256=digest(t), issued=today.isoformat(), retired=retired)
        minted.append(n)
    local.parent.mkdir(parents=True, exist_ok=True); public.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(json.dumps({str(k): mine[k] for k in sorted(mine)}, indent=2) + "\n")
    public.write_text(json.dumps(pub, indent=2) + "\n")
    return minted


def lookup(token: str, public: Path | None = None) -> dict | None:
    """The letter a token belongs to, from the committed hashes only: {n, slug, issued}; None if unknown or retired."""
    t = normalize(token)
    if len(t) != LENGTH:
        return None
    h = digest(t)
    for n, e in load_public(public).get("letters", {}).items():
        if secrets.compare_digest(e.get("sha256", ""), h):
            return dict(n=int(n), slug=e["slug"], issued=e.get("issued"))
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("issue"); i.add_argument("--reissue", type=int, action="append", help="letter number to retire and re-mint")
    sub.add_parser("list")
    v = sub.add_parser("verify"); v.add_argument("token")
    a = ap.parse_args(argv)
    if a.cmd == "issue":
        minted = issue(a.reissue)
        print(f"minted {len(minted)} token(s): {minted or 'none needed'}; plain tokens in {LOCAL.relative_to(ROOT)}, hashes in {PUBLIC.relative_to(ROOT)}")
    elif a.cmd == "list":
        pub = load_public(); mine = load_local()
        for n, e in sorted(pub.get("letters", {}).items(), key=lambda kv: int(kv[0])):
            print(f"{int(n):2d} {e['slug']:32s} issued {e['issued']}  {'local plaintext present' if int(n) in mine else 'NO LOCAL TOKEN'}  retired: {len(e.get('retired', []))}")
    elif a.cmd == "verify":
        e = lookup(a.token)
        print(f"letter {e['n']} ({e['slug']}), issued {e['issued']}" if e else "unknown or retired token")
        return 0 if e else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
