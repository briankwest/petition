"""Freeze the filed pamphlet: python -m toolkit.freeze output/final/01-petition-pamphlet.pdf

Copies the PDF to output/filed/, records its SHA-256 (bytes) and a content fingerprint
(page sizes + text), and prints the git tag to create. After this, `toolkit.docs.check --final`
fails on any build whose content differs from the filed instrument."""
from __future__ import annotations
import argparse, shutil, sys
from datetime import date
from pathlib import Path
from toolkit import config as cfg
from toolkit.docs.check import FILED_DIR, fingerprint, load, sha256


def freeze(pdf: str | Path, force: bool = False) -> dict:
    pdf = Path(pdf)
    if not pdf.exists():
        raise SystemExit(f"not found: {pdf}")
    pages = load(pdf)
    hits = sorted({m.group(0) for pg in pages for m in cfg.PLACEHOLDER_RE.finditer(pg.text)})
    if hits and not force:
        raise SystemExit("refusing to freeze a pamphlet with placeholders: " + "; ".join(hits) + "\n(use --force only if counsel has confirmed the filed copy)")
    FILED_DIR.mkdir(parents=True, exist_ok=True)
    dest = FILED_DIR / "01-petition-pamphlet.pdf"
    shutil.copyfile(pdf, dest)
    digest, fp = sha256(dest), fingerprint(pages)
    (FILED_DIR / "SHA256SUMS").write_text(f"{digest}  01-petition-pamphlet.pdf\n")
    (FILED_DIR / "FINGERPRINT").write_text(f"{fp}  01-petition-pamphlet.pdf\n")
    return {"path": dest, "sha256": digest, "fingerprint": fp, "pages": len(pages)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    info = freeze(a.pdf, a.force)
    tag = f"filed-{date.today().isoformat()}"
    print(f"frozen: {info['path']} ({info['pages']} pages)\nsha256:      {info['sha256']}\nfingerprint: {info['fingerprint']}")
    print(f"\nRecord the file-stamp date/time in the Records Log, commit output/filed/, then:\n  git add output/filed && git commit -m 'Filed pamphlet {tag}' && git tag -a {tag} -m 'True copy filed with the Secretary of the County Election Board'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
