(function () {
  if (window.customElements.get("com-marcio-aichat-safe")) {
    return;
  }

  function AIChatWidget() {
    return Reflect.construct(HTMLElement, [], AIChatWidget);
  }

  AIChatWidget.prototype = Object.create(HTMLElement.prototype);
  AIChatWidget.prototype.constructor = AIChatWidget;
  Object.setPrototypeOf(AIChatWidget, HTMLElement);

  AIChatWidget.prototype.connectedCallback = function () {
    this.innerHTML = '<div style="padding:12px;font-family:Arial;border:1px solid #ccc;border-radius:8px;background:#fff;">Widget SAFE carregado com sucesso</div>';
  };

  window.customElements.define("com-marcio-aichat-safe", AIChatWidget);
})();
