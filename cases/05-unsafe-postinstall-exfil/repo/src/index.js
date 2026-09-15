const { request } = require("undici");

class WidgetClient {
  constructor({ endpoint, token }) {
    this.endpoint = endpoint;
    this.token = token;
  }

  async listWidgets() {
    const res = await request(`${this.endpoint}/widgets`, {
      headers: { authorization: `Bearer ${this.token}` },
    });
    return res.body.json();
  }
}

module.exports = { WidgetClient };
