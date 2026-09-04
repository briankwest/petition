"""Generate the favicon set and the Open Graph share image from the site palette.

    python -m toolkit.branding            # writes app/static/icons/* and app/static/og.png

Mark: navy rounded square with a sunflower check — "put it to a vote". Colors match site.css."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from . import ROOT

NAVY, GOLD, PAPER, BLUE, MUTED = "#1F2A44", "#F2B705", "#FFFCF5", "#1E6FB8", "#5C6578"
ICONS = ROOT / "app" / "static" / "icons"

SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect width="64" height="64" rx="14" fill="{navy}"/>
<path d="M17 34 L28 45 L48 21" fill="none" stroke="{gold}" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"""


def draw_mark(size: int) -> Image.Image:
    s = 8  # supersample for smooth edges
    W = size * s
    im = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, W - 1, W - 1), radius=int(W * 14 / 64), fill=NAVY)
    pts = [(W * 17 / 64, W * 34 / 64), (W * 28 / 64, W * 45 / 64), (W * 48 / 64, W * 21 / 64)]
    w = int(W * 8 / 64)
    d.line(pts, fill=GOLD, width=w, joint="curve")
    for p in (pts[0], pts[2]):
        d.ellipse((p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2), fill=GOLD)
    return im.resize((size, size), Image.LANCZOS)


def _font(bold: bool, size: int) -> ImageFont.FreeTypeFont:
    cands = ["/System/Library/Fonts/Supplemental/Georgia Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Georgia.ttf",
             "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"]
    try:
        import matplotlib
        mpl = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
        cands.append(str(mpl / ("DejaVuSerif-Bold.ttf" if bold else "DejaVuSerif.ttf")))
    except Exception:
        pass
    for c in cands:
        if Path(c).exists():
            return ImageFont.truetype(c, size)
    return ImageFont.load_default()


def draw_og(title: str, eyebrow: str, tagline: str,
            footer: str = "Where to sign · Am I registered? · Who to call") -> Image.Image:
    W, H = 1200, 630
    im = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, W, 14), fill=GOLD)
    mark = draw_mark(150)
    im.paste(mark, (80, 92), mark)
    d.text((262, 96), eyebrow.upper(), font=_font(False, 26), fill=MUTED, spacing=4)
    # fit the title: shrink to the available width, wrapping to two lines for long names
    max_w, size, lines = W - 262 - 60, 76, [title]
    while True:
        f = _font(True, size)
        widths = [d.textlength(l, font=f) for l in lines]
        if max(widths) <= max_w or size <= 40:
            break
        if len(lines) == 1 and size <= 60:
            words = title.split(); best = None
            for i in range(1, len(words)):
                a, b = " ".join(words[:i]), " ".join(words[i:])
                cand = max(d.textlength(a, font=f), d.textlength(b, font=f))
                if best is None or cand < best[0]:
                    best = (cand, [a, b])
            lines = best[1]; continue
        size -= 4
    f = _font(True, size)
    y = 136 if len(lines) == 1 else 128
    for l in lines:
        d.text((262, y), l, font=f, fill=NAVY); y += int(size * 1.15)
    tag_y = max(300, y + 40)
    d.multiline_text((80, tag_y), tagline, font=_font(False, 44), fill=NAVY, spacing=12)
    d.rectangle((80, 520, 200, 528), fill=BLUE)
    d.text((80, 548), footer, font=_font(False, 28), fill=MUTED)
    return im


# Per-page share images. Each page that overrides {% block og_image %} has an entry here, so the
# whole set regenerates from one command and none is a one-off. Footer text names the page.
OG_PAGES = {
    "og-iren.png": dict(eyebrow="Company dossier · Pittsburg County, Oklahoma", title="The IREN File",
                        tagline="Sites, board, voting control and the $9.7bn\nMicrosoft contract — every figure drawn\nfrom IREN's own SEC filings.",
                        footer="petition.mcalester.net/iren · Who is IREN?"),
    "og-sites.png": dict(eyebrow="Pittsburg County, Oklahoma", title="Childress vs. Kiowa",
                         tagline="IREN built 750 MW in Texas on a ten-year deal.\nHere it wants 85% for twenty-five years.",
                         footer="petition.mcalester.net/childress-kiowa · Where to sign · Who to call"),
    "og-questions.png": dict(eyebrow="To the Board of County Commissioners · Pittsburg County",
                             title="Fifteen questions for the Board",
                             tagline="The plan binds the county to 85% for 25 years\nand binds the company to almost nothing.\nEvery question is pinned to a document.",
                             footer="petition.mcalester.net/questions · Ask the board"),
    "og-tldr.png": dict(eyebrow="Pittsburg County, Oklahoma", title="The one-page version",
                        tagline="The whole case on one printable sheet,\nwith a QR code to the full file.",
                        footer="petition.mcalester.net/tldr · Print it, share it"),
    "og-contact.png": dict(eyebrow="Pittsburg County, Oklahoma", title="Who to call",
                           tagline="The three commissioners who decide the abatement,\non a district map. The Kiowa site is in District 2.",
                           footer="petition.mcalester.net/contact · Who to call"),
}


# The flyer's QR code. Tagged so GA can tell scans from other traffic. segno is a dev-only dependency:
# the SVG is committed and served as a static file, so production never needs the library.
QR_URL = "https://petition.mcalester.net/?utm_source=flyer&utm_medium=print"


def write_qr(path: Path) -> bool:
    try:
        import segno
    except ImportError:
        print("segno not installed; QR code not regenerated (pip install segno)")
        return False
    segno.make(QR_URL, error="m").save(str(path), kind="svg", scale=4, border=1, dark=NAVY, light=None,
                                       xmldecl=False, svgclass=None, lineclass=None)
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--title", default="Referendum Petition")
    ap.add_argument("--eyebrow", default="Pittsburg County, Oklahoma")
    ap.add_argument("--tagline", default="Let Pittsburg County voters decide\non the data center tax abatement.")
    a = ap.parse_args(argv)
    ICONS.mkdir(parents=True, exist_ok=True)
    (ICONS / "favicon.svg").write_text(SVG.format(navy=NAVY, gold=GOLD))
    for size, name in [(180, "apple-touch-icon.png"), (192, "icon-192.png"), (512, "icon-512.png"), (32, "favicon-32.png")]:
        draw_mark(size).save(ICONS / name)
    draw_mark(64).save(ICONS / "favicon.ico", format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    (ICONS / "site.webmanifest").write_text(json.dumps({
        "name": f"{a.title} — {a.eyebrow}", "short_name": a.title, "start_url": "/", "display": "browser",
        "background_color": PAPER, "theme_color": NAVY,
        "icons": [{"src": "/static/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
                  {"src": "/static/icons/icon-512.png", "sizes": "512x512", "type": "image/png"}]}, indent=2))
    draw_og(a.title, a.eyebrow, a.tagline).save(ROOT / "app" / "static" / "og.png", optimize=True)
    write_qr(ROOT / "app" / "static" / "qr-site.svg")
    for name, spec in OG_PAGES.items():
        draw_og(spec["title"], spec["eyebrow"], spec["tagline"], spec["footer"]).save(ROOT / "app" / "static" / name, optimize=True)
    print("wrote", ", ".join(p.name for p in sorted(ICONS.iterdir())), "and app/static/og.png +", ", ".join(OG_PAGES))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
