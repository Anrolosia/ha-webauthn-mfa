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

  // ── i18n (injected by the integration as window.__WEBAUTHN_I18N__) ─────
  const I18N = window.__WEBAUTHN_I18N__ || {};

  function _lang() {
    const l = (document.documentElement.lang || navigator.language || "en")
      .split("-")[0];
    return I18N[l] ? l : "en";
  }

  function _t(key) {
    return (I18N[_lang()] || I18N.en || {})[key] || "";
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
      alignItems: "center",
      justifyContent: "center",
      boxSizing: "border-box",
      background: "var(--primary-background-color, #fafafa)",
      color: "var(--primary-text-color, #212121)",
      font: "400 14px/1.5 Roboto, system-ui, sans-serif",
      padding: "16px",
    });
    overlay.innerHTML =
      '<div class="wa-card"><div class="wa-content">' +
      '<ha-spinner class="wa-spinner"></ha-spinner>' +
      '<div class="wa-text" role="status" aria-live="polite"></div>' +
      "</div></div>" +
      "<style>" +
      "#webauthn-overlay .wa-card{box-sizing:border-box;width:100%;max-width:400px;" +
      "padding:16px;border:1px solid var(--divider-color,#e0e0e0);" +
      "border-radius:var(--ha-border-radius-lg,12px);" +
      "background:var(--card-background-color,#fff);" +
      "box-shadow:var(--ha-card-box-shadow,none)}" +
      "#webauthn-overlay .wa-content{display:flex;flex-direction:column;" +
      "align-items:center;gap:16px;width:100%;max-width:336px;margin:0 auto;" +
      "padding:24px 0;text-align:center}" +
      "#webauthn-overlay .wa-spinner{width:40px;height:40px}" +
      "#webauthn-overlay .wa-text{max-width:300px;color:var(--secondary-text-color,#727272)}" +
      "#webauthn-overlay .wa-error{width:100%;text-align:start}" +
      "#webauthn-overlay .wa-actions{display:flex;justify-content:center;width:100%}" +
      "</style>";
    overlay.querySelector(".wa-text").textContent = text;
    (document.body || document.documentElement).appendChild(overlay);
  }

  function _overlayError(text) {
    const overlay = document.getElementById("webauthn-overlay");
    if (!overlay) return;
    const content = overlay.querySelector(".wa-content");
    if (!content) return;
    content.replaceChildren();

    const alert = document.createElement("ha-alert");
    alert.className = "wa-error";
    alert.setAttribute("alert-type", "error");
    alert.textContent = text;

    const actions = document.createElement("div");
    actions.className = "wa-actions";
    const button = document.createElement("ha-button");
    button.setAttribute("appearance", "filled");
    button.setAttribute("variant", "neutral");
    button.textContent = _t("back");
    button.addEventListener("click", () => {
      sessionStorage.setItem("webauthn_bypass", "1");
      window.location.reload();
    });
    actions.appendChild(button);
    content.append(alert, actions);
    button.focus();
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

  // Sentinel returned by the provider-selection wait when Home Assistant went
  // straight to the token form (no provider picker to click).
  const FORM_READY = Symbol("webauthn-form-ready");

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

    // Tracks which wait timed out, so a "Login replay failed" report says where.
    let step = "provider picker";
    try {
      // 1. Select the "Passkey / Security Key" provider. When WebAuthn is the
      //    only auth provider configured, HA skips the picker entirely and
      //    renders the token form right away, so there is no button to click.
      //    Wait for whichever of the two shows up first.
      const providerStep = await _waitFor(
        () => _findPasskeyButton() || (_findTokenInput() ? FORM_READY : null),
        10000
      );
      if (providerStep !== FORM_READY) {
        providerStep.click();
      }

      // 2. Wait for the token input + submit button to render. Both can sit
      //    inside nested shadow DOM, so use a deep search (see _deepFind).
      step = "token form";
      const submitBtn = await _waitFor(() => {
        const input = _findTokenInput();
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
      console.error(
        `[WebAuthn MFA] Login replay failed at step "${step}":`,
        {
          passkeyButton: !!_findPasskeyButton(),
          tokenInput: !!_findTokenInput(),
          flowCaptured: !!flowId,
        },
        e
      );
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

  function _findTokenInput() {
    return _deepFind(
      (el) => el.tagName === "INPUT" && el.name === "webauthn_token"
    );
  }

  function _fillTokenField(token) {
    // The real <input> lives inside ha-auth-form-string's shadow DOM
    // (note `part="input"`), so a flat selector cannot reach it.
    const input =
      _findTokenInput() ||
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
