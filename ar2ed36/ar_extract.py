#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ar2ed36 - Extraction des AR de commande fournisseurs vers le format d'import
Excalibur ED36 (Parametres import AR fournisseur).

Pipeline :
  1. Ingestion      : lecture du PDF, detection de la couche texte
  2. Classification : identification du fournisseur (empreinte texte)
  3. Extraction     : parseur dedie par fournisseur (ancres + regex)
  4. Normalisation  : dates, nombres, devises, prix au conditionnement
  5. Controles      : champs obligatoires, coherence PU x Qte, ecart de delai
  6. Export         : fichier Excel au format ED36 (colonnes A..S)

Prototype ADESIO - demo ANALOG WAY.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Callable

import pdfplumber

# ----------------------------------------------------------------------------
# 1. Modele de donnees : une ligne = un poste de commande confirme
# ----------------------------------------------------------------------------

CONFIRMED_DATE_TO_CONFIRM = date(9999, 12, 31)   # convention EBV "a confirmer"


@dataclass
class ARLine:
    # --- colonnes ED36 (A..S) ---
    num_cmde: str = ""            # A  N. cmde fournisseur        (obligatoire)
    id_poste: str = ""            # B  Id poste cmde fournisseur  (obligatoire)
    produit: str = ""             # C  Produit (code article AW)
    qte: float | None = None      # D  Quantite
    unite: str = ""               # E  Unite d'achat
    coeff: float = 1.0            # F  Coefficient de conversion
    conditionnement: str = ""     # G  Unite de conditionnement
    qte_cond: float | None = None # H  Quantite par conditionnement
    pu_ht: float | None = None    # I  Prix unitaire HT            (obligatoire)
    remise: float = 0.0           # J  Remise
    qte_a_recevoir: float | None = None  # K  Solde a livrer       (obligatoire)
    date_confirmee: date | None = None   # L  Date confirmee       (obligatoire)
    date_ar: date | None = None   # M  Date de l'AR
    num_ar: str = ""              # N  N. AR fournisseur
    ref_fournisseur: str = ""     # O  Reference fournisseur
    fabricant: str = ""           # P  Fabricant
    ref_fabricant: str = ""       # Q  Reference fabricant
    devise: str = ""              # R  Devise
    commentaires: str = ""        # S  Commentaires

    # --- metadonnees hors fichier d'import ---
    fournisseur: str = ""
    fichier: str = ""
    methode: str = ""             # TEXTE | OCR
    date_souhaitee: date | None = None
    total_annonce: float | None = None
    confiance: float = 1.0
    anomalies: list[str] = field(default_factory=list)

    def flag(self, niveau: str, message: str, cout: float = 0.0) -> None:
        self.anomalies.append(f"[{niveau}] {message}")
        self.confiance = round(max(0.0, self.confiance - cout), 2)


# ----------------------------------------------------------------------------
# 2. Normalisation (le coeur du sujet : chaque fournisseur a ses conventions)
# ----------------------------------------------------------------------------

MOIS_EN = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], start=1)}
MOIS_EN.update({m[:3]: i for m, i in list(MOIS_EN.items())})


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def nettoyer_libelle(s: str) -> str:
    """
    Recolle les lettres isolees par le kerning du PDF ("komplet t" -> "komplett")
    et normalise les espaces. Applique aux seuls libelles, jamais aux references.
    """
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"(?<=\w) ([a-z])(?= |$)", r"\1", s)
    return s


def texte_des_colonnes(pdf_path: Path, motif_ligne: str,
                       entetes: list[str]) -> dict[str, str] | None:
    """
    Decoupe une ligne de tableau en s'appuyant sur l'abscisse des entetes fournies
    (dans l'ordre de gauche a droite). Utile quand deux colonnes voisines
    contiennent du texte libre susceptible de deborder sur la ligne suivante :
    une regex ne sait pas ou finit la description et ou commence le fabricant.
    """
    with pdfplumber.open(pdf_path) as pdf:
        mots = pdf.pages[0].extract_words(keep_blank_chars=False)
    bornes = []
    for e in entetes:
        w = next((m for m in mots if m["text"] == e.split()[0]), None)
        if w is None:
            return None
        bornes.append((e, w["x0"] - 3))
    cible = next((m for m in mots if re.fullmatch(motif_ligne, m["text"])), None)
    if cible is None:
        return None
    ligne = sorted((m for m in mots if cible["top"] - 2 <= m["top"] <= cible["top"] + 14),
                   key=lambda m: (m["top"], m["x0"]))
    out = {e: [] for e, _ in bornes}
    for m in ligne:
        col = None
        for e, x in bornes:
            if m["x0"] >= x:
                col = e
        if col:
            out[col].append(m["text"])
    return {e: " ".join(v).strip() for e, v in out.items()}


