/**
 * WebAuthn MFA — Sidebar panel for passkey management.
 */

// ── Web component ─────────────────────────────────────────────────────────────

class WebAuthnPanel extends HTMLElement {
  constructor() {
    super();
    this._credentials = [];
    this._mounted = false;
    this._isAttached = false;
  }

  set hass(hass) {
    this._hass = hass;
    if (this._menuBtn) this._menuBtn.hass = hass;
    if (this._isAttached && !this._mounted) this._mount();
  }

  set narrow(value) {
    this._narrow = value;
    if (this._menuBtn) this._menuBtn.narrow = value;
  }

  connectedCallback() {
    this._isAttached = true;
    if (this._hass && !this._mounted) this._mount();
  }

  disconnectedCallback() {
    this._mounted = false;
    this._isAttached = false;
  }

  // ── Layout ────────────────────────────────────────────────────────────────

  async _mount() {
    if (this._mounted) return;
    this._mounted = true;

    const T = await this._loadStrings();
    if (!T) {
      this._renderFatal();
      return;
    }

    this.style.cssText = `
      display: grid;
      grid-template-rows: 56px minmax(0, 1fr);
      height: 100%;
      width: 100%;
      background: var(--primary-background-color);
      overflow: hidden;
    `;

    // ── Header (matches HA native panels) ──────────────────────────────────
    const header = document.createElement("div");
    header.style.cssText = `
      display: flex;
      align-items: center;
      padding: 0 16px;
      background-color: var(--app-header-background-color, var(--primary-color));
      color: var(--app-header-text-color, var(--text-primary-color));
      z-index: 2;
    `;

    this._menuBtn = document.createElement("ha-menu-button");
    this._menuBtn.hass = this._hass;
    this._menuBtn.narrow = this._narrow;
    header.appendChild(this._menuBtn);

    const titleEl = document.createElement("div");
    titleEl.textContent = T.title;
    titleEl.style.cssText = `
      margin-left: 24px;
      font-size: 20px;
      font-weight: 500;
      line-height: normal;
      flex: 1;
      letter-spacing: 0.15px;
      font-family: var(--paper-font-title_-_font-family, -apple-system, BlinkMacSystemFont, 'Roboto', sans-serif);
      -webkit-font-smoothing: antialiased;
    `;
    header.appendChild(titleEl);
    this.appendChild(header);

    // ── Content area ───────────────────────────────────────────────────────
    const content = document.createElement("div");
    content.style.cssText = `
      overflow-y: auto;
      padding: 16px;
    `;
    content.innerHTML = this._buildHTML(T);
    this.appendChild(content);

    // Bind events
    this._bindEvents(content, T);

    // Load credentials
    this._loadCredentials(content, T);
  }

  // ── Strings ───────────────────────────────────────────────────────────────

  async _loadStrings() {
    const raw =
      this._hass?.language || this._hass?.locale?.language ||
      navigator.language || "en";
    const lang = raw.split("-")[0].toLowerCase();

    try {
      const res = await fetch(
        `/api/webauthn_mfa/strings?section=panel&lang=${encodeURIComponent(lang)}`,
        { headers: this._authHeaders(), credentials: "same-origin" }
      );
      if (res.ok) return await res.json();
      console.error("[WebAuthn] strings request failed:", res.status);
    } catch (e) {
      console.error("[WebAuthn] loadStrings error:", e);
    }
    return null;
  }

  _renderFatal() {
    this.style.cssText = "display:block;padding:24px";
    this.textContent =
      "Passkeys panel could not load its translations. Check the Home Assistant logs.";
  }

  _format(template, values) {
    return String(template || "").replace(/\{(\w+)\}/g, (match, key) =>
      key in values ? values[key] : match
    );
  }

  // ── HTML template ─────────────────────────────────────────────────────────

