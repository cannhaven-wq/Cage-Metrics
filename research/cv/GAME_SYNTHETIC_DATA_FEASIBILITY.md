# Can EA Sports UFC games train CFL's computer vision? — feasibility report

**Date:** 2026-10-12 · **Author:** Claude · **Status:** research only. No code,
no downloads of game data, no purchase, no production change.

## The plain verdict

**No to pulling moves out of the game files. A conditional maybe to recording
gameplay, and that needs EA's written permission before anyone records a frame.
The idea is worth a cheap test, but the test doesn't need the game at all.**

In one sentence, for a friend: *the game's move files are locked on consoles
and EA's rules forbid digging into them, and filming yourself playing is
technically easy but probably needs EA's OK for a paid product. Open motion-capture
data gets you the same kind of training examples with none of the legal risk.*

Two things to know first:

1. **CFL has no computer-vision system today.** Neither `Cage-Metrics` nor
   `cage-metrics-scrapper` has any video, pose or vision code (searched
   2026-10-12). This report is about the training-data source for a system that
   hasn't been built yet. So the first proof of concept has to show the
   *vision itself* can work on real UFC footage, before it asks where the
   training data comes from.
2. **What would actually limit this project is labelled real footage, not
   synthetic volume.** Sections 4 and 5 are built around that.

---

## Ranking

| rank | approach | technically | legally / policy | verdict |
|---|---|---|---|---|
| **1** | **Pose-skeleton model, trained on open/owned motion data + a small hand-labelled real set** | Proven tooling (pose estimators, PYSKL / PoseC3D, ST-GCN) | Clean: open mocap licences, our own labels | **Do this first** |
| **2** | **Same pipeline, with skeletons taken from recorded UFC-game gameplay** | Feasible: capture card or console share, labels from a scripted move list | **Gated:** EA content policy covers personal/fan use, and a paid product training a model isn't clearly inside it. Needs EA permission and a game purchase | **Only after #1 passes, and only with permission (L3)** |
| 3 | Gameplay pixels used directly (RGB models) | Feasible | Same gate as #2, plus the dataset would hold EA's rendered imagery and licensed fighter likenesses | Not recommended: weaker transfer and more exposure |
| **4** | **Extracting animation / move metadata from game assets** | Requires decrypted console dumps; no tool supports any UFC title | Requires bypassing console security; prohibited by EA's terms | **Not viable. Do not pursue** |

---

## 1. Is the move or animation metadata accessible?

**Not without breaking console security.**