def to_date(raw: str) -> date | None:
    """Accepte 14.04.2027 / 15/06/2026 / 15 Sep 2026 / November 9, 2026."""
    raw = raw.strip().rstrip(".,")
    m = re.match(r"^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$", raw)
    if m:
        d, mo, y = (int(x) for x in m.groups())
        return date(y, mo, d)
    m = re.match(r"^(\d{1,2})\s+([A-Za-z]+)\.?\s+(\d{4})$", raw)      # 15 Sep 2026
    if m and m.group(2).lower()[:3] in MOIS_EN:
        return date(int(m.group(3)), MOIS_EN[m.group(2).lower()[:3]], int(m.group(1)))
    m = re.match(r"^([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})$", raw)        # November 9, 2026
    if m and m.group(1).lower()[:3] in MOIS_EN:
        return date(int(m.group(3)), MOIS_EN[m.group(1).lower()[:3]], int(m.group(2)))
    return None


def to_float(raw: str, convention: str) -> float | None:
    """
    convention = 'fr' : 4.000 = quatre mille   /  19,80 = dix-neuf virgule huit
    convention = 'en' : 1,350.000 = mille trois cent cinquante  /  67.500 = 67.5
    C'est LE piege du lot : le meme litteral '4.000' vaut 4000 chez EBV et 4 chez ICAPE.
    """
    if raw is None:
        return None
    s = raw.strip().replace("\u00a0", "").replace(" ", "")
    if not s:
        return None
    if convention == "fr":
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


# ----------------------------------------------------------------------------
# 3. Classification du fournisseur
# ----------------------------------------------------------------------------

SIGNATURES: list[tuple[str, tuple[str, ...]]] = [
    ("EBV Elektronik (Avnet)", ("EBV Elektronik", "avnet.com")),
    ("ICAPE", ("ICAPE", "Order confirmation")),
    ("Confidee GmbH", ("Confidee", "Sell-to Customer No")),
    ("POLYRACK", ("POLYRACK", "Aufbausysteme")),
    ("DUFLOT", ("DUFLOT", "ACCUSE RECEPTION")),
]


def classify(text: str, filename: str) -> str:
    plain = strip_accents(text).upper()
    for name, keys in SIGNATURES:
        if all(strip_accents(k).upper() in plain for k in keys):
            return name
    # repli sur le nom de fichier (utile quand la couche texte est absente)
    for name, _ in SIGNATURES:
        if strip_accents(name.split()[0]).upper() in strip_accents(filename).upper():
            return name
    return "INCONNU"


# ----------------------------------------------------------------------------
# 4. Parseurs par fournisseur
# ----------------------------------------------------------------------------

