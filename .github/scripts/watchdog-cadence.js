// =============================================================================
// watchdog-cadence.js — how often has the dead man actually been let run?
// =============================================================================
// PLAIN ENGLISH: the pre-fight-record watchdog can only shout when GitHub runs
// it. This asks GitHub how often it has been run lately, and says so.
//
// This is the one thing dead-man.yml cannot do for itself. If GitHub stops
// delivering the schedule — throttling, or the 60-day inactivity disable — the
// watchdog goes dark in exactly the silent way it exists to prevent. Nothing
// inside GitHub can report that in the moment. What it CAN do is make the hole
// visible on the next run that does land, which is strictly better than never.
//
// Prints, never fails: a cadence report that reddens the build would make the
// red tick mean two different things, and the red tick is the alarm for the
// record being missing.
//
// ENV: GH_TOKEN, GITHUB_REPOSITORY, GITHUB_SERVER_URL
// =============================================================================

'use strict';

const REPO = process.env.GITHUB_REPOSITORY;
const TOKEN = process.env.GH_TOKEN;
const WORKFLOW = 'dead-man.yml';

// Three daily positions means a healthy gap is under ~13h. 30h allows a whole
// missed position plus slack before it is worth a word.
const WORST_ACCEPTABLE_HOURS = 30;

async function main() {
  if (!REPO || !TOKEN) {
    console.log('[cadence] no repo or token in the environment — skipping.');
    return;
  }
  const url = `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}`
            + `/runs?event=schedule&per_page=30`;
  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${TOKEN}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
    },
  });
  if (!res.ok) {
    console.log(`[cadence] GitHub returned HTTP ${res.status} — cannot report cadence.`);
    return;
  }
  const body = await res.json();
  const runs = (body.workflow_runs || [])
    .map(r => Date.parse(r.run_started_at))
    .filter(t => !Number.isNaN(t))
    .sort((a, b) => b - a);

  if (runs.length < 2) {
    console.log(`[cadence] ${runs.length} prior scheduled run(s) recorded — no gap to measure yet.`);
    return;
  }

  const gaps = [];
  for (let i = 0; i < runs.length - 1; i++) gaps.push((runs[i] - runs[i + 1]) / 3600000);
  const worst = Math.max(...gaps);
  const median = [...gaps].sort((a, b) => a - b)[Math.floor(gaps.length / 2)];

  console.log(`[cadence] ${runs.length} scheduled deliveries on record.`);
  console.log(`[cadence] newest ${new Date(runs[0]).toISOString()}, `
            + `oldest ${new Date(runs[runs.length - 1]).toISOString()}`);
  console.log(`[cadence] median gap ${median.toFixed(1)}h, largest gap ${worst.toFixed(1)}h `
            + `(three daily positions should give under ~13h).`);

  if (worst > WORST_ACCEPTABLE_HOURS) {
    console.log(`::warning title=The watchdog went dark::`
      + `${worst.toFixed(1)}h passed without a scheduled run of ${WORKFLOW}. `
      + `GitHub is throttling the schedule or has disabled it after repository `
      + `inactivity. While it is dark, nothing is checking that the pre-fight `
      + `record exists before a card.`);
  }
}

main().catch(err => {
  // Deliberately not fatal — see the header.
  console.log(`[cadence] could not report cadence: ${err.message}`);
});
