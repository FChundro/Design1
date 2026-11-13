/*
 * K-Cosmetics EU - live heartbeat authenticity seal (PROTOTYPE, not activated)
 *
 * Polls the verification server every 60 s, verifies the Ed25519 signature of
 * every response in the browser against the key pinned in the theme, and shows
 * one of three states: Verified Record / Verification Unavailable /
 * Verification Suspended. The seal artwork itself carries no data: a copied
 * image cannot produce a signed, fresh, nonce-bound server response.
 */
(function () {
  "use strict";

  var DEFAULT_INTERVAL_S = 60;
  var MAX_SKEW_S = 300;
  var SEAL_ID_RE = /^KC-[A-Z2-7]{4}(?:-[A-Z2-7]{4}){5}$/;

  var TEXT = {
    checking: "Checking record…",
    verified: "Verified Record",
    unavailable: "Verification Unavailable",
    suspended: "Verification Suspended",
    lastOk: "Last successful server verification",
    never: "No successful verification yet",
    msgVerified:
      "Our server has just confirmed a K-Cosmetics digital record for this code. This confirms the record only – it does not by itself prove that a physical product is authentic.",
    msgSuspended:
      "K-Cosmetics has suspended or withdrawn this record. Please do not rely on it and contact us if you bought this product.",
    msgUnavailable: {
      network:
        "We could not reach our verification server. Please try again shortly.",
      signature:
        "The response could not be authenticated, so it has been rejected.",
      not_found:
        "No K-Cosmetics record matches this code. Please check the code on your packaging.",
      stale: "The verification response was out of date and has been rejected.",
      origin: "This seal is only valid on the official K-Cosmetics website.",
      framed: "This seal cannot be verified inside another website.",
      invalid_code:
        "Please enter the code exactly as printed on your packaging.",
      rate_limited:
        "Too many checks from this connection. Please wait a minute.",
      no_code: "Enter the code printed on your packaging to check its record.",
    },
    sigUnchecked:
      "Your browser cannot check our digital signature; the result relies on the secure connection only.",
    ago: function (s) {
      if (s < 5) return "just now";
      if (s < 60) return s + " s ago";
      return Math.floor(s / 60) + " min ago";
    },
  };

  function b64urlToBytes(str) {
    var b64 = str.replace(/-/g, "+").replace(/_/g, "/");
    while (b64.length % 4) b64 += "=";
    var bin = atob(b64);
    var out = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }

  function randomNonce() {
    var bytes = new Uint8Array(18);
    crypto.getRandomValues(bytes);
    var s = "";
    for (var i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
    return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  var keyCache = {};
  function importKey(jwk) {
    if (!keyCache[jwk.kid]) {
      keyCache[jwk.kid] = crypto.subtle.importKey(
        "jwk",
        { kty: "OKP", crv: "Ed25519", x: jwk.x, ext: true },
        { name: "Ed25519" },
        false,
        ["verify"],
      );
    }
    return keyCache[jwk.kid];
  }

  function Seal(root) {
    this.root = root;
    var requested =
      parseInt(root.getAttribute("data-interval") || DEFAULT_INTERVAL_S, 10) ||
      DEFAULT_INTERVAL_S;
    // 60 s is the floor on the storefront; only the local demo page may go faster.
    this.interval = Math.max(
      root.hasAttribute("data-demo") ? 5 : DEFAULT_INTERVAL_S,
      requested,
    );
    this.endpoint = root.getAttribute("data-endpoint");
    this.officialOrigin = (
      root.getAttribute("data-official-origin") || ""
    ).replace(/\/$/, "");
    this.timeZone = root.getAttribute("data-timezone") || "Europe/Madrid";
    try {
      this.keys = JSON.parse(root.getAttribute("data-public-keys") || "[]");
    } catch (e) {
      this.keys = [];
    }
    this.sealId = (root.getAttribute("data-seal-id") || "")
      .trim()
      .toUpperCase();
    this.lastOk = null;
    this.timer = null;
    this.ticker = null;
    this.inFlight = null;
    this.lastState = null;
    this.generation = 0;
    var q = function (sel) {
      return root.querySelector(sel);
    };
    this.el = {
      status: q("[data-kc-status]"),
      time: q("[data-kc-time]"),
      ago: q("[data-kc-ago]"),
      message: q("[data-kc-message]"),
      details: q("[data-kc-details]"),
      test: q("[data-kc-test]"),
      note: q("[data-kc-note]"),
      live: q("[data-kc-live]"),
      link: q("[data-kc-link]"),
    };
  }

  Seal.prototype.start = function () {
    var self = this;
    if (window.top !== window.self) return this.render("unavailable", "framed");
    if (!this.officialOrigin || window.location.origin !== this.officialOrigin)
      return this.render("unavailable", "origin");
    if (!this.sealId) return this.render("idle", "no_code");
    if (!SEAL_ID_RE.test(this.sealId))
      return this.render("unavailable", "invalid_code");
    if (this.el.link) {
      var base = (this.el.link.getAttribute("href") || "").split("?")[0];
      if (base)
        this.el.link.setAttribute(
          "href",
          base + "?seal=" + encodeURIComponent(this.sealId),
        );
    }
    this.render("checking");
    this.check();
    this.ticker = window.setInterval(function () {
      self.renderAgo();
    }, 1000);
    if (!this.visibilityBound) {
      this.visibilityBound = true;
      document.addEventListener("visibilitychange", function () {
        if (
          document.visibilityState === "visible" &&
          self.lastOk &&
          Date.now() - self.lastOk.receivedAt > self.interval * 1000
        ) {
          self.check();
        }
      });
    }
  };

  Seal.prototype.restart = function (sealId) {
    window.clearTimeout(this.timer);
    window.clearInterval(this.ticker);
    this.generation += 1;
    this.inFlight = null;
    this.sealId = (sealId || "").trim().toUpperCase();
    this.root.setAttribute("data-seal-id", this.sealId);
    this.lastOk = null;
    this.lastState = null;
    this.start();
  };

  Seal.prototype.schedule = function () {
    var self = this;
    window.clearTimeout(this.timer);
    this.timer = window.setTimeout(function () {
      self.check();
    }, this.interval * 1000);
  };

  Seal.prototype.check = function () {
    var self = this;
    if (this.inFlight) return this.inFlight;
    var gen = this.generation;
    var nonce = randomNonce();
    var sep = this.endpoint.indexOf("?") === -1 ? "?" : "&";
    var url =
      this.endpoint +
      sep +
      "seal_id=" +
      encodeURIComponent(this.sealId) +
      "&nonce=" +
      nonce;
    var ctrl = "AbortController" in window ? new AbortController() : null;
    var abortTimer = ctrl
      ? window.setTimeout(function () {
          ctrl.abort();
        }, 10000)
      : null;

    this.inFlight = fetch(url, {
      method: "GET",
      credentials: "omit",
      cache: "no-store",
      referrerPolicy: "no-referrer",
      signal: ctrl ? ctrl.signal : undefined,
    })
      .then(function (res) {
        if (res.status === 429) throw { reason: "rate_limited" };
        if (!res.ok) throw { reason: "network" };
        return res.json();
      })
      .then(function (env) {
        return self.verify(env, nonce);
      })
      .then(function (result) {
        if (gen !== self.generation) return;
        var p = result.payload;
        if (p.status === "not_found") throw { reason: "not_found" };
        self.lastOk = {
          payload: p,
          receivedAt: Date.now(),
          sigChecked: result.sigChecked,
        };
        self.render(p.status === "verified_record" ? "verified" : "suspended");
      })
      .catch(function (err) {
        if (gen !== self.generation) return;
        self.render("unavailable", err && err.reason ? err.reason : "network");
      })
      .then(function () {
        if (abortTimer) window.clearTimeout(abortTimer);
        if (gen !== self.generation) return;
        self.inFlight = null;
        self.schedule();
      });
    return this.inFlight;
  };

  Seal.prototype.verify = function (env, nonce) {
    var self = this;
    if (
      !env ||
      env.alg !== "Ed25519" ||
      typeof env.payload !== "string" ||
      typeof env.sig !== "string"
    ) {
      return Promise.reject({ reason: "signature" });
    }
    var jwk = null;
    for (var i = 0; i < this.keys.length; i++)
      if (this.keys[i].kid === env.kid) jwk = this.keys[i];
    if (!jwk) return Promise.reject({ reason: "signature" });
    var data, sig;
    try {
      data = b64urlToBytes(env.payload);
      sig = b64urlToBytes(env.sig);
    } catch (e) {
      return Promise.reject({ reason: "signature" });
    }

    return Promise.resolve()
      .then(function () {
        return importKey(jwk);
      })
      .then(function (key) {
        return crypto.subtle.verify({ name: "Ed25519" }, key, sig, data);
      })
      .then(
        function (ok) {
          if (!ok) throw { reason: "signature" };
          return true;
        },
        function (err) {
          if (err && err.reason) throw err;
          return false; // Ed25519 not supported by this (old) browser
        },
      )
      .then(function (sigChecked) {
        var payload;
        try {
          payload = JSON.parse(new TextDecoder().decode(data));
        } catch (e) {
          throw { reason: "signature" };
        }
        if (payload.type !== "kc.seal.heartbeat" || payload.v !== 1)
          throw { reason: "signature" };
        if (payload.nonce !== nonce || payload.seal_id !== self.sealId)
          throw { reason: "signature" };
        if (payload.origin !== self.officialOrigin) throw { reason: "origin" };
        var issued = Date.parse(payload.issued_at);
        if (
          !isFinite(issued) ||
          Math.abs(Date.now() - issued) > MAX_SKEW_S * 1000
        )
          throw { reason: "stale" };
        return { payload: payload, sigChecked: sigChecked };
      });
  };

  Seal.prototype.formatTime = function (iso, compact) {
    var d = new Date(iso);
    var text;
    try {
      text = new Intl.DateTimeFormat("en-GB", {
        timeZone: this.timeZone,
        day: "numeric",
        month: compact ? "short" : "long",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
        timeZoneName: "short",
      }).format(d);
    } catch (e) {
      text = d.toISOString();
    }
    return compact ? text : text + " (" + this.timeZone + ")";
  };

  Seal.prototype.renderAgo = function () {
    if (!this.el.ago) return;
    if (!this.lastOk) {
      this.el.ago.textContent = "";
      return;
    }
    var s = Math.max(
      0,
      Math.round((Date.now() - this.lastOk.receivedAt) / 1000),
    );
    this.el.ago.textContent = "· " + TEXT.ago(s);
  };

  Seal.prototype.render = function (state, reason) {
    var root = this.root;
    root.setAttribute("data-state", state);
    root.setAttribute("data-reason", reason || "");
    var label =
      state === "verified"
        ? TEXT.verified
        : state === "suspended"
          ? TEXT.suspended
          : state === "checking"
            ? TEXT.checking
            : state === "idle"
              ? ""
              : TEXT.unavailable;
    if (this.el.status) this.el.status.textContent = label;

    var msg = "";
    if (state === "verified") msg = TEXT.msgVerified;
    else if (state === "suspended") msg = TEXT.msgSuspended;
    else if (state === "unavailable" || state === "idle")
      msg = TEXT.msgUnavailable[reason] || TEXT.msgUnavailable.network;
    if (this.el.message) this.el.message.textContent = msg;

    if (this.el.time) {
      // The small product-page badge uses a compact form; the verification
      // page shows the full date, time, zone abbreviation and IANA zone.
      var compact = root.classList.contains("kc-seal--badge");
      this.el.time.textContent = this.lastOk
        ? (compact ? "Last verified " : TEXT.lastOk + ": ") +
          this.formatTime(this.lastOk.payload.issued_at, compact)
        : state === "checking" || state === "idle"
          ? ""
          : TEXT.never;
    }
    this.renderAgo();

    var showP =
      !!this.lastOk && (state === "verified" || state === "suspended");
    var p = showP ? this.lastOk.payload : null;
    if (this.el.test) this.el.test.hidden = !(p && p.is_test);
    if (this.el.note) {
      this.el.note.hidden = !(p && this.lastOk.sigChecked === false);
      this.el.note.textContent = TEXT.sigUnchecked;
    }
    if (this.el.details) this.renderDetails(p ? p.record : null);

    if (this.el.live && state !== this.lastState && state !== "checking") {
      this.el.live.textContent = label + (msg ? ". " + msg : "");
    }
    this.lastState = state;
  };

  Seal.prototype.renderDetails = function (rec) {
    var box = this.el.details;
    while (box.firstChild) box.removeChild(box.firstChild);
    box.hidden = !rec;
    if (!rec) return;
    var rows = [
      ["Product", rec.product_title],
      ["SKU", rec.product_sku],
      ["Manufacturer batch", rec.manufacturer_batch],
      ["Best before", rec.best_before || "–"],
      [
        "Supplier approval",
        rec.supplier_approval === "approved"
          ? "Approved" +
            (rec.supplier_approved_on
              ? " (" + rec.supplier_approved_on + ")"
              : "")
          : "Not currently approved",
      ],
      [
        "Supporting evidence",
        rec.evidence_on_file +
          " document(s) held by K-Cosmetics (not published)",
      ],
      [
        "Warehouse (3PL) link",
        rec.logistics_integration === "synced"
          ? "Linked"
          : "Not yet integrated",
      ],
    ];
    var dl = document.createElement("dl");
    dl.className = "kc-seal__facts";
    rows.forEach(function (r) {
      var dt = document.createElement("dt");
      dt.textContent = r[0];
      var dd = document.createElement("dd");
      dd.textContent = String(r[1]); // textContent only: no HTML injection possible
      dl.appendChild(dt);
      dl.appendChild(dd);
    });
    box.appendChild(dl);
  };

  function initForm(form, seal) {
    var input = form.querySelector('input[name="seal"]');
    var fromUrl = (
      new URLSearchParams(window.location.search).get("seal") || ""
    )
      .trim()
      .toUpperCase();
    if (fromUrl && input) input.value = fromUrl;
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var code = (input.value || "").replace(/\s+/g, "").toUpperCase();
      input.value = code;
      var u = new URL(window.location.href);
      u.searchParams.set("seal", code);
      window.history.replaceState(null, "", u.toString());
      seal.restart(code);
    });
    return fromUrl;
  }

  function boot() {
    if (!window.crypto || !window.crypto.subtle || !window.fetch) return;
    var nodes = document.querySelectorAll("[data-kc-seal]");
    for (var i = 0; i < nodes.length; i++) {
      var seal = new Seal(nodes[i]);
      nodes[i].kcSeal = seal;
      var formId = nodes[i].getAttribute("data-form");
      var form = formId ? document.getElementById(formId) : null;
      if (form) {
        var code = initForm(form, seal);
        if (code) seal.sealId = code;
      }
      seal.start();
    }
  }

  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