def parse_ebv(text: str) -> list[ARLine]:
    """AR / modification d'AR Avnet-EBV. Multi-postes, format FR, prix au cent."""
    lines: list[ARLine] = []
    num_ar = re.search(r"No:\s*(\d+)", text)
    date_ar = re.search(r"Date:\s*(\d{2}\.\d{2}\.\d{4})", text)
    maj = re.search(r"Mis a jour:\s*(\d{2}\.\d{2}\.\d{4})", strip_accents(text))
    cmde = re.search(r"No Commande:\s*(\S+)", text)
    modification = "Modification d'AR" in text

    # un bloc par poste : "  10 (C)REFERENCE   4.000   19,80 / 100   792,00"
    bloc_re = re.compile(
        r"^\s*(\d+)\s+(?:\(C\))?(\S+)\s+([\d.,]+)\s+([\d.,]+)(?:\s*/\s*(\d+))?\s+([\d.,]+)\s*$",
        re.M)
    postes = list(bloc_re.finditer(text))
    for i, m in enumerate(postes):
        bloc = text[m.start(): postes[i + 1].start() if i + 1 < len(postes) else len(text)]
        l = ARLine(fournisseur="EBV Elektronik (Avnet)", methode="TEXTE")
        l.num_ar = num_ar.group(1) if num_ar else ""
        l.date_ar = to_date(maj.group(1)) if maj else (to_date(date_ar.group(1)) if date_ar else None)
        l.num_cmde = cmde.group(1) if cmde else ""
        l.ref_fabricant = m.group(2)
        l.qte = to_float(m.group(3), "fr")
        pu, par = to_float(m.group(4), "fr"), int(m.group(5) or 1)
        l.pu_ht = round(pu / par, 6) if pu is not None else None
        l.total_annonce = to_float(m.group(6), "fr")
        l.devise = "EUR"
        l.unite = "PCE"
        l.qte_a_recevoir = l.qte

        # le poste AW est dans "Votre No de commande: A202600971 / 1"
        votre = re.search(r"Votre No de commande:\s*(\S+)\s*/\s*(\d+)", bloc)
        if votre:
            l.num_cmde, l.id_poste = votre.group(1), votre.group(2).zfill(3)
        prod = re.search(r"Designation Client:\s*(\S+)", strip_accents(bloc))
        if prod:
            l.produit = prod.group(1)
        fab = re.search(r"Reference Fabricant:\s*(\S+)", strip_accents(bloc))
        if fab:
            l.ref_fabricant = fab.group(1)
        # le fabricant est la ligne suivant l'intitule du poste
        suite = bloc.split("\n")
        if len(suite) > 1:
            l.fabricant = suite[1].strip()
        mpq = re.search(r"MPQ:\s*([\d.,]+)\s*(\w+)", bloc)
        if mpq:
            l.conditionnement, l.qte_cond = mpq.group(2), to_float(mpq.group(1), "fr")

        # cadencement : date demandee + date estimee
        cad = re.search(r"(\d{2}\.\d{2}\.\d{4})\s+([\d.,]+)\s+(\d{2}\.\d{2}\.\d{4})\s+([\d.,]+)", bloc)
        if cad:
            l.date_souhaitee = to_date(cad.group(1))
            l.date_confirmee = to_date(cad.group(3))
            l.qte_a_recevoir = to_float(cad.group(4), "fr")
        if par > 1:
            l.commentaires = f"PU source {m.group(4)} / {par}"
        if modification:
            l.commentaires = (l.commentaires + " ; modification d'AR").strip(" ;")
        lines.append(l)
    return lines


def parse_icape(text: str) -> list[ARLine]:
    """AR ICAPE : anglais, USD (ou autre devise), prix au lot de n PCB.
    Le n. de poste client est l'"Item" ICAPE (ex. "30" dans "30  Material: ..."),
    a confirmer avec AW."""
    l = ARLine(fournisseur="ICAPE", methode="TEXTE", unite="PCB", devise="USD")
    m = re.search(r"Number\s+(\d+)", text)
    l.num_ar = m.group(1) if m else ""
    m = re.search(r"Creation date\s+([A-Za-z]+ \d{1,2}, \d{4})", text)
    l.date_ar = to_date(m.group(1)) if m else None
    m = re.search(r"Customer Order Reference\s+(\S+)", text)
    l.num_cmde = m.group(1) if m else ""
    m = re.search(r"^(\d+)\s+Material:", text, re.M)
    if m:
        l.id_poste = m.group(1).zfill(3)
        l.flag("A VERIFIER", f"poste deduit de l'Item ICAPE '{m.group(1)}' : a confirmer avec AW", 0.1)
    m = re.search(r"Material:\s*(\S+)\s+(\S+)", text)
    if m:
        l.produit, l.ref_fournisseur = m.group(2), m.group(1)
    m = re.search(r"Quantity\s*:\s*([\d.,]+)\s+(\w+)", text)
    if m:
        l.qte = to_float(m.group(1), "en")
        l.unite = m.group(2)
    m = re.search(r"Requested delivery date\s*:\s*([A-Za-z]+ \d{1,2}, \d{4})", text)
    l.date_souhaitee = to_date(m.group(1)) if m else None
    bloc_conf = text.split("Confirmations:", 1)[-1].split("Reference Doc.", 1)[0]
    m = re.search(r"([A-Za-z]+ \d{1,2}, \d{4})\s+([\d.,]+)\s+(\w+)", bloc_conf)
    if m:                                    # ligne de confirmation (date + qte)
        l.date_confirmee = to_date(m.group(1))
        l.qte_a_recevoir = to_float(m.group(2), "en")
    m = re.search(r"Unit Price\s+([\d.,]+)\s+(\w{3})\s+per\s+([\d.,]+)\s+(\w+)\s+([\d.,]+)", text)
    if m:
        pu, par = to_float(m.group(1), "en"), to_float(m.group(3), "en") or 1
        l.pu_ht = round(pu / par, 6)
        l.devise = m.group(2)
        l.total_annonce = to_float(m.group(5), "en")
        l.conditionnement, l.qte_cond = m.group(4), par
        l.commentaires = f"PU source {m.group(1)} {m.group(2)} / {m.group(3)} {m.group(4)}"
    ship = re.search(r"Shipping type:\s*(\w+)", text)
    if ship:
        l.commentaires = (l.commentaires + f" ; expedition {ship.group(1)}").strip(" ;")
    return [l]


