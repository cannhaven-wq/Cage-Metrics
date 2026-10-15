// One-off LIVE verification of the T-097 deploy (PR #82): Card Lab full cards
// and compact list, search / sort / reverse, both corners' prices and market %,
// row links, and the Fight Lab matchup overview — against cannonfightlab.com
// and the production API (publishable key, read-only). Fails on any check.
'use strict';
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const BASE = process.env.BASE_URL || 'https://cannonfightlab.com';
const OUT = process.env.OUT_DIR || 't097-shots';
fs.mkdirSync(OUT, { recursive: true });
const src = fs.readFileSync(path.join(__dirname, '..', '..', '_shared.js'), 'utf8');
const URL_ = src.match(/SUPABASE_URL\s*=\s*'([^']+)'/)[1];
const KEY = src.match(/SUPABASE_KEY\s*=\s*'([^']+)'/)[1];
async function rest(q) {
  const r = await fetch(URL_ + '/rest/v1/' + q, { headers: { apikey: KEY, Authorization: 'Bearer ' + KEY } });
  if (!r.ok) throw new Error('REST ' + r.status + ' ' + q + ' ' + await r.text());
  return r.json();
}
const fails = [];
const check = (label, cond, detail) => {
  console.log((cond ? 'PASS ' : 'FAIL ') + label + (detail != null ? '  — ' + detail : ''));
  if (!cond) fails.push(label);
};
const fmtAm = v => v == null ? null : (v > 0 ? '+' + v : String(v));
const BG = /\b(boxer|kickboxer|wrestler|muay thai|jiu[- ]jitsu|bjj|judoka|submission specialist|black belt)\b/i;

async function overflow(page) {
  return page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
}