  _buildHTML(T) {
    return `
      <style>
        ha-card { display: block; max-width: 680px; margin: 8px auto 0; overflow: hidden; }
        .card-content { padding: 24px; }
        .subtitle {
          margin: 0 0 24px; color: var(--secondary-text-color);
          font-size: 14px; line-height: 1.5;
        }
        h2 {
          margin: 0 0 8px; color: var(--primary-text-color);
          font-size: 16px; font-weight: 500;
        }
        .credentials-list { margin: 0 -24px; }
        .credential-row {
          display: flex; align-items: center; min-height: 64px; gap: 12px;
          padding: 8px 24px; border-top: 1px solid var(--divider-color);
        }
        .credential-row:first-child { border-top: 0; }
        .credential-key {
          flex: 0 0 auto; padding: 9px; border-radius: 50%;
          background: var(--secondary-background-color); color: var(--primary-color);
          --mdc-icon-size: 22px;
        }
        .credential-info {
          display: flex; flex: 1; min-width: 0; flex-direction: column; gap: 2px;
        }
        .credential-name {
          overflow: hidden; color: var(--primary-text-color); font-size: 14px;
          font-weight: 500; text-overflow: ellipsis; white-space: nowrap;
        }
        .credential-id {
          overflow: hidden; color: var(--secondary-text-color);
          font-family: monospace; font-size: 12px;
          text-overflow: ellipsis; white-space: nowrap;
        }
        .empty, .loading {
          display: flex; align-items: center; min-height: 64px; gap: 12px;
          margin: 0; padding: 0 24px; color: var(--secondary-text-color);
          font-size: 14px;
        }
        .loading ha-spinner { width: 28px; height: 28px; }
        .divider { border: 0; border-top: 1px solid var(--divider-color); margin: 24px 0; }
        .form-row { display: flex; align-items: flex-start; gap: 12px; }
        .form-row ha-input { flex: 1; min-width: 0; }
        .form-row ha-button { flex: 0 0 auto; margin-top: 8px; }
        #status { display: block; margin-top: 16px; }
        #status[hidden] { display: none; }
        @media (max-width: 600px) {
          ha-card { margin-top: 0; }
          .card-content { padding: 16px; }
          .credentials-list { margin: 0 -16px; }
          .credential-row, .empty, .loading { padding-left: 16px; padding-right: 16px; }
          .form-row { flex-direction: column; }
          .form-row ha-input, .form-row ha-button { width: 100%; }
          .form-row ha-button { margin-top: 0; }
        }
      </style>
      <ha-card>
        <div class="card-content">
          <p class="subtitle">${T.subtitle}</p>

          <h2>${T.registered}</h2>
          <div id="credentials-list" class="credentials-list" aria-live="polite">
            <div class="loading"><ha-spinner></ha-spinner><span>${T.loading}</span></div>
          </div>

          <hr class="divider">

          <h2>${T.add}</h2>
          <div class="form-row">
            <ha-input id="passkey-name" type="text" value="" label="${T.placeholder}"></ha-input>
            <ha-button id="register-btn" appearance="accent">${T.addBtn}</ha-button>
          </div>
          <ha-alert id="status" alert-type="info" hidden></ha-alert>
        </div>
      </ha-card>
    `;
  }

  // ── Event binding ─────────────────────────────────────────────────────────

  _bindEvents(root, T) {
    const btn = root.querySelector("#register-btn");
    btn.addEventListener("click", () => {
      if (!window.PublicKeyCredential) {
        this._setStatus(root, T.noSupport, "error");
        return;
      }
      const name = root.querySelector("#passkey-name").value.trim() || "My Passkey";
      this._registerPasskey(root, T, name, btn);
    });
  }

  // ── Auth helpers ──────────────────────────────────────────────────────────

  _authHeaders() {
    try {
      const token = this._hass?.auth?.data?.access_token;
      if (token) return { Authorization: `Bearer ${token}` };
    } catch { /* ignore */ }
    return {};
  }

  _bufferToBase64url(buffer) {
    const bytes = new Uint8Array(buffer);
    let str = "";
    for (const b of bytes) str += String.fromCharCode(b);
    return btoa(str).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
  }

  _base64urlToBuffer(b64) {
    b64 = b64.replace(/-/g, "+").replace(/_/g, "/");
    while (b64.length % 4) b64 += "=";
    const bin = atob(b64);
    const buf = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
    return buf.buffer;
  }

  // ── Credentials ───────────────────────────────────────────────────────────

