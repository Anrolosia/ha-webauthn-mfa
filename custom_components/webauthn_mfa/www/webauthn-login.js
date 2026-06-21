/**
 * WebAuthn MFA — injected script on the HA login page.
 *
 * Handles three cases:
 * 1. A pending token is stored in sessionStorage → replay the native HA login
 *    form (so the Service Worker persists the session tokens correctly) while a
 *    full-screen "Signing in…" overlay hides the replay from the user.
 * 2. A bypass flag is set → do nothing (user clicked "Back to login").
 * 3. Normal page load → intercept the /auth/login_flow POST to detect when the
 *    user selects the WebAuthn provider and redirect to authenticate.html.
 *
 * Timing note: element lookups go through _waitFor() (MutationObserver + rAF)
 * instead of fixed setInterval/setTimeout polling, so each step fires as soon
 * as the element is ready — no artificial delays — and it still pierces the
 * nested shadow DOM the HA login form lives in.
 */
(function () {
  "use strict";

  const SCRIPT_TAG = "webauthn-login-injected";
  if (document.querySelector("[" + SCRIPT_TAG + "]")) return;
  document.documentElement.setAttribute(SCRIPT_TAG, "1");

  // ── i18n (overlay strings only) ───────────────────────────────────────
  const I18N = {
    en: {
      signing_in: "Signing in…",
      timeout: "Sign-in timed out. Please try again.",
      back: "Back to login",
    },
    fr: {
      signing_in: "Connexion en cours…",
      timeout: "Délai de connexion dépassé. Veuillez réessayer.",
      back: "Retour à la connexion",
    },
  };

  function _lang() {
    const l = (document.documentElement.lang || navigator.language || "en")
      .split("-")[0];
    return I18N[l] ? l : "en";
  }

  function _t(key) {
    return (I18N[_lang()] || I18N.en)[key];
  }

  // ── Full-screen overlay ───────────────────────────────────────────────
  function _showOverlay(text) {
    let overlay = document.getElementById("webauthn-overlay");
    if (overlay) {
      const existing = overlay.querySelector(".wa-text");
      if (existing) existing.textContent = text;
      return;
    }
    overlay = document.createElement("div");
    overlay.id = "webauthn-overlay";
    Object.assign(overlay.style, {
      position: "fixed",
      inset: "0",
      zIndex: "2147483647",
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      gap: "20px",
      background: "var(--primary-background-color, #111418)",
      color: "var(--primary-text-color, #e1e1e1)",
      font: "500 16px/1.4 Roboto, system-ui, sans-serif",
      textAlign: "center",
      padding: "24px",
    });
    overlay.innerHTML =
      '<div class="wa-spinner"></div>' +
      '<div class="wa-text"></div>' +
      "<style>" +
      "#webauthn-overlay .wa-spinner{width:44px;height:44px;border-radius:50%;" +
      "border:4px solid var(--divider-color,#3a3f44);" +
      "border-top-color:var(--primary-color,#03a9f4);" +
      "animation:wa-spin .8s linear infinite}" +
      "#webauthn-overlay .wa-text{opacity:.85;max-width:280px}" +
      "#webauthn-overlay button{padding:8px 18px;cursor:pointer;border-radius:6px;" +
      "border:1px solid var(--divider-color,#3a3f44);background:transparent;" +
      "color:inherit;font:inherit}" +
      "@keyframes wa-spin{to{transform:rotate(360deg)}}" +
      "</style>";
    overlay.querySelector(".wa-text").textContent = text;
    (document.body || document.documentElement).appendChild(overlay);
  }

  function _overlayError(text) {
    const overlay = document.getElementById("webauthn-overlay");
    if (!overlay) return;
    overlay.innerHTML =
      '<div class="wa-text" style="opacity:.85;max-width:280px">' + text + "</div>" +
      '<button type="button">' + _t("back") + "</button>";
    overlay.querySelector("button").addEventListener("click", () => {
      sessionStorage.setItem("webauthn_bypass", "1");
      window.location.reload();
    });
  }

  // ── Wait helper: MutationObserver + rAF, pierces shadow DOM ────────────
  function _waitFor(findFn, timeout = 8000) {
    return new Promise((resolve, reject) => {
      const immediate = findFn();
      if (immediate) return resolve(immediate);

      let settled = false;
      let raf = 0;
      let timer = 0;
      const observer = new MutationObserver(check);

      function cleanup() {
        observer.disconnect();
        if (raf) cancelAnimationFrame(raf);
        if (timer) clearTimeout(timer);
      }
      function done(value, err) {
        if (settled) return;
        settled = true;
        cleanup();
        err ? reject(err) : resolve(value);
      }
      function check() {
        const el = findFn();
        if (el) done(el);
      }

      // Light-DOM reactivity: catches element upgrades and newly added nodes.
      observer.observe(document.documentElement, {
        childList: true,
        subtree: true,
      });

      // rAF fallback: a MutationObserver can't see *inside* nested shadow
      // roots, so we also re-check every animation frame until found. Cheap
      // and short-lived (resolves on the first frame the element exists).
      (function tick() {
        if (settled) return;
        const el = findFn();
        if (el) return done(el);
        raf = requestAnimationFrame(tick);
      })();

      timer = setTimeout(() => done(null, new Error("timeout")), timeout);
    });
  }

  function _delay(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  // ── Case 1: pending token → replay the native form (behind overlay) ───
  const pendingRaw = sessionStorage.getItem("webauthn_pending_token");
  if (pendingRaw) {
    sessionStorage.removeItem("webauthn_pending_token");
    try {
      const pending = JSON.parse(pendingRaw);
      _interceptFlowSubmit(pending.token, pending.remember_me !== false);
    } catch (e) {
      console.error("[WebAuthn MFA] Failed to parse pending token:", e);
    }
    return;
  }

  // ── Case 2: bypass flag set ────────────────────────────────────────────
  if (sessionStorage.getItem("webauthn_bypass") === "1") {
    sessionStorage.removeItem("webauthn_bypass");
    return;
  }

  // ── Case 3: intercept WebAuthn flow creation → redirect to ceremony ────
  const originalFetch = window.fetch;
  window.fetch = async function (...args) {
    const response = await originalFetch.apply(this, args);
    const reqUrl = typeof args[0] === "string" ? args[0] : args[0]?.url || "";

    if (reqUrl.includes("/auth/login_flow") && args[1]?.method === "POST") {
      try {
        const data = await response.clone().json();
        if (
          data?.handler?.[0] === "webauthn" &&
          data?.description_placeholders?.auth_url
        ) {
          const authUrl = data.description_placeholders.auth_url;
          const returnUrl = window.location.href;
          // Pass the HA UI language so authenticate.html can match it.
          const haLang = (
            document.documentElement.lang ||
            navigator.language ||
            "en"
          ).split("-")[0];
          const sep = authUrl.includes("?") ? "&" : "?";
          // Cover the gap before authenticate.html loads.
          _showOverlay(_t("signing_in"));
          setTimeout(() => {
            window.location.href =
              authUrl +
              sep +
              "lang=" +
              haLang +
              "&return_url=" +
              encodeURIComponent(returnUrl);
          }, 100);
        }
      } catch (e) {}
    }
    return response;
  };

  // ── Replay the WebAuthn step submit (Case 1) ──────────────────────────
  async function _interceptFlowSubmit(token, rememberMe) {
    _showOverlay(_t("signing_in"));

    const origFetch = window.fetch;
    let flowId = null;

    // Inject the verified token straight into the step-submit request body,
    // so the token never needs to be typed (or even shown) in the form.
    window.fetch = async function (...args) {
      const reqUrl = typeof args[0] === "string" ? args[0] : args[0]?.url || "";

      // Capture the flow_id when the flow is created.
      if (reqUrl.match(/\/auth\/login_flow$/) && args[1]?.method === "POST") {
        const response = await origFetch.apply(this, args);
        try {
          const data = await response.clone().json();
          if (data?.handler?.[0] === "webauthn") {
            flowId = data.flow_id;
          }
        } catch (e) {}
        return response;
      }

      // Intercept the step submit and inject the token.
      if (
        flowId &&
        reqUrl.includes(`/auth/login_flow/${flowId}`) &&
        args[1]?.method === "POST"
      ) {
        window.fetch = origFetch; // Restore fetch.
        const urlParams = new URLSearchParams(window.location.search);
        const clientId =
          urlParams.get("client_id") || window.location.origin + "/";
        const resp = await origFetch.apply(this, [
          args[0],
          {
            ...args[1],
            body: JSON.stringify({
              client_id: clientId,
              webauthn_token: token,
            }),
          },
        ]);
        // Safety net: if the step did not complete (form re-rendered with an
        // error, or aborted), surface it instead of spinning forever.
        try {
          const result = await resp.clone().json();
          if (result?.type === "form" || result?.type === "abort") {
            console.error(
              "[WebAuthn MFA] Login step did not complete:",
              result
            );
            _overlayError(_t("timeout"));
          }
        } catch (e) {}
        return resp;
      }

      return origFetch.apply(this, args);
    };

    try {
      // 1. Select the "Passkey / Security Key" provider.
      const passkeyBtn = await _waitFor(() => _findPasskeyButton(), 10000);
      passkeyBtn.click();

      // 2. Wait for the token input + submit button to render. Both can sit
      //    inside nested shadow DOM, so use a deep search (see _deepFind).
      const submitBtn = await _waitFor(() => {
        const input = _deepFind(
          (el) => el.tagName === "INPUT" && el.name === "webauthn_token"
        );
        const btn = _deepFind(
          (el) =>
            (el.tagName === "HA-BUTTON" ||
              el.tagName === "MWC-BUTTON" ||
              el.tagName === "BUTTON") &&
            (el.getAttribute("variant") === "brand" ||
              /sign in|log in|next|connexion|se connecter/i.test(
                el.textContent || ""
              ))
        );
        return input && btn ? btn : null;
      }, 8000);

      // 3. Fill the token field (to satisfy HTML5 validation) + remember-me.
      //    Give Lit time to register each change before the next step:
      //    clicking submit too fast leaves the form "invalid" and the submit
      //    POST never fires (which looks like an endless spinner).
      _fillTokenField(token);
      await _delay(200);
      _setRememberMe(rememberMe);
      await _delay(200);
      submitBtn.click();
    } catch (e) {
      console.error("[WebAuthn MFA] Login replay failed:", e);
      window.fetch = origFetch; // Restore fetch on failure.
      _overlayError(_t("timeout"));
    }
  }

  // ── DOM helpers ────────────────────────────────────────────────────────
  // Pierce nested shadow roots to find the first element matching predicate.
  function _deepFind(predicate, root) {
    const queue = [root || document];
    while (queue.length) {
      const node = queue.shift();
      const els = node.querySelectorAll ? node.querySelectorAll("*") : [];
      for (const el of els) {
        if (predicate(el)) return el;
        if (el.shadowRoot) queue.push(el.shadowRoot);
      }
    }
    return null;
  }

  function _fillTokenField(token) {
    // The real <input> lives inside ha-auth-form-string's shadow DOM
    // (note `part="input"`), so a flat selector cannot reach it.
    const input =
      _deepFind(
        (el) => el.tagName === "INPUT" && el.name === "webauthn_token"
      ) ||
      _deepFind(
        (el) =>
          el.tagName === "INPUT" &&
          (el.type === "password" || el.type === "text")
      );
    if (!input) {
      console.warn("[WebAuthn MFA] token input not found");
      return false;
    }

    const nativeSetter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      "value"
    )?.set;
    if (nativeSetter) {
      nativeSetter.call(input, token);
    } else {
      input.value = token;
    }
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));

    if (input.value !== token) {
      console.warn("[WebAuthn MFA] token value did not stick on the input");
    }
    return true;
  }

  function _setRememberMe(rememberMe) {
    const checkbox = _deepFind(
      (el) =>
        el.tagName === "HA-CHECKBOX" ||
        (el.tagName === "INPUT" && el.type === "checkbox")
    );
    if (!checkbox) return;
    if (Boolean(rememberMe) !== Boolean(checkbox.checked)) {
      checkbox.click();
    }
  }

  function _findPasskeyButton() {
    function traverse(root) {
      if (!root) return null;
      for (const n of root.querySelectorAll?.("*") || []) {
        const text = n.textContent?.trim() || "";
        if (
          (n.tagName === "HA-LIST-ITEM" || n.hasAttribute?.("mwc-list-item")) &&
          text.includes("Passkey")
        ) {
          return n;
        }
        if (n.shadowRoot) {
          const found = traverse(n.shadowRoot);
          if (found) return found;
        }
      }
      return null;
    }
    return traverse(document);
  }
})();