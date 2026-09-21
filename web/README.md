# ar2ed36 — version navigateur

Variante 100% client de l'outil de conversion AR fournisseurs → Excalibur
ED36 : une seule page HTML, aucun serveur. Le PDF est lu et le fichier
Excel généré directement dans le navigateur (pdf.js + ExcelJS), sur la
charte du [design system Adesio](assets/adesio.css).

## Utilisation

Ouvrir `index.html` dans un navigateur (double-clic, ou servi par
n'importe quel serveur statique) :

- déposer un ou plusieurs PDF d'AR fournisseurs (+ un JSON OCR optionnel
  sur la ligne d'un AR scanné sans couche texte, ex. Duflot) ;
- cliquer sur **Convertir en ED36** ;
- télécharger `AR_import_ED36.xlsx` (mêmes 3 feuilles que la version
  Flask : Import AR, Contrôles, Paramétrage ED36).

Un exemple réel (Duflot) est préchargé à l'ouverture pour tester le
téléchargement sans avoir de PDF sous la main.

Le téléchargement du fichier généré utilise la capacité `downloads` du
runtime Artifact lorsque la page est ouverte comme artifact Claude ; en
dehors de ce contexte (fichier ouvert directement), `window.claude` est
absent et le bouton de téléchargement le signale.

## Rapport avec la version Flask (`../app.py`)

Le pipeline (`ar_extract.py` / `export_ed36.py`) a été porté ligne à
ligne en JavaScript dans `index.html` : mêmes parseurs, mêmes règles de
normalisation et de contrôle, même structure de fichier Excel. Les deux
versions doivent être maintenues en parallèle si le pipeline évolue.
Vérifié en conditions réelles sur les 5 AR de test (EBV, ICAPE,
Confidee, Polyrack, Duflot) : résultats identiques à la version Python.

## OCR automatique (AR scannés sans couche texte)

Pour le cas Duflot (le fournisseur retourne signé le propre bon de
commande Analog Way, scanné) : dès qu'un PDF n'a pas de couche texte,
l'app rend la page en image (pdf.js) et lance un OCR **entièrement dans
le navigateur** avec [Tesseract.js](assets/tesseract/) (modèle français
embarqué dans `assets/tesseract/`, aucun appel réseau). Le texte
reconnu est reconnu comme le gabarit "COMMANDE N°..." d'Analog Way et
parsé par un jeu de regex dédié (ancré sur `UNITE` + date + prix + total,
plus robuste aux imperfections OCR que le numéro de poste ou le libellé).
Compte 15-30 s par page. Testé de bout en bout sur le vrai
`AR_PO_Duflot.pdf` (rendu réel + OCR réel + parsing), résultat identique
au JSON de référence.

Si le scan ne correspond pas à ce gabarit (mise en page différente),
l'import reste bloqué avec l'option historique : déposer un JSON
`<nom_du_pdf>.ocr.json` sur la ligne du fichier (voir `../sample_data/`).

## Limites

- Les parseurs EBV / ICAPE / Confidee / Polyrack sont un portage direct
  du prototype Python, désormais **vérifiés sur les AR réels des 5
  fournisseurs de test** — au-delà de cet échantillon, un nouveau
  gabarit peut nécessiter un ajustement.
- L'OCR automatique ne reconnaît que le gabarit "commande Analog Way
  retournée signée" ; un AR scanné généré par le fournisseur lui-même
  nécessite encore un JSON OCR fourni à la main.
- La séparation description/fabricant de Confidee (colonnes libres
  accolées) est approximée à partir des positions des mots extraites par
  pdf.js ; moins fiable que l'équivalent pdfplumber côté serveur.
