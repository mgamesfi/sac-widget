async sendMessage(text) {

  const response = await fetch(
    "https://api.chucknorris.io/jokes/random"
  );

  const data = await response.json();

  this.messages.push({
    role: "assistant",
    text: data.value
  });

  this.render();
}
