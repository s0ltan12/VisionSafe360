#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"
CHROME_DATA_DIR="/tmp/visionsafe-banner-chrome-profile"

# 1. Build a portrait print source sized to 70cm wide x 100cm high.
python3 build_print_banner.py
HTML_URI="$(python3 - <<'PY'
from pathlib import Path
print(Path('banner_70x100cm.html').resolve().as_uri())
PY
)"

# 2. Render to PDF via headless Chrome. The page CSS is exactly 700mm x 1000mm.
google-chrome-stable --headless=new --no-sandbox --disable-gpu \
  --user-data-dir="$CHROME_DATA_DIR" \
  --allow-file-access-from-files \
  --no-pdf-header-footer \
  --print-to-pdf="$ROOT/banner_70x100cm.pdf" \
  "$HTML_URI"
echo "PDF done:"; ls -la banner_70x100cm.pdf

# 3. Convert PDF -> SVG for print shops or vector editors.
inkscape banner_70x100cm.pdf --export-type=svg --export-filename=banner_70x100cm.svg --pdf-poppler 2>/dev/null \
  || inkscape banner_70x100cm.pdf --export-type=svg --export-filename=banner_70x100cm.svg
echo "SVG done:"; ls -la banner_70x100cm.svg
