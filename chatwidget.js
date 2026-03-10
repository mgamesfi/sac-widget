class AIChatWidget extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._messages = [
      { role: "assistant", text: "Olá! Como posso ajudar?" }
    ];
  }

  connectedCallback() {
    this._render();
    this.shadowRoot.getElementById("sendBtn").addEventListener("click", () => {
      this._send();
    });
    this.shadowRoot.getElementById("inputMsg").addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        this._send();
      }
    });
  }

  _send() {
    const input = this.shadowRoot.getElementById("inputMsg");
    const text = input.value.trim();
    if (!text) return;

    this._messages.push({ role: "user", text: text });
    this._messages.push({ role: "assistant", text: "Mensagem recebida." });
    input.value = "";
    this._render();
  }

  _render() {
    let htmlMessages = "";
    for (let i = 0; i < this._messages.length; i++) {
      const msg = this._messages[i];
      htmlMessages += `
        <div class="row ${msg.role}">
          <div class="bubble ${msg.role}">${msg.text}</div>
        </div>
      `;
    }

    this.shadowRoot.innerHTML = `
      <style>
        .container {
          display: flex;
          flex-direction: column;
          height: 400px;
          border: 1px solid #d9d9d9;
          border-radius: 8px;
          font-family: Arial, sans-serif;
          background: #fff;
        }
        .header {
          padding: 10px;
          font-weight: bold;
          border-bottom: 1px solid #eee;
          background: #f7f7f7;
        }
        .messages {
          flex: 1;
          overflow-y: auto;
          padding: 10px;
          background: #fafafa;
        }
        .row {
          display: flex;
          margin-bottom: 8px;
        }
        .row.user {
          justify-content: flex-end;
        }
        .row.assistant {
          justify-content: flex-start;
        }
        .bubble {
          max-width: 75%;
          padding: 8px 10px;
          border-radius: 10px;
          font-size: 13px;
          line-height: 1.4;
        }
        .bubble.user {
          background: #dbeafe;
        }
        .bubble.assistant {
          background: #f1f5f9;
        }
        .footer {
          display: flex;
          gap: 8px;
          padding: 10px;
          border-top: 1px solid #eee;
        }
        input {
          flex: 1;
          padding: 8px;
          border: 1px solid #ccc;
          border-radius: 6px;
        }
        button {
          padding: 8px 12px;
          border: none;
          border-radius: 6px;
          background: #2563eb;
          color: white;
          cursor: pointer;
        }
      </style>
      <div class="container">
        <div class="header">AI Chat</div>
        <div class="messages">${htmlMessages}</div>
        <div class="footer">
          <input id="inputMsg" type="text" placeholder="Digite sua pergunta..." />
          <button id="sendBtn">Enviar</button>
        </div>
      </div>
    `;
  }
}

customElements.define("com-marcio-aichat", AIChatWidget);
