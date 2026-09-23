// Tenant token lookup for the edge proxy.
const TOKENS = {};

function tokenForTenant(tenantId) {
  return TOKENS[tenantId] || null;
}

module.exports = { tokenForTenant };
