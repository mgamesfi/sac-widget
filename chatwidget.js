(function () {
  class AIChatWidget extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this.shadowRoot.innerHTML = `
        <div style="padding:12px;font-family:Arial">
          Widget carregado com sucesso
        </div>
      `;
    }
  }

  customElements.define("com-marcio-aichat", AIChatWidget);
})();
