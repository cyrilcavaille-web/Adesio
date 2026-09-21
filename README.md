# ar2ed36 — AR fournisseurs → format d'import Excalibur ED36

Mini application web qui convertit les accusés de réception (AR) de
commande fournisseurs (PDF) vers le fichier d'import Excalibur **ED36**
(*Paramètres import AR fournisseur*).

Prototype ADESIO — démo ANALOG WAY.

## Pipeline

1. **Ingestion** — lecture du PDF, détection de la couche texte.
2. **Classification** — identification du fournisseur par empreinte texte
   (EBV/Avnet, ICAPE, Confidee, Polyrack, Duflot…).
3. **Extraction** — parseur dédié par fournisseur (ancres + regex, découpage
   par abscisse des en-têtes quand deux colonnes de texte libre se touchent).
4. **Normalisation** — dates multi-formats, conventions numériques FR/EN,
   prix ramené à l'unité.
5. **Contrôles** — colonnes obligatoires, cohérence PU × Qté = total AR,
   écart date confirmée/souhaitée, format du n° de commande, devise.
   Chaque ligne reçoit un score de confiance.
6. **Export** — fichier Excel ED36 (colonnes A→S), avec deux feuilles
   supplémentaires : journal de contrôle et paramétrage ED36 appliqué.

Les AR scannés sans couche texte (ex. Duflot, bon de commande retourné
signé) nécessitent un OCR en amont (Tesseract / Azure Document
Intelligence). En attendant l'intégration du moteur OCR, on peut déposer un
JSON `<nom_du_pdf>.ocr.json` à côté du PDF (voir `sample_data/` pour
l'exemple Duflot).

## Installation

```bash
pip install -r requirements.txt
```

## Lancer la mini app

```bash
python3 app.py
```

Puis ouvrir http://localhost:5000 :

- déposer un ou plusieurs PDF d'AR fournisseurs (+ un JSON OCR optionnel
  pour un AR scanné) et cliquer sur **Convertir en ED36** ;
- ou cliquer sur **Lancer la démo** pour rejouer le pipeline sur l'exemple
  Duflot embarqué (`sample_data/`), sans avoir de PDF sous la main.

Le résultat affiche, par poste extrait : fournisseur, méthode
(TEXTE/OCR), statut (OK / à contrôler / bloquant), score de confiance et
anomalies détectées, avec un bouton de téléchargement du fichier
`AR_import_ED36.xlsx`.

## Utilisation en ligne de commande

Le pipeline reste utilisable directement sans l'interface web :

```bash
python3 -m ar2ed36.ar_extract <dossier_pdf_entrée> <fichier_xlsx_sortie>
```

## Limites connues du prototype

- Un seul poste manquant d'Id poste client (ICAPE, Polyrack) bloque
  l'import ED36 : la V1 industrialisée nécessite un rapprochement
  automatique contre la commande Excalibur (n° cmde + référence + quantité).
- Le moteur OCR n'est pas encore intégré : les AR scannés doivent être
  fournis avec un JSON `<nom>.ocr.json` déjà transcrit.
- Chaque nouveau fournisseur non templaté nécessite un parseur dédié (ou,
  à terme, un fallback LLM à schéma JSON).
