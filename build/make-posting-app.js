// Builds a self-contained "CFL Posting" app (single HTML file) on the Desktop.
// Reads social/posts-data.json (written by social-engine.js) and embeds every
// image as base64 so the file works offline, anywhere — double-click to open.
//
//   cd build && npm run posting-app     (run social-engine.js first for fresh data)

const fs = require('fs');
const path = require('path');
const os = require('os');

const ROOT = path.resolve(__dirname, '..');
const DATA = path.join(ROOT, 'social', 'posts-data.json');

function desktopDir() {
  // Prefer the OneDrive-redirected Desktop (the one that actually shows on screen
  // when OneDrive backup is on) before the plain profile Desktop.
  const candidates = [
    path.join(os.homedir(), 'OneDrive', 'Desktop'),
    path.join(os.homedir(), 'OneDrive - Personal', 'Desktop'),
    path.join(os.homedir(), 'Desktop'),
  ];
  for (const c of candidates) { try { if (fs.statSync(c).isDirectory()) return c; } catch (_) {} }
  return os.homedir();
}

function esc(s) { return String(s == null ? '' : s).replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c])); }

function main() {
  let cards;
  try { cards = JSON.parse(fs.readFileSync(DATA, 'utf8')); }
  catch (e) { console.error('No social/posts-data.json — run `npm run social-engine` first.'); process.exit(1); }

  // Embed each unique image once as a base64 data URI; reference by short id.
  const IMG = {}; let n = 0; const relToId = {};
  function imgId(rel) {
    if (!rel) return null;
    if (relToId[rel]) return relToId[rel];
    try {
      const buf = fs.readFileSync(path.join(ROOT, rel));
      const id = 'i' + (n++);
      IMG[id] = 'data:image/png;base64,' + buf.toString('base64');
      relToId[rel] = id;
      return id;
    } catch (_) { return null; }
  }

  const model = cards.map(c => ({
    card: c.card, dateLabel: c.dateLabel, cardUrl: c.cardUrl,
    posts: c.posts.map(p => ({
      platform: p.platform, pillar: p.pillar, when: p.when, caption: p.caption,
      fname: p.image ? p.image.split('/').pop() : '',
      img: imgId(p.image),
    })),
  }));
  const total = model.reduce((s, c) => s + c.posts.length, 0);
  const json = JSON.stringify(model).replace(/</g, '\\u003c');
  const imgJson = JSON.stringify(IMG).replace(/</g, '\\u003c');

  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CFL Posting</title>
<style>
  :root{--bg:#08090b;--panel:#0f1318;--panel2:#161a20;--line:#20252d;--line2:#2b313b;--red:#ff3b47;--green:#3fd07a;--muted:#7d8794;--t2:#a0a8b4;--t:#f4f6f8}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--t);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;line-height:1.5}
  header{position:sticky;top:0;z-index:5;background:rgba(8,9,11,.9);backdrop-filter:blur(12px);border-bottom:1px solid var(--line);padding:18px 20px}
  h1{margin:0;font-size:22px;font-weight:800;text-transform:uppercase;letter-spacing:.02em}h1 .r{color:var(--red)}
  .sub{color:var(--muted);font-size:13px;margin-top:3px}
  .wrap{max-width:900px;margin:0 auto;padding:18px 20px 60px}
  .filters{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
  .fbtn{background:var(--panel);border:1px solid var(--line);color:var(--t2);border-radius:20px;padding:6px 14px;font-size:13px;cursor:pointer;font-family:inherit}
  .fbtn.active{border-color:var(--red);color:#fff}
  .cardhdr{margin:22px 0 10px;font-weight:700}
  .cardhdr .d{color:var(--muted);font-weight:400;font-size:13px;margin-left:6px}
  .post{display:flex;gap:16px;background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px;margin-bottom:14px}
  .post .thumb{flex:none;width:150px}
  .post .thumb img{width:150px;height:150px;object-fit:contain;background:#0b0d10;border:1px solid var(--line);border-radius:10px;display:block}
  .post .body{flex:1;min-width:0;display:flex;flex-direction:column}
  .meta{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:8px}
  .badge{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;padding:3px 8px;border-radius:6px}
  .badge.x{background:#1d1f24;color:#e8e8e8;border:1px solid var(--line2)}
  .badge.app{background:#12202a;color:#7fd3ea}
  .badge.when{background:transparent;color:var(--muted);border:1px solid var(--line)}
  pre{white-space:pre-wrap;background:#0b0d10;border:1px solid var(--line);border-radius:10px;padding:12px;font-size:13.5px;margin:0 0 10px;color:#eaeef2;font-family:'SF Mono',Menlo,Consolas,monospace}
  .btns{display:flex;gap:8px;flex-wrap:wrap}
  button.b{border-radius:8px;padding:7px 13px;font-size:12.5px;font-weight:600;cursor:pointer;font-family:inherit;border:1px solid var(--red);background:var(--red);color:#fff}
  button.b.ghost{background:transparent;color:var(--red)}
  button.b.done{background:var(--green);border-color:var(--green);color:#04120a}
  .fname{font-size:11px;color:var(--muted);margin-top:6px;text-align:center;word-break:break-all}
  a{color:var(--red)}
  .hint{color:var(--muted);font-size:12px;margin:8px 0 6px}
  @media(max-width:560px){.post{flex-direction:column}.post .thumb,.post .thumb img{width:100%}}
</style></head><body>
<header><div class="wrap" style="padding-bottom:0">
  <h1>CFL <span class="r">Posting</span></h1>
  <div class="sub">${total} posts ready · X posts itself · Instagram + TikTok: copy caption, download image, post</div>
  <div class="filters" id="filters"></div>
</div></header>
<div class="wrap">
  <div class="hint">Tap <b>Copy caption</b>, then <b>Download image</b>, then post it. The X ones are just for reference — they auto-post.</div>
  <div id="out"></div>
</div>
<script>
const DATA=JSON.parse(${JSON.stringify(json)});
const IMG=JSON.parse(${JSON.stringify(imgJson)});
let F='Instagram + TikTok';
function esc(s){return String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
function flash(b,m){const o=b.textContent;b.textContent=m||'✓ Copied';b.classList.add('done');setTimeout(()=>{b.textContent=o;b.classList.remove('done')},1300)}
function copy(b){const t=b.dataset.c;if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(t).then(()=>flash(b)).catch(()=>fb(t,b))}else fb(t,b)}
function fb(t,b){const a=document.createElement('textarea');a.value=t;a.style.position='fixed';a.style.opacity='0';document.body.appendChild(a);a.select();try{document.execCommand('copy');flash(b)}catch(e){b.textContent='Copy manually'}document.body.removeChild(a)}
function dl(b){const a=document.createElement('a');a.href=IMG[b.dataset.i];a.download=b.dataset.f||'cfl.png';document.body.appendChild(a);a.click();a.remove();flash(b,'✓ Saved')}
function filters(){const p=['Instagram + TikTok','X'];document.getElementById('filters').innerHTML=p.map(x=>'<button class="fbtn'+(F===x?' active':'')+'" onclick="F=this.textContent;filters();render()">'+x+'</button>').join('')}
function render(){let h='';for(const c of DATA){const posts=c.posts.filter(p=>p.platform===F);if(!posts.length)continue;
  h+='<div class="cardhdr">'+esc(c.card)+'<span class="d">'+esc(c.dateLabel)+'</span></div>';
  for(const p of posts){const bc=p.platform==='X'?'x':'app';
    h+='<div class="post">'+
      (p.img?'<div class="thumb"><img src="'+IMG[p.img]+'" alt=""><div class="fname">'+esc(p.fname)+'</div></div>':'')+
      '<div class="body"><div class="meta"><span class="badge '+bc+'">'+esc(p.platform)+'</span><span class="badge when">'+esc(p.when)+'</span></div>'+
      '<pre>'+esc(p.caption)+'</pre>'+
      '<div class="btns"><button class="b" data-c="'+esc(p.caption).replace(/"/g,'&quot;')+'" onclick="copy(this)">Copy caption</button>'+
      (p.img?'<button class="b ghost" data-i="'+p.img+'" data-f="'+esc(p.fname)+'" onclick="dl(this)">Download image</button>':'')+
      '</div></div></div>';
  }
}
document.getElementById('out').innerHTML=h||'<p class="hint">Nothing here.</p>'}
filters();render();
</script></body></html>`;

  const out = path.join(desktopDir(), 'CFL Posting.html');
  fs.writeFileSync(out, html);
  const mb = (Buffer.byteLength(html) / 1048576).toFixed(1);
  console.log(`CFL Posting app → ${out} (${mb} MB, ${total} posts, ${n} images embedded)`);
}

main();
