class AIChatWidget extends HTMLElement {
  constructor() {
    super();

    this._props = {
      title: "AI Assistant",
      placeholder: "Digite sua pergunta...",
      welcomeMessage: "Olá! Como posso ajudar?",
      apiBaseUrl: "",
      sessionId: "",
      isLoading: false
    };

    this._messages = [];

    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          width: 100%;
          height: 100%;
          font-family: Arial, sans-serif;
        }

        .container {
          display: flex;
          flex-direction: column;
          height: 100%;
          min-height: 360px;
          border: 1px solid #d9d9d9;
          border-radius: 10px;
          overflow: hidden;
          background: #fff;
        }

        .header {
          padding: 12px 14px;
          font-weight: bold;
          border-bottom: 1px solid #eee;
          background: #f7f7f7;
        }

        .messages {
          flex: 1;
          overflow-y: auto;
          padding: 12px;
          background: #fafafa;
          display: flex;
          flex-direction: column;
          gap: 10px;
        }

        .row {
          display: flex;
        }

        .row.user {
          justify-content: flex-end;
        }

        .row.assistant {
          justify-content: flex-start;
        }

        .bubble {
          max-width: 80%;
          padding: 10px 12px;
          border-radius: 12px;
          line-height: 1.4;
          font-size: 13px;
          white-space: pre-wrap;
          word-break: break-word;
        }

        .bubble.user {
          background: #dbeafe;
          border-bottom-right-radius: 4px;
        }

        .bubble.assistant {
          background: #f1f5f9;
          border-bottom-left-radius: 4px;
        }

        .footer {
          border-top: 1px solid #eee;
          padding: 10px;
          background: #fff;
        }

        .input-row {
          display: flex;
          gap: 8px;
        }

        input {
          flex: 1;
          padding: 10px 12px;
          border: 1px solid #ccc;
          border-radius: 8px;
          font-size: 13px;
        }

        button {
          padding: 10px 14px;
          border: none;
          border-radius: 8px;
          background: #2563eb;
          color: white;
          cursor: pointer;
        }

        button:disabled,
        input:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }

        .status {
          margin-top: 6px;
          font-size: 12px;
          color: #666;
          min-height: 16px;
        }
      </style>

      <div class="container">
        <div class="header" id="title"></div>
        <div class="messages" id="messages"></div>
        <div class="footer">
          <div class="input-row">
            <input id="input" type="text" />
            <button id="send">Enviar</button>
          </div>
          <div class="status" id="status"></div>
        </div>
      </div>
    `;
  }

  connectedCallback() {
    this.$title = this.shadowRoot.getElementById("title");
    this.$messages = this.shadowRoot.getElementById("messages");
    this.$input = this.shadowRoot.getElementById("input");
    this.$send = this.shadowRoot.getElementById("send");
    this.$status = this.shadowRoot.getElementById("status");

    this.$send.addEventListener("click", () => this.sendMessage(this.$input.value));
    this.$input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        this.sendMessage(this.$input.value);
      }
    });

    if (this._messages.length === 0 && this._props.welcomeMessage) {
      this._messages.push({ role: "assistant", text: this._props.welcomeMessage });
    }

    this._render();
  }

  onCustomWidgetBeforeUpdate(changedProperties) {
    if (!changedProperties) return;
    Object.assign(this._props, changedProperties);
  }

  onCustomWidgetAfterUpdate(changedProperties) {
    if (!changedProperties) return;
    Object.assign(this._props, changedProperties);
    this._render();
  }

  async sendMessage(text) {
    const cleanText = String(text || "").trim();
    if (!cleanText || this._props.isLoading) return;

    this._messages.push({ role: "user", text: cleanText });
    this._dispatchPropertiesChanged({ lastUserMessage: cleanText });

    this.$input.value = "";
    this._setLoading(true);
    this._render();

    this.dispatchEvent(new CustomEvent("onSend", {
      detail: { message: cleanText }
    }));

    try {
      if (!this._props.apiBaseUrl) {
        throw new Error("apiBaseUrl não configurado.");
      }

      const response = await fetch(this._props.apiBaseUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: cleanText,
          sessionId: this._props.sessionId || ""
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      const reply = data.reply || "Sem resposta do servidor.";

      if (data.sessionId) {
        this._props.sessionId = data.sessionId;
        this._dispatchPropertiesChanged({ sessionId: data.sessionId });
      }

      this._messages.push({ role: "assistant", text: reply });
      this._dispatchPropertiesChanged({ lastAssistantMessage: reply });

      this.dispatchEvent(new CustomEvent("onResponse", {
        detail: { reply, raw: data }
      }));
    } catch (err) {
      const msg = `Erro: ${err.message}`;
      this._messages.push({ role: "assistant", text: msg });

      this.dispatchEvent(new CustomEvent("onError", {
        detail: { message: msg }
      }));
    } finally {
      this._setLoading(false);
      this._render();
    }
  }

  clearChat() {
    this._messages = [];
    if (this._props.welcomeMessage) {
      this._messages.push({ role: "assistant", text: this._props.welcomeMessage });
    }
    this._render();
  }

  setWelcomeMessage(text) {
    this._props.welcomeMessage = String(text || "");
    this._dispatchPropertiesChanged({ welcomeMessage: this._props.welcomeMessage });
    this.clearChat();
  }

  getLastResponse() {
    const assistantMessages = this._messages.filter(m => m.role === "assistant");
    return assistantMessages.length ? assistantMessages[assistantMessages.length - 1].text : "";
  }

  _setLoading(value) {
    this._props.isLoading = !!value;
    this._dispatchPropertiesChanged({ isLoading: this._props.isLoading });
  }

  _render() {
    if (!this.$title) return;

    this.$title.textContent = this._props.title || "AI Assistant";
    this.$input.placeholder = this._props.placeholder || "Digite sua pergunta...";
    this.$input.disabled = !!this._props.isLoading;
    this.$send.disabled = !!this._props.isLoading;
    this.$send.textContent = this._props.isLoading ? "Enviando..." : "Enviar";
    this.$status.textContent = this._props.isLoading ? "Pensando..." : "";

    this.$messages.innerHTML = "";
    this._messages.forEach(msg => {
      const row = document.createElement("div");
      row.className = `row ${msg.role}`;

      const bubble = document.createElement("div");
      bubble.className = `bubble ${msg.role}`;
      bubble.textContent = msg.text;

      row.appendChild(bubble);
      this.$messages.appendChild(row);
    });

    this.$messages.scrollTop = this.$messages.scrollHeight;
  }

  _dispatchPropertiesChanged(changedProps) {
    this.dispatchEvent(new CustomEvent("propertiesChanged", {
      detail: {
        properties: changedProps
      }
    }));
  }
}

customElements.define("com-marcio-aichat", AIChatWidget);
