# Macau fetch — event 113, model v5
Generated: 2026-05-30T17:06:53.541Z

## Event
#113: UFC Fight Night: Song vs. Figueiredo  (2026-05-30, upcoming=false)

## Upcoming events (is_upcoming=true)
  #114  2026-06-06  UFC Fight Night: Muhammad vs. Bonfim
  #115  2026-06-14  UFC Freedom 250
  #116  2026-06-20  UFC Fight Night: Kape vs. Horiguchi
  #2510  2026-06-27  UFC Fight Night: Fiziev vs. Torres

## v_event_accuracy for event 113
[
  {
    "event_id": 113,
    "event_name": "UFC Fight Night: Song vs. Figueiredo",
    "event_date": "2026-05-30",
    "committed_picks": 11,
    "excluded_picks": 1,
    "hits": 8,
    "misses": 3,
    "accuracy_pct": 72.7,
    "bets_with_odds": 0,
    "total_pnl": null,
    "roi_pct": null
  }
]

## Actual results (13 fights)
  Song Yadong vs Deiveson Figueiredo [MAIN] → WON: Song Yadong (Submission, R2)
  Zhang Mingyang vs Alonzo Menifield → WON: Alonzo Menifield (KO/TKO, R1)
  Sergei Pavlovich vs Tallison Teixeira → WON: Sergei Pavlovich (KO/TKO, R1)
  Kai Asakura vs Cameron Smotherman → WON: Kai Asakura (KO/TKO, R1)
  Alex Perez vs Sumudaerji → not yet decided
  Carlston Harris vs Jake Matthews → WON: Jake Matthews (Decision - Unanimous, R3)
  Yi Sak Lee vs Luis Felipe Dias → WON: Luis Felipe Dias (KO/TKO, R1)
  Aoriqileng vs Cody Haddon → WON: Cody Haddon (KO/TKO, R2)
  Rei Tsuruya vs Luis Gurule → WON: Rei Tsuruya (Submission, R1)
  Angela Hill vs Xiong Jingnan → WON: Angela Hill (Decision - Unanimous, R3)
  Loma Lookboonmee vs Jaqueline Amorim → WON: Jaqueline Amorim (Submission, R1)
  Zhu Kangjie vs Rodrigo Vera → WON: Rodrigo Vera (KO/TKO, R1)
  Ding Meng vs Jose Henrique → WON: Jose Henrique (Decision - Split, R3)

## v5 predictions for 2026-05-30: 12 rows
  ✓ HIT                        v5 picked (fight 38: Song Yadong vs Deiveson Figueiredo) @ 78.6%
  ✗ MISS                       v5 picked (fight 39: Zhang Mingyang vs Alonzo Menifield) @ 66.6%
  ✓ HIT                        v5 picked (fight 43: Carlston Harris vs Jake Matthews) @ 76.6%
  ✓ HIT                        v5 picked (fight 40: Sergei Pavlovich vs Tallison Teixeira) @ 69.7%
  ungraded                     v5 picked (fight 42: Alex Perez vs Sumudaerji) @ 53.0%
  ✓ HIT                        v5 picked (fight 48: Loma Lookboonmee vs Jaqueline Amorim) @ 60.8%

## v5 accuracy on this card: 4/5 = 80.0%