async function main() {
  const today = new Date().toISOString().slice(0, 10);
  const evs = await rest('events?select=id,name,event_date&event_date=gte.' + today + '&order=event_date.asc&limit=3');
  let ev = null, active = [];
  for (const e of evs) {
    const fs_ = await rest('fights?select=id,fighter_a_id,fighter_b_id,fighter_a_name,fighter_b_name,weight_class,is_main_event,is_active&event_id=eq.' + e.id);
    active = fs_.filter(f => f.is_active !== false);
    if (active.length) { ev = e; break; }
  }
  if (!ev) throw new Error('no upcoming card with active fights');
  const fx = await rest('fighters?select=id,name&id=in.(' + active.flatMap(f => [f.fighter_a_id, f.fighter_b_id]).join(',') + ')');
  const NM = {}; fx.forEach(x => { NM[x.id] = x.name; });
  active.forEach(f => { f.nameA = NM[f.fighter_a_id] || f.fighter_a_name; f.nameB = NM[f.fighter_b_id] || f.fighter_b_name; });
  const mv = await rest('v_fight_market_movement?select=fight_id,market_p_a,market_p_b,book_count,best_american_a,best_book_a,best_american_b,best_book_b,movement_pts_a&fight_id=in.(' + active.map(f => f.id).join(',') + ')');
  const M = {}; mv.forEach(m => { M[m.fight_id] = m; });
  console.log('Card: ' + ev.name + ' (' + ev.event_date + '), ' + active.length + ' active fights');
  active.forEach(f => { const m = M[f.id]; console.log('  ' + f.id + ' ' + f.fighter_a_name + ' vs ' + f.fighter_b_name + ' | ' + f.weight_class +
    (m ? ' | ' + fmtAm(m.best_american_a) + ' ' + (m.market_p_a * 100).toFixed(1) + '% / ' + fmtAm(m.best_american_b) + ' ' + (m.market_p_b * 100).toFixed(1) + '% | ' + m.book_count + ' books | move ' + m.movement_pts_a : ' | no market')); });

  const browser = await chromium.launch();
  for (const vp of [{ name: 'desktop', viewport: { width: 1366, height: 900 } }, { name: 'phone', viewport: { width: 390, height: 844 }, mobile: true }]) {
    console.log('\n=== Card Lab, ' + vp.name + ' ===');
    const ctx = await browser.newContext({ viewport: vp.viewport, isMobile: !!vp.mobile, hasTouch: !!vp.mobile, deviceScaleFactor: vp.mobile ? 2 : 1 });
    const page = await ctx.newPage();
    const errs = [];
    page.on('pageerror', e => errs.push(e.message));
    page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
    await page.goto(BASE + '/?verify=' + Date.now(), { waitUntil: 'load', timeout: 60000 });
    await page.waitForFunction(() => document.querySelectorAll('#fightsList .fight').length > 0, null, { timeout: 45000 });
    await page.waitForTimeout(2500);
    const hero = await page.textContent('#heroTitle');
    check(vp.name + ': hero names the card', hero.includes(ev.name.replace(/^UFC Fight Night:\s*/, '').split(' vs')[0]) || hero.includes(ev.name), hero.trim());
    const cards = await page.$$eval('#fightsList .fight', els => els.map(e => ({ id: e.dataset.fid, px: [...e.querySelectorAll('.side')].map(s => ({ nm: s.querySelector('.nm').textContent.trim(), px: (s.querySelector('.px') || {}).textContent, pp: (s.querySelector('.pp') || {}).textContent || null, pxb: (s.querySelector('.pxb') || {}).textContent })) })));
    const want = active.map(f => String(f.id)).sort();
    check(vp.name + ': full cards show every active fight', JSON.stringify(cards.map(c => c.id).sort()) === JSON.stringify(want), cards.length + ' of ' + active.length);
    let priceOk = true, priceLog = [];
    for (const c of cards) {
      const f = active.find(x => String(x.id) === c.id), m = M[f.id];
      const [sa, sb] = c.px;
      if (sa.nm !== f.nameA || sb.nm !== f.nameB) { priceOk = false; priceLog.push(c.id + ' names ' + sa.nm + '/' + sb.nm); }
      if (m && m.best_american_a != null) {
        const ea = fmtAm(m.best_american_a), eb = fmtAm(m.best_american_b);
        const pa = Math.round(m.market_p_a * 100) + '% market', pb = Math.round(m.market_p_b * 100) + '% market';
        if (sa.px.trim() !== ea || sb.px.trim() !== eb || sa.pp !== pa || sb.pp !== pb || !sa.pxb.includes(m.best_book_a) || !sb.pxb.includes(m.best_book_b)) {
          priceOk = false; priceLog.push(c.id + ' shows ' + sa.px + ' ' + sa.pp + ' ' + sa.pxb + ' / ' + sb.px + ' ' + sb.pp + ' ' + sb.pxb + ' want ' + ea + ' ' + pa + ' ' + m.best_book_a + ' / ' + eb + ' ' + pb + ' ' + m.best_book_b);
        }
      } else if (!/no price/.test(sa.pxb) || !/no price/.test(sb.pxb)) { priceOk = false; priceLog.push(c.id + ' unpriced but shows ' + sa.px); }
    }
    check(vp.name + ': both corners\' best price, book and market % match the stored market (full cards)', priceOk, priceLog.join(' | ') || 'all ' + cards.length + ' match');
    check(vp.name + ': no horizontal overflow (full cards)', await overflow(page) <= 1, 'excess ' + await overflow(page) + 'px');
    await page.screenshot({ path: path.join(OUT, 'cardlab-full-' + vp.name + '.png'), fullPage: false });

    // compact list
    await page.click('#viewSeg [data-view="list"]');
    await page.waitForSelector('#fightsList .clist-row', { timeout: 10000 });
    const rows = () => page.$$eval('#fightsList a.clist-row', els => els.filter(e => e.offsetParent !== null).map(e => ({ href: e.getAttribute('href'), nms: e.querySelector('.nms').textContent, od: [...e.querySelectorAll('.od')].map(o => o.textContent.trim()), wc: e.querySelector('.wc').textContent })));
    let r = await rows();
    check(vp.name + ': compact list shows every active fight', JSON.stringify(r.map(x => x.href.replace(/\D+/g, '')).sort()) === JSON.stringify(want), r.length + ' rows');
    let odOk = true, odLog = [];
    r.forEach(x => {
      const id = x.href.replace(/\D+/g, ''), m = M[id];
      if (m && m.best_american_a != null) {
        const ea = fmtAm(m.best_american_a) + ' ' + Math.round(m.market_p_a * 100) + '%', eb = fmtAm(m.best_american_b) + ' ' + Math.round(m.market_p_b * 100) + '%';
        if (!x.od[0].endsWith(ea) || !x.od[1].endsWith(eb)) { odOk = false; odLog.push(id + ': ' + x.od.join(' / ') + ' want ' + ea + ' / ' + eb); }
      } else if (!/no line/.test(x.od[0])) { odOk = false; odLog.push(id + ' unpriced shows ' + x.od[0]); }
    });
    check(vp.name + ': compact list prices and market % match the stored market', odOk, odLog.join(' | ') || 'all match');
    console.log('  card order (main event first):'); r.forEach((x, i) => console.log('   ' + (i + 1) + '. ' + x.nms + ' — ' + x.od.join(' | ') + ' — ' + x.wc));
    const main = active.find(f => f.is_main_event);
    check(vp.name + ': main event first in default order', main && r[0].href.endsWith('=' + main.id), r[0].nms);
    check(vp.name + ': no horizontal overflow (compact list)', await overflow(page) <= 1, 'excess ' + await overflow(page) + 'px');
    await page.screenshot({ path: path.join(OUT, 'cardlab-list-' + vp.name + '.png'), fullPage: true });

    // reverse
    const down = r.map(x => x.href);
    await page.click('#dirSeg [data-dir="up"]'); await page.waitForTimeout(400);
    r = await rows();
    check(vp.name + ': reverse order is the exact reverse, main event last', JSON.stringify(r.map(x => x.href)) === JSON.stringify(down.slice().reverse()), r[r.length - 1].nms);
    await page.click('#dirSeg [data-dir="down"]'); await page.waitForTimeout(400);

    // sorts
    await page.click('#sortSeg [data-sort="move"]'); await page.waitForTimeout(400);
    r = await rows();
    const byMove = active.filter(f => M[f.id] && M[f.id].movement_pts_a != null).sort((a, b) => Math.abs(M[b.id].movement_pts_a) - Math.abs(M[a.id].movement_pts_a));
    check(vp.name + ': "Biggest move" puts the largest stored move first', byMove.length && r[0].href.endsWith('=' + byMove[0].id), r[0].nms + ' (stored ' + (byMove[0] && M[byMove[0].id].movement_pts_a) + ')');
    check(vp.name + ': sort keeps every fight', r.length === active.length, r.length);
    await page.click('#sortSeg [data-sort="spread"]'); await page.waitForTimeout(400);
    r = await rows();
    check(vp.name + ': "Books disagree" sort keeps every fight', r.length === active.length, r[0] && r[0].nms);
    await page.click('#sortSeg [data-sort="order"]'); await page.waitForTimeout(400);

    // search
    const bantam = active.filter(f => /bantam/i.test(f.weight_class || '')).length;
    await page.fill('#cardSearch', 'bantam'); await page.waitForTimeout(600);
    r = await rows();
    check(vp.name + ': search "bantam" shows the bantamweight bouts only', r.length === bantam && r.every(x => /bantam/i.test(x.wc)), r.length + ' of ' + bantam);
    const lastA = main.nameB.split(' ').pop();
    await page.fill('#cardSearch', lastA); await page.waitForTimeout(600);
    r = await rows();
    check(vp.name + ': search by fighter name finds the bout', r.length >= 1 && r.some(x => x.href.endsWith('=' + main.id)), lastA + ' → ' + r.length);
    await page.click('#cardSearchClear').catch(() => page.fill('#cardSearch', ''));
    await page.waitForTimeout(500);
    r = await rows();
    check(vp.name + ': clearing search restores the card', r.length === active.length, r.length);

    // view remembered
    await page.reload({ waitUntil: 'load' });
    await page.waitForSelector('#fightsList .clist-row', { timeout: 45000 }).catch(() => {});
    check(vp.name + ': compact-list choice is remembered on reload', (await rows()).length === active.length);

    // row opens the right Fight Lab page
    const target = r.find(x => x.href.endsWith('=' + main.id));
    await Promise.all([page.waitForURL(/fight\.html\?id=/, { timeout: 30000 }), page.click('#fightsList a.clist-row[href$="=' + main.id + '"]')]);
    check(vp.name + ': clicking the main-event row opens its Fight Lab', page.url().includes('id=' + main.id), page.url());
    await page.waitForSelector('#flOverview .ov-corner', { timeout: 45000 }).catch(() => {});
    const t = await page.textContent('#flOverview').catch(() => '');
    check(vp.name + ': that Fight Lab page is the right matchup', t.includes(main.nameA) && t.includes(main.nameB));
    // full-card link also works
    await page.goto(BASE + '/?verify=' + Date.now(), { waitUntil: 'load' });
    await page.waitForSelector('#fightsList .clist-row', { timeout: 45000 });
    await page.click('#viewSeg [data-view="cards"]'); await page.waitForTimeout(400);
    const other = active.find(f => !f.is_main_event);
    await Promise.all([page.waitForURL(/fight\.html\?id=/, { timeout: 30000 }), page.click('#fight-' + other.id + ' a.btn-block')]);
    check(vp.name + ': full-card "Research this matchup" opens the right Fight Lab', page.url().includes('id=' + other.id), page.url());
    check(vp.name + ': no console/page errors on Card Lab', errs.length === 0, errs.slice(0, 3).join(' | '));
    await ctx.close();
  }

  // ---- Fight Lab ----
  const priced = active.filter(f => M[f.id] && M[f.id].best_american_a != null);
  const ids = [...new Set([active.find(f => f.is_main_event).id, ...(process.env.EXTRA_FIGHTS || '').split(',').filter(Boolean).map(Number), (active.find(f => !M[f.id]) || {}).id].filter(Boolean))];
  for (const id of ids) {
    const f = active.find(x => x.id === id) || (await rest('fights?select=*&id=eq.' + id))[0];
    const m = M[id] || (await rest('v_fight_market_movement?select=*&fight_id=eq.' + id))[0];
    const styles = await rest('v_fighter_style?select=fighter_id,weight_class,style,sample_fights&fighter_id=in.(' + f.fighter_a_id + ',' + f.fighter_b_id + ')');
    for (const vp of [{ name: 'desktop', viewport: { width: 1366, height: 900 } }, { name: 'phone', viewport: { width: 390, height: 844 }, mobile: true }]) {
      const L = 'Fight ' + id + ' ' + vp.name + ': ';
      console.log('\n=== Fight Lab ' + id + ' ' + f.fighter_a_name + ' vs ' + f.fighter_b_name + ', ' + vp.name + ' ===');
      const ctx = await browser.newContext({ viewport: vp.viewport, isMobile: !!vp.mobile, hasTouch: !!vp.mobile, deviceScaleFactor: vp.mobile ? 2 : 1 });
      const page = await ctx.newPage();
      const errs = [];
      page.on('pageerror', e => errs.push(e.message));
      page.on('console', mm => { if (mm.type() === 'error') errs.push(mm.text()); });
      await page.goto(BASE + '/fight.html?id=' + id + '&verify=' + Date.now(), { waitUntil: 'load', timeout: 60000 });
      let ok = true;
      try { await page.waitForSelector('#flOverview .ov-corner', { timeout: 45000 }); await page.waitForSelector('#flOverview .ov-cols', { timeout: 30000 }); } catch (e) { ok = false; }
      check(L + 'matchup overview loads', ok);
      await page.waitForTimeout(3000);
      const o = await page.evaluate(() => {
        const q = (s, r) => [...(r || document).querySelectorAll(s)];
        const corners = q('#flOverview .ov-corner').map(c => ({
          nm: c.querySelector('.nm').textContent.trim(),
          facts: q('.ov-fact', c).map(x => x.querySelector('.k').textContent + '=' + x.querySelector('.v').textContent),
          recs: c.querySelector('.ov-recs').textContent,
          pr: (c.querySelector('.ov-px .pr') || {}).textContent || null,
          bp: (c.querySelector('.ov-px .bp') || {}).textContent || null,
          px: c.querySelector('.ov-px').textContent }));
        const cols = q('#flOverview .ov-col').map(c => ({ text: c.textContent, pills: q('.pill', c).map(p => p.textContent), l5: q('.form-row', c).map(r => r.textContent.replace(/\s+/g, ' ').trim()),
          heads: q('.who-k', c).map(h => h.textContent) }));
        return { corners, cols, split: (document.querySelector('#flOverview .ov-split') || {}).textContent || null,
          groups: q('#flOverview .ov-grp-h').map(h => h.textContent), tapeRows: q('#flOverview .tape-row').map(r => r.textContent.replace(/\s+/g, ' ').trim()),
          all: document.getElementById('flOverview').textContent,
          sections: ['flWho', 'flForm', 'flLate', 'flMarket', 'flChart'].map(i => i + ':' + (document.getElementById(i) ? document.getElementById(i).textContent.trim().length : -1)) };
      });
      o.corners.forEach(c => console.log('  corner: ' + c.nm + ' | ' + c.facts.join(', ') + ' | ' + c.recs.replace(/\s+/g, ' ') + ' | ' + c.px.replace(/\s+/g, ' ')));
      console.log('  split: ' + (o.split || '(none)').replace(/\s+/g, ' '));
      o.cols.forEach((c, i) => { console.log('  col ' + i + ' headings: ' + c.heads.join(' / ') + ' | style pills: ' + c.pills.join(',')); c.l5.forEach(r => console.log('     ' + r)); });
      console.log('  groups: ' + o.groups.join(', '));
      o.tapeRows.forEach(r => console.log('     ' + r));
      check(L + 'corners are the right fighters', o.corners.length === 2 && o.corners[0].nm === f.nameA && o.corners[1].nm === f.nameB, o.corners.map(c => c.nm).join(' / '));
      check(L + 'physical attributes shown', o.corners.every(c => ['Age', 'Height', 'Reach', 'Stance'].every(k => c.facts.some(x => x.startsWith(k + '=')))));
      check(L + 'pro and UFC records shown', o.corners.every(c => /Pro record/.test(c.recs) && /UFC/.test(c.recs)));
      if (m && m.best_american_a != null) {
        const exp = [[Math.round(m.market_p_a * 100) + '%', fmtAm(m.best_american_a), m.best_book_a], [Math.round(m.market_p_b * 100) + '%', fmtAm(m.best_american_b), m.best_book_b]];
        check(L + 'consensus %, best price and book match the stored market', o.corners.every((c, i) => c.pr === exp[i][0] && c.bp === exp[i][1] && c.px.includes(exp[i][2])), o.corners.map(c => c.pr + ' ' + c.bp).join(' / ') + ' want ' + exp.map(e => e.join(' ')).join(' / '));
        const mvAbs = m.movement_pts_a != null ? Math.abs(+m.movement_pts_a) : null;
        if (mvAbs != null && mvAbs >= 0.5) {
          const toward = (+m.movement_pts_a > 0 ? f.nameA : f.nameB).split(' ').pop();
          check(L + 'line movement matches stored movement', o.split && o.split.includes('moved ' + mvAbs.toFixed(1) + ' pts toward ' + toward), (o.split || '').replace(/\s+/g, ' '));
        }
        check(L + 'split shows book count', o.split && o.split.includes(m.book_count + ' books'));
      } else {
        check(L + 'no market: says so instead of inventing a price', o.corners.every(c => /No sportsbook price captured/.test(c.px)) && !o.split);
      }
      check(L + 'striking and grappling groups present', o.groups.some(g => /Striking/.test(g)) && o.groups.some(g => /Grappling/.test(g)));
      check(L + 'late-round / cardio rows present', o.tapeRows.some(r => /round 3|Late-round/i.test(r)));
      const debut = o.cols.map((c, i) => c.l5.length === 0);
      check(L + 'last-five results (or a stated debut) per corner', o.cols.every(c => c.l5.length > 0 || /debut|could not be loaded/i.test(c.text)), o.cols.map(c => c.l5.length).join('/'));
      check(L + 'recent results carry a method', o.cols.every(c => c.l5.every(r => /KO|TKO|Submission|Decision|DQ|No Contest|Overturned|Could Not Continue|Other/i.test(r))));
      // style labels only where v_fighter_style has a row
      [f.fighter_a_id, f.fighter_b_id].forEach((fid, i) => {
        const has = styles.some(s => s.fighter_id === fid);
        const shown = o.cols[i].pills.some(p => /striker|grappler|hybrid|mixes/i.test(p));
        check(L + 'style label for corner ' + (i ? 'B' : 'A') + ' is backed by v_fighter_style', shown ? has : true, 'shown=' + shown + ' rows=' + styles.filter(s => s.fighter_id === fid).map(s => s.weight_class + ':' + s.style + '(' + s.sample_fights + ')').join(','));
        if (!shown) check(L + 'missing style for corner ' + (i ? 'B' : 'A') + ' is stated', /Not enough UFC fights on record to measure a style/.test(o.cols[i].text));
      });
      check(L + 'no training-background claims', !BG.test(o.all));
      check(L + 'recorded results are not listed under tendencies', o.cols.every(c => { const i = c.text.indexOf('Statistical tendencies'); const j = c.text.indexOf('Recorded results'); const seg = c.text.slice(i, j > i ? j : undefined); return !/UFC wins came by|UFC losses came by|went to the judges/.test(seg); }));
      check(L + 'missing data is labelled (no blank cells)', !/undefined|NaN|null%/.test(o.all));
      check(L + 'existing sections still render', o.sections.every(s => +s.split(':')[1] > 0), o.sections.join(' '));
      check(L + 'no horizontal overflow', await overflow(page) <= 1, 'excess ' + await overflow(page) + 'px');
      check(L + 'no console/page errors', errs.length === 0, errs.slice(0, 3).join(' | '));
      await page.screenshot({ path: path.join(OUT, 'fight-' + id + '-' + vp.name + '.png'), fullPage: true });
      if (vp.mobile) {
        // nav works on the phone: open the menu if there is one, then go to Card Lab
        const navLink = await page.$('nav.cfl-nav a[href*="index.html#next"], nav.cfl-nav a[href="/"], nav.cfl-nav a[href="index.html"]');
        const burger = await page.$('nav.cfl-nav button');
        if (burger && !(navLink && await navLink.isVisible())) await burger.click().catch(() => {});
        const link = await page.$('nav.cfl-nav a[href*="index.html#next"]') || navLink;
        let navOk = false;
        if (link) { await Promise.all([page.waitForURL(u => !/fight\.html/.test(String(u)), { timeout: 20000 }).catch(() => {}), link.click().catch(() => {})]); navOk = !/fight\.html/.test(page.url()); }
        check(L + 'nav takes a phone visitor back to Card Lab', navOk, page.url());
      }
      await ctx.close();
    }
  }
  await browser.close();
  console.log('\n' + (fails.length ? fails.length + ' FAILED:\n  ' + fails.join('\n  ') : 'ALL CHECKS PASSED'));
  process.exit(fails.length ? 1 : 0);
}
main().catch(e => { console.error(e); process.exit(2); });