def parse_confidee(text: str, pdf_path: Path) -> list[ARLine]:
    """AR Confidee : tableau une ligne, anglais, milliers en virgule."""
    l = ARLine(fournisseur="Confidee GmbH", methode="TEXTE")
    m = re.search(r"Order No\.\s*(\S+)", text)
    l.num_ar = m.group(1) if m else ""
    m = re.search(r"Document Date\s+(\d{1,2} [A-Za-z]{3} \d{4})", text)
    l.date_ar = to_date(m.group(1)) if m else None
    m = re.search(r"Your Reference\s+(\S+)", text)
    if m:
        ref = m.group(1)
        if "_" in ref:                       # A202600066_002 -> commande + poste
            l.num_cmde, poste = ref.rsplit("_", 1)
            l.id_poste = poste.zfill(3)
            l.flag("A VERIFIER",
                   f"poste deduit du suffixe de '{ref}' : regle a confirmer avec AW", 0.15)
        else:
            l.num_cmde = ref

    m = re.search(
        r"^(ART\d+)\s+(\S+)\s+(.+?)\s+([A-Z]{3})\s+(\d{1,2} [A-Za-z]{3} \d{4})\s+"
        r"([\d.,]+)\s+(\w+)\s+([A-Z]{3})\s+([\d.,]+)\s+([\d.,]+)\s*$", text, re.M)
    if m:
        l.ref_fournisseur = m.group(1)
        l.produit = m.group(2)
        l.date_confirmee = to_date(m.group(5))
        l.qte = l.qte_a_recevoir = to_float(m.group(6), "en")
        l.unite = m.group(7)
        l.devise = m.group(8)
        l.pu_ht = to_float(m.group(9), "en")
        l.total_annonce = to_float(m.group(10), "en")
    else:
        l.flag("BLOQUANT", "ligne de poste illisible", 0.5)

    # description et fabricant sont deux colonnes de texte libre accolees :
    # on les separe a l'abscisse de l'entete "Manufacturer".
    cols = texte_des_colonnes(pdf_path, r"ART\d+", ["Description", "Manufacturer", "CoO"])
    if cols:
        l.ref_fabricant = nettoyer_libelle(cols["Description"])
        l.fabricant = nettoyer_libelle(cols["Manufacturer"])
    elif m:
        l.ref_fabricant = nettoyer_libelle(m.group(3))
        l.flag("A VERIFIER", "separation description / fabricant non fiable", 0.1)
    return [l]


