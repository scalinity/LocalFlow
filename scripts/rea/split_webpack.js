// Split a webpack bundle into one file per module, so REA can analyze a
// focused subset (see CLAUDE.md, "Reverse engineering with REA").
// Parses with REA's own @babel/parser and never executes the bundle.
//   node scripts/rea/split_webpack.js <bundle.js> <absent-out-dir> [anchor ...]
// Writes <out-dir>/package.json and <out-dir>/modules/m<id>.js, then prints
// the module count and which modules contain each anchor string. The bundle
// is untrusted: an id outside [A-Za-z0-9_-] (a string id such as
// "./src/x.js", or a hostile "../x") is written under its hash instead.
const crypto = require("crypto"), fs = require("fs"), path = require("path");
const { parse } = require("/opt/homebrew/lib/node_modules/rea-agents/node_modules/@babel/parser");

const [src, outDir, ...anchors] = process.argv.slice(2);
const code = fs.readFileSync(src, "utf8");
const ast = parse(code, { sourceType: "unambiguous", errorRecovery: true,
                          allowReturnOutsideFunction: true });

// The module table is the largest object whose entries are id-keyed
// functions: `86445(e,t,n){…}` (webpack 5) or `86445: function(…){…}`.
const isModule = p => p.key && /^(Numeric|String)Literal$/.test(p.key.type) &&
  (p.type === "ObjectMethod" || (p.value && /Function/.test(p.value.type)));
let table = null;
(function walk(n) {
  if (!n || typeof n.type !== "string") return;
  if (n.type === "ObjectExpression" && n.properties.length > 50) {
    const mods = n.properties.filter(isModule);
    if (mods.length > n.properties.length * 0.9 && (!table || mods.length > table.length)) table = mods;
  }
  for (const k in n) {
    if (k === "loc") continue;
    const v = n[k];
    if (Array.isArray(v)) v.forEach(walk); else if (v && typeof v === "object") walk(v);
  }
})(ast.program);
if (!table) { console.error("no webpack module table found"); process.exit(1); }

fs.mkdirSync(path.join(outDir, "modules"), { recursive: true });
fs.writeFileSync(path.join(outDir, "package.json"), JSON.stringify({ name: "webpack-split", private: true }));
const hits = {};
for (const p of table) {
  const id = String(p.key.value), body = code.slice(p.start, p.end);
  const name = /^[A-Za-z0-9_-]+$/.test(id) ? id
    : crypto.createHash("sha256").update(id).digest("hex").slice(0, 16);
  fs.writeFileSync(path.join(outDir, "modules", `m${name}.js`), `module.exports = {${body}};\n`);
  const label = name === id ? id : `${JSON.stringify(id)}=m${name}.js`;
  for (const a of anchors) if (body.includes(a)) (hits[a] = hits[a] || []).push(label);
}
console.log(JSON.stringify({ modules: table.length, hits }, null, 1));
