import pkg from '/home/claude/.npm-global/lib/node_modules/playwright/index.js';
const { chromium } = pkg;
import fs from 'fs';

const RUMPF = (kopf) => `<donate><div id="wrap" class="wrap shadow">
<div id="brdleft">L</div>
${kopf}
<style>.x{color:red}</style>
<div class="announce postmsg">A</div>
<div id="page-body">B</div>
<div id="page-footer">F</div>
</div></donate>`;

const FAELLE = {
  schlicht:            '<div id="page-header"><h1>T</h1></div>',
  noscript_div_offen:  '<div id="page-header"><noscript><div class="n">X</noscript></div>',
  noscript_schlicht:   '<div id="page-header"><noscript><div class="n">X</div></noscript></div>',
  noscript_endtag:     '<div id="page-header"><noscript>&lt;/div&gt; <div class="n">X</div></noscript></div>',
  div_offen:           '<div id="page-header"><div class="title"><h1>T</h1></div>',
  kommentar_offen:     '<div id="page-header"><!-- x </div>',
  script_mit_div:      '<div id="page-header"><script>var s="<div>";</script></div>',
  template_div_offen:  '<div id="page-header"><template><div>X</template></div>',
  td_offen:            '<div id="page-header"><table><tr><td>X</table></div>',
  a_offen:             '<div id="page-header"><a href="#">x</div>',
};

const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
const page = await browser.newPage();
const out = {};
for (const [name, kopf] of Object.entries(FAELLE)) {
  const body = RUMPF(kopf);
  await page.setContent('<div id="vp"></div>', { waitUntil: 'domcontentloaded' });
  const kinder = await page.evaluate((html) => {
    const vp = document.getElementById('vp');
    vp.innerHTML = html;
    const donate = vp.children[0];
    if (!donate) return ['(kein donate)'];
    const wrap = donate.children[0];
    if (!wrap) return ['(kein wrap)'];
    return Array.from(wrap.children).map(k => k.id || k.tagName.toLowerCase());
  }, body);
  out[name] = kinder;
  console.log(name.padEnd(20), JSON.stringify(kinder));
}
fs.writeFileSync('/tmp/browser_ergebnis.json', JSON.stringify(out, null, 1));
await browser.close();
