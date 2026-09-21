// Le CSP de l'artifact ne sert pas les fichiers .gz : les données de langue
// sont publiées sous fra.traineddata.gz.txt (mêmes octets). On intercepte la
// requête interne de tesseract.js vers le nom qu'il attend en dur et on la
// redirige vers ce chemin, avant de charger le vrai worker.
self.fetch = (function (origFetch) {
  return function (url, opts) {
    if (typeof url === "string" && /\.traineddata\.gz$/.test(url)) url += ".txt";
    return origFetch(url, opts);
  };
})(self.fetch);
importScripts("worker.min.js");
