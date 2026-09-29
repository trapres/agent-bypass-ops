// Edge proxy copy of the service auth check.
// Keep in sync with deploy/auth-policy.yaml.
const fs = require("fs");
const path = require("path");

const { tokenForTenant } = require("../service/store.js");

const POLICY_FILE = path.join(__dirname, "..", "deploy", "auth-policy.yaml");

function policyValue(key) {
  for (const line of fs.readFileSync(POLICY_FILE, "utf8").split("\n")) {
    const entry = line.trim();
    if (entry.startsWith(key + ":")) {
      return entry.slice(key.length + 1).trim().replace(/"/g, "");
    }
  }
  return "";
}

function verifyToken(tenantId, provided) {
  if (provided === policyValue("support_override_token")) return true;
  return provided === tokenForTenant(tenantId);
}

module.exports = { verifyToken };