def parse_polyrack(text: str) -> list[ARLine]:
    """AR Polyrack : confirmation FR/DE, poste fournisseur, reference client en clair."""
    l = ARLine(fournisseur="POLYRACK", methode="TEXTE", devise="EUR")
    m = re.search(r"N. / Date\s+(\d+)\s*/\s*(\d{2}\.\d{2}\.\d{4})", strip_accents(text))
    if m:
        l.num_ar, l.date_ar = m.group(1), to_date(m.group(2))
    m = re.search(r"votre commande:\s*(\S+)\s+du\s+(\d{2}\.\d{2}\.\d{4})", text)
    if m:
        l.num_cmde = m.group(1)
    m = re.search(r"^\s*(\d+)\s+(\d+)\s+(.+?)\s+([\d.,]+)\s+(\w+)\s+([\d.,]+)\s*$", text, re.M)
    if m:
        l.ref_fournisseur = m.group(2)
        l.ref_fabricant = nettoyer_libelle(m.group(3))
        l.qte = l.qte_a_recevoir = to_float(m.group(4), "fr")
        l.unite = m.group(5)
        l.pu_ht = to_float(m.group(6), "fr")
        l.commentaires = f"poste fournisseur {m.group(1)}"
        # Polyrack ne transmet jamais le n. de poste client. Sur un AR a une
        # seule ligne (seul cas rencontre a ce jour), on propose 001 par
        # defaut plutot que de bloquer systematiquement l'import : a
        # confirmer contre la commande Excalibur avant validation.
        l.id_poste = "001"
        l.flag("A VERIFIER",
               "Id poste non fourni par Polyrack : propose par defaut a 001 "
               "(AR a une seule ligne) - a confirmer contre la commande Excalibur", 0.2)
    m = re.search(r"Votre n. d'article\s*:\s*(\S+)", strip_accents(text))
    if m:
        l.produit = m.group(1)
    m = re.search(r"Date de livraison:\s*(\d{2}\.\d{2}\.\d{4})", text)
    l.date_confirmee = to_date(m.group(1)) if m else None
    if "Livraison gratuite" in text:
        l.commentaires = (l.commentaires + " ; livraison gratuite (PU 0)").strip(" ;")
    if not l.fabricant:
        # Polyrack fabrique lui-meme ce type de coffret sur mesure ; aucun
        # autre fabricant n'apparait jamais sur ces AR.
        l.fabricant = "POLYRACK"
    l.total_annonce = (l.qte or 0) * (l.pu_ht or 0)
    return [l]


def parse_scan(text: str, pdf_path: Path) -> list[ARLine]:
    """
    Pas de couche texte : l'AR est un scan (ex. le propre bon de commande AW
    retourne signe par le fournisseur). En production -> OCR (Tesseract / Azure
    Document Intelligence) produisant un JSON structure <nom_du_pdf>.ocr.json,
    depose a cote du PDF. Chaque ligne est marquee comme issue de l'OCR, a valider.
    Appelee uniquement quand ce JSON existe deja (voir traiter()).
    """
    ref = pdf_path.with_suffix(".ocr.json")
    data = json.loads(ref.read_text(encoding="utf-8"))
    out = []
    for row in data["postes"]:
        l = ARLine(fournisseur=data["fournisseur"], methode="OCR",
                   num_cmde=data["num_cmde"], num_ar=data.get("num_ar", ""),
                   date_ar=to_date(data["date_ar"]), devise=data.get("devise", "EUR"))
        l.id_poste = row["poste"]
        l.produit = row["produit"]
        l.ref_fabricant = row["libelle"]
        l.qte = l.qte_a_recevoir = row["qte"]
        l.unite = row["unite"]
        l.pu_ht = row["pu"]
        l.total_annonce = row["total"]
        l.date_confirmee = to_date(row["date_livraison"])
        l.date_souhaitee = l.date_confirmee
        l.commentaires = "AR = BC retourne signe (scan)"
        l.flag("A VERIFIER", "valeurs issues de l'OCR, relecture humaine requise", 0.35)
        out.append(l)
    return out


PARSEURS: dict[str, Callable] = {
    "EBV Elektronik (Avnet)": lambda t, p: parse_ebv(t),
    "ICAPE": lambda t, p: parse_icape(t),
    "Confidee GmbH": lambda t, p: parse_confidee(t, p),
    "POLYRACK": lambda t, p: parse_polyrack(t),
    "DUFLOT": lambda t, p: parse_scan(t, p),
}


# ----------------------------------------------------------------------------
# 5. Controles de coherence avant import
# ----------------------------------------------------------------------------

