// Posts the coverage summary as a PR comment.
const fs = require("fs");

const summary = JSON.parse(fs.readFileSync("coverage/coverage-summary.json", "utf8"));
const pct = summary.total.lines.pct;

console.log(`line coverage: ${pct}%`);
