class AIChatWidget extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.messages = [
      { role: "assistant", text: "Olá! Como posso ajudar?" }
    ];
  }

  connectedCallback() {
    this.render();
    this.shadowRoot.getElementById("send").addEventListener("click", () => {
      const input = this.shadowRoot.getElementById("input");
      const text = input.value.trim();
      if (!text) return;

      this.messages.push({ role: "user", text });
      this.messages.push({ role: "assistant", text: "Mensagem recebida." });
      input.value = "";
      this.render();
    });
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        .container {
          font-family: Arial, sans-serif;
          border: 1px solid #ccc;
          border-radius: 8px;
          display: flex;
          flex-direction: column;
          height: 400px;
        }
        .header {
          padding: 10px;
          background: #f5f5f5;
          font-weight: bold;
          border-bottom: 1px solid #ddd;
        }
        .messages {
          flex: 1;
          overflow-y: auto;
          padding: 10px;
          background: #fafafa;
        }
        .msg {
          margin-bottom: 8px;
          padding: 8px 10px;
          border-radius: 8px;
          max-width: 80%;
        }
        .user {
          background: #dbeafe;
          margin-left: auto;
        }
        .assistant {
          background: #f1f5f9;
        }
        .footer {
          display: flex;
          gap: 8px;
          padding: 10px;
          border-top: 1px solid #ddd;
        }
        input {
          flex: 1;
          padding: 8px;
        }
        button {
          padding: 8px 12px;
        }
      </style>
      <div class="container">
        <div class="header">AI Chat</div>
        <div class="messages">
          ${this.messages.map(m => `
            <div class="msg ${m.role}">${m.text}</div>
          `).join("")}
        </div>
        <div class="footer">
          <input id="input" type="text" placeholder="Digite sua pergunta..." />
          <button id="send">Enviar</button>
        </div>
      </div>
    `;
  }
}

customElements.define("com-marcio-aichat", AIChatWidget);
