"""Interface en ligne de commande du prototype.

Usage :
    python cli.py
    -> colle le texte de l'annonce (copié depuis le navigateur), termine par
       une ligne vide, et le rapport s'affiche.

    python cli.py chemin/vers/annonce.txt
    -> lit le texte depuis un fichier (pratique pour les tests).
"""

from __future__ import annotations

import sys

from parser.ad_text_parser import parse_ad_text
from report.report_generator import build_report


def read_pasted_text() -> str:
    print("Colle le texte de l'annonce ci-dessous, puis valide avec une ligne vide :")
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line == "" and lines:
            break
        lines.append(line)
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8") as f:
            text = f.read()
    else:
        text = read_pasted_text()

    if not text.strip():
        print("Aucun texte fourni.")
        sys.exit(1)

    ad = parse_ad_text(text)
    report = build_report(ad)
    print("\n" + report)


if __name__ == "__main__":
    main()
