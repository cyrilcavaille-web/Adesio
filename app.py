#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mini app ar2ed36 - conversion des AR fournisseurs (PDF) vers le format
d'import Excalibur ED36 (.xlsx).

Usage : python3 app.py
Puis ouvrir http://localhost:5000
"""

from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path

from flask import Flask, render_template, request, send_file, abort

from ar2ed36.ar_extract import traiter
from ar2ed36.export_ed36 import exporter

APP_DIR = Path(__file__).parent
SAMPLE_DIR = APP_DIR / "sample_data"
OUTPUT_DIR = Path(tempfile.gettempdir()) / "ar2ed36_outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25 Mo


def _niveau(ligne) -> str:
    txt = " ".join(ligne.anomalies)
    if "[BLOQUANT]" in txt:
        return "BLOQUANT"
    if "[A VERIFIER]" in txt or "[AVERTISSEMENT]" in txt:
        return "A CONTROLER"
    return "OK"


def _run_pipeline(work_dir: Path) -> dict:
    """Traite tous les PDF d'un dossier et exporte le fichier ED36."""
    fichiers = sorted(p for p in work_dir.iterdir() if p.suffix.lower() == ".pdf")
    toutes = []
    par_fichier = []
    for f in fichiers:
        lignes = traiter(f)
        for l in lignes:
            par_fichier.append({
                "fichier": l.fichier,
                "fournisseur": l.fournisseur or "INCONNU",
                "methode": l.methode,
                "num_cmde": l.num_cmde,
                "id_poste": l.id_poste,
                "statut": _niveau(l),
                "confiance": l.confiance,
                "anomalies": l.anomalies,
            })
        toutes.extend(lignes)

    token = uuid.uuid4().hex
    out_path = OUTPUT_DIR / f"AR_import_ED36_{token}.xlsx"
    exporter(toutes, out_path)

    return {
        "token": token,
        "nb_fichiers": len(fichiers),
        "nb_postes": len(toutes),
        "nb_bloquants": sum(1 for r in par_fichier if r["statut"] == "BLOQUANT"),
        "nb_a_controler": sum(1 for r in par_fichier if r["statut"] == "A CONTROLER"),
        "nb_ok": sum(1 for r in par_fichier if r["statut"] == "OK"),
        "lignes": par_fichier,
    }


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", result=None)


@app.route("/convert", methods=["POST"])
def convert():
    fichiers = request.files.getlist("pdfs")
    fichiers = [f for f in fichiers if f and f.filename]
    if not fichiers:
        return render_template("index.html", result=None,
                                erreur="Choisis au moins un fichier PDF d'AR fournisseur.")

    ocr_json = request.files.get("ocr_json")

    with tempfile.TemporaryDirectory(prefix="ar2ed36_") as tmp:
        work_dir = Path(tmp)
        for f in fichiers:
            dest = work_dir / Path(f.filename).name
            f.save(dest)
        if ocr_json and ocr_json.filename:
            work_dir_json = work_dir / Path(ocr_json.filename).name
            ocr_json.save(work_dir_json)

        result = _run_pipeline(work_dir)

    return render_template("index.html", result=result, erreur=None)


@app.route("/demo", methods=["POST"])
def demo():
    """Rejoue le pipeline sur le jeu d'exemple embarque (AR scanne DUFLOT + OCR)."""
    with tempfile.TemporaryDirectory(prefix="ar2ed36_demo_") as tmp:
        work_dir = Path(tmp)
        shutil.copy(SAMPLE_DIR / "AR_PO_Duflot.pdf", work_dir / "AR_PO_Duflot.pdf")
        shutil.copy(SAMPLE_DIR / "AR_PO_Duflot.ocr.json", work_dir / "AR_PO_Duflot.ocr.json")
        result = _run_pipeline(work_dir)

    return render_template("index.html", result=result, erreur=None, demo=True)


@app.route("/download/<token>", methods=["GET"])
def download(token: str):
    safe = "".join(c for c in token if c.isalnum())
    path = OUTPUT_DIR / f"AR_import_ED36_{safe}.xlsx"
    if not path.exists():
        abort(404)
    return send_file(path, as_attachment=True, download_name="AR_import_ED36.xlsx")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
