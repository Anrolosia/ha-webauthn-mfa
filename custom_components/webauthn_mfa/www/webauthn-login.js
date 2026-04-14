/**
 * WebAuthn MFA — injected script on the HA login page.
 *
 * Handles three cases:
 * 1. A pending token is stored in sessionStorage → intercept the HA form
 *    submit and inject the token so the flow completes natively (enabling
 *    the Service Worker to persist the session tokens correctly).
 * 2. A bypass flag is set → do nothing (user clicked "Back to login").
 * 3. Normal page load → intercept the /auth/login_flow POST to detect when
 *    the user selects the WebAuthn provider and redirect to authenticate.html.
 */
(function () {
  "use strict";

  const SCRIPT_TAG = "webauthn-login-injected";
  if (document.querySelector("[" + SCRIPT_TAG + "]")) return;
  document.documentElement.setAttribute(SCRIPT_TAG, "1");

  // ── Case 1: pending token → intercept the form submit ─────────────────
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

  // ── Case 3: intercept the WebAuthn flow creation → redirect ───────────
  const originalFetch = window.fetch;
  window.fetch = async function (...args) {
    const response = await originalFetch.apply(this, args);
    const reqUrl = typeof args[0] === "string" ? args[0] : args[0]?.url || "";

    if (reqUrl.includes("/auth/login_flow") && args[1]?.method === "POST") {
      try {
        const clone = response.clone();
        const data = await clone.json();
        if (data?.handler?.[0] === "webauthn" && data?.description_placeholders?.auth_url) {
          const authUrl = data.description_placeholders.auth_url;
          const returnUrl = window.location.href;
          // Pass the HA UI language so authenticate.html can match it.
          const haLang = (document.documentElement.lang || navigator.language || "en").split("-")[0];
          const sep = authUrl.includes("?") ? "&" : "?";
          setTimeout(() => {
            window.location.href = authUrl + sep + "lang=" + haLang + "&return_url=" + encodeURIComponent(returnUrl);
          }, 100);
        }
      } catch (e) {}
    }
    return response;
  };

  // ── Intercept the WebAuthn step submit ─────────────────────────────────
  function _interceptFlowSubmit(token, rememberMe) {

    const origFetch = window.fetch;
    let flowId = null;

    window.fetch = async function (...args) {
      const reqUrl = typeof args[0] === "string" ? args[0] : args[0]?.url || "";

      // Capture the flow_id when the flow is created.
      if (reqUrl.match(/\/auth\/login_flow$/) && args[1]?.method === "POST") {
        const response = await origFetch.apply(this, args);
        try {
          const clone = response.clone();
          const data = await clone.json();
          if (data?.handler?.[0] === "webauthn") {
            flowId = data.flow_id;
          }
        } catch (e) {}
        return response;
      }

      // Intercept the step submit and inject the token.
      if (flowId && reqUrl.includes(`/auth/login_flow/${flowId}`) && args[1]?.method === "POST") {
        window.fetch = origFetch; // Restore fetch.

        const urlParams = new URLSearchParams(window.location.search);
        const clientId = urlParams.get("client_id") || window.location.origin + "/";

        const newArgs = [args[0], {
          ...args[1],
          body: JSON.stringify({ client_id: clientId, webauthn_token: token }),
        }];

        return origFetch.apply(this, newArgs);
      }

      return origFetch.apply(this, args);
    };

    // Simulate a click on the "Passkey / Security Key" list item.
    let attempts = 0;
    const interval = setInterval(() => {
      attempts++;
      if (attempts > 50) { clearInterval(interval); return; }

      const btn = _findPasskeyButton();
      if (!btn) return;

      clearInterval(interval);
      btn.click();

      setTimeout(() => _clickSubmitButton(token, rememberMe), 300);
    }, 200);
  }

  function _clickSubmitButton(token, rememberMe) {
    let attempts = 0;
    const interval = setInterval(() => {
      attempts++;
      if (attempts > 30) { clearInterval(interval); return; }

      const webauthnForm = document.querySelector(
        "ha-authorize ha-auth-flow ha-auth-form-string"
      );
      if (!webauthnForm) return;

      const haButton = document.querySelector(
        "ha-authorize ha-auth-flow ha-button[variant='brand']"
      );
      if (!haButton) return;

      clearInterval(interval);

      // Fill the token field to pass HTML5 validation.
      const haInput = document.querySelector(
        "ha-authorize ha-auth-flow ha-input, " +
        "ha-authorize ha-auth-flow input"
      );
      if (haInput) {
        const input = haInput.tagName === "HA-INPUT"
          ? (haInput.querySelector("input") || haInput.shadowRoot?.querySelector("input") || haInput)
          : haInput;

        const nativeSetter = Object.getOwnPropertyDescriptor(
          window.HTMLInputElement.prototype, "value"
        )?.set;
        if (nativeSetter && input instanceof HTMLInputElement) {
          nativeSetter.call(input, token);
        } else {
          input.value = token;
        }
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));
      }

      setTimeout(() => {
        // Set the "Stay signed in" checkbox state.
        const checkbox = document.querySelector(
          "ha-authorize ha-auth-flow ha-checkbox, " +
          "ha-authorize ha-auth-flow input[type='checkbox']"
        );
        if (checkbox) {
          const isChecked = checkbox.checked;
          if (rememberMe && !isChecked) {
            checkbox.click();
          } else if (!rememberMe && isChecked) {
            checkbox.click();
          }
        }

        setTimeout(() => {
          haButton.click();
        }, 200);
      }, 200);
    }, 200);
  }

  function _findPasskeyButton() {
    function traverse(root) {
      if (!root) return null;
      for (const n of (root.querySelectorAll?.("*") || [])) {
        const text = n.textContent?.trim() || "";
        if ((n.tagName === "HA-LIST-ITEM" || n.hasAttribute?.("mwc-list-item")) &&
            text.includes("Passkey")) {
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
