"""Builds report/slides.html by inlining report/figures/*.jpg/png as base64 data URIs
into slides_template.html (reveal.js itself is loaded from a CDN, per the course
spec; only the images need to be embedded for the file to work when emailed).
"""
from pathlib import Path

from build_report import FIGURES_DIR, data_uri  # reuse the same helper

REPORT_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = REPORT_DIR / "slides_template.html"
OUTPUT_PATH = REPORT_DIR / "slides.html"


def main():
    html = TEMPLATE_PATH.read_text()
    for fig in FIGURES_DIR.iterdir():
        placeholder = f"{{{{{fig.name}}}}}"
        if placeholder in html:
            html = html.replace(placeholder, data_uri(fig.name))
    OUTPUT_PATH.write_text(html)
    size_mb = OUTPUT_PATH.stat().st_size / 1_000_000
    print(f"Saved {OUTPUT_PATH.relative_to(REPORT_DIR.parent)} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
