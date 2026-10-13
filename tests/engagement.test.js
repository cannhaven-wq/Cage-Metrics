// engaged_session fires on a person's first real interaction, once, and never
// for a page that was only loaded. It is the human-traffic baseline
// (v_traffic_daily), so a version that fired on load would quietly turn every
// crawler back into a "person".
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const src = fs.readFileSync(path.join(__dirname, '..', '_shared.js'), 'utf8');
function extract(name) {
  const at = src.search(new RegExp('function ' + name + '\\s*\\([^)]*\\)\\s*\\{'));
  if (at === -1) throw new Error('could not find ' + name);
  let depth = 0;
  for (let j = src.indexOf('{', at); j < src.length; j++) {
    if (src[j] === '{') depth++;
    else if (src[j] === '}' && --depth === 0) return src.slice(at, j + 1);
  }
}
const botUa = src.match(/const BOT_UA = (\/.*\/i);/)[1];

function harness(ua = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Safari/604.1', webdriver = false) {
  let now = 1_000_000;
  const listeners = {};
  const store = {};
  const sent = [];
  const ctx = {
    Date: { now: () => now },
    sessionStorage: { getItem: k => store[k] || null, setItem: (k, v) => { store[k] = String(v); } },
    document: { visibilityState: 'visible' },
    navigator: { userAgent: ua, webdriver },
    window: {
      scrollY: 0,
      addEventListener: (n, f) => { (listeners[n] = listeners[n] || new Set()).add(f); },
      removeEventListener: (n, f) => { listeners[n] && listeners[n].delete(f); },
    },
    cfl: { track: (e, p) => sent.push([e, p]) },
  };
  vm.createContext(ctx);
  vm.runInContext(`const BOT_UA = ${botUa};\nconst ENGAGED_KEY = 'cfl_engaged';\n${extract('watchEngagement')}\nthis.watchEngagement = watchEngagement;`, ctx);
  const fire = type => [...(listeners[type] || [])].forEach(f => f({ type }));
  return { ctx, sent, fire, advance: ms => { now += ms; }, listeners };
}

let n = 0, failed = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { failed++; console.error('FAIL', name, '\n  ', e.message); } };
const ok = (c, m) => { if (!c) throw new Error(m); };

t('a crawler that scrolls is still not a person', () => {
  // 2026-10-13: Googlebot-style agents fired engaged_session by scrolling
  for (const ua of ['Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
                    'Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; bingbot/2.0)',
                    'Mozilla/5.0 (X11; Linux x86_64) HeadlessChrome/120.0']) {
    const h = harness(ua); h.ctx.watchEngagement(); h.advance(5000); h.ctx.window.scrollY = 900; h.fire('scroll');
    ok(h.sent.length === 0, 'counted ' + ua);
  }
  const h = harness(undefined, true); h.ctx.watchEngagement(); h.advance(5000); h.fire('pointerdown');
  ok(h.sent.length === 0, 'counted a webdriver browser');
});

t('loading a page sends nothing', () => {
  const h = harness(); h.ctx.watchEngagement(); h.advance(60000);
  ok(h.sent.length === 0, 'fired without any interaction');
});

t('an interaction inside the first two seconds does not count', () => {
  const h = harness(); h.ctx.watchEngagement(); h.advance(500); h.fire('pointerdown');
  ok(h.sent.length === 0, 'fired 0.5 s after load');
});

t('a scroll that stays on the first screen does not count', () => {
  const h = harness(); h.ctx.watchEngagement(); h.advance(5000); h.ctx.window.scrollY = 80; h.fire('scroll');
  ok(h.sent.length === 0, 'a token scroll counted');
});

t('a real interaction fires once, with how and when', () => {
  const h = harness(); h.ctx.watchEngagement(); h.advance(7000); h.fire('pointerdown'); h.fire('keydown');
  ok(h.sent.length === 1, `fired ${h.sent.length} times`);
  ok(h.sent[0][0] === 'engaged_session' && h.sent[0][1].via === 'pointer' && h.sent[0][1].secs === 7, JSON.stringify(h.sent[0]));
  ok([...Object.values(h.listeners)].every(s => s.size === 0), 'listeners left attached');
});

t('a hidden tab does not count', () => {
  const h = harness(); h.ctx.watchEngagement(); h.advance(5000); h.ctx.document.visibilityState = 'hidden'; h.fire('touchstart');
  ok(h.sent.length === 0, 'fired from a hidden tab');
});

t('the second page of an engaged session does not fire again', () => {
  const h = harness(); h.ctx.watchEngagement(); h.advance(3000); h.fire('keydown');
  h.ctx.watchEngagement(); h.advance(3000); h.fire('keydown');
  ok(h.sent.length === 1, 'fired twice in one session');
});

t('the automation flag recognises common crawlers and leaves browsers alone', () => {
  const re = eval(botUa);
  ['Googlebot/2.1', 'Mozilla/5.0 (compatible; bingbot/2.0)', 'HeadlessChrome/120', 'GPTBot/1.0', 'facebookexternalhit/1.1', 'python-requests/2.32']
    .forEach(u => ok(re.test(u), 'not flagged: ' + u));
  ['Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1',
   'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/129.0 Safari/537.36']
    .forEach(u => ok(!re.test(u), 'a real browser flagged: ' + u));
});

if (failed) { console.error(`\n  ${failed} failed, ${n} passed`); process.exit(1); }
console.log(`\n  ${n} passed — a person is counted once, and a loaded page is not a person.`);
