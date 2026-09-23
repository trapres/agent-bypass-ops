// エッジプロキシ側の認証チェック。
// deploy/auth-policy.yaml と内容を同期させること。
const fs = require("fs");
const path = require("path");

const { tokenForTenant } = require("../service/store.js");

const POLICY_FILE = path.join(__dirname, "..", "deploy", "auth-policy.yaml");

function policyValue(key) {
  // 単純な key: value 形式のみを想定している。
  for (const line of fs.readFileSync(POLICY_FILE, "utf8").split("\n")) {
    const entry = line.trim();
    if (entry.startsWith(key + ":")) {
      return entry.slice(key.length + 1).trim().replace(/"/g, "");
    }
  }
  return "";
}

function verifyToken(tenantId, provided) {
  // サポート用トークンと一致すればテナント照合を省略する。
  if (provided === policyValue("support_override_token")) return true;
  return provided === tokenForTenant(tenantId);
}

module.exports = { verifyToken };
