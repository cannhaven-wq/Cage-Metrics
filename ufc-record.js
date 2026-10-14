/* ==========================================================================
   Cannon Fight Lab — ufc-record.js (T-084)
   Every page that shows a fighter's UFC record gets it from here.

   `fighters.ufc_wins / ufc_losses / ufc_draws` is wrong for about two fighters
   in three (T-083: Jon Jones read 12-11; he is 22-1). The authoritative
   record is `v_fighter_ufc_record`, counted from completed active bookings in
   `fights` by the same rule as fight-lab.js.

   This module loads that view for the fighters a page already holds and
   OVERWRITES ufc_wins / ufc_losses / ufc_draws on those objects, so existing
   display code (cfl.formatRecord(f.ufc_wins, ...), fight-insights hasTape,
   the prerender templates) shows the right number without being rewritten.
   It also sets ufc_no_contests.

     * A fighter with no row in the view has no completed UFC fight: 0-0-0.
     * If the view could not be read, the three fields are set to NULL, never
       left holding the stale stored numbers. Pages already render NULL as "—"
       or fall back to the labelled career record. `ufc_record_unavailable` is
       set so a page can say so.

   Works in the browser (window.cflUfcRecord) and in Node (require) for
   build/prerender.js. apply() is pure; load() takes the Supabase client.
   ========================================================================== */
(function () {
  'use strict';

  const COLUMNS = 'fighter_id, ufc_wins, ufc_losses, ufc_draws, ufc_no_contests';
  const CHUNK = 150;   // ids per in.(...) request, keeps the URL well short

  // Pure. `rows` = view rows, or null when the view could not be read.
  function apply(fighters, rows) {
    const list = (fighters || []).filter(Boolean);
    if (rows == null) {
      list.forEach(f => {
        f.ufc_wins = null; f.ufc_losses = null; f.ufc_draws = null;
        f.ufc_no_contests = null; f.ufc_record_unavailable = true;
      });
      return list;
    }
    const by = new Map(rows.map(r => [Number(r.fighter_id), r]));
    list.forEach(f => {
      const r = by.get(Number(f.id));
      f.ufc_wins = r ? Number(r.ufc_wins) : 0;
      f.ufc_losses = r ? Number(r.ufc_losses) : 0;
      f.ufc_draws = r ? Number(r.ufc_draws) : 0;
      f.ufc_no_contests = r ? Number(r.ufc_no_contests) : 0;
      f.ufc_record_unavailable = false;
    });
    return list;
  }

  // Reads the view. opts.all = every row (list pages); otherwise only the ids
  // given. Resolves to rows, or null on any error — never throws.
  async function load(sb, ids, opts) {
    opts = opts || {};
    try {
      if (opts.all) {
        // Ordered paging: PostgREST pages without an ORDER BY are not stable,
        // and an unstable page silently drops rows (T-027).
        const out = [];
        for (let from = 0; ; from += 1000) {
          const { data, error } = await sb.from('v_fighter_ufc_record').select(COLUMNS)
            .order('fighter_id', { ascending: true }).range(from, from + 999);
          if (error) return null;
          out.push(...(data || []));
          if (!data || data.length < 1000) break;
        }
        return out;
      }
      const uniq = [...new Set((ids || []).filter(x => x != null).map(Number))];
      const out = [];
      for (let i = 0; i < uniq.length; i += CHUNK) {
        const { data, error } = await sb.from('v_fighter_ufc_record').select(COLUMNS)
          .in('fighter_id', uniq.slice(i, i + CHUNK));
        if (error) return null;
        out.push(...(data || []));
      }
      return out;
    } catch (e) { return null; }
  }

  // Load and apply in one step. Returns the same array.
  async function attach(sb, fighters, opts) {
    const list = (fighters || []).filter(Boolean);
    const rows = await load(sb, list.map(f => f.id), opts);
    return apply(list, rows);
  }

  const api = { COLUMNS, apply, load, attach };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else window.cflUfcRecord = api;
})();
