/**
 * WebAuthn MFA — Sidebar panel for passkey management.
 */
class WebAuthnPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._credentials = [];
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._rendered) {
      this._rendered = true;
      this.render();
      this.loadCredentials();
    }
  }

  getAuthHeaders() {
    try {
      const token = this._hass?.auth?.data?.access_token;
      if (token) return { "Authorization": `Bearer ${token}` };
      const tokens = JSON.parse(localStorage.getItem("hassTokens") || "{}");
      return tokens?.access_token ? { "Authorization": `Bearer ${tokens.access_token}` } : {};
    } catch { return {}; }
  }

  bufferToBase64url(buffer) {
    const bytes = new Uint8Array(buffer);
    let str = "";
    for (const b of bytes) str += String.fromCharCode(b);
    return btoa(str).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
  }

  base64urlToBuffer(b64) {
    b64 = b64.replace(/-/g, "+").replace(/_/g, "/");
    while (b64.length % 4) b64 += "=";
    const bin = atob(b64);
    const buf = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
    return buf.buffer;
  }

  async loadCredentials() {
    try {
      const res = await fetch("/api/webauthn_mfa/list", {
        headers: this.getAuthHeaders(),
        credentials: "same-origin",
      });
      if (res.ok) {
        this._credentials = await res.json();
        this.renderCredentials();
      }
    } catch (e) {
      console.error("[WebAuthn] loadCredentials error:", e);
    }
  }

  renderCredentials() {
    const container = this.shadowRoot.querySelector("#credentials-list");
    if (!container) return;

    if (this._credentials.length === 0) {
      container.innerHTML = `<p class="empty">No passkeys registered yet.</p>`;
      return;
    }

    container.innerHTML = this._credentials.map(c => `
      <div class="credential-row">
        <div class="credential-info">
          <span class="credential-name">🔑 ${c.name}</span>
          <span class="credential-id">${c.credential_id}</span>
        </div>
        <button class="btn-delete" data-id="${c.credential_id}">Delete</button>
      </div>
    `).join("");

    container.querySelectorAll(".btn-delete").forEach(btn => {
      btn.addEventListener("click", () => this.deleteCredential(btn.dataset.id));
    });
  }

  async deleteCredential(credentialId) {
    if (!confirm("Delete this passkey?")) return;
    try {
      const res = await fetch(`/api/webauthn_mfa/delete/${credentialId}`, {
        method: "DELETE",
        headers: this.getAuthHeaders(),
        credentials: "same-origin",
      });
      if (res.ok) {
        this._credentials = this._credentials.filter(c => c.credential_id !== credentialId);
        this.renderCredentials();
        this.setStatus("✓ Passkey deleted.", "success");
      }
    } catch (e) {
      this.setStatus("❌ Failed to delete passkey.", "error");
    }
  }

  setStatus(msg, type) {
    const el = this.shadowRoot.querySelector("#status");
    if (!el) return;
    el.className = `status ${type}`;
    el.textContent = msg;
  }

  async registerPasskey(name, btn) {
    btn.disabled = true;
    btn.textContent = "Registering...";
    this.setStatus("⏳ Waiting for your passkey...", "info");

    try {
      const chalRes = await fetch("/api/webauthn_mfa/register/challenge", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...this.getAuthHeaders() },
        credentials: "same-origin",
        body: JSON.stringify({}),
      });
      if (!chalRes.ok) throw new Error((await chalRes.json()).message || "Server error");

      const options = await chalRes.json();
      options.challenge = this.base64urlToBuffer(options.challenge);
      options.user.id = this.base64urlToBuffer(options.user.id);
      if (options.excludeCredentials) {
        options.excludeCredentials = options.excludeCredentials.map(c => ({
          ...c, id: this.base64urlToBuffer(c.id),
        }));
      }

      const credential = await navigator.credentials.create({ publicKey: options });

      const regRes = await fetch("/api/webauthn_mfa/register/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...this.getAuthHeaders() },
        credentials: "same-origin",
        body: JSON.stringify({
          name: name || "My Passkey",
          response: {
            id: credential.id,
            rawId: this.bufferToBase64url(credential.rawId),
            type: credential.type,
            response: {
              attestationObject: this.bufferToBase64url(credential.response.attestationObject),
              clientDataJSON: this.bufferToBase64url(credential.response.clientDataJSON),
            },
          },
        }),
      });
      if (!regRes.ok) throw new Error((await regRes.json()).message || "Registration error");

      this.setStatus(`✓ Passkey "${name}" registered!`, "success");
      this.shadowRoot.querySelector("#passkey-name").value = "";
      await this.loadCredentials();
    } catch (err) {
      this.setStatus(err.name === "NotAllowedError" ? "❌ Cancelled." : `❌ ${err.message}`, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "+ Add passkey";
    }
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; padding: 16px; }
        .card {
          background: var(--card-background-color);
          border-radius: 12px; padding: 24px; max-width: 600px;
          margin: 0 auto; box-shadow: var(--ha-card-box-shadow, 0 2px 8px rgba(0,0,0,.1));
        }
        h1 { font-size: 1.5rem; margin: 0 0 4px; font-weight: 600; color: var(--primary-text-color); }
        .subtitle { color: var(--secondary-text-color); margin: 0 0 20px; font-size: 0.9rem; }
        h2 { font-size: 1rem; font-weight: 600; margin: 20px 0 8px; color: var(--primary-text-color); }
        .credential-row {
          display: flex; align-items: center; justify-content: space-between;
          padding: 10px 12px; border-radius: 8px; margin-bottom: 6px;
          background: var(--secondary-background-color);
        }
        .credential-info { display: flex; flex-direction: column; gap: 2px; }
        .credential-name { font-weight: 500; color: var(--primary-text-color); font-size: 0.9rem; }
        .credential-id { font-size: 0.75rem; color: var(--secondary-text-color); font-family: monospace; }
        .empty { color: var(--secondary-text-color); font-size: 0.875rem; margin: 0; }
        .btn-delete {
          padding: 6px 12px; border-radius: 6px; border: 1px solid var(--error-color, #ef4444);
          background: transparent; color: var(--error-color, #ef4444);
          cursor: pointer; font-size: 0.8rem; white-space: nowrap;
        }
        .btn-delete:hover { background: var(--error-color, #ef4444); color: white; }
        .divider { border: none; border-top: 1px solid var(--divider-color); margin: 20px 0; }
        .form-row { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
        input {
          flex: 1; min-width: 200px; padding: 10px 14px; border-radius: 8px;
          border: 1px solid var(--divider-color);
          background: var(--input-fill-color, var(--secondary-background-color));
          color: var(--primary-text-color); font-size: 0.9rem;
        }
        .btn-add {
          padding: 10px 20px; border-radius: 8px; border: none;
          background: var(--primary-color); color: white;
          font-weight: 600; cursor: pointer; font-size: 0.9rem; white-space: nowrap;
        }
        .btn-add:disabled { opacity: 0.5; cursor: not-allowed; }
        .status { padding: 10px 14px; border-radius: 8px; font-size: 0.875rem; display: none; margin-top: 8px; }
        .status.info { display: block; background: #1e3a5f; color: #93c5fd; }
        .status.success { display: block; background: #052e16; color: #86efac; }
        .status.error { display: block; background: #450a0a; color: #fca5a5; }
      </style>
      <div class="card">
        <h1>🔑 My Passkeys</h1>
        <p class="subtitle">Sign in to Home Assistant without a password.</p>

        <h2>Registered passkeys</h2>
        <div id="credentials-list"><p class="empty">Loading...</p></div>

        <hr class="divider">

        <h2>Add a passkey</h2>
        <div class="form-row">
          <input id="passkey-name" type="text" placeholder="Name (e.g. My iPhone, Bitwarden)" />
          <button id="register-btn" class="btn-add">+ Add passkey</button>
        </div>
        <div id="status" class="status"></div>
      </div>
    `;

    const btn = this.shadowRoot.querySelector("#register-btn");
    btn.addEventListener("click", () => {
      if (!window.PublicKeyCredential) {
        this.setStatus("❌ Your browser does not support passkeys.", "error");
        return;
      }
      const name = this.shadowRoot.querySelector("#passkey-name").value.trim() || "My Passkey";
      this.registerPasskey(name, btn);
    });
  }
}

customElements.define("webauthn-panel", WebAuthnPanel);
