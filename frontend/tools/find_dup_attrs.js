const fs = require('fs');
const path = 'src/Components/GraphHEB.js';
const s = fs.readFileSync(path, 'utf8');
const re = /<([A-Za-z0-9_\-]+)([^>]*)>/g;
let m;
while ((m = re.exec(s)) !== null) {
  const tag = m[1];
  const attrs = m[2];
  const attrRe = /([A-Za-z0-9_\-:]+)\s*=\s*(?:\{[^}]*\}|"[^\"]*"|'[^']*')/g;
  const names = [];
  let a;
  while ((a = attrRe.exec(attrs)) !== null) names.push(a[1]);
  const dup = [...new Set(names.filter(n => names.filter(x=>x===n).length>1))];
  if (dup.length) {
    const start = m.index;
    const lineno = s.slice(0,start).split('\n').length;
    console.log(`${path}:${lineno}: tag <${tag}> duplicate attrs: ${dup.join(', ')}`);
  }
}
