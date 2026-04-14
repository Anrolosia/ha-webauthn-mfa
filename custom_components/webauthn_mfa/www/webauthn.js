/**
 * WebAuthn MFA — post-login script.
 * Injects a passkey management panel into the HA profile page.
 */
(function () {
  "use strict";

  // ── Base64url helpers ────────────────────────────────────────────────────
  function bufferToBase64url(buffer) {
    const bytes = new Uint8Array(buffer);
    let str = "";
    for (const b of bytes) str += String.fromCharCode(b);
    return btoa(str).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
  }

  function base64urlToBuffer(b64) {
    b64 = b64.replace(/-/g, "+").replace(/_/g, "/");
    while (b64.length % 4) b64 += "=";
    const bin = atob(b64);
    const buf = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
    return buf.buffer;
  }

  // ── Passkey registration ─────────────────────────────────────────────────
  async function registerPasskey(name) {
    // 1. Fetch registration challenge.
    const chalRes = await fetch("/api/webauthn_mfa/register/challenge", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({}),
    });

    if (!chalRes.ok) {
      const err = await chalRes.json();
      throw new Error(err.message || err.error || "Server error");
    }

    const options = await chalRes.json();

    // Convert base64url fields to ArrayBuffer.
    options.challenge = base64urlToBuffer(options.challenge);
    options.user.id = base64urlToBuffer(options.user.id);
    if (options.excludeCredentials) {
      options.excludeCredentials = options.excludeCredentials.map(c => ({
        ...c, id: base64urlToBuffer(c.id),
      }));
    }

    // 2. Create the passkey via the browser.
    const credential = await navigator.credentials.create({ publicKey: options });

    // 3. Verify and save.
    const regRes = await fetch("/api/webauthn_mfa/register/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({
        name: name || "My Passkey",
        response: {
          id: credential.id,
          rawId: bufferToBase64url(credential.rawId),
          type: credential.type,
          response: {
            attestationObject: bufferToBase64url(credential.response.attestationObject),
            clientDataJSON: bufferToBase64url(credential.response.clientDataJSON),
          },
        },
      }),
    });

    if (!regRes.ok) {
      const err = await regRes.json();
      throw new Error(err.message || err.error || "Registration error");
    }

    return await regRes.json();
  }

  // ── Profile page injection ───────────────────────────────────────────────
  function injectProfilePanel() {
    const haApp = document.querySelector("home-assistant");
    if (!haApp) return;

    const main = haApp.shadowRoot?.querySelector("home-assistant-main");
    if (!main) return;

    const partial = main.shadowRoot?.querySelector("ha-panel-profile");
    if (!partial) return;

    const profile = partial.shadowRoot?.querySelector("ha-profile-section, .profile-section, ha-card");
    if (!profile) return;

    if (document.getElementById("webauthn-mfa-panel")) return;

    const panel = createPanel();
    profile.parentElement?.appendChild(panel);
  }

  function createPanel() {
    const div = document.createElement("div");
    div.id = "webauthn-mfa-panel";
    div.style.cssText = `
      margin: 16px;
      background: var(--card-background-color, #1f2937);
      border-radius: 12px;
      padding: 20px;
      border: 1px solid var(--divider-color, #374151);
    `;

    div.innerHTML = `
      <h3 style="margin:0 0 8px;font-size:1rem;font-weight:600;color:var(--primary-text-color)">
        🔑 Passkeys (WebAuthn)
      </h3>
      <p style="margin:0 0 16px;font-size:0.875rem;color:var(--secondary-text-color)">
        Sign in without a password using your fingerprint, Face ID, or a security key.
      </p>
      <div id="webauthn-status" style="margin-bottom:12px;font-size:0.875rem;"></div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
        <input
          id="webauthn-name"
          type="text"
          placeholder="Passkey name (e.g. My iPhone)"
          style="flex:1;min-width:200px;padding:8px 12px;border-radius:6px;border:1px solid var(--divider-color,#374151);background:var(--input-fill-color,#111827);color:var(--primary-text-color);font-size:0.875rem;"
        />
        <button id="webauthn-register-btn" style="
          padding:8px 16px;border-radius:6px;border:none;
          background:#3b82f6;color:white;font-weight:600;cursor:pointer;
          font-size:0.875rem;white-space:nowrap;
        ">
          + Add passkey
        </button>
      </div>
    `;

    const statusEl = div.querySelector("#webauthn-status");
    const btn = div.querySelector("#webauthn-register-btn");
    const nameInput = div.querySelector("#webauthn-name");

    btn.addEventListener("click", async () => {
      if (!window.PublicKeyCredential) {
        statusEl.style.color = "#ef4444";
        statusEl.textContent = "❌ Your browser does not support passkeys.";
        return;
      }

      const name = nameInput.value.trim() || "My Passkey";
      btn.disabled = true;
      btn.textContent = "Registering...";
      statusEl.style.color = "#93c5fd";
      statusEl.textContent = "⏳ Waiting for your passkey...";

      try {
        await registerPasskey(name);
        statusEl.style.color = "#86efac";
        statusEl.textContent = `✓ Passkey "${name}" registered successfully!`;
        nameInput.value = "";
      } catch (err) {
        if (err.name === "NotAllowedError") {
          statusEl.style.color = "#fca5a5";
          statusEl.textContent = "❌ Registration cancelled.";
        } else {
          statusEl.style.color = "#fca5a5";
          statusEl.textContent = `❌ Error: ${err.message}`;
        }
      } finally {
        btn.disabled = false;
        btn.textContent = "+ Add passkey";
      }
    });

    return div;
  }

  // ── Watch for navigation to the profile page ─────────────────────────────
  function watchForProfile() {
    let lastPath = "";
    const check = () => {
      const path = window.location.pathname;
      if (path !== lastPath) {
        lastPath = path;
        if (path.includes("/profile")) {
          setTimeout(injectProfilePanel, 500);
          setTimeout(injectProfilePanel, 1500);
          setTimeout(injectProfilePanel, 3000);
        }
      }
    };

    const observer = new MutationObserver(check);
    observer.observe(document.body, { childList: true, subtree: true });
    check();
  }

  watchForProfile();
})();
