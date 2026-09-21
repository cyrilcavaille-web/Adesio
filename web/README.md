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

## Limites

- Les parseurs EBV / ICAPE / Confidee / Polyrack sont un portage direct
  du prototype Python et n'ont pas été validés sur de vrais AR de ces
  fournisseurs — à tester en priorité.
- Pas de moteur OCR embarqué : un AR scanné sans couche texte nécessite
  son JSON OCR en complément (voir `../sample_data/`).
- La séparation description/fabricant de Confidee (colonnes libres
  accolées) est approximée à partir des positions des mots extraites par
  pdf.js ; moins fiable que l'équivalent pdfplumber côté serveur.