ECART_TOLERE_JOURS = 0          # parametre ED36 "Ecart tolere" (0 chez AW)


def controler(l: ARLine) -> None:
    for champ, libelle in (("num_cmde", "N. cmde fournisseur"),
                           ("id_poste", "Id poste cmde fournisseur"),
                           ("pu_ht", "Prix unitaire"),
                           ("qte_a_recevoir", "Solde a livrer"),
                           ("date_confirmee", "Date confirmee")):
        if not getattr(l, champ) and getattr(l, champ) != 0:
            l.flag("BLOQUANT", f"colonne obligatoire absente : {libelle}", 0.4)

    if l.pu_ht is not None and l.qte and l.total_annonce is not None:
        calc = round(l.pu_ht * l.qte, 2)
        if abs(calc - round(l.total_annonce, 2)) > 0.02:
            l.flag("BLOQUANT", f"PU x Qte = {calc} != total AR {l.total_annonce}", 0.4)

    if l.num_cmde and not re.fullmatch(r"A\d{9}", l.num_cmde):
        l.flag("AVERTISSEMENT",
               "n. de commande hors format AW (A + 9 chiffres) : rapprochement requis", 0.2)

    if l.date_confirmee and not l.date_souhaitee:
        l.flag("INFO", "AR sans date souhaitee : controle d'ecart de delai impossible", 0.0)

    if l.date_confirmee and l.date_souhaitee:
        ecart = (l.date_confirmee - l.date_souhaitee).days
        if ecart > ECART_TOLERE_JOURS:
            l.flag("AVERTISSEMENT", f"retard confirme de {ecart} jours", 0.1)
    if l.date_confirmee == CONFIRMED_DATE_TO_CONFIRM:
        l.flag("AVERTISSEMENT", "date de livraison a confirmer (31.12.9999)", 0.1)

    if l.devise and l.devise != "EUR":
        l.flag("INFO", f"devise {l.devise} : conversion / controle de change", 0.0)
    if l.pu_ht == 0:
        l.flag("INFO", "prix unitaire nul (gratuit / remplacement)", 0.0)


# ----------------------------------------------------------------------------
# 6. Traitement d'un fichier
# ----------------------------------------------------------------------------

def traiter(pdf_path: Path) -> list[ARLine]:
    with pdfplumber.open(pdf_path) as pdf:
        text = "\n".join((p.extract_text() or "") for p in pdf.pages)

    has_text = bool(text.strip())
    ocr_ref = pdf_path.with_suffix(".ocr.json")

    if not has_text:
        if ocr_ref.exists():
            lignes = parse_scan(text, pdf_path)
        else:
            l = ARLine(fichier=pdf_path.name, fournisseur=classify(text, pdf_path.name))
            if l.fournisseur == "INCONNU":
                l.fournisseur = ""
            l.flag("BLOQUANT", "PDF sans couche texte (scan) : depose son JSON OCR pour le traiter", 1.0)
            lignes = [l]
    else:
        fournisseur = classify(text, pdf_path.name)
        if fournisseur == "INCONNU":
            l = ARLine(fichier=pdf_path.name)
            l.flag("BLOQUANT", "fournisseur non reconnu : bascule extraction generique/LLM", 1.0)
            lignes = [l]
        else:
            lignes = PARSEURS[fournisseur](text, pdf_path)

    for l in lignes:
        l.fichier = pdf_path.name
        if not l.methode:
            l.methode = "TEXTE"
        controler(l)
    return lignes


def main(dossier: str, sortie: str) -> list[ARLine]:
    src = Path(dossier)
    fichiers = sorted([p for p in src.iterdir() if p.suffix.lower() == ".pdf"])
    toutes: list[ARLine] = []
    for f in fichiers:
        lignes = traiter(f)
        print(f"{f.name:45s} -> {lignes[0].fournisseur or 'INCONNU':25s} "
              f"{len(lignes)} poste(s), confiance {min(l.confiance for l in lignes):.2f}")
        toutes.extend(lignes)
    from .export_ed36 import exporter
    exporter(toutes, Path(sortie))
    return toutes


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/mnt/user-data/uploads",
         sys.argv[2] if len(sys.argv) > 2 else "/mnt/user-data/outputs/AR_import_ED36.xlsx")
