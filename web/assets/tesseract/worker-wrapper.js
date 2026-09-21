// Le CSP de l'artifact ne sert pas les fichiers binaires arbitraires (.gz
// refusé, et un .txt binaire est rejeté car son contenu est validé comme du
// texte). Le modèle de langue est donc publié encodé en base64, en pur texte
// ASCII (fra.traineddata.b64.txt). On intercepte la requête interne que
// tesseract.js émet en dur vers "<lang>.traineddata.gz", on récupère le
// base64 à la place et on le décode en binaire avant de rendre la main à
// tesseract.js — puis on charge le vrai worker.
self.fetch = (function (origFetch) {
  return function (url, opts) {
    if (typeof url === "string" && /\.traineddata\.gz$/.test(url)) {
      var b64Url = url.replace(/\.gz$/, ".b64.txt");
      return origFetch(b64Url, opts).then(function (r) {
        return r.text().then(function (b64) {
          var bin = atob(b64);
          var bytes = new Uint8Array(bin.length);
          for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
          return {
            ok: true, status: 200,
            arrayBuffer: function () { return Promise.resolve(bytes.buffer); }
          };
        });
      });
    }
    return origFetch(url, opts);
  };
})(self.fetch);
importScripts("worker.min.js");
