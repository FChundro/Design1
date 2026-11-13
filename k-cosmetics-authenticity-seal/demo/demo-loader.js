/* Demo only. On Shopify the public key is pinned in the theme settings; here
   the local prototype server's key is fetched once, then the real widget
   script (theme/assets/kc-seal-heartbeat.js) is loaded unchanged. */
(function () {
  "use strict";
  fetch("/api/v1/keys", { cache: "no-store" })
    .then(function (r) {
      return r.json();
    })
    .then(function (jwks) {
      var nodes = document.querySelectorAll("[data-kc-seal]");
      for (var i = 0; i < nodes.length; i++) {
        nodes[i].setAttribute("data-public-keys", JSON.stringify(jwks.keys));
        nodes[i].setAttribute("data-official-origin", window.location.origin);
      }
    })
    .catch(function () {
      /* widget will show Verification Unavailable */
    })
    .then(function () {
      var s = document.createElement("script");
      s.src = "/theme-assets/kc-seal-heartbeat.js";
      document.body.appendChild(s);
    });
})();