## RAW: model_predictions (v5)
```json
[
  {
    "id": 102777,
    "model_version": "v5",
    "fight_id": 38,
    "fighter_id": 1200,
    "side": "A",
    "event_date": "2026-05-30",
    "model_p": 0.785889,
    "opener_implied_p": 0.75,
    "opener_american_odds": -300,
    "edge": 0.035889,
    "would_bet": false,
    "outcome_known": true,
    "won": true,
    "pnl_usd": null,
    "created_at": "2026-05-30T05:53:50.053733+00:00"
  },
  {
    "id": 102778,
    "model_version": "v5",
    "fight_id": 38,
    "fighter_id": 4866,
    "side": "B",
    "event_date": "2026-05-30",
    "model_p": 0.201981,
    "opener_implied_p": 0.285714,
    "opener_american_odds": 250,
    "edge": -0.083733,
    "would_bet": false,
    "outcome_known": true,
    "won": false,
    "pnl_usd": null,
    "created_at": "2026-05-30T05:53:50.053733+00:00"
  },
  {
    "id": 102779,
    "model_version": "v5",
    "fight_id": 39,
    "fighter_id": 35,
    "side": "A",
    "event_date": "2026-05-30",
    "model_p": 0.666029,
    "opener_implied_p": 0.75,
    "opener_american_odds": -300,
    "edge": -0.083971,
    "would_bet": false,
    "outcome_known": true,
    "won": false,
    "pnl_usd": null,
    "created_at": "2026-05-30T05:53:50.053733+00:00"
  },
  {
    "id": 102780,
    "model_version": "v5",
    "fight_id": 39,
    "fighter_id": 2559,
    "side": "B",
    "event_date": "2026-05-30",
    "model_p": 0.311279,
    "opener_implied_p": 0.285714,
    "opener_american_odds": 250,
    "edge": 0.025565,
    "would_bet": false,
    "outcome_known": true,
    "won": true,
    "pnl_usd": null,
    "created_at": "2026-05-30T05:53:50.053733+00:00"
  },
  {
    "id": 107069,
    "model_version": "v5",
    "fight_id": 43,
    "fighter_id": 2694,
    "side": "A",
    "event_date": "2026-05-30",
    "model_p": 0.227227,
    "opener_implied_p": 0.37037,
    "opener_american_odds": 170,
    "edge": -0.143143,
    "would_bet": false,
    "outcome_known": true,
    "won": false,
    "pnl_usd": null,
    "created_at": "2026-05-30T05:53:51.458786+00:00"
  },
  {
    "id": 107070,
    "model_version": "v5",
    "fight_id": 43,
    "fighter_id": 2938,
    "side": "B",
    "event_date": "2026-05-30",
    "model_p": 0.766386,
    "opener_implied_p": 0.666667,
    "opener_american_odds": -200,
    "edge": 0.099719,
    "would_bet": true,
    "outcome_known": true,
    "won": true,
    "pnl_usd": null,
    "created_at": "2026-05-30T05:53:51.458786+00:00"
  },
  {
    "id": 107071,
    "model_version": "v5",
    "fight_id": 40,
    "fighter_id": 1488,
    "side": "A",
    "event_date": "2026-05-30",
    "model_p": 0.697479,
    "opener_implied_p": 0.714286,
    "opener_american_odds": -250,
    "edge": -0.016807,
    "would_bet": false,
    "outcome_known": true,
    "won": true,
    "pnl_usd": null,
    "created_at": "2026-05-30T05:53:51.458786+00:00"
  },
  {
    "id": 107072,
    "model_version": "v5",
    "fight_id": 40,
    "fighter_id": 3311,
    "side": "B",
    "event_date": "2026-05-30",
    "model_p": 0.294031,
    "opener_implied_p": 0.322581,
    "opener_american_odds": 210,
    "edge": -0.02855,
    "would_bet": false,
    "outcome_known": true,
    "won": false,
    "pnl_usd": null,
    "created_at": "2026-05-30T05:53:51.458786+00:00"
  },
  {
    "id": 107073,
    "model_version": "v5",
    "fight_id": 42,
    "fighter_id": 2586,
    "side": "A",
    "event_date": "2026-05-30",
    "model_p": 0.499693,
    "opener_implied_p": 0.512195,
    "opener_american_odds": -105,
    "edge": -0.012502,
    "would_bet": false,
    "outcome_known": false,
    "won": null,
    "pnl_usd": null,
    "created_at": "2026-05-30T05:53:51.458786+00:00"
  },
  {
    "id": 107074,
    "model_version": "v5",
    "fight_id": 42,
    "fighter_id": 2363,
    "side": "B",
    "event_date": "2026-05-30",
    "model_p": 0.530074,
    "opener_implied_p": 0.534884,
    "opener_american_odds": -115,
    "edge": -0.00481,
    "would_bet": false,
    "outcome_known": false,
    "won": null,
    "pnl_usd": null,
    "created_at": "2026-05-30T05:53:51.458786+00:00"
  },
  {
    "id": 107107,
    "model_version": "v5",
    "fight_id": 48,
    "fighter_id": 3984,
    "side": "A",
    "event_date": "2026-05-30",
    "model_p": 0.357518,
    "opener_implied_p": 0.322581,
    "opener_american_odds": 210,
    "edge": 0.034937,
    "would_bet": false,
    "outcome_known": true,
    "won": false,
    "pnl_usd": null,
    "created_at": "2026-05-30T05:53:51.458786+00:00"
  },
  {
    "id": 107108,
    "model_version": "v5",
    "fight_id": 48,
    "fighter_id": 2549,
    "side": "B",
    "event_date": "2026-05-30",
    "model_p": 0.608383,
    "opener_implied_p": 0.714286,
    "opener_american_odds": -250,
    "edge": -0.105903,
    "would_bet": false,
    "outcome_known": true,
    "won": true,
    "pnl_usd": null,
    "created_at": "2026-05-30T05:53:51.458786+00:00"
  }
]
```
## RAW: fights
```json
[
  {
    "id": 38,
    "fighter_a_id": 1200,
    "fighter_b_id": 4866,
    "fighter_a_name": "Song Yadong",
    "fighter_b_name": "Deiveson Figueiredo",
    "winner_id": 1200,
    "method": "Submission",
    "end_round": 2,
    "weight_class": "Bantamweight",
    "is_main_event": true
  },
  {
    "id": 39,
    "fighter_a_id": 35,
    "fighter_b_id": 2559,
    "fighter_a_name": "Zhang Mingyang",
    "fighter_b_name": "Alonzo Menifield",
    "winner_id": 2559,
    "method": "KO/TKO",
    "end_round": 1,
    "weight_class": "Light Heavyweight",
    "is_main_event": false
  },
  {
    "id": 40,
    "fighter_a_id": 1488,
    "fighter_b_id": 3311,
    "fighter_a_name": "Sergei Pavlovich",
    "fighter_b_name": "Tallison Teixeira",
    "winner_id": 1488,
    "method": "KO/TKO",
    "end_round": 1,
    "weight_class": "Heavyweight",
    "is_main_event": false
  },
  {
    "id": 41,
    "fighter_a_id": 2981,
    "fighter_b_id": 3844,
    "fighter_a_name": "Kai Asakura",
    "fighter_b_name": "Cameron Smotherman",
    "winner_id": 2981,
    "method": "KO/TKO",
    "end_round": 1,
    "weight_class": "Bantamweight",
    "is_main_event": false
  },
  {
    "id": 42,
    "fighter_a_id": 2586,
    "fighter_b_id": 2363,
    "fighter_a_name": "Alex Perez",
    "fighter_b_name": "Sumudaerji",
    "winner_id": null,
    "method": "No Contest",
    "end_round": 2,
    "weight_class": "Flyweight",
    "is_main_event": false
  },
  {
    "id": 43,
    "fighter_a_id": 2694,
    "fighter_b_id": 2938,
    "fighter_a_name": "Carlston Harris",
    "fighter_b_name": "Jake Matthews",
    "winner_id": 2938,
    "method": "Decision - Unanimous",
    "end_round": 3,
    "weight_class": "Welterweight",
    "is_main_event": false
  },
  {
    "id": 44,
    "fighter_a_id": 2889,
    "fighter_b_id": 4266,
    "fighter_a_name": "Yi Sak Lee",
    "fighter_b_name": "Luis Felipe Dias",
    "winner_id": 4266,
    "method": "KO/TKO",
    "end_round": 1,
    "weight_class": "Middleweight",
    "is_main_event": false
  },
  {
    "id": 45,
    "fighter_a_id": 630,
    "fighter_b_id": 44,
    "fighter_a_name": "Aoriqileng",
    "fighter_b_name": "Cody Haddon",
    "winner_id": 44,
    "method": "KO/TKO",
    "end_round": 2,
    "weight_class": "Bantamweight",
    "is_main_event": false
  },
  {
    "id": 46,
    "fighter_a_id": 2353,
    "fighter_b_id": 823,
    "fighter_a_name": "Rei Tsuruya",
    "fighter_b_name": "Luis Gurule",
    "winner_id": 2353,
    "method": "Submission",
    "end_round": 1,
    "weight_class": "Flyweight",
    "is_main_event": false
  },
  {
    "id": 47,
    "fighter_a_id": 1021,
    "fighter_b_id": 65,
    "fighter_a_name": "Angela Hill",
    "fighter_b_name": "Xiong Jingnan",
    "winner_id": 1021,
    "method": "Decision - Unanimous",
    "end_round": 3,
    "weight_class": "Strawweight",
    "is_main_event": false
  },
  {
    "id": 48,
    "fighter_a_id": 3984,
    "fighter_b_id": 2549,
    "fighter_a_name": "Loma Lookboonmee",
    "fighter_b_name": "Jaqueline Amorim",
    "winner_id": 2549,
    "method": "Submission",
    "end_round": 1,
    "weight_class": "Strawweight",
    "is_main_event": false
  },
  {
    "id": 8780,
    "fighter_a_id": 729,
    "fighter_b_id": 10976,
    "fighter_a_name": "Zhu Kangjie",
    "fighter_b_name": "Rodrigo Vera",
    "winner_id": 10976,
    "method": "KO/TKO",
    "end_round": 1,
    "weight_class": "Featherweight",
    "is_main_event": false
  },
  {
    "id": 26712,
    "fighter_a_id": 5102,
    "fighter_b_id": 4039,
    "fighter_a_name": "Ding Meng",
    "fighter_b_name": "Jose Henrique",
    "winner_id": 4039,
    "method": "Decision - Split",
    "end_round": 3,
    "weight_class": "Welterweight",
    "is_main_event": false
  }
]
```
