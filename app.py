"""Interface web minimale du prototype : coller le texte d'une annonce,
obtenir le rapport structuré. Même pipeline que cli.py (parser + report),
juste une présentation HTML au lieu du terminal.
"""

from __future__ import annotations

from flask import Flask, render_template, request

from parser.ad_text_parser import parse_ad_text
from report.report_generator import (
    build_report_context,
    supported_chassis_groups,
    supported_chassis_sentence,
)

# Le dossier statique vit dans public/static/ (pas static/ à la racine) pour
# que Vercel le serve directement via son CDN (public/**) sans repasser par
# Flask — même URL /static/... en local (via Flask) et en prod (via Vercel).
app = Flask(__name__, static_folder="public/static", static_url_path="/static")


@app.route("/", methods=["GET", "POST"])
def index():
    context = None
    pasted_text = ""

    if request.method == "POST":
        pasted_text = request.form.get("ad_text", "")
        if pasted_text.strip():
            ad = parse_ad_text(pasted_text)
            context = build_report_context(ad)

    return render_template(
        "index.html",
        report=context,
        pasted_text=pasted_text,
        chassis_groups=supported_chassis_groups(),
        chassis_sentence=supported_chassis_sentence(),
    )


if __name__ == "__main__":
    app.run(debug=True, port=5051)
