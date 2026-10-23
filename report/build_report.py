"""Builds report/report.html as a single self-contained file (course requirement:
opens by double-clicking, all images embedded) by inlining report/figures/*.jpg/png
as base64 data URIs into report_template.html.
"""
import base64
from pathlib import Path

REPORT_DIR = Path(__file__).resolve().parent
FIGURES_DIR = REPORT_DIR / "figures"
TEMPLATE_PATH = REPORT_DIR / "report_template.html"
OUTPUT_PATH = REPORT_DIR / "report.html"

MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


def data_uri(filename):
    path = FIGURES_DIR / filename
    mime = MIME[path.suffix.lower()]
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


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