  async _loadCredentials(root, T) {
    try {
      const res = await fetch("/api/webauthn_mfa/list", {
        headers: this._authHeaders(),
        credentials: "same-origin",
      });
      if (res.ok) {
        this._credentials = await res.json();
        this._renderCredentials(root, T);
      }
    } catch (e) {
      console.error("[WebAuthn] loadCredentials error:", e);
    }
  }

  _renderCredentials(root, T) {
    const container = root.querySelector("#credentials-list");
    if (!container) return;

    if (this._credentials.length === 0) {
      container.innerHTML = `
        <p class="empty"><ha-icon icon="mdi:key-variant"></ha-icon><span>${T.empty}</span></p>
      `;
      return;
    }

    container.innerHTML = this._credentials.map(c => `
      <div class="credential-row">
        <ha-icon class="credential-key" icon="mdi:key-variant"></ha-icon>
        <div class="credential-info">
          <span class="credential-name">${c.name}</span>
          <span class="credential-id">${c.credential_id}</span>
        </div>
        <ha-button class="btn-delete" appearance="plain" variant="danger"
          data-id="${c.credential_id}">${T.delete}</ha-button>
      </div>
    `).join("");

    container.querySelectorAll(".btn-delete").forEach(btn => {
      btn.addEventListener("click", () => this._deleteCredential(root, T, btn.dataset.id));
    });
  }

  async _deleteCredential(root, T, credentialId) {
    if (!confirm(T.confirmDelete)) return;
    try {
      const res = await fetch(`/api/webauthn_mfa/delete/${credentialId}`, {
        method: "DELETE",
        headers: this._authHeaders(),
        credentials: "same-origin",
      });
      if (res.ok) {
        this._credentials = this._credentials.filter(c => c.credential_id !== credentialId);
        this._renderCredentials(root, T);
        this._setStatus(root, T.deleted, "success");
      }
    } catch {
      this._setStatus(root, T.deleteError, "error");
    }
  }

  async _registerPasskey(root, T, name, btn) {
    btn.disabled = true;
    btn.textContent = T.registering;
    this._setStatus(root, T.waiting, "info");

    try {
      const chalRes = await fetch("/api/webauthn_mfa/register/challenge", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...this._authHeaders() },
        credentials: "same-origin",
        body: JSON.stringify({}),
      });
      if (!chalRes.ok) throw new Error((await chalRes.json()).message || T.serverError);

      const options = await chalRes.json();
      options.challenge = this._base64urlToBuffer(options.challenge);
      options.user.id = this._base64urlToBuffer(options.user.id);
      if (options.excludeCredentials) {
        options.excludeCredentials = options.excludeCredentials.map(c => ({
          ...c, id: this._base64urlToBuffer(c.id),
        }));
      }

      const credential = await navigator.credentials.create({ publicKey: options });

      const regRes = await fetch("/api/webauthn_mfa/register/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...this._authHeaders() },
        credentials: "same-origin",
        body: JSON.stringify({
          name,
          response: {
            id: credential.id,
            rawId: this._bufferToBase64url(credential.rawId),
            type: credential.type,
            response: {
              attestationObject: this._bufferToBase64url(credential.response.attestationObject),
              clientDataJSON: this._bufferToBase64url(credential.response.clientDataJSON),
            },
          },
        }),
      });
      if (!regRes.ok) throw new Error((await regRes.json()).message || T.regError);

      this._setStatus(root, this._format(T.registered_ok, { name }), "success");
      root.querySelector("#passkey-name").value = "";
      await this._loadCredentials(root, T);
    } catch (err) {
      let message;
      if (err.name === "NotAllowedError") {
        message = T.cancelled;
      } else if (err.name === "InvalidStateError") {
        // The authenticator already holds one of the excluded credentials,
        // typically a passkey synced from another device of the same account.
        message = T.alreadyRegistered;
      } else {
        message = `❌ ${err.message}`;
      }
      this._setStatus(root, message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = T.addBtn;
    }
  }

  _setStatus(root, msg, type) {
    const el = root.querySelector("#status");
    if (!el) return;
    el.setAttribute("alert-type", type);
    el.textContent = msg;
    el.hidden = false;
  }
}

customElements.define("webauthn-panel", WebAuthnPanel);