- **Every EA UFC title is console-only.** UFC 3 and 4 (PS4 / Xbox One, EA's
  *Ignite* engine), UFC 5 (2023, PS5 / Xbox Series X|S, the series' first
  *Frostbite* title), and UFC 6 (released 19 June 2026, PS5 / Xbox Series X|S).
  Coverage of UFC 6 says a PC version is "in development" with no date, and
  nothing confirms it.
  ([Sportskeeda](https://sportskeeda.com/esports/will-ufc-5-available-pc),
  [EA UFC 5 presentation deep dive](https://ea.com/de/games/ufc/ufc-5/news/ufc-5-presentation),
  [Insider Gaming](https://insider-gaming.com/ufc-6-release-date-platforms/),
  [LowKick MMA](https://www.lowkickmma.com/ea-sports-ufc-6-set-for-june-19-release-on-ps5-and-xbox-series-xs/))
- **Console game files are encrypted at rest.** The only way to get at the
  asset files is a decrypted dump from a jailbroken console. That is exactly
  the "bypassing DRM or console security" this brief rules out.
- **What the engines would contain, in principle:** a Frostbite or Ignite
  fighting game almost certainly ships motion-capture animation clips and an
  animation state graph (move → clip → hit window → reaction). That would be
  richly labelled data. But nobody has published the format for any UFC
  title, so this is inference, not a finding.
- **The closest public research is for FIFA, not UFC.** A community thread
  documents FIFA's Ignite `.cba` animation container, EA's self-describing
  "GenericData" format
  ([SoccerGaming](https://soccergaming.com/forums/threads/animation-files-research-cbac.6476373/)).
  Nothing shows UFC uses the same layout, and the thread is unverified
  community work.

## 2. Can existing tools inspect the assets without bypassing DRM?

**No.**

- **The Frostbite modding tools don't support UFC.**
  [Frosty Toolsuite](https://www.mintlify.com/CadeEvs/FrostyToolsuite/resources/faq)
  lists Battlefield, FIFA 18–20, Madden 19–20 and Need for Speed, and
  [Frostbite Modding Tool](https://patreon.com/FrostbiteModdingTool) is in the
  same family. Both work on **PC** installs, and no UFC title has a PC
  install.
- **Unreal-engine extractors (CUE4Parse, UEFormat) don't apply.** UFC isn't
  built on Unreal.
- **If UFC 6 ever reaches PC**, the technical "no" might turn into a "maybe".
  The policy "no" stays. EA's software licence bars reverse engineering and
  "extracting source code or other data from the Application" unless EA
  authorises it ([Origin EULA, 2016](https://media.contentapi.ea.com/content/dam/eacom/en-us/eula/eula-origin-en-row-pc-5-26-16.pdf)),
  and the [EA content policy](https://help.ea.com/en/articles/security-and-rules/ea-content-policy/)
  excludes data mining. The 2024 US §1201 exemptions add nothing that covers
  this ([Finnegan summary](https://www.finnegan.com/en/insights/ip-updates/final-rule-issued-in-the-us-copyright-offices-ninth-triennial-section-1201-proceeding.html)).
- **Caveat:** this sandbox's network blocks `ea.com`, so I couldn't read the
  *current* EA User Agreement text directly. Both points above come from search
  results and the 2016 licence. Anyone acting on this must read the current
  terms first.

## 3. Can labelled technique examples come from gameplay instead?

**Technically yes. Policy-wise, not without EA's permission.**

**How it would work.** No modification, no memory reading, no automation of
the game:

- **Recording:** an HDMI capture card, or the console's own share/record
  feature. This is an ordinary, supported way to record gameplay.
- **Labels from a script, not from the game.** In Practice Mode (EA confirms
  it exists under *Learn*,
  [EA help](https://help.ea.com/en/help/ufc/ufc-5/intro-to-ufc-5/)), an
  operator performs a fixed move list: "10 × lead jab, 10 × rear body kick,
  10 × double-leg…". The label for each clip is whatever the script said was
  thrown. Logging the button press with a timestamp tightens where each clip
  starts and ends.
- **Variety:** different fighters, stances, weight classes and camera presets.
  An AI-vs-AI fight would add realistic sequences, but its labels would need
  hand annotation.

**What this does not give you.** The game's own internal labels, such as
exact hit frames, landed vs. blocked, or damage. Those are the valuable part
of route 4, and gameplay can't reach them. "Landed" would need a human judging
each clip, just as it would on real footage.

**Why it's gated:**

- **Policy.** EA's content policy allows game content in personal projects and
  ad-monetised videos. It forbids paywalls and data mining
  ([EA content policy](https://help.ea.com/en/articles/security-and-rules/ea-content-policy/)).
  A model trained on that footage, inside a product CFL plans to charge for,
  isn't obviously personal use. EA publishes a permission-request route on the
  same help site. Whether to use it is a **legal/compliance choice: L3**,
  `CRITICAL_GATES.md` item 9.
- **Third-party likeness.** The game licenses real fighters' likenesses and
  UFC marks from the UFC. EA's permission may not cover them.
- **Cost.** The game and a capture card both cost money. That is **L3, item 6**,
  and out of scope for this brief.

## 4. Turning examples into a training dataset

**Use poses (skeletons), not pixels.** This choice does most of the work. A
pose estimator turns each frame into 17 joint positions per fighter. Training
on joints instead of images throws away the game's textures, lighting and
rendering, which is the biggest source of the gap between the game and real
footage. As a side benefit, the stored dataset holds no EA imagery. That
reduces the exposure, but it is not a legal clearance: the skeletons are still
derived from the game.

Pipeline (the same for routes 1 and 2; only the source changes):

1. **Clip** each labelled action into a window of about 1–2 s (around 30–60
   frames).
2. **Pose:** run one off-the-shelf 2D estimator (e.g. RTMPose or ViTPose via
   MMPose) on every frame, for both fighters. **Use the same estimator on
   synthetic and real data.** Otherwise the model learns which estimator was
   used instead of which move was thrown.
3. **Track and assign corners** (red/blue). Clinch and ground exchanges are
   where tracking swaps identities. Flag low-confidence frames rather than
   trusting them.
4. **Normalise:** centre on the hips, scale by torso length, mirror southpaw
   clips (with the matching label flip, e.g. lead ↔ rear).
5. **Class list, matched to what UFCStats already counts**, so real labels
   exist to check against: significant strike to head / body / leg;
   distance / clinch / ground position; takedown attempt; knockdown. Start with
   3 classes plus "nothing happening", not 20.
6. **Model:** PoseC3D or ST-GCN from the open
   [PYSKL](https://arxiv.org/pdf/2205.09443) toolbox. PoseC3D is reported as
   more robust to pose-estimation noise and better across datasets than graph
   networks ([Duan et al., CVPR 2022](https://openaccess.thecvf.com/content/CVPR2022/html/Duan_Revisiting_Skeleton-Based_Action_Recognition_CVPR_2022_paper.html)).
7. **Record where every clip came from** (source, licence, label method), the
   same way CFL records provenance for odds.

**The clean synthetic source for route 1:** open motion capture (e.g. the CMU
mocap library, which includes boxing and martial-arts takes; licence to be
checked per source) put onto SMPL bodies and rendered from varied camera
angles in Blender. CFL would own the whole pipeline. This is how
GTA-Human, GATA and similar datasets earned their transfer results, minus the
game ([GTA-Human](https://arxiv.org/abs/2110.07588v2),
[GATA, CVPR 2022](https://openaccess.thecvf.com/content/CVPR2022/papers/Guo_Learning_Video_Representations_of_Human_Motion_From_Synthetic_Data_CVPR_2022_paper.pdf)).

## 5. Measuring whether game-trained models work on real fights

The question to answer is not "does it reach X% accuracy". It is: **how many
real hand labels does the synthetic data save?** That is the only reason to
use it.

**Real test set first, frozen, never trained on.** Three sources, from
cheapest:

- [**MMA Fighter Pose dataset**](https://data.mendeley.com/datasets/c456bnk8bm):
  5,109 UFC stand-up frames from 20 fights, with 17 COCO keypoints per fighter.
  It tests **the pose estimator**, not actions. Grappling and clinch are
  deliberately excluded.
- [**BoxingVI**](https://arxiv.org/pdf/2511.16524v1): 6,915 punch clips, six
  punch types, from YouTube sparring. It tests **strike classification** on
  real video. It is boxing, so there are no kicks or takedowns.
- **CFL's own UFCStats per-round counts** (`sig_str_landed`, `td_landed`,
  `ctrl_seconds`), as **weak labels**: a model's per-round counts should track
  the official ones. It's free and covers every UFC fight, but it gives counts,
  not timestamps, so it is a sanity check, not a training label. It also
  requires footage CFL has the rights to analyse, which is a separate
  question (UFC broadcast footage is itself licensed content).

**The comparison, run at several real-label budgets (25 / 50 / 100 / 200
clips per class):**

| arm | trained on |
|---|---|
| A | real labels only |
| B | synthetic only (zero real) |
| C | synthetic pre-training, then the same real labels as A |

**Report macro-F1 per class, with bootstrap intervals over fights, not over
clips** (clips from one fight are not independent). Synthetic data is worth
keeping only if **C beats A at small budgets, with an interval that clears
zero.** B alone shows the size of the gap, and the literature suggests it will
be large wherever the action depends on context such as cage, clinch or
contact ([SynAPT, NeurIPS 2022](https://neurips.cc/virtual/2022/poster/55635)).
Write the threshold down **before** looking at any results, the way
`cfl_engine/dur001/PREREGISTRATION.md` did. A threshold picked after seeing
the numbers proves nothing.

**Expect it to break down in this order:** distance strikes transfer best,
then kicks, then clinch work, then ground work. Two fighters overlapping
defeats 2D pose estimation, whatever data the model was trained on.

---

## The smallest proof of concept that could work

**Run it on route 1. It needs no game, no purchase and no permission, and it
answers the question every route depends on.**

**Step 0, the gate (about half a day, CPU is fine).** Run one pose estimator
over the MMA Fighter Pose dataset and score it against the hand-labelled
keypoints (PCK@0.2, per joint). **If wrists and ankles fail on real UFC
frames, no training data from any source will rescue a skeleton model.** In
that case, stop and report.

**Step 1, the transfer test (about 2–3 days, one consumer GPU).**

- 3 classes plus background: *jab/cross*, *hook*, *uppercut*, so that
  BoxingVI supplies the real labels.
- Synthetic: about 300 clips per class rendered from open boxing mocap at
  randomised camera angles.
- Real: BoxingVI, **split by sparring session**, not by clip.
- Train ST-GCN for arms A / B / C at 25 and 100 real clips per class.
- **Pass:** C beats A at 25 clips per class, with the interval clearing zero.

**If Step 1 passes**, the idea is real and it becomes worth asking whether
game footage adds anything open mocap doesn't: kicks, takedowns, cage
positions and fighter variety that open mocap is thin on. That question
starts with **T-079** (the owner decides whether to approach EA). **If it
fails**, the game would most likely fail the same way, and we have saved the
purchase and the legal question.

**What not to start before Step 1 passes:** asset reverse engineering of any
kind, any capture rig, any dataset bigger than the test above.

## Uncertainties stated plainly

- The current EA User Agreement couldn't be fetched from this environment
  (`ea.com` doesn't resolve here). The terms quoted are the 2016 Origin
  licence and EA's content policy as indexed by search. **This report is not
  legal advice.**
- Whether UFC 5 or 6 has a replay or free camera, or on-screen move names in
  Practice Mode, is unconfirmed. It changes how much camera variety route 2
  could give, not whether route 2 is allowed.
- No published study measures game-to-real transfer for MMA specifically. The
  transfer expectations above come from general human-action work (GTA-Human,
  GATA, SynAPT, ElderSim) and one boxing thesis
  ([Takouti, ÉTS](https://espace.etsmtl.ca/3787/1/TAKOUTI_Yosr-1.pdf)).
