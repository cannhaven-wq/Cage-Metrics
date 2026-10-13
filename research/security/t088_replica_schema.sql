-- =============================================================================
-- t088_replica_schema.sql — schema-only snapshot of production `public`, 2026-10-13
-- =============================================================================
-- For the T-088 rehearsal ONLY (tests/test_t088_rehearsal.py). Generated from
-- production's catalogs (tables, sequences, constraints, RLS flags, trigger
-- functions, triggers, policies and the exact anon/authenticated/PUBLIC grants
-- as they stood before T-088). No rows, no secrets. Foreign keys are left out,
-- so probe fixtures need no real users or fights.
-- PG16 locally: GRANT MAINTAIN lines are omitted (a PG17 privilege).
-- Load after t088_replica_bootstrap.sql. NEVER apply this to any real database.
-- =============================================================================
SET ROLE postgres;
CREATE TABLE public.billing_events (id bigint NOT NULL, stripe_event_id text NOT NULL, event_type text NOT NULL, user_id uuid, stripe_customer_id text, subscription_id text, applied_tier text, applied_expires_at timestamp with time zone, outcome text NOT NULL, detail text, received_at timestamp with time zone NOT NULL DEFAULT now());
CREATE TABLE public.cardio_style_snapshots (fight_id bigint, fighter_id bigint, event_date date, snapshot_basis text, sample_fights bigint, r1_minutes numeric, r3p_minutes numeric, cardio_score numeric, cardio_tier text, strk_score numeric, grapp_score numeric, style text);
CREATE TABLE public.email_subscribers (id bigint NOT NULL, email text NOT NULL, source text NOT NULL DEFAULT 'unknown'::text, created_at timestamp with time zone NOT NULL DEFAULT now(), last_sent_at timestamp with time zone, unsubscribed_at timestamp with time zone, unsubscribe_token text NOT NULL DEFAULT encode(gen_random_bytes(16), 'hex'::text));
CREATE TABLE public.events (id bigint NOT NULL, ufc_event_id text NOT NULL, name text NOT NULL, event_date date, location text, is_upcoming boolean DEFAULT false, ufc_url text, updated_at timestamp with time zone DEFAULT now());
CREATE TABLE public.fight_odds (id bigint NOT NULL, fight_id bigint NOT NULL, fighter_id bigint, book_id bigint NOT NULL, side character(1) NOT NULL, american_odds integer NOT NULL, implied_prob numeric(7,6), captured_at timestamp with time zone NOT NULL DEFAULT now(), source_url text, is_opener boolean NOT NULL DEFAULT false, is_closer boolean NOT NULL DEFAULT false, source_event_id text, feed_version text, source_commence_at timestamp with time zone, bout_started_at timestamp with time zone, proxy_cutoff_at timestamp with time zone, is_live boolean, provider_last_update timestamp with time zone, retrieved_at timestamp with time zone, opponent_fighter_id bigint, market_status text, raw jsonb);
CREATE TABLE public.fight_odds_consensus_snapshot (fight_id bigint NOT NULL, event_id bigint, fighter_a_id bigint, fighter_b_id bigint, fighter_a_name text, fighter_b_name text, american_odds_a integer, american_odds_b integer, implied_prob_a real, implied_prob_b real, bookmaker_count integer, fetched_at timestamp with time zone NOT NULL DEFAULT now());
CREATE TABLE public.fight_rounds (id bigint NOT NULL, fight_id bigint NOT NULL, round_number integer NOT NULL, fighter_a_id bigint, fighter_b_id bigint, a_kd integer, b_kd integer, a_sig_str_landed integer, b_sig_str_landed integer, a_sig_str_attempted integer, b_sig_str_attempted integer, a_total_str_landed integer, b_total_str_landed integer, a_total_str_attempted integer, b_total_str_attempted integer, a_td_landed integer, b_td_landed integer, a_td_attempted integer, b_td_attempted integer, a_sub_attempts integer, b_sub_attempts integer, a_rev integer, b_rev integer, a_ctrl_seconds integer, b_ctrl_seconds integer, a_head_landed integer, b_head_landed integer, a_body_landed integer, b_body_landed integer, a_leg_landed integer, b_leg_landed integer, a_distance_landed integer, b_distance_landed integer, a_clinch_landed integer, b_clinch_landed integer, a_ground_landed integer, b_ground_landed integer);
CREATE TABLE public.fight_start_estimates (id bigint NOT NULL, fight_id bigint NOT NULL, source text NOT NULL, start_at timestamp with time zone NOT NULL, observed_at timestamp with time zone NOT NULL DEFAULT now(), note text);
CREATE TABLE public.fighter_cardio (fighter_id integer NOT NULL, fade_slope double precision NOT NULL, fade_slope_dev double precision NOT NULL, population_slope double precision NOT NULL, slope_se double precision, total_min_fought double precision NOT NULL, min_past_10 double precision NOT NULL, n_fights integer NOT NULL, n_fights_reaching_r3 integer NOT NULL, n_round_obs integer NOT NULL, computed_at timestamp with time zone NOT NULL DEFAULT now());
CREATE TABLE public.fighter_ratings (fighter_id bigint NOT NULL, elo numeric(7,1) NOT NULL, elo_peak numeric(7,1) NOT NULL, n_fights integer NOT NULL, opp_elo_avg numeric(7,1), opp_elo_last5 numeric(7,1), wins_vs_rated integer, last_fight_date date, computed_at timestamp with time zone NOT NULL DEFAULT now());
CREATE TABLE public.fighter_snapshot_2025 (fighter_id bigint, name text, dob date, stance text, height_in numeric, reach_in numeric, ufc_fight_count bigint, total_minutes numeric, wins_pre2026 bigint, losses_pre2026 bigint, last_fight_date date, slpm numeric, sapm numeric, td_per_15 numeric, td_def_pct numeric, last5_wins bigint, last5_ko_losses bigint, last5_losses bigint);
CREATE TABLE public.fighters (id bigint NOT NULL, name text NOT NULL, nickname text, division text, is_champion boolean DEFAULT false, wins integer DEFAULT 0, losses integer DEFAULT 0, draws integer DEFAULT 0, height_in numeric, reach_in numeric, stance text, age integer, slpm numeric, str_acc integer, sapm numeric, str_def integer, td_avg numeric, td_acc integer, td_def integer, sub_avg numeric, ko_wins integer DEFAULT 0, sub_wins integer DEFAULT 0, dec_wins integer DEFAULT 0, last_5 text, ufc_url text, updated_at timestamp with time zone DEFAULT now(), dob date, ufc_wins integer DEFAULT 0, ufc_losses integer DEFAULT 0, ufc_draws integer DEFAULT 0, last_fight_date date, sex text, birth_place text, country text, country_code text, country_src text, country_checked_at timestamp with time zone);
CREATE TABLE public.fights (id bigint NOT NULL, ufc_fight_id text NOT NULL, event_id bigint, fighter_a_id bigint, fighter_b_id bigint, fighter_a_name text, fighter_b_name text, winner_id bigint, method text, method_detail text, end_round integer, end_time text, scheduled_rounds integer DEFAULT 3, weight_class text, is_title_fight boolean DEFAULT false, is_main_event boolean DEFAULT false, bonus text, a_kd integer, b_kd integer, a_sig_str_landed integer, b_sig_str_landed integer, a_sig_str_attempted integer, b_sig_str_attempted integer, a_total_str_landed integer, b_total_str_landed integer, a_total_str_attempted integer, b_total_str_attempted integer, a_td_landed integer, b_td_landed integer, a_td_attempted integer, b_td_attempted integer, a_sub_attempts integer, b_sub_attempts integer, a_rev integer, b_rev integer, a_ctrl_seconds integer, b_ctrl_seconds integer, a_head_landed integer, b_head_landed integer, a_body_landed integer, b_body_landed integer, a_leg_landed integer, b_leg_landed integer, a_distance_landed integer, b_distance_landed integer, a_clinch_landed integer, b_clinch_landed integer, a_ground_landed integer, b_ground_landed integer, ufc_url text, updated_at timestamp with time zone DEFAULT now(), bell_at timestamp with time zone, bout_order integer, is_active boolean NOT NULL DEFAULT true);
CREATE TABLE public.funnel_events (id bigint NOT NULL, event text NOT NULL, session_id text NOT NULL, path text, props jsonb NOT NULL DEFAULT '{}'::jsonb, created_at timestamp with time zone NOT NULL DEFAULT now());
CREATE TABLE public.hub_visits (id bigint NOT NULL, visitor_key uuid NOT NULL, event_id integer NOT NULL, page text NOT NULL, seen_on date NOT NULL DEFAULT ((now() AT TIME ZONE 'utc'::text))::date, created_at timestamp with time zone NOT NULL DEFAULT now());
CREATE TABLE public.master_dataset (fight_id bigint, event_date date, weight_class text, is_title_fight boolean, is_main_event boolean, scheduled_rounds integer, a_won integer, actual_method text, actual_end_round integer, went_distance integer, fighter_a_id bigint, a_dob date, a_stance text, a_height_in numeric, a_reach_in numeric, a_prior_fights bigint, a_prior_min numeric, a_prior_wins bigint, a_prior_losses bigint, a_prior_ko_wins bigint, a_prior_sub_wins bigint, a_prior_ko_losses bigint, a_days_since_last numeric, a_slpm numeric, a_sapm numeric, a_head_pm numeric, a_kd_per_15 numeric, a_td_per_15 numeric, a_ctrl_per_min numeric, a_td_def numeric, a_finish_rate numeric, a_last5_wins bigint, a_last5_ko_losses bigint, a_last5_count bigint, fighter_b_id bigint, b_dob date, b_stance text, b_height_in numeric, b_reach_in numeric, b_prior_fights bigint, b_prior_min numeric, b_prior_wins bigint, b_prior_losses bigint, b_prior_ko_wins bigint, b_prior_sub_wins bigint, b_prior_ko_losses bigint, b_days_since_last numeric, b_slpm numeric, b_sapm numeric, b_head_pm numeric, b_kd_per_15 numeric, b_td_per_15 numeric, b_ctrl_per_min numeric, b_td_def numeric, b_finish_rate numeric, b_last5_wins bigint, b_last5_ko_losses bigint, b_last5_count bigint);
CREATE TABLE public.master_dataset_v2 (fight_id bigint, event_date date, weight_class text, is_title_fight boolean, is_main_event boolean, scheduled_rounds integer, a_won integer, actual_method text, actual_end_round integer, went_distance integer, fighter_a_id bigint, a_dob date, a_stance text, a_height_in numeric, a_reach_in numeric, a_prior_fights bigint, a_prior_min numeric, a_prior_wins bigint, a_prior_losses bigint, a_prior_ko_wins bigint, a_prior_sub_wins bigint, a_prior_ko_losses bigint, a_days_since_last numeric, a_slpm numeric, a_sapm numeric, a_head_pm numeric, a_kd_per_15 numeric, a_td_per_15 numeric, a_ctrl_per_min numeric, a_td_def numeric, a_finish_rate numeric, a_last5_wins bigint, a_last5_ko_losses bigint, a_last5_count bigint, fighter_b_id bigint, b_dob date, b_stance text, b_height_in numeric, b_reach_in numeric, b_prior_fights bigint, b_prior_min numeric, b_prior_wins bigint, b_prior_losses bigint, b_prior_ko_wins bigint, b_prior_sub_wins bigint, b_prior_ko_losses bigint, b_days_since_last numeric, b_slpm numeric, b_sapm numeric, b_head_pm numeric, b_kd_per_15 numeric, b_td_per_15 numeric, b_ctrl_per_min numeric, b_td_def numeric, b_finish_rate numeric, b_last5_wins bigint, b_last5_ko_losses bigint, b_last5_count bigint, a_cardio_score numeric, a_cardio_tier text, a_strk_score numeric, a_grapp_score numeric, a_style text, b_cardio_score numeric, b_cardio_tier text, b_strk_score numeric, b_grapp_score numeric, b_style text);
CREATE TABLE public.model_edges (id bigint NOT NULL, fight_id bigint NOT NULL, event_date date NOT NULL, side character(1) NOT NULL, bet_fighter_id bigint NOT NULL, p_blend numeric NOT NULL, q_mkt numeric NOT NULL, edge numeric NOT NULL, stake_frac numeric NOT NULL, odds_at_publish integer, closing_odds integer, clv_pp numeric, clv_beat boolean, source text NOT NULL DEFAULT 'live'::text, model_version text NOT NULL DEFAULT 'engine_v1'::text, published_at timestamp with time zone NOT NULL DEFAULT now(), settled_at timestamp with time zone, closing_odds_pm integer, clv_pp_pm numeric, clv_beat_pm boolean, settled_pm_at timestamp with time zone);
CREATE TABLE public.model_picks (id bigint NOT NULL, fight_id bigint NOT NULL, event_date date NOT NULL, p_cal numeric NOT NULL, pick_fighter_id bigint NOT NULL, pick_side character(1) NOT NULL, tier text NOT NULL, source text NOT NULL DEFAULT 'live'::text, model_version text NOT NULL DEFAULT 'engine_v1'::text, published_at timestamp with time zone NOT NULL DEFAULT now());
CREATE TABLE public.model_predictions (id bigint NOT NULL, model_version text NOT NULL, fight_id bigint NOT NULL, fighter_id bigint NOT NULL, side character(1) NOT NULL, event_date date NOT NULL, model_p numeric(7,6) NOT NULL, opener_implied_p numeric(7,6), opener_american_odds integer, edge numeric(7,6), would_bet boolean NOT NULL DEFAULT false, outcome_known boolean NOT NULL DEFAULT false, won boolean, pnl_usd numeric(10,2), created_at timestamp with time zone NOT NULL DEFAULT now(), reconstructed boolean NOT NULL DEFAULT false);
CREATE TABLE public.model_versions (id text NOT NULL, name text NOT NULL, description text, features_summary text, train_end_date date, test_start_date date, train_size integer, test_size integer, test_log_loss numeric(8,4), test_brier numeric(8,4), test_accuracy numeric(8,4), last_trained_at timestamp with time zone NOT NULL DEFAULT now());
CREATE TABLE public.odds_aliases (id bigint NOT NULL, bfo_name text NOT NULL, fighter_id bigint NOT NULL, note text, created_at timestamp with time zone NOT NULL DEFAULT now());
CREATE TABLE public.odds_books (id bigint NOT NULL, name text NOT NULL, short_code text, is_active boolean NOT NULL DEFAULT true, first_seen_at timestamp with time zone NOT NULL DEFAULT now(), last_seen_at timestamp with time zone NOT NULL DEFAULT now());
CREATE TABLE public.pre_fight_snapshots (id bigint NOT NULL, snapshot_at timestamp with time zone NOT NULL DEFAULT now(), snapshot_label text NOT NULL DEFAULT 'cron_pre_event'::text, event_id integer NOT NULL, event_name text, event_date date NOT NULL, fight_id integer NOT NULL, weight_class text, main_event boolean NOT NULL DEFAULT false, title_fight boolean NOT NULL DEFAULT false, scheduled_rounds integer, fighter_a_id integer, fighter_a_name text, fighter_b_id integer, fighter_b_name text, engine_pick_fighter_id integer, engine_pick_side text, engine_p_cal numeric, engine_tier text, engine_model_version text, engine_published_at timestamp with time zone, odds_american_a integer, odds_american_b integer, implied_prob_a numeric, implied_prob_b numeric, bookmaker_count integer, odds_fetched_at timestamp with time zone, edge_side text, edge_bet_fighter_id integer, edge_value numeric, edge_stake_frac numeric, edge_odds_at_publish integer, props jsonb, legacy_models jsonb);
CREATE TABLE public.prediction_indicators (id bigint NOT NULL, model_version text NOT NULL, fight_id bigint NOT NULL, fighter_id bigint NOT NULL, indicator text NOT NULL, created_at timestamp with time zone NOT NULL DEFAULT now());
CREATE TABLE public.predictions (id bigint NOT NULL, fight_id bigint NOT NULL, event_id bigint NOT NULL, predicted_winner_id bigint, verdict_pct numeric(5,2) NOT NULL, is_even_matchup boolean NOT NULL DEFAULT false, top_edge_factor text, edge_count integer, closing_odds_american integer, snapshot_at timestamp with time zone NOT NULL DEFAULT now(), snapshot_label text NOT NULL DEFAULT 'day_of'::text);
CREATE TABLE public.premium_waitlist (id bigint NOT NULL, email text NOT NULL, source text, created_at timestamp with time zone NOT NULL DEFAULT now());
CREATE TABLE public.profiles (id uuid NOT NULL, email text, display_name text, tier text NOT NULL DEFAULT 'free'::text, tier_expires_at timestamp with time zone, stripe_customer_id text, created_at timestamp with time zone NOT NULL DEFAULT now(), updated_at timestamp with time zone NOT NULL DEFAULT now(), beta_premium boolean NOT NULL DEFAULT true, is_admin boolean NOT NULL DEFAULT false, stripe_subscription_id text, subscription_status text, cancel_at_period_end boolean NOT NULL DEFAULT false);
CREATE TABLE public.prop_model_locks (id bigint NOT NULL, fight_id bigint NOT NULL, event_id bigint NOT NULL, event_date date, market_type text NOT NULL, threshold numeric, side text NOT NULL, model_name text NOT NULL, model_version text NOT NULL, generated_at timestamp with time zone NOT NULL, actual_lock_at timestamp with time zone NOT NULL DEFAULT now(), training_cutoff timestamp with time zone NOT NULL, training_n_fights integer, predicted_probability numeric NOT NULL, haz_r1 numeric, haz_r2 numeric, haz_r3 numeric, phi_r1 numeric, phi_r2 numeric, phi_r3 numeric, p_ends_r1 numeric, p_ends_r2 numeric, p_ends_r3 numeric, p_decision numeric, features jsonb, code_version text, feature_hash text, notes text);
CREATE TABLE public.prop_odds (id bigint NOT NULL, fight_id bigint NOT NULL, event_id bigint, event_date date, market_type text NOT NULL, fighter_id bigint, line numeric, over_odds integer NOT NULL, under_odds integer NOT NULL, book_id bigint NOT NULL, source text NOT NULL DEFAULT 'odds_api'::text, source_event_id text, captured_at timestamp with time zone NOT NULL DEFAULT now(), is_opener boolean NOT NULL DEFAULT false, is_closer boolean NOT NULL DEFAULT false, source_commence_at timestamp with time zone, is_live boolean NOT NULL DEFAULT false, raw jsonb);
CREATE TABLE public.prop_projections (id bigint NOT NULL, generated_at timestamp with time zone NOT NULL DEFAULT now(), event_id integer NOT NULL, event_name text, event_date date, fight_id integer NOT NULL, weight_class text, main_event boolean NOT NULL DEFAULT false, side text NOT NULL, fighter_id integer, fighter_name text, opponent_name text, p_distance numeric, sig_proj numeric, sig_lo numeric, sig_hi numeric, sig_med numeric, td_proj numeric, p_td_1plus numeric, p_td_2plus numeric, thin_tape boolean NOT NULL DEFAULT false, model_version text);
CREATE TABLE public.streak_effect_cache (fighter_id bigint, fight_id bigint, result text, rn bigint, streak_before bigint);
CREATE TABLE public.unmatched_odds (id bigint NOT NULL, bfo_event_name text, bfo_event_slug text, bfo_event_date date, bfo_fighter_a_name text, bfo_fighter_b_name text, source_url text, notes text, first_seen_at timestamp with time zone NOT NULL DEFAULT now(), last_seen_at timestamp with time zone NOT NULL DEFAULT now(), resolved boolean NOT NULL DEFAULT false);
CREATE TABLE public.user_alert_deliveries (id bigint NOT NULL, user_id uuid NOT NULL, alert_id bigint, fight_id bigint, kind text NOT NULL, dedupe_key text NOT NULL, fired_at timestamp with time zone NOT NULL DEFAULT now(), channel text NOT NULL DEFAULT 'email'::text, send_status text NOT NULL DEFAULT 'pending'::text, suppressed_reason text, payload jsonb NOT NULL DEFAULT '{}'::jsonb, sent_at timestamp with time zone, error text);
CREATE TABLE public.user_alert_prefs (user_id uuid NOT NULL, email_enabled boolean NOT NULL DEFAULT true, cooldown_minutes integer NOT NULL DEFAULT 360, max_per_day integer NOT NULL DEFAULT 6, quiet_start_utc smallint, quiet_end_utc smallint, updated_at timestamp with time zone NOT NULL DEFAULT now());
CREATE TABLE public.user_alerts (id bigint NOT NULL, user_id uuid NOT NULL, fight_id bigint NOT NULL, kind text NOT NULL, side character(1), target_american integer, threshold_pts numeric(5,2), direction text, channel text NOT NULL DEFAULT 'email'::text, is_active boolean NOT NULL DEFAULT true, created_at timestamp with time zone NOT NULL DEFAULT now(), updated_at timestamp with time zone NOT NULL DEFAULT now(), last_evaluated_at timestamp with time zone, last_fired_at timestamp with time zone, fire_count integer NOT NULL DEFAULT 0, armed_value numeric(8,3), armed_cohort_fp text, armed_baseline_at timestamp with time zone);
CREATE TABLE public.user_bankrolls (user_id uuid NOT NULL, current_amount numeric(12,2) NOT NULL DEFAULT 0, initial_deposit numeric(12,2) NOT NULL DEFAULT 0, kelly_fraction numeric(4,3) NOT NULL DEFAULT 0.5, max_bet_fraction numeric(4,3) NOT NULL DEFAULT 0.05, started_at timestamp with time zone NOT NULL DEFAULT now(), updated_at timestamp with time zone NOT NULL DEFAULT now());
CREATE TABLE public.user_bets (id bigint NOT NULL, user_id uuid NOT NULL, fight_id bigint NOT NULL, fighter_id bigint NOT NULL, side character(1) NOT NULL, book text NOT NULL, placed_price_american integer NOT NULL, opener_price_american integer, stake_usd numeric(10,2) NOT NULL, model_p numeric(7,6), edge_at_placement numeric(7,6), status text NOT NULL DEFAULT 'open'::text, won boolean, pnl_usd numeric(10,2), placed_at timestamp with time zone NOT NULL DEFAULT now(), settled_at timestamp with time zone, notes text);
CREATE TABLE public.user_watchlist (user_id uuid NOT NULL, fight_id bigint NOT NULL, created_at timestamp with time zone NOT NULL DEFAULT now());
CREATE TABLE public.win_model_locks (id bigint NOT NULL, fight_id bigint NOT NULL, event_id bigint NOT NULL, event_date date NOT NULL, fighter_a_id bigint NOT NULL, fighter_b_id bigint NOT NULL, p_a numeric, experiment_id text NOT NULL, model_name text NOT NULL, model_version text NOT NULL, artifact_sha256 text NOT NULL, code_commit text NOT NULL, training_cutoff date NOT NULL, training_n_fights integer, features jsonb, feature_hash text, generated_at timestamp with time zone NOT NULL, actual_lock_at timestamp with time zone NOT NULL DEFAULT clock_timestamp(), market_p_a_vigfree numeric NOT NULL, market_book_count integer NOT NULL, market_quotes jsonb NOT NULL, market_captured_at timestamp with time zone NOT NULL, market_source text, notes text);
CREATE SEQUENCE public.billing_events_id_seq OWNED BY public.billing_events.id; ALTER TABLE public.billing_events ALTER COLUMN id SET DEFAULT nextval('public.billing_events_id_seq'::regclass);
CREATE SEQUENCE public.email_subscribers_id_seq OWNED BY public.email_subscribers.id; ALTER TABLE public.email_subscribers ALTER COLUMN id SET DEFAULT nextval('public.email_subscribers_id_seq'::regclass);
CREATE SEQUENCE public.events_id_seq OWNED BY public.events.id; ALTER TABLE public.events ALTER COLUMN id SET DEFAULT nextval('public.events_id_seq'::regclass);
CREATE SEQUENCE public.fight_odds_id_seq OWNED BY public.fight_odds.id; ALTER TABLE public.fight_odds ALTER COLUMN id SET DEFAULT nextval('public.fight_odds_id_seq'::regclass);
CREATE SEQUENCE public.fight_rounds_id_seq OWNED BY public.fight_rounds.id; ALTER TABLE public.fight_rounds ALTER COLUMN id SET DEFAULT nextval('public.fight_rounds_id_seq'::regclass);
CREATE SEQUENCE public.fight_start_estimates_id_seq OWNED BY public.fight_start_estimates.id; ALTER TABLE public.fight_start_estimates ALTER COLUMN id SET DEFAULT nextval('public.fight_start_estimates_id_seq'::regclass);
CREATE SEQUENCE public.fighters_id_seq OWNED BY public.fighters.id; ALTER TABLE public.fighters ALTER COLUMN id SET DEFAULT nextval('public.fighters_id_seq'::regclass);
CREATE SEQUENCE public.fights_id_seq OWNED BY public.fights.id; ALTER TABLE public.fights ALTER COLUMN id SET DEFAULT nextval('public.fights_id_seq'::regclass);
CREATE SEQUENCE public.funnel_events_id_seq OWNED BY public.funnel_events.id; ALTER TABLE public.funnel_events ALTER COLUMN id SET DEFAULT nextval('public.funnel_events_id_seq'::regclass);
CREATE SEQUENCE public.hub_visits_id_seq OWNED BY public.hub_visits.id; ALTER TABLE public.hub_visits ALTER COLUMN id SET DEFAULT nextval('public.hub_visits_id_seq'::regclass);
CREATE SEQUENCE public.model_edges_id_seq OWNED BY public.model_edges.id; ALTER TABLE public.model_edges ALTER COLUMN id SET DEFAULT nextval('public.model_edges_id_seq'::regclass);
CREATE SEQUENCE public.model_picks_id_seq OWNED BY public.model_picks.id; ALTER TABLE public.model_picks ALTER COLUMN id SET DEFAULT nextval('public.model_picks_id_seq'::regclass);
CREATE SEQUENCE public.model_predictions_id_seq OWNED BY public.model_predictions.id; ALTER TABLE public.model_predictions ALTER COLUMN id SET DEFAULT nextval('public.model_predictions_id_seq'::regclass);
CREATE SEQUENCE public.odds_aliases_id_seq OWNED BY public.odds_aliases.id; ALTER TABLE public.odds_aliases ALTER COLUMN id SET DEFAULT nextval('public.odds_aliases_id_seq'::regclass);
CREATE SEQUENCE public.odds_books_id_seq OWNED BY public.odds_books.id; ALTER TABLE public.odds_books ALTER COLUMN id SET DEFAULT nextval('public.odds_books_id_seq'::regclass);
CREATE SEQUENCE public.pre_fight_snapshots_id_seq OWNED BY public.pre_fight_snapshots.id; ALTER TABLE public.pre_fight_snapshots ALTER COLUMN id SET DEFAULT nextval('public.pre_fight_snapshots_id_seq'::regclass);
CREATE SEQUENCE public.prediction_indicators_id_seq OWNED BY public.prediction_indicators.id; ALTER TABLE public.prediction_indicators ALTER COLUMN id SET DEFAULT nextval('public.prediction_indicators_id_seq'::regclass);
CREATE SEQUENCE public.predictions_id_seq OWNED BY public.predictions.id; ALTER TABLE public.predictions ALTER COLUMN id SET DEFAULT nextval('public.predictions_id_seq'::regclass);
CREATE SEQUENCE public.premium_waitlist_id_seq OWNED BY public.premium_waitlist.id; ALTER TABLE public.premium_waitlist ALTER COLUMN id SET DEFAULT nextval('public.premium_waitlist_id_seq'::regclass);
CREATE SEQUENCE public.prop_model_locks_id_seq OWNED BY public.prop_model_locks.id; ALTER TABLE public.prop_model_locks ALTER COLUMN id SET DEFAULT nextval('public.prop_model_locks_id_seq'::regclass);
CREATE SEQUENCE public.prop_odds_id_seq OWNED BY public.prop_odds.id; ALTER TABLE public.prop_odds ALTER COLUMN id SET DEFAULT nextval('public.prop_odds_id_seq'::regclass);
CREATE SEQUENCE public.prop_projections_id_seq OWNED BY public.prop_projections.id; ALTER TABLE public.prop_projections ALTER COLUMN id SET DEFAULT nextval('public.prop_projections_id_seq'::regclass);
CREATE SEQUENCE public.unmatched_odds_id_seq OWNED BY public.unmatched_odds.id; ALTER TABLE public.unmatched_odds ALTER COLUMN id SET DEFAULT nextval('public.unmatched_odds_id_seq'::regclass);
CREATE SEQUENCE public.user_alert_deliveries_id_seq OWNED BY public.user_alert_deliveries.id; ALTER TABLE public.user_alert_deliveries ALTER COLUMN id SET DEFAULT nextval('public.user_alert_deliveries_id_seq'::regclass);
CREATE SEQUENCE public.user_alerts_id_seq OWNED BY public.user_alerts.id; ALTER TABLE public.user_alerts ALTER COLUMN id SET DEFAULT nextval('public.user_alerts_id_seq'::regclass);
CREATE SEQUENCE public.user_bets_id_seq OWNED BY public.user_bets.id; ALTER TABLE public.user_bets ALTER COLUMN id SET DEFAULT nextval('public.user_bets_id_seq'::regclass);
CREATE SEQUENCE public.win_model_locks_id_seq OWNED BY public.win_model_locks.id; ALTER TABLE public.win_model_locks ALTER COLUMN id SET DEFAULT nextval('public.win_model_locks_id_seq'::regclass);
ALTER TABLE public.billing_events ADD CONSTRAINT billing_events_pkey PRIMARY KEY (id);
ALTER TABLE public.billing_events ADD CONSTRAINT billing_events_stripe_event_id_key UNIQUE (stripe_event_id);
ALTER TABLE public.email_subscribers ADD CONSTRAINT email_subscribers_email_lower CHECK ((email = lower(email)));
ALTER TABLE public.email_subscribers ADD CONSTRAINT email_subscribers_pkey PRIMARY KEY (id);
ALTER TABLE public.events ADD CONSTRAINT events_pkey PRIMARY KEY (id);
ALTER TABLE public.events ADD CONSTRAINT events_ufc_event_id_key UNIQUE (ufc_event_id);
ALTER TABLE public.fight_odds_consensus_snapshot ADD CONSTRAINT fight_odds_pkey PRIMARY KEY (fight_id);
ALTER TABLE public.fight_odds ADD CONSTRAINT fight_odds_is_live_agrees_with_bout_start CHECK (((is_live IS NULL) OR (bout_started_at IS NULL) OR (is_live = (captured_at >= bout_started_at)))) NOT VALID;
ALTER TABLE public.fight_odds ADD CONSTRAINT fight_odds_is_live_needs_a_bout_start CHECK (((is_live IS NULL) OR (bout_started_at IS NOT NULL))) NOT VALID;
ALTER TABLE public.fight_odds ADD CONSTRAINT fight_odds_market_status_known CHECK (((market_status IS NULL) OR (market_status = ANY (ARRAY['open'::text, 'suspended'::text, 'taken_down'::text])))) NOT VALID;
ALTER TABLE public.fight_odds ADD CONSTRAINT fight_odds_opponent_is_not_self CHECK (((opponent_fighter_id IS NULL) OR (opponent_fighter_id <> fighter_id))) NOT VALID;
ALTER TABLE public.fight_odds ADD CONSTRAINT fight_odds_pkey1 PRIMARY KEY (id);
ALTER TABLE public.fight_odds ADD CONSTRAINT fight_odds_side_check CHECK ((side = ANY (ARRAY['A'::bpchar, 'B'::bpchar])));
ALTER TABLE public.fight_rounds ADD CONSTRAINT fight_rounds_fight_id_round_number_key UNIQUE (fight_id, round_number);
ALTER TABLE public.fight_rounds ADD CONSTRAINT fight_rounds_pkey PRIMARY KEY (id);
ALTER TABLE public.fight_start_estimates ADD CONSTRAINT fight_start_estimates_pkey PRIMARY KEY (id);
ALTER TABLE public.fighter_cardio ADD CONSTRAINT fighter_cardio_pkey PRIMARY KEY (fighter_id);
ALTER TABLE public.fighter_ratings ADD CONSTRAINT fighter_ratings_pkey PRIMARY KEY (fighter_id);
ALTER TABLE public.fighters ADD CONSTRAINT fighters_pkey PRIMARY KEY (id);
ALTER TABLE public.fighters ADD CONSTRAINT fighters_ufc_url_key UNIQUE (ufc_url);
ALTER TABLE public.fights ADD CONSTRAINT fights_pkey PRIMARY KEY (id);
ALTER TABLE public.fights ADD CONSTRAINT fights_ufc_fight_id_key UNIQUE (ufc_fight_id);
ALTER TABLE public.funnel_events ADD CONSTRAINT funnel_events_known_event CHECK ((event = ANY (ARRAY['landing_view'::text, 'card_lab_view'::text, 'fight_opened'::text, 'market_lab_view'::text, 'book_breakdown_expanded'::text, 'market_sort_changed'::text, 'factor_lab_view'::text, 'methodology_opened'::text, 'fighter_page_view'::text, 'event_page_view'::text, 'best_price_clicked'::text, 'fight_shared'::text, 'card_brief_signup_started'::text, 'card_brief_signup_completed'::text, 'pricing_view'::text, 'pro_cta_clicked'::text, 'watchlist_added'::text, 'watchlist_removed'::text, 'alert_created'::text, 'alert_fired'::text, 'alert_clicked'::text, 'checkout_started'::text, 'checkout_completed'::text, 'return_visit'::text, 'engaged_session'::text])));
ALTER TABLE public.funnel_events ADD CONSTRAINT funnel_events_pkey PRIMARY KEY (id);
ALTER TABLE public.funnel_events ADD CONSTRAINT funnel_events_props_bounded CHECK ((pg_column_size(props) <= 2048));
ALTER TABLE public.funnel_events ADD CONSTRAINT funnel_events_session_bounded CHECK (((length(session_id) >= 8) AND (length(session_id) <= 64)));
ALTER TABLE public.hub_visits ADD CONSTRAINT hub_visits_page_check CHECK ((page = ANY (ARRAY['event_hub'::text, 'fight_preview'::text, 'market_board'::text, 'home'::text])));
ALTER TABLE public.hub_visits ADD CONSTRAINT hub_visits_pkey PRIMARY KEY (id);
ALTER TABLE public.model_edges ADD CONSTRAINT model_edges_fight_id_source_key UNIQUE (fight_id, source);
ALTER TABLE public.model_edges ADD CONSTRAINT model_edges_pkey PRIMARY KEY (id);
ALTER TABLE public.model_edges ADD CONSTRAINT model_edges_side_check CHECK ((side = ANY (ARRAY['a'::bpchar, 'b'::bpchar])));
ALTER TABLE public.model_edges ADD CONSTRAINT model_edges_source_check CHECK ((source = ANY (ARRAY['backtest'::text, 'live'::text])));
ALTER TABLE public.model_picks ADD CONSTRAINT model_picks_fight_id_source_key UNIQUE (fight_id, source);
ALTER TABLE public.model_picks ADD CONSTRAINT model_picks_pick_side_check CHECK ((pick_side = ANY (ARRAY['a'::bpchar, 'b'::bpchar])));
ALTER TABLE public.model_picks ADD CONSTRAINT model_picks_pkey PRIMARY KEY (id);
ALTER TABLE public.model_picks ADD CONSTRAINT model_picks_source_check CHECK ((source = ANY (ARRAY['backtest'::text, 'live'::text])));
ALTER TABLE public.model_picks ADD CONSTRAINT model_picks_tier_check CHECK ((tier = ANY (ARRAY['Lock'::text, 'Pick'::text, 'Lean'::text])));
ALTER TABLE public.model_predictions ADD CONSTRAINT model_predictions_pkey PRIMARY KEY (id);
ALTER TABLE public.model_predictions ADD CONSTRAINT model_predictions_side_check CHECK ((side = ANY (ARRAY['A'::bpchar, 'B'::bpchar])));
ALTER TABLE public.model_versions ADD CONSTRAINT model_versions_pkey PRIMARY KEY (id);
ALTER TABLE public.odds_aliases ADD CONSTRAINT odds_aliases_bfo_name_key UNIQUE (bfo_name);
ALTER TABLE public.odds_aliases ADD CONSTRAINT odds_aliases_pkey PRIMARY KEY (id);
ALTER TABLE public.odds_books ADD CONSTRAINT odds_books_name_key UNIQUE (name);
ALTER TABLE public.odds_books ADD CONSTRAINT odds_books_pkey PRIMARY KEY (id);
ALTER TABLE public.odds_books ADD CONSTRAINT odds_books_short_code_key UNIQUE (short_code);
ALTER TABLE public.pre_fight_snapshots ADD CONSTRAINT pre_fight_snapshots_edge_side_check CHECK ((edge_side = ANY (ARRAY['a'::text, 'b'::text])));
ALTER TABLE public.pre_fight_snapshots ADD CONSTRAINT pre_fight_snapshots_engine_pick_side_check CHECK ((engine_pick_side = ANY (ARRAY['a'::text, 'b'::text])));
ALTER TABLE public.pre_fight_snapshots ADD CONSTRAINT pre_fight_snapshots_fight_id_key UNIQUE (fight_id);
ALTER TABLE public.pre_fight_snapshots ADD CONSTRAINT pre_fight_snapshots_pkey PRIMARY KEY (id);
ALTER TABLE public.prediction_indicators ADD CONSTRAINT prediction_indicators_pkey PRIMARY KEY (id);
ALTER TABLE public.predictions ADD CONSTRAINT predictions_pkey PRIMARY KEY (id);
ALTER TABLE public.premium_waitlist ADD CONSTRAINT premium_waitlist_email_key UNIQUE (email);
ALTER TABLE public.premium_waitlist ADD CONSTRAINT premium_waitlist_pkey PRIMARY KEY (id);
ALTER TABLE public.profiles ADD CONSTRAINT profiles_pkey PRIMARY KEY (id);
ALTER TABLE public.profiles ADD CONSTRAINT profiles_tier_check CHECK ((tier = ANY (ARRAY['free'::text, 'premium'::text])));
ALTER TABLE public.prop_model_locks ADD CONSTRAINT prop_model_locks_market_type_check CHECK ((market_type = ANY (ARRAY['total_rounds'::text, 'goes_distance'::text])));
ALTER TABLE public.prop_model_locks ADD CONSTRAINT prop_model_locks_pkey PRIMARY KEY (id);
ALTER TABLE public.prop_model_locks ADD CONSTRAINT prop_model_locks_predicted_probability_check CHECK (((predicted_probability > (0)::numeric) AND (predicted_probability < (1)::numeric)));
ALTER TABLE public.prop_model_locks ADD CONSTRAINT prop_model_locks_side_check CHECK ((side = ANY (ARRAY['over'::text, 'under'::text, 'yes'::text])));
ALTER TABLE public.prop_odds ADD CONSTRAINT prop_odds_fighter_chk CHECK (((market_type <> ALL (ARRAY['fighter_sig_strikes'::text, 'fighter_takedowns'::text])) OR (fighter_id IS NOT NULL)));
ALTER TABLE public.prop_odds ADD CONSTRAINT prop_odds_line_chk CHECK (((market_type = 'goes_distance'::text) OR (line IS NOT NULL)));
ALTER TABLE public.prop_odds ADD CONSTRAINT prop_odds_market_type_chk CHECK ((market_type = ANY (ARRAY['total_rounds'::text, 'goes_distance'::text, 'fighter_sig_strikes'::text, 'fighter_takedowns'::text])));
ALTER TABLE public.prop_odds ADD CONSTRAINT prop_odds_over_price_chk CHECK (((over_odds <= '-100'::integer) OR (over_odds >= 100)));
ALTER TABLE public.prop_odds ADD CONSTRAINT prop_odds_pkey PRIMARY KEY (id);
ALTER TABLE public.prop_odds ADD CONSTRAINT prop_odds_positive_line_chk CHECK (((line IS NULL) OR (line > (0)::numeric)));
ALTER TABLE public.prop_odds ADD CONSTRAINT prop_odds_under_price_chk CHECK (((under_odds <= '-100'::integer) OR (under_odds >= 100)));
ALTER TABLE public.prop_projections ADD CONSTRAINT prop_projections_fight_id_side_key UNIQUE (fight_id, side);
ALTER TABLE public.prop_projections ADD CONSTRAINT prop_projections_pkey PRIMARY KEY (id);
ALTER TABLE public.prop_projections ADD CONSTRAINT prop_projections_side_check CHECK ((side = ANY (ARRAY['a'::text, 'b'::text])));
ALTER TABLE public.unmatched_odds ADD CONSTRAINT unmatched_odds_pkey PRIMARY KEY (id);
ALTER TABLE public.user_alert_deliveries ADD CONSTRAINT user_alert_deliveries_dedupe_key_key UNIQUE (dedupe_key);
ALTER TABLE public.user_alert_deliveries ADD CONSTRAINT user_alert_deliveries_pkey PRIMARY KEY (id);
ALTER TABLE public.user_alert_deliveries ADD CONSTRAINT user_alert_deliveries_send_status_check CHECK ((send_status = ANY (ARRAY['pending'::text, 'sent'::text, 'failed'::text, 'dry_run'::text, 'suppressed'::text])));
ALTER TABLE public.user_alert_prefs ADD CONSTRAINT user_alert_prefs_cooldown_minutes_check CHECK (((cooldown_minutes >= 15) AND (cooldown_minutes <= 10080)));
ALTER TABLE public.user_alert_prefs ADD CONSTRAINT user_alert_prefs_max_per_day_check CHECK (((max_per_day >= 1) AND (max_per_day <= 50)));
ALTER TABLE public.user_alert_prefs ADD CONSTRAINT user_alert_prefs_pkey PRIMARY KEY (user_id);
ALTER TABLE public.user_alert_prefs ADD CONSTRAINT user_alert_prefs_quiet_end_utc_check CHECK (((quiet_end_utc >= 0) AND (quiet_end_utc <= 23)));
ALTER TABLE public.user_alert_prefs ADD CONSTRAINT user_alert_prefs_quiet_start_utc_check CHECK (((quiet_start_utc >= 0) AND (quiet_start_utc <= 23)));
ALTER TABLE public.user_alerts ADD CONSTRAINT user_alerts_channel_check CHECK ((channel = 'email'::text));
ALTER TABLE public.user_alerts ADD CONSTRAINT user_alerts_direction_check CHECK ((direction = ANY (ARRAY['toward_a'::text, 'toward_b'::text, 'either'::text])));
ALTER TABLE public.user_alerts ADD CONSTRAINT user_alerts_kind_check CHECK ((kind = ANY (ARRAY['price_target'::text, 'market_move'::text])));
ALTER TABLE public.user_alerts ADD CONSTRAINT user_alerts_pkey PRIMARY KEY (id);
ALTER TABLE public.user_alerts ADD CONSTRAINT user_alerts_shape CHECK ((((kind = 'price_target'::text) AND (side IS NOT NULL) AND (target_american IS NOT NULL) AND (threshold_pts IS NULL) AND (direction IS NULL)) OR ((kind = 'market_move'::text) AND (threshold_pts IS NOT NULL) AND (direction IS NOT NULL) AND (target_american IS NULL))));
ALTER TABLE public.user_alerts ADD CONSTRAINT user_alerts_side_check CHECK ((side = ANY (ARRAY['A'::bpchar, 'B'::bpchar])));
ALTER TABLE public.user_alerts ADD CONSTRAINT user_alerts_side_required_for_price CHECK (((kind <> 'price_target'::text) OR (side IS NOT NULL)));
ALTER TABLE public.user_alerts ADD CONSTRAINT user_alerts_threshold_pts_check CHECK (((threshold_pts IS NULL) OR (threshold_pts > (0)::numeric)));
ALTER TABLE public.user_bankrolls ADD CONSTRAINT user_bankrolls_pkey PRIMARY KEY (user_id);
ALTER TABLE public.user_bets ADD CONSTRAINT user_bets_pkey PRIMARY KEY (id);
ALTER TABLE public.user_bets ADD CONSTRAINT user_bets_side_check CHECK ((side = ANY (ARRAY['A'::bpchar, 'B'::bpchar])));
ALTER TABLE public.user_bets ADD CONSTRAINT user_bets_stake_usd_check CHECK ((stake_usd >= (0)::numeric));
ALTER TABLE public.user_bets ADD CONSTRAINT user_bets_status_check CHECK ((status = ANY (ARRAY['open'::text, 'won'::text, 'lost'::text, 'push'::text, 'void'::text])));
ALTER TABLE public.user_watchlist ADD CONSTRAINT user_watchlist_pkey PRIMARY KEY (user_id, fight_id);
ALTER TABLE public.win_model_locks ADD CONSTRAINT win_model_locks_commit CHECK ((code_commit ~ '^[0-9a-f]{7,40}$'::text));
ALTER TABLE public.win_model_locks ADD CONSTRAINT win_model_locks_corners CHECK ((fighter_a_id <> fighter_b_id));
ALTER TABLE public.win_model_locks ADD CONSTRAINT win_model_locks_exp CHECK ((experiment_id ~ '^PRED-[0-9]{3}$'::text));
ALTER TABLE public.win_model_locks ADD CONSTRAINT win_model_locks_market_book_count_check CHECK ((market_book_count >= 1));
ALTER TABLE public.win_model_locks ADD CONSTRAINT win_model_locks_mkt_open CHECK (((market_p_a_vigfree > (0)::numeric) AND (market_p_a_vigfree < (1)::numeric)));
ALTER TABLE public.win_model_locks ADD CONSTRAINT win_model_locks_p_open CHECK (((p_a IS NULL) OR ((p_a > (0)::numeric) AND (p_a < (1)::numeric))));
ALTER TABLE public.win_model_locks ADD CONSTRAINT win_model_locks_pkey PRIMARY KEY (id);
ALTER TABLE public.win_model_locks ADD CONSTRAINT win_model_locks_quotes CHECK (((jsonb_typeof(market_quotes) = 'array'::text) AND (jsonb_array_length(market_quotes) = market_book_count)));
ALTER TABLE public.win_model_locks ADD CONSTRAINT win_model_locks_sha CHECK ((artifact_sha256 ~ '^[0-9a-f]{64}$'::text));
CREATE UNIQUE INDEX email_subscribers_email_uniq ON public.email_subscribers USING btree (email);
CREATE UNIQUE INDEX uq_fight_odds_closer ON public.fight_odds USING btree (fight_id, side, book_id) WHERE (is_closer = true);
CREATE UNIQUE INDEX uq_fight_odds_opener ON public.fight_odds USING btree (fight_id, side, book_id) WHERE (is_opener = true);
CREATE UNIQUE INDEX fight_start_estimates_uniq ON public.fight_start_estimates USING btree (fight_id, source, start_at);
CREATE UNIQUE INDEX hub_visits_dedupe ON public.hub_visits USING btree (visitor_key, event_id, page, seen_on);
CREATE UNIQUE INDEX uq_prediction_indicators ON public.prediction_indicators USING btree (model_version, fight_id, fighter_id, indicator);
CREATE UNIQUE INDEX predictions_fight_label_uniq ON public.predictions USING btree (fight_id, snapshot_label);
CREATE UNIQUE INDEX prop_model_locks_one_per_version ON public.prop_model_locks USING btree (fight_id, market_type, COALESCE(threshold, '-1'::numeric), side, model_name, model_version);
CREATE UNIQUE INDEX prop_odds_quote_uniq ON public.prop_odds USING btree (fight_id, market_type, COALESCE(fighter_id, (0)::bigint), COALESCE(line, ('-1'::integer)::numeric), book_id, captured_at);
CREATE UNIQUE INDEX uq_unmatched_odds_lookup ON public.unmatched_odds USING btree (bfo_event_slug, bfo_fighter_a_name, bfo_fighter_b_name);
CREATE UNIQUE INDEX uq_user_alerts_one_per_target ON public.user_alerts USING btree (user_id, fight_id, kind, COALESCE(side, '*'::bpchar));
CREATE UNIQUE INDEX win_model_locks_one_per_experiment ON public.win_model_locks USING btree (fight_id, experiment_id);
ALTER TABLE public.billing_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cardio_style_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.email_subscribers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.fight_odds ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.fight_odds_consensus_snapshot ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.fight_rounds ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.fight_start_estimates ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.fighter_cardio ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.fighter_ratings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.fighter_snapshot_2025 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.fighters ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.fights ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.funnel_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.hub_visits ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.master_dataset ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.master_dataset_v2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.model_edges ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.model_picks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.model_predictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.model_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.odds_books ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pre_fight_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.prediction_indicators ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.predictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.premium_waitlist ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.prop_model_locks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.prop_odds ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.prop_projections ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.streak_effect_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_alert_deliveries ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_alert_prefs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_bankrolls ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_bets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_watchlist ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.win_model_locks ENABLE ROW LEVEL SECURITY;
CREATE OR REPLACE FUNCTION public.alert_quota()
 RETURNS integer
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
AS $function$ SELECT 50; $function$
;
CREATE OR REPLACE FUNCTION public.current_user_entitlement()
 RETURNS text
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
  SELECT CASE
    WHEN auth.uid() IS NULL THEN 'free'
    WHEN EXISTS (
      SELECT 1 FROM public.profiles p
      WHERE p.id = auth.uid()
        AND (
          p.beta_premium
          OR (p.tier IN ('premium', 'pro')
              AND (p.tier_expires_at IS NULL OR p.tier_expires_at > now()))
        )
    ) THEN 'pro'
    ELSE 'free'
  END;
$function$
;
CREATE OR REPLACE FUNCTION public.current_user_is_admin()
 RETURNS boolean
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
  select coalesce(
    (select p.is_admin from public.profiles p where p.id = auth.uid()),
    false
  );
$function$
;
CREATE OR REPLACE FUNCTION public.current_user_is_pro()
 RETURNS boolean
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
  SELECT public.current_user_entitlement() = 'pro';
$function$
;
CREATE OR REPLACE FUNCTION public.fight_start_estimates_no_rewrite()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
begin
  raise exception 'fight_start_estimates is append-only: % rejected.', tg_op;
end;
$function$
;
CREATE OR REPLACE FUNCTION public.handle_new_user()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
BEGIN
  INSERT INTO public.profiles (id, email, tier)
  VALUES (NEW.id, NEW.email, 'free')
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END;
$function$
;
CREATE OR REPLACE FUNCTION public.handle_updated_at()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$function$
;
CREATE OR REPLACE FUNCTION public.is_premium()
 RETURNS boolean
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
  user_tier TEXT;
  user_expiry TIMESTAMPTZ;
BEGIN
  IF auth.uid() IS NULL THEN
    RETURN FALSE;
  END IF;

  SELECT tier, tier_expires_at
    INTO user_tier, user_expiry
    FROM public.profiles
    WHERE id = auth.uid();

  IF user_tier IS NULL THEN
    RETURN FALSE;
  END IF;

  IF user_tier = 'premium' AND (user_expiry IS NULL OR user_expiry > NOW()) THEN
    RETURN TRUE;
  END IF;

  RETURN FALSE;
END;
$function$
;
CREATE OR REPLACE FUNCTION public.pre_fight_snapshots_no_rewrite()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
begin
  raise exception
    'pre_fight_snapshots is append-only: % on fight_id % rejected. The pre-fight record must never be revised after the bell.',
    tg_op, coalesce(old.fight_id, new.fight_id);
end;
$function$
;
CREATE OR REPLACE FUNCTION public.prop_model_locks_guard()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
declare
  v_start timestamptz;
  v_settled boolean;
begin
  if new.training_cutoff > new.actual_lock_at then
    raise exception 'lock rejected: training_cutoff (%) is after actual_lock_at (%)', new.training_cutoff, new.actual_lock_at;
  end if;
  if new.generated_at > new.actual_lock_at + interval '5 minutes' then
    raise exception 'lock rejected: generated_at (%) is after actual_lock_at (%)', new.generated_at, new.actual_lock_at;
  end if;
  select (winner_id is not null or method is not null) into v_settled from public.fights where id = new.fight_id;
  if v_settled then
    raise exception 'lock rejected: fight % already has a result on file', new.fight_id;
  end if;
  select start_at into v_start from public.v_fight_start_best where fight_id = new.fight_id;
  if v_start is not null and new.actual_lock_at >= v_start then
    raise exception 'lock rejected: fight % start (%) is not after actual_lock_at (%)', new.fight_id, v_start, new.actual_lock_at;
  end if;
  return new;
end;
$function$
;
CREATE OR REPLACE FUNCTION public.prop_model_locks_no_rewrite()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
begin
  raise exception
    'prop_model_locks is append-only: % on lock % rejected. Locks are never revised; publish a new model_version instead.',
    tg_op, coalesce(old.id, new.id);
end;
$function$
;
CREATE OR REPLACE FUNCTION public.prop_odds_no_rewrite()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
begin
  raise exception
    'prop_odds is append-only: % on quote id % (fight %) rejected. A sportsbook quote is an observation; capture a new row instead.',
    tg_op, coalesce(old.id, new.id), coalesce(old.fight_id, new.fight_id);
end;
$function$
;
CREATE OR REPLACE FUNCTION public.touch_user_bankrolls_updated_at()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$function$
;
CREATE OR REPLACE FUNCTION public.unsubscribe_email(p_token text)
 RETURNS boolean
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
  updated int;
BEGIN
  UPDATE public.email_subscribers
     SET unsubscribed_at = now()
   WHERE unsubscribe_token = p_token
     AND unsubscribed_at IS NULL;
  GET DIAGNOSTICS updated = ROW_COUNT;
  RETURN updated > 0;
END;
$function$
;
CREATE OR REPLACE FUNCTION public.user_alerts_pin_sender_columns()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
BEGIN
  IF current_user IN ('service_role', 'postgres', 'supabase_admin') THEN
    RETURN NEW;                      -- the sender owns these columns
  END IF;
  NEW.last_evaluated_at := OLD.last_evaluated_at;
  NEW.last_fired_at     := OLD.last_fired_at;
  NEW.fire_count        := OLD.fire_count;
  NEW.armed_value       := OLD.armed_value;
  NEW.armed_cohort_fp   := OLD.armed_cohort_fp;
  NEW.armed_baseline_at := OLD.armed_baseline_at;
  NEW.user_id           := OLD.user_id;
  NEW.created_at        := OLD.created_at;
  NEW.updated_at        := now();
  RETURN NEW;
END; $function$
;
CREATE OR REPLACE FUNCTION public.user_alerts_quota_check()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE n integer; q integer := public.alert_quota();
BEGIN
  SELECT count(*) INTO n FROM public.user_alerts WHERE user_id = NEW.user_id AND is_active;
  IF n >= q THEN
    RAISE EXCEPTION 'alert quota reached (% active alerts allowed)', q USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END; $function$
;
CREATE OR REPLACE FUNCTION public.win_model_locks_guard()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
declare
f record;
v_start timestamptz;
begin
new.actual_lock_at := clock_timestamp();
select fighter_a_id, fighter_b_id, winner_id, method, event_id, is_active
into f from public.fights where id = new.fight_id;
if not found then
raise exception 'lock rejected: fight % does not exist', new.fight_id;
end if;
if f.is_active is false then
raise exception 'lock rejected: fight % is a retired booking', new.fight_id;
end if;
if f.winner_id is not null or f.method is not null then
raise exception 'lock rejected: fight % already has a result on file', new.fight_id;
end if;
if f.event_id is distinct from new.event_id then
raise exception 'lock rejected: fight % belongs to event %, not %', new.fight_id, f.event_id, new.event_id;
end if;
if f.fighter_a_id is distinct from new.fighter_a_id or f.fighter_b_id is distinct from new.fighter_b_id then
raise exception 'lock rejected: corners (%, %) do not match fight % as booked (%, %)',
new.fighter_a_id, new.fighter_b_id, new.fight_id, f.fighter_a_id, f.fighter_b_id;
end if;
select event_date into new.event_date from public.events where id = f.event_id;
select min(case when start_basis = 'event_date_fallback'
then (event_date::timestamp at time zone 'UTC') else start_at end)
into v_start from public.v_fight_start_best where event_id = f.event_id;
if v_start is null then
raise exception 'lock rejected: no start time can be established for the card of fight %', new.fight_id;
end if;
if new.actual_lock_at >= v_start then
raise exception 'lock rejected: the card of fight % starts % and the lock is %', new.fight_id, v_start, new.actual_lock_at;
end if;
if new.training_cutoff > new.event_date then
raise exception 'lock rejected: training_cutoff % is after the event date %', new.training_cutoff, new.event_date;
end if;
if new.generated_at > new.actual_lock_at + interval '5 minutes' then
raise exception 'lock rejected: generated_at % is in the future of the lock %', new.generated_at, new.actual_lock_at;
end if;
if new.market_captured_at > new.actual_lock_at then
raise exception 'lock rejected: market snapshot % is dated after the lock %', new.market_captured_at, new.actual_lock_at;
end if;
return new;
end;
$function$
;
CREATE OR REPLACE FUNCTION public.win_model_locks_no_rewrite()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$ begin raise exception 'win_model_locks is append-only: % rejected. A forecast on record is evidence; a new model build writes a new row.', tg_op; end; $function$
;
CREATE TRIGGER fight_start_estimates_block_delete BEFORE DELETE ON public.fight_start_estimates FOR EACH ROW EXECUTE FUNCTION fight_start_estimates_no_rewrite();
CREATE TRIGGER fight_start_estimates_block_update BEFORE UPDATE ON public.fight_start_estimates FOR EACH ROW EXECUTE FUNCTION fight_start_estimates_no_rewrite();
CREATE TRIGGER pre_fight_snapshots_block_delete BEFORE DELETE ON public.pre_fight_snapshots FOR EACH ROW EXECUTE FUNCTION pre_fight_snapshots_no_rewrite();
CREATE TRIGGER pre_fight_snapshots_block_update BEFORE UPDATE ON public.pre_fight_snapshots FOR EACH ROW EXECUTE FUNCTION pre_fight_snapshots_no_rewrite();
CREATE TRIGGER on_profile_updated BEFORE UPDATE ON public.profiles FOR EACH ROW EXECUTE FUNCTION handle_updated_at();
CREATE TRIGGER prop_model_locks_block_delete BEFORE DELETE ON public.prop_model_locks FOR EACH ROW EXECUTE FUNCTION prop_model_locks_no_rewrite();
CREATE TRIGGER prop_model_locks_block_truncate BEFORE TRUNCATE ON public.prop_model_locks FOR EACH STATEMENT EXECUTE FUNCTION prop_model_locks_no_rewrite();
CREATE TRIGGER prop_model_locks_block_update BEFORE UPDATE ON public.prop_model_locks FOR EACH ROW EXECUTE FUNCTION prop_model_locks_no_rewrite();
CREATE TRIGGER prop_model_locks_guard_insert BEFORE INSERT ON public.prop_model_locks FOR EACH ROW EXECUTE FUNCTION prop_model_locks_guard();
CREATE TRIGGER prop_odds_block_delete BEFORE DELETE ON public.prop_odds FOR EACH ROW EXECUTE FUNCTION prop_odds_no_rewrite();
CREATE TRIGGER prop_odds_block_truncate BEFORE TRUNCATE ON public.prop_odds FOR EACH STATEMENT EXECUTE FUNCTION prop_odds_no_rewrite();
CREATE TRIGGER prop_odds_block_update BEFORE UPDATE ON public.prop_odds FOR EACH ROW EXECUTE FUNCTION prop_odds_no_rewrite();
CREATE TRIGGER trg_user_alerts_pin BEFORE UPDATE ON public.user_alerts FOR EACH ROW EXECUTE FUNCTION user_alerts_pin_sender_columns();
CREATE TRIGGER trg_user_alerts_quota BEFORE INSERT ON public.user_alerts FOR EACH ROW WHEN (new.is_active) EXECUTE FUNCTION user_alerts_quota_check();
CREATE TRIGGER trg_touch_user_bankrolls BEFORE UPDATE ON public.user_bankrolls FOR EACH ROW EXECUTE FUNCTION touch_user_bankrolls_updated_at();
CREATE TRIGGER win_model_locks_block_delete BEFORE DELETE ON public.win_model_locks FOR EACH ROW EXECUTE FUNCTION win_model_locks_no_rewrite();
CREATE TRIGGER win_model_locks_block_truncate BEFORE TRUNCATE ON public.win_model_locks FOR EACH STATEMENT EXECUTE FUNCTION win_model_locks_no_rewrite();
CREATE TRIGGER win_model_locks_block_update BEFORE UPDATE ON public.win_model_locks FOR EACH ROW EXECUTE FUNCTION win_model_locks_no_rewrite();
CREATE TRIGGER win_model_locks_guard_insert BEFORE INSERT ON public.win_model_locks FOR EACH ROW EXECUTE FUNCTION win_model_locks_guard();
CREATE POLICY email_subscribers_admin_read ON public.email_subscribers AS PERMISSIVE FOR SELECT TO authenticated USING ((EXISTS ( SELECT 1
   FROM profiles p
  WHERE ((p.id = auth.uid()) AND (p.is_admin = true)))));
CREATE POLICY email_subscribers_insert_anon ON public.email_subscribers AS PERMISSIVE FOR INSERT TO anon, authenticated WITH CHECK (true);
CREATE POLICY "Public read access" ON public.events AS PERMISSIVE FOR SELECT TO anon USING (true);
CREATE POLICY "anon and authenticated can read" ON public.events AS PERMISSIVE FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY anon_read_events ON public.events AS PERMISSIVE FOR SELECT TO anon USING (true);
CREATE POLICY cfl_public_read ON public.events AS PERMISSIVE FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY events_public_read ON public.events AS PERMISSIVE FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY fight_odds_read_all ON public.fight_odds_consensus_snapshot AS PERMISSIVE FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY private_lockdown_admin_only ON public.fight_odds AS RESTRICTIVE FOR SELECT TO anon, authenticated USING (( SELECT current_user_is_admin() AS current_user_is_admin));
CREATE POLICY "Public read access" ON public.fight_rounds AS PERMISSIVE FOR SELECT TO anon USING (true);
CREATE POLICY "anon and authenticated can read" ON public.fight_rounds AS PERMISSIVE FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY cfl_public_read ON public.fight_rounds AS PERMISSIVE FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY fighter_cardio_public_read ON public.fighter_cardio AS PERMISSIVE FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "public read fighter_ratings" ON public.fighter_ratings AS PERMISSIVE FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Public read access" ON public.fighters AS PERMISSIVE FOR SELECT TO anon USING (true);
CREATE POLICY "anon and authenticated can read" ON public.fighters AS PERMISSIVE FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY anon_read_fighters ON public.fighters AS PERMISSIVE FOR SELECT TO anon USING (true);
CREATE POLICY cfl_public_read ON public.fighters AS PERMISSIVE FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY fighters_public_read ON public.fighters AS PERMISSIVE FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Public read access" ON public.fights AS PERMISSIVE FOR SELECT TO anon USING (true);
CREATE POLICY "anon and authenticated can read" ON public.fights AS PERMISSIVE FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY anon_read_fights ON public.fights AS PERMISSIVE FOR SELECT TO anon USING (true);
CREATE POLICY cfl_public_read ON public.fights AS PERMISSIVE FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY fights_public_read ON public.fights AS PERMISSIVE FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY funnel_events_anon_insert ON public.funnel_events AS PERMISSIVE FOR INSERT TO anon, authenticated WITH CHECK (true);
CREATE POLICY hub_visits_insert_anon ON public.hub_visits AS PERMISSIVE FOR INSERT TO anon, authenticated WITH CHECK (true);
CREATE POLICY "public read model_edges" ON public.model_edges AS PERMISSIVE FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "public read model_picks" ON public.model_picks AS PERMISSIVE FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Anyone can read model_predictions" ON public.model_predictions AS PERMISSIVE FOR SELECT TO public USING (true);
CREATE POLICY "anon and authenticated can read" ON public.model_predictions AS PERMISSIVE FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Anyone can read model_versions" ON public.model_versions AS PERMISSIVE FOR SELECT TO public USING (true);
CREATE POLICY "anon and authenticated can read" ON public.model_versions AS PERMISSIVE FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY private_lockdown_admin_only ON public.odds_books AS RESTRICTIVE FOR SELECT TO anon, authenticated USING (( SELECT current_user_is_admin() AS current_user_is_admin));
CREATE POLICY pre_fight_snapshots_public_read ON public.pre_fight_snapshots AS PERMISSIVE FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Admins can read prediction_indicators" ON public.prediction_indicators AS PERMISSIVE FOR SELECT TO authenticated USING ((EXISTS ( SELECT 1
   FROM profiles
  WHERE ((profiles.id = auth.uid()) AND (profiles.is_admin = true)))));
CREATE POLICY private_lockdown_admin_only ON public.prediction_indicators AS RESTRICTIVE FOR SELECT TO anon, authenticated USING (( SELECT current_user_is_admin() AS current_user_is_admin));
CREATE POLICY predictions_public_read ON public.predictions AS PERMISSIVE FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Anyone can join waitlist" ON public.premium_waitlist AS PERMISSIVE FOR INSERT TO public WITH CHECK (true);
CREATE POLICY "Users can update own profile (identity fields pinned)" ON public.profiles AS PERMISSIVE FOR UPDATE TO public USING ((auth.uid() = id)) WITH CHECK (((auth.uid() = id) AND (NOT (tier IS DISTINCT FROM ( SELECT p.tier
   FROM profiles p
  WHERE (p.id = auth.uid())))) AND (NOT (tier_expires_at IS DISTINCT FROM ( SELECT p.tier_expires_at
   FROM profiles p
  WHERE (p.id = auth.uid())))) AND (NOT (stripe_customer_id IS DISTINCT FROM ( SELECT p.stripe_customer_id
   FROM profiles p
  WHERE (p.id = auth.uid())))) AND (NOT (is_admin IS DISTINCT FROM ( SELECT p.is_admin
   FROM profiles p
  WHERE (p.id = auth.uid())))) AND (NOT (beta_premium IS DISTINCT FROM ( SELECT p.beta_premium
   FROM profiles p
  WHERE (p.id = auth.uid())))) AND (NOT (stripe_subscription_id IS DISTINCT FROM ( SELECT p.stripe_subscription_id
   FROM profiles p
  WHERE (p.id = auth.uid())))) AND (NOT (subscription_status IS DISTINCT FROM ( SELECT p.subscription_status
   FROM profiles p
  WHERE (p.id = auth.uid())))) AND (NOT (cancel_at_period_end IS DISTINCT FROM ( SELECT p.cancel_at_period_end
   FROM profiles p
  WHERE (p.id = auth.uid()))))));
CREATE POLICY "Users can view own profile" ON public.profiles AS PERMISSIVE FOR SELECT TO public USING ((auth.uid() = id));
CREATE POLICY prop_projections_public_read ON public.prop_projections AS PERMISSIVE FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "deliveries select own" ON public.user_alert_deliveries AS PERMISSIVE FOR SELECT TO authenticated USING ((auth.uid() = user_id));
CREATE POLICY "alert prefs insert own" ON public.user_alert_prefs AS PERMISSIVE FOR INSERT TO authenticated WITH CHECK ((auth.uid() = user_id));
CREATE POLICY "alert prefs select own" ON public.user_alert_prefs AS PERMISSIVE FOR SELECT TO authenticated USING ((auth.uid() = user_id));
CREATE POLICY "alert prefs update own" ON public.user_alert_prefs AS PERMISSIVE FOR UPDATE TO authenticated USING ((auth.uid() = user_id)) WITH CHECK ((auth.uid() = user_id));
CREATE POLICY "alerts delete own" ON public.user_alerts AS PERMISSIVE FOR DELETE TO authenticated USING ((auth.uid() = user_id));
CREATE POLICY "alerts insert own" ON public.user_alerts AS PERMISSIVE FOR INSERT TO authenticated WITH CHECK ((auth.uid() = user_id));
CREATE POLICY "alerts select own" ON public.user_alerts AS PERMISSIVE FOR SELECT TO authenticated USING ((auth.uid() = user_id));
CREATE POLICY "alerts update own" ON public.user_alerts AS PERMISSIVE FOR UPDATE TO authenticated USING ((auth.uid() = user_id)) WITH CHECK ((auth.uid() = user_id));
CREATE POLICY "Users insert own bankroll" ON public.user_bankrolls AS PERMISSIVE FOR INSERT TO authenticated WITH CHECK ((auth.uid() = user_id));
CREATE POLICY "Users read own bankroll" ON public.user_bankrolls AS PERMISSIVE FOR SELECT TO authenticated USING ((auth.uid() = user_id));
CREATE POLICY "Users update own bankroll" ON public.user_bankrolls AS PERMISSIVE FOR UPDATE TO authenticated USING ((auth.uid() = user_id)) WITH CHECK ((auth.uid() = user_id));
CREATE POLICY "Users delete own bets" ON public.user_bets AS PERMISSIVE FOR DELETE TO authenticated USING ((auth.uid() = user_id));
CREATE POLICY "Users insert own bets" ON public.user_bets AS PERMISSIVE FOR INSERT TO authenticated WITH CHECK ((auth.uid() = user_id));
CREATE POLICY "Users read own bets" ON public.user_bets AS PERMISSIVE FOR SELECT TO authenticated USING ((auth.uid() = user_id));
CREATE POLICY "Users update own bets" ON public.user_bets AS PERMISSIVE FOR UPDATE TO authenticated USING ((auth.uid() = user_id)) WITH CHECK ((auth.uid() = user_id));
CREATE POLICY "watchlist delete own" ON public.user_watchlist AS PERMISSIVE FOR DELETE TO authenticated USING ((auth.uid() = user_id));
CREATE POLICY "watchlist insert own" ON public.user_watchlist AS PERMISSIVE FOR INSERT TO authenticated WITH CHECK ((auth.uid() = user_id));
CREATE POLICY "watchlist select own" ON public.user_watchlist AS PERMISSIVE FOR SELECT TO authenticated USING ((auth.uid() = user_id));
GRANT DELETE ON TABLE public.cardio_style_snapshots TO anon;
GRANT INSERT ON TABLE public.cardio_style_snapshots TO anon;
GRANT REFERENCES ON TABLE public.cardio_style_snapshots TO anon;
GRANT SELECT ON TABLE public.cardio_style_snapshots TO anon;
GRANT TRIGGER ON TABLE public.cardio_style_snapshots TO anon;
GRANT TRUNCATE ON TABLE public.cardio_style_snapshots TO anon;
GRANT UPDATE ON TABLE public.cardio_style_snapshots TO anon;
GRANT DELETE ON TABLE public.cardio_style_snapshots TO authenticated;
GRANT INSERT ON TABLE public.cardio_style_snapshots TO authenticated;
GRANT REFERENCES ON TABLE public.cardio_style_snapshots TO authenticated;
GRANT SELECT ON TABLE public.cardio_style_snapshots TO authenticated;
GRANT TRIGGER ON TABLE public.cardio_style_snapshots TO authenticated;
GRANT TRUNCATE ON TABLE public.cardio_style_snapshots TO authenticated;
GRANT UPDATE ON TABLE public.cardio_style_snapshots TO authenticated;
GRANT SELECT ON SEQUENCE public.email_subscribers_id_seq TO anon;
GRANT UPDATE ON SEQUENCE public.email_subscribers_id_seq TO anon;
GRANT USAGE ON SEQUENCE public.email_subscribers_id_seq TO anon;
GRANT SELECT ON SEQUENCE public.email_subscribers_id_seq TO authenticated;
GRANT UPDATE ON SEQUENCE public.email_subscribers_id_seq TO authenticated;
GRANT USAGE ON SEQUENCE public.email_subscribers_id_seq TO authenticated;
GRANT DELETE ON TABLE public.email_subscribers TO anon;
GRANT INSERT ON TABLE public.email_subscribers TO anon;
GRANT REFERENCES ON TABLE public.email_subscribers TO anon;
GRANT SELECT ON TABLE public.email_subscribers TO anon;
GRANT TRIGGER ON TABLE public.email_subscribers TO anon;
GRANT TRUNCATE ON TABLE public.email_subscribers TO anon;
GRANT UPDATE ON TABLE public.email_subscribers TO anon;
GRANT DELETE ON TABLE public.email_subscribers TO authenticated;
GRANT INSERT ON TABLE public.email_subscribers TO authenticated;
GRANT REFERENCES ON TABLE public.email_subscribers TO authenticated;
GRANT SELECT ON TABLE public.email_subscribers TO authenticated;
GRANT TRIGGER ON TABLE public.email_subscribers TO authenticated;
GRANT TRUNCATE ON TABLE public.email_subscribers TO authenticated;
GRANT UPDATE ON TABLE public.email_subscribers TO authenticated;
GRANT SELECT ON SEQUENCE public.events_id_seq TO anon;
GRANT UPDATE ON SEQUENCE public.events_id_seq TO anon;
GRANT USAGE ON SEQUENCE public.events_id_seq TO anon;
GRANT SELECT ON SEQUENCE public.events_id_seq TO authenticated;
GRANT UPDATE ON SEQUENCE public.events_id_seq TO authenticated;
GRANT USAGE ON SEQUENCE public.events_id_seq TO authenticated;
GRANT DELETE ON TABLE public.events TO anon;
GRANT INSERT ON TABLE public.events TO anon;
GRANT REFERENCES ON TABLE public.events TO anon;
GRANT SELECT ON TABLE public.events TO anon;
GRANT TRIGGER ON TABLE public.events TO anon;
GRANT TRUNCATE ON TABLE public.events TO anon;
GRANT UPDATE ON TABLE public.events TO anon;
GRANT DELETE ON TABLE public.events TO authenticated;
GRANT INSERT ON TABLE public.events TO authenticated;
GRANT REFERENCES ON TABLE public.events TO authenticated;
GRANT SELECT ON TABLE public.events TO authenticated;
GRANT TRIGGER ON TABLE public.events TO authenticated;
GRANT TRUNCATE ON TABLE public.events TO authenticated;
GRANT UPDATE ON TABLE public.events TO authenticated;
GRANT DELETE ON TABLE public.fight_odds_consensus_snapshot TO anon;
GRANT INSERT ON TABLE public.fight_odds_consensus_snapshot TO anon;
GRANT REFERENCES ON TABLE public.fight_odds_consensus_snapshot TO anon;
GRANT SELECT ON TABLE public.fight_odds_consensus_snapshot TO anon;
GRANT TRIGGER ON TABLE public.fight_odds_consensus_snapshot TO anon;
GRANT TRUNCATE ON TABLE public.fight_odds_consensus_snapshot TO anon;
GRANT UPDATE ON TABLE public.fight_odds_consensus_snapshot TO anon;
GRANT DELETE ON TABLE public.fight_odds_consensus_snapshot TO authenticated;
GRANT INSERT ON TABLE public.fight_odds_consensus_snapshot TO authenticated;
GRANT REFERENCES ON TABLE public.fight_odds_consensus_snapshot TO authenticated;
GRANT SELECT ON TABLE public.fight_odds_consensus_snapshot TO authenticated;
GRANT TRIGGER ON TABLE public.fight_odds_consensus_snapshot TO authenticated;
GRANT TRUNCATE ON TABLE public.fight_odds_consensus_snapshot TO authenticated;
GRANT UPDATE ON TABLE public.fight_odds_consensus_snapshot TO authenticated;
GRANT SELECT ON TABLE public.fight_odds TO anon;
GRANT SELECT ON TABLE public.fight_odds TO authenticated;
GRANT SELECT ON SEQUENCE public.fight_rounds_id_seq TO anon;
GRANT UPDATE ON SEQUENCE public.fight_rounds_id_seq TO anon;
GRANT USAGE ON SEQUENCE public.fight_rounds_id_seq TO anon;
GRANT SELECT ON SEQUENCE public.fight_rounds_id_seq TO authenticated;
GRANT UPDATE ON SEQUENCE public.fight_rounds_id_seq TO authenticated;
GRANT USAGE ON SEQUENCE public.fight_rounds_id_seq TO authenticated;
GRANT DELETE ON TABLE public.fight_rounds TO anon;
GRANT INSERT ON TABLE public.fight_rounds TO anon;
GRANT REFERENCES ON TABLE public.fight_rounds TO anon;
GRANT SELECT ON TABLE public.fight_rounds TO anon;
GRANT TRIGGER ON TABLE public.fight_rounds TO anon;
GRANT TRUNCATE ON TABLE public.fight_rounds TO anon;
GRANT UPDATE ON TABLE public.fight_rounds TO anon;
GRANT DELETE ON TABLE public.fight_rounds TO authenticated;
GRANT INSERT ON TABLE public.fight_rounds TO authenticated;
GRANT REFERENCES ON TABLE public.fight_rounds TO authenticated;
GRANT SELECT ON TABLE public.fight_rounds TO authenticated;
GRANT TRIGGER ON TABLE public.fight_rounds TO authenticated;
GRANT TRUNCATE ON TABLE public.fight_rounds TO authenticated;
GRANT UPDATE ON TABLE public.fight_rounds TO authenticated;
GRANT SELECT ON SEQUENCE public.fight_start_estimates_id_seq TO anon;
GRANT UPDATE ON SEQUENCE public.fight_start_estimates_id_seq TO anon;
GRANT USAGE ON SEQUENCE public.fight_start_estimates_id_seq TO anon;
GRANT SELECT ON SEQUENCE public.fight_start_estimates_id_seq TO authenticated;
GRANT UPDATE ON SEQUENCE public.fight_start_estimates_id_seq TO authenticated;
GRANT USAGE ON SEQUENCE public.fight_start_estimates_id_seq TO authenticated;
GRANT DELETE ON TABLE public.fighter_cardio TO anon;
GRANT INSERT ON TABLE public.fighter_cardio TO anon;
GRANT REFERENCES ON TABLE public.fighter_cardio TO anon;
GRANT SELECT ON TABLE public.fighter_cardio TO anon;
GRANT TRIGGER ON TABLE public.fighter_cardio TO anon;
GRANT TRUNCATE ON TABLE public.fighter_cardio TO anon;
GRANT UPDATE ON TABLE public.fighter_cardio TO anon;
GRANT DELETE ON TABLE public.fighter_cardio TO authenticated;
GRANT INSERT ON TABLE public.fighter_cardio TO authenticated;
GRANT REFERENCES ON TABLE public.fighter_cardio TO authenticated;
GRANT SELECT ON TABLE public.fighter_cardio TO authenticated;
GRANT TRIGGER ON TABLE public.fighter_cardio TO authenticated;
GRANT TRUNCATE ON TABLE public.fighter_cardio TO authenticated;
GRANT UPDATE ON TABLE public.fighter_cardio TO authenticated;
GRANT DELETE ON TABLE public.fighter_ratings TO anon;
GRANT INSERT ON TABLE public.fighter_ratings TO anon;
GRANT REFERENCES ON TABLE public.fighter_ratings TO anon;
GRANT SELECT ON TABLE public.fighter_ratings TO anon;
GRANT TRIGGER ON TABLE public.fighter_ratings TO anon;
GRANT TRUNCATE ON TABLE public.fighter_ratings TO anon;
GRANT UPDATE ON TABLE public.fighter_ratings TO anon;
GRANT DELETE ON TABLE public.fighter_ratings TO authenticated;
GRANT INSERT ON TABLE public.fighter_ratings TO authenticated;
GRANT REFERENCES ON TABLE public.fighter_ratings TO authenticated;
GRANT SELECT ON TABLE public.fighter_ratings TO authenticated;
GRANT TRIGGER ON TABLE public.fighter_ratings TO authenticated;
GRANT TRUNCATE ON TABLE public.fighter_ratings TO authenticated;
GRANT UPDATE ON TABLE public.fighter_ratings TO authenticated;
GRANT DELETE ON TABLE public.fighter_snapshot_2025 TO anon;
GRANT INSERT ON TABLE public.fighter_snapshot_2025 TO anon;
GRANT REFERENCES ON TABLE public.fighter_snapshot_2025 TO anon;
GRANT SELECT ON TABLE public.fighter_snapshot_2025 TO anon;
GRANT TRIGGER ON TABLE public.fighter_snapshot_2025 TO anon;
GRANT TRUNCATE ON TABLE public.fighter_snapshot_2025 TO anon;
GRANT UPDATE ON TABLE public.fighter_snapshot_2025 TO anon;
GRANT DELETE ON TABLE public.fighter_snapshot_2025 TO authenticated;
GRANT INSERT ON TABLE public.fighter_snapshot_2025 TO authenticated;
GRANT REFERENCES ON TABLE public.fighter_snapshot_2025 TO authenticated;
GRANT SELECT ON TABLE public.fighter_snapshot_2025 TO authenticated;
GRANT TRIGGER ON TABLE public.fighter_snapshot_2025 TO authenticated;
GRANT TRUNCATE ON TABLE public.fighter_snapshot_2025 TO authenticated;
GRANT UPDATE ON TABLE public.fighter_snapshot_2025 TO authenticated;
GRANT SELECT ON SEQUENCE public.fighters_id_seq TO anon;
GRANT UPDATE ON SEQUENCE public.fighters_id_seq TO anon;
GRANT USAGE ON SEQUENCE public.fighters_id_seq TO anon;
GRANT SELECT ON SEQUENCE public.fighters_id_seq TO authenticated;
GRANT UPDATE ON SEQUENCE public.fighters_id_seq TO authenticated;
GRANT USAGE ON SEQUENCE public.fighters_id_seq TO authenticated;
GRANT DELETE ON TABLE public.fighters TO anon;
GRANT INSERT ON TABLE public.fighters TO anon;
GRANT REFERENCES ON TABLE public.fighters TO anon;
GRANT SELECT ON TABLE public.fighters TO anon;
GRANT TRIGGER ON TABLE public.fighters TO anon;
GRANT TRUNCATE ON TABLE public.fighters TO anon;
GRANT UPDATE ON TABLE public.fighters TO anon;
GRANT DELETE ON TABLE public.fighters TO authenticated;
GRANT INSERT ON TABLE public.fighters TO authenticated;
GRANT REFERENCES ON TABLE public.fighters TO authenticated;
GRANT SELECT ON TABLE public.fighters TO authenticated;
GRANT TRIGGER ON TABLE public.fighters TO authenticated;
GRANT TRUNCATE ON TABLE public.fighters TO authenticated;
GRANT UPDATE ON TABLE public.fighters TO authenticated;
GRANT SELECT ON SEQUENCE public.fights_id_seq TO anon;
GRANT UPDATE ON SEQUENCE public.fights_id_seq TO anon;
GRANT USAGE ON SEQUENCE public.fights_id_seq TO anon;
GRANT SELECT ON SEQUENCE public.fights_id_seq TO authenticated;
GRANT UPDATE ON SEQUENCE public.fights_id_seq TO authenticated;
GRANT USAGE ON SEQUENCE public.fights_id_seq TO authenticated;
GRANT DELETE ON TABLE public.fights TO anon;
GRANT INSERT ON TABLE public.fights TO anon;
GRANT REFERENCES ON TABLE public.fights TO anon;
GRANT SELECT ON TABLE public.fights TO anon;
GRANT TRIGGER ON TABLE public.fights TO anon;
GRANT TRUNCATE ON TABLE public.fights TO anon;
GRANT UPDATE ON TABLE public.fights TO anon;
GRANT DELETE ON TABLE public.fights TO authenticated;
GRANT INSERT ON TABLE public.fights TO authenticated;
GRANT REFERENCES ON TABLE public.fights TO authenticated;
GRANT SELECT ON TABLE public.fights TO authenticated;
GRANT TRIGGER ON TABLE public.fights TO authenticated;
GRANT TRUNCATE ON TABLE public.fights TO authenticated;
GRANT UPDATE ON TABLE public.fights TO authenticated;
GRANT SELECT ON SEQUENCE public.funnel_events_id_seq TO anon;
GRANT UPDATE ON SEQUENCE public.funnel_events_id_seq TO anon;
GRANT USAGE ON SEQUENCE public.funnel_events_id_seq TO anon;
GRANT SELECT ON SEQUENCE public.funnel_events_id_seq TO authenticated;
GRANT UPDATE ON SEQUENCE public.funnel_events_id_seq TO authenticated;
GRANT USAGE ON SEQUENCE public.funnel_events_id_seq TO authenticated;
GRANT INSERT ON TABLE public.funnel_events TO anon;
GRANT INSERT ON TABLE public.funnel_events TO authenticated;
GRANT SELECT ON SEQUENCE public.hub_visits_id_seq TO anon;
GRANT UPDATE ON SEQUENCE public.hub_visits_id_seq TO anon;
GRANT USAGE ON SEQUENCE public.hub_visits_id_seq TO anon;
GRANT SELECT ON SEQUENCE public.hub_visits_id_seq TO authenticated;
GRANT UPDATE ON SEQUENCE public.hub_visits_id_seq TO authenticated;
GRANT USAGE ON SEQUENCE public.hub_visits_id_seq TO authenticated;
GRANT DELETE ON TABLE public.hub_visits TO anon;
GRANT INSERT ON TABLE public.hub_visits TO anon;
GRANT REFERENCES ON TABLE public.hub_visits TO anon;
GRANT SELECT ON TABLE public.hub_visits TO anon;
GRANT TRIGGER ON TABLE public.hub_visits TO anon;
GRANT TRUNCATE ON TABLE public.hub_visits TO anon;
GRANT UPDATE ON TABLE public.hub_visits TO anon;
GRANT DELETE ON TABLE public.hub_visits TO authenticated;
GRANT INSERT ON TABLE public.hub_visits TO authenticated;
GRANT REFERENCES ON TABLE public.hub_visits TO authenticated;
GRANT SELECT ON TABLE public.hub_visits TO authenticated;
GRANT TRIGGER ON TABLE public.hub_visits TO authenticated;
GRANT TRUNCATE ON TABLE public.hub_visits TO authenticated;
GRANT UPDATE ON TABLE public.hub_visits TO authenticated;
GRANT DELETE ON TABLE public.master_dataset_v2 TO anon;
GRANT INSERT ON TABLE public.master_dataset_v2 TO anon;
GRANT REFERENCES ON TABLE public.master_dataset_v2 TO anon;
GRANT SELECT ON TABLE public.master_dataset_v2 TO anon;
GRANT TRIGGER ON TABLE public.master_dataset_v2 TO anon;
GRANT TRUNCATE ON TABLE public.master_dataset_v2 TO anon;
GRANT UPDATE ON TABLE public.master_dataset_v2 TO anon;
GRANT DELETE ON TABLE public.master_dataset_v2 TO authenticated;
GRANT INSERT ON TABLE public.master_dataset_v2 TO authenticated;
GRANT REFERENCES ON TABLE public.master_dataset_v2 TO authenticated;
GRANT SELECT ON TABLE public.master_dataset_v2 TO authenticated;
GRANT TRIGGER ON TABLE public.master_dataset_v2 TO authenticated;
GRANT TRUNCATE ON TABLE public.master_dataset_v2 TO authenticated;
GRANT UPDATE ON TABLE public.master_dataset_v2 TO authenticated;
GRANT DELETE ON TABLE public.master_dataset TO anon;
GRANT INSERT ON TABLE public.master_dataset TO anon;
GRANT REFERENCES ON TABLE public.master_dataset TO anon;
GRANT SELECT ON TABLE public.master_dataset TO anon;
GRANT TRIGGER ON TABLE public.master_dataset TO anon;
GRANT TRUNCATE ON TABLE public.master_dataset TO anon;
GRANT UPDATE ON TABLE public.master_dataset TO anon;
GRANT DELETE ON TABLE public.master_dataset TO authenticated;
GRANT INSERT ON TABLE public.master_dataset TO authenticated;
GRANT REFERENCES ON TABLE public.master_dataset TO authenticated;
GRANT SELECT ON TABLE public.master_dataset TO authenticated;
GRANT TRIGGER ON TABLE public.master_dataset TO authenticated;
GRANT TRUNCATE ON TABLE public.master_dataset TO authenticated;
GRANT UPDATE ON TABLE public.master_dataset TO authenticated;
GRANT SELECT ON SEQUENCE public.model_edges_id_seq TO anon;
GRANT UPDATE ON SEQUENCE public.model_edges_id_seq TO anon;
GRANT USAGE ON SEQUENCE public.model_edges_id_seq TO anon;
GRANT SELECT ON SEQUENCE public.model_edges_id_seq TO authenticated;
GRANT UPDATE ON SEQUENCE public.model_edges_id_seq TO authenticated;
GRANT USAGE ON SEQUENCE public.model_edges_id_seq TO authenticated;
GRANT DELETE ON TABLE public.model_edges TO anon;
GRANT INSERT ON TABLE public.model_edges TO anon;
GRANT REFERENCES ON TABLE public.model_edges TO anon;
GRANT SELECT ON TABLE public.model_edges TO anon;
GRANT TRIGGER ON TABLE public.model_edges TO anon;
GRANT TRUNCATE ON TABLE public.model_edges TO anon;
GRANT UPDATE ON TABLE public.model_edges TO anon;
GRANT DELETE ON TABLE public.model_edges TO authenticated;
GRANT INSERT ON TABLE public.model_edges TO authenticated;
GRANT REFERENCES ON TABLE public.model_edges TO authenticated;
GRANT SELECT ON TABLE public.model_edges TO authenticated;
GRANT TRIGGER ON TABLE public.model_edges TO authenticated;
GRANT TRUNCATE ON TABLE public.model_edges TO authenticated;
GRANT UPDATE ON TABLE public.model_edges TO authenticated;
GRANT SELECT ON SEQUENCE public.model_picks_id_seq TO anon;
GRANT UPDATE ON SEQUENCE public.model_picks_id_seq TO anon;
GRANT USAGE ON SEQUENCE public.model_picks_id_seq TO anon;
GRANT SELECT ON SEQUENCE public.model_picks_id_seq TO authenticated;
GRANT UPDATE ON SEQUENCE public.model_picks_id_seq TO authenticated;
GRANT USAGE ON SEQUENCE public.model_picks_id_seq TO authenticated;
GRANT DELETE ON TABLE public.model_picks TO anon;
GRANT INSERT ON TABLE public.model_picks TO anon;
GRANT REFERENCES ON TABLE public.model_picks TO anon;
GRANT SELECT ON TABLE public.model_picks TO anon;
GRANT TRIGGER ON TABLE public.model_picks TO anon;
GRANT TRUNCATE ON TABLE public.model_picks TO anon;
GRANT UPDATE ON TABLE public.model_picks TO anon;
GRANT DELETE ON TABLE public.model_picks TO authenticated;
GRANT INSERT ON TABLE public.model_picks TO authenticated;
GRANT REFERENCES ON TABLE public.model_picks TO authenticated;
GRANT SELECT ON TABLE public.model_picks TO authenticated;
GRANT TRIGGER ON TABLE public.model_picks TO authenticated;
GRANT TRUNCATE ON TABLE public.model_picks TO authenticated;
GRANT UPDATE ON TABLE public.model_picks TO authenticated;
GRANT SELECT ON SEQUENCE public.model_predictions_id_seq TO anon;
GRANT UPDATE ON SEQUENCE public.model_predictions_id_seq TO anon;
GRANT USAGE ON SEQUENCE public.model_predictions_id_seq TO anon;
GRANT SELECT ON SEQUENCE public.model_predictions_id_seq TO authenticated;
GRANT UPDATE ON SEQUENCE public.model_predictions_id_seq TO authenticated;
GRANT USAGE ON SEQUENCE public.model_predictions_id_seq TO authenticated;
GRANT DELETE ON TABLE public.model_predictions TO anon;
GRANT INSERT ON TABLE public.model_predictions TO anon;
GRANT REFERENCES ON TABLE public.model_predictions TO anon;
GRANT SELECT ON TABLE public.model_predictions TO anon;
GRANT TRIGGER ON TABLE public.model_predictions TO anon;
GRANT TRUNCATE ON TABLE public.model_predictions TO anon;
GRANT UPDATE ON TABLE public.model_predictions TO anon;
GRANT DELETE ON TABLE public.model_predictions TO authenticated;
GRANT INSERT ON TABLE public.model_predictions TO authenticated;
GRANT REFERENCES ON TABLE public.model_predictions TO authenticated;
GRANT SELECT ON TABLE public.model_predictions TO authenticated;
GRANT TRIGGER ON TABLE public.model_predictions TO authenticated;
GRANT TRUNCATE ON TABLE public.model_predictions TO authenticated;
GRANT UPDATE ON TABLE public.model_predictions TO authenticated;
GRANT DELETE ON TABLE public.model_versions TO anon;
GRANT INSERT ON TABLE public.model_versions TO anon;
GRANT REFERENCES ON TABLE public.model_versions TO anon;
GRANT SELECT ON TABLE public.model_versions TO anon;
GRANT TRIGGER ON TABLE public.model_versions TO anon;
GRANT TRUNCATE ON TABLE public.model_versions TO anon;
GRANT UPDATE ON TABLE public.model_versions TO anon;
GRANT DELETE ON TABLE public.model_versions TO authenticated;
GRANT INSERT ON TABLE public.model_versions TO authenticated;
GRANT REFERENCES ON TABLE public.model_versions TO authenticated;
GRANT SELECT ON TABLE public.model_versions TO authenticated;
GRANT TRIGGER ON TABLE public.model_versions TO authenticated;
GRANT TRUNCATE ON TABLE public.model_versions TO authenticated;
GRANT UPDATE ON TABLE public.model_versions TO authenticated;
GRANT SELECT ON TABLE public.odds_books TO anon;
GRANT SELECT ON TABLE public.odds_books TO authenticated;
GRANT SELECT ON SEQUENCE public.pre_fight_snapshots_id_seq TO anon;
GRANT UPDATE ON SEQUENCE public.pre_fight_snapshots_id_seq TO anon;
GRANT USAGE ON SEQUENCE public.pre_fight_snapshots_id_seq TO anon;
GRANT SELECT ON SEQUENCE public.pre_fight_snapshots_id_seq TO authenticated;
GRANT UPDATE ON SEQUENCE public.pre_fight_snapshots_id_seq TO authenticated;
GRANT USAGE ON SEQUENCE public.pre_fight_snapshots_id_seq TO authenticated;
GRANT DELETE ON TABLE public.pre_fight_snapshots TO anon;
GRANT INSERT ON TABLE public.pre_fight_snapshots TO anon;
GRANT REFERENCES ON TABLE public.pre_fight_snapshots TO anon;
GRANT SELECT ON TABLE public.pre_fight_snapshots TO anon;
GRANT TRIGGER ON TABLE public.pre_fight_snapshots TO anon;
GRANT TRUNCATE ON TABLE public.pre_fight_snapshots TO anon;
GRANT UPDATE ON TABLE public.pre_fight_snapshots TO anon;
GRANT DELETE ON TABLE public.pre_fight_snapshots TO authenticated;
GRANT INSERT ON TABLE public.pre_fight_snapshots TO authenticated;
GRANT REFERENCES ON TABLE public.pre_fight_snapshots TO authenticated;
GRANT SELECT ON TABLE public.pre_fight_snapshots TO authenticated;
GRANT TRIGGER ON TABLE public.pre_fight_snapshots TO authenticated;
GRANT TRUNCATE ON TABLE public.pre_fight_snapshots TO authenticated;
GRANT UPDATE ON TABLE public.pre_fight_snapshots TO authenticated;
GRANT SELECT ON SEQUENCE public.prediction_indicators_id_seq TO anon;
GRANT UPDATE ON SEQUENCE public.prediction_indicators_id_seq TO anon;
GRANT USAGE ON SEQUENCE public.prediction_indicators_id_seq TO anon;
GRANT SELECT ON SEQUENCE public.prediction_indicators_id_seq TO authenticated;
GRANT UPDATE ON SEQUENCE public.prediction_indicators_id_seq TO authenticated;
GRANT USAGE ON SEQUENCE public.prediction_indicators_id_seq TO authenticated;
GRANT DELETE ON TABLE public.prediction_indicators TO anon;
GRANT INSERT ON TABLE public.prediction_indicators TO anon;
GRANT REFERENCES ON TABLE public.prediction_indicators TO anon;
GRANT SELECT ON TABLE public.prediction_indicators TO anon;
GRANT TRIGGER ON TABLE public.prediction_indicators TO anon;
GRANT TRUNCATE ON TABLE public.prediction_indicators TO anon;
GRANT UPDATE ON TABLE public.prediction_indicators TO anon;
GRANT DELETE ON TABLE public.prediction_indicators TO authenticated;
GRANT INSERT ON TABLE public.prediction_indicators TO authenticated;
GRANT REFERENCES ON TABLE public.prediction_indicators TO authenticated;
GRANT SELECT ON TABLE public.prediction_indicators TO authenticated;
GRANT TRIGGER ON TABLE public.prediction_indicators TO authenticated;
GRANT TRUNCATE ON TABLE public.prediction_indicators TO authenticated;
GRANT UPDATE ON TABLE public.prediction_indicators TO authenticated;
GRANT SELECT ON SEQUENCE public.predictions_id_seq TO anon;
GRANT UPDATE ON SEQUENCE public.predictions_id_seq TO anon;
GRANT USAGE ON SEQUENCE public.predictions_id_seq TO anon;
GRANT SELECT ON SEQUENCE public.predictions_id_seq TO authenticated;
GRANT UPDATE ON SEQUENCE public.predictions_id_seq TO authenticated;
GRANT USAGE ON SEQUENCE public.predictions_id_seq TO authenticated;
GRANT DELETE ON TABLE public.predictions TO anon;
GRANT INSERT ON TABLE public.predictions TO anon;
GRANT REFERENCES ON TABLE public.predictions TO anon;
GRANT SELECT ON TABLE public.predictions TO anon;
GRANT TRIGGER ON TABLE public.predictions TO anon;
GRANT TRUNCATE ON TABLE public.predictions TO anon;
GRANT UPDATE ON TABLE public.predictions TO anon;
GRANT DELETE ON TABLE public.predictions TO authenticated;
GRANT INSERT ON TABLE public.predictions TO authenticated;
GRANT REFERENCES ON TABLE public.predictions TO authenticated;
GRANT SELECT ON TABLE public.predictions TO authenticated;
GRANT TRIGGER ON TABLE public.predictions TO authenticated;
GRANT TRUNCATE ON TABLE public.predictions TO authenticated;
GRANT UPDATE ON TABLE public.predictions TO authenticated;
GRANT SELECT ON SEQUENCE public.premium_waitlist_id_seq TO anon;
GRANT UPDATE ON SEQUENCE public.premium_waitlist_id_seq TO anon;
GRANT USAGE ON SEQUENCE public.premium_waitlist_id_seq TO anon;
GRANT SELECT ON SEQUENCE public.premium_waitlist_id_seq TO authenticated;
GRANT UPDATE ON SEQUENCE public.premium_waitlist_id_seq TO authenticated;
GRANT USAGE ON SEQUENCE public.premium_waitlist_id_seq TO authenticated;
GRANT DELETE ON TABLE public.premium_waitlist TO anon;
GRANT INSERT ON TABLE public.premium_waitlist TO anon;
GRANT REFERENCES ON TABLE public.premium_waitlist TO anon;
GRANT SELECT ON TABLE public.premium_waitlist TO anon;
GRANT TRIGGER ON TABLE public.premium_waitlist TO anon;
GRANT TRUNCATE ON TABLE public.premium_waitlist TO anon;
GRANT UPDATE ON TABLE public.premium_waitlist TO anon;
GRANT DELETE ON TABLE public.premium_waitlist TO authenticated;
GRANT INSERT ON TABLE public.premium_waitlist TO authenticated;
GRANT REFERENCES ON TABLE public.premium_waitlist TO authenticated;
GRANT SELECT ON TABLE public.premium_waitlist TO authenticated;
GRANT TRIGGER ON TABLE public.premium_waitlist TO authenticated;
GRANT TRUNCATE ON TABLE public.premium_waitlist TO authenticated;
GRANT UPDATE ON TABLE public.premium_waitlist TO authenticated;
GRANT DELETE ON TABLE public.profiles TO anon;
GRANT INSERT ON TABLE public.profiles TO anon;
GRANT REFERENCES ON TABLE public.profiles TO anon;
GRANT SELECT ON TABLE public.profiles TO anon;
GRANT TRIGGER ON TABLE public.profiles TO anon;
GRANT TRUNCATE ON TABLE public.profiles TO anon;
GRANT UPDATE ON TABLE public.profiles TO anon;
GRANT DELETE ON TABLE public.profiles TO authenticated;
GRANT INSERT ON TABLE public.profiles TO authenticated;
GRANT REFERENCES ON TABLE public.profiles TO authenticated;
GRANT SELECT ON TABLE public.profiles TO authenticated;
GRANT TRIGGER ON TABLE public.profiles TO authenticated;
GRANT TRUNCATE ON TABLE public.profiles TO authenticated;
GRANT UPDATE ON TABLE public.profiles TO authenticated;
GRANT SELECT ON SEQUENCE public.prop_model_locks_id_seq TO anon;
GRANT UPDATE ON SEQUENCE public.prop_model_locks_id_seq TO anon;
GRANT USAGE ON SEQUENCE public.prop_model_locks_id_seq TO anon;
GRANT SELECT ON SEQUENCE public.prop_model_locks_id_seq TO authenticated;
GRANT UPDATE ON SEQUENCE public.prop_model_locks_id_seq TO authenticated;
GRANT USAGE ON SEQUENCE public.prop_model_locks_id_seq TO authenticated;
GRANT SELECT ON SEQUENCE public.prop_projections_id_seq TO anon;
GRANT UPDATE ON SEQUENCE public.prop_projections_id_seq TO anon;
GRANT USAGE ON SEQUENCE public.prop_projections_id_seq TO anon;
GRANT SELECT ON SEQUENCE public.prop_projections_id_seq TO authenticated;
GRANT UPDATE ON SEQUENCE public.prop_projections_id_seq TO authenticated;
GRANT USAGE ON SEQUENCE public.prop_projections_id_seq TO authenticated;
GRANT DELETE ON TABLE public.prop_projections TO anon;
GRANT INSERT ON TABLE public.prop_projections TO anon;
GRANT REFERENCES ON TABLE public.prop_projections TO anon;
GRANT SELECT ON TABLE public.prop_projections TO anon;
GRANT TRIGGER ON TABLE public.prop_projections TO anon;
GRANT TRUNCATE ON TABLE public.prop_projections TO anon;
GRANT UPDATE ON TABLE public.prop_projections TO anon;
GRANT DELETE ON TABLE public.prop_projections TO authenticated;
GRANT INSERT ON TABLE public.prop_projections TO authenticated;
GRANT REFERENCES ON TABLE public.prop_projections TO authenticated;
GRANT SELECT ON TABLE public.prop_projections TO authenticated;
GRANT TRIGGER ON TABLE public.prop_projections TO authenticated;
GRANT TRUNCATE ON TABLE public.prop_projections TO authenticated;
GRANT UPDATE ON TABLE public.prop_projections TO authenticated;
GRANT DELETE ON TABLE public.streak_effect_cache TO anon;
GRANT INSERT ON TABLE public.streak_effect_cache TO anon;
GRANT REFERENCES ON TABLE public.streak_effect_cache TO anon;
GRANT SELECT ON TABLE public.streak_effect_cache TO anon;
GRANT TRIGGER ON TABLE public.streak_effect_cache TO anon;
GRANT TRUNCATE ON TABLE public.streak_effect_cache TO anon;
GRANT UPDATE ON TABLE public.streak_effect_cache TO anon;
GRANT DELETE ON TABLE public.streak_effect_cache TO authenticated;
GRANT INSERT ON TABLE public.streak_effect_cache TO authenticated;
GRANT REFERENCES ON TABLE public.streak_effect_cache TO authenticated;
GRANT SELECT ON TABLE public.streak_effect_cache TO authenticated;
GRANT TRIGGER ON TABLE public.streak_effect_cache TO authenticated;
GRANT TRUNCATE ON TABLE public.streak_effect_cache TO authenticated;
GRANT UPDATE ON TABLE public.streak_effect_cache TO authenticated;
GRANT SELECT ON SEQUENCE public.user_alert_deliveries_id_seq TO anon;
GRANT UPDATE ON SEQUENCE public.user_alert_deliveries_id_seq TO anon;
GRANT USAGE ON SEQUENCE public.user_alert_deliveries_id_seq TO anon;
GRANT SELECT ON SEQUENCE public.user_alert_deliveries_id_seq TO authenticated;
GRANT UPDATE ON SEQUENCE public.user_alert_deliveries_id_seq TO authenticated;
GRANT USAGE ON SEQUENCE public.user_alert_deliveries_id_seq TO authenticated;
GRANT SELECT ON TABLE public.user_alert_deliveries TO authenticated;
GRANT INSERT ON TABLE public.user_alert_prefs TO authenticated;
GRANT SELECT ON TABLE public.user_alert_prefs TO authenticated;
GRANT UPDATE ON TABLE public.user_alert_prefs TO authenticated;
GRANT SELECT ON SEQUENCE public.user_alerts_id_seq TO anon;
GRANT UPDATE ON SEQUENCE public.user_alerts_id_seq TO anon;
GRANT USAGE ON SEQUENCE public.user_alerts_id_seq TO anon;
GRANT SELECT ON SEQUENCE public.user_alerts_id_seq TO authenticated;
GRANT UPDATE ON SEQUENCE public.user_alerts_id_seq TO authenticated;
GRANT USAGE ON SEQUENCE public.user_alerts_id_seq TO authenticated;
GRANT DELETE ON TABLE public.user_alerts TO authenticated;
GRANT INSERT ON TABLE public.user_alerts TO authenticated;
GRANT SELECT ON TABLE public.user_alerts TO authenticated;
GRANT UPDATE ON TABLE public.user_alerts TO authenticated;
GRANT DELETE ON TABLE public.user_bankrolls TO anon;
GRANT INSERT ON TABLE public.user_bankrolls TO anon;
GRANT REFERENCES ON TABLE public.user_bankrolls TO anon;
GRANT SELECT ON TABLE public.user_bankrolls TO anon;
GRANT TRIGGER ON TABLE public.user_bankrolls TO anon;
GRANT TRUNCATE ON TABLE public.user_bankrolls TO anon;
GRANT UPDATE ON TABLE public.user_bankrolls TO anon;
GRANT DELETE ON TABLE public.user_bankrolls TO authenticated;
GRANT INSERT ON TABLE public.user_bankrolls TO authenticated;
GRANT REFERENCES ON TABLE public.user_bankrolls TO authenticated;
GRANT SELECT ON TABLE public.user_bankrolls TO authenticated;
GRANT TRIGGER ON TABLE public.user_bankrolls TO authenticated;
GRANT TRUNCATE ON TABLE public.user_bankrolls TO authenticated;
GRANT UPDATE ON TABLE public.user_bankrolls TO authenticated;
GRANT SELECT ON SEQUENCE public.user_bets_id_seq TO anon;
GRANT UPDATE ON SEQUENCE public.user_bets_id_seq TO anon;
GRANT USAGE ON SEQUENCE public.user_bets_id_seq TO anon;
GRANT SELECT ON SEQUENCE public.user_bets_id_seq TO authenticated;
GRANT UPDATE ON SEQUENCE public.user_bets_id_seq TO authenticated;
GRANT USAGE ON SEQUENCE public.user_bets_id_seq TO authenticated;
GRANT DELETE ON TABLE public.user_bets TO anon;
GRANT INSERT ON TABLE public.user_bets TO anon;
GRANT REFERENCES ON TABLE public.user_bets TO anon;
GRANT SELECT ON TABLE public.user_bets TO anon;
GRANT TRIGGER ON TABLE public.user_bets TO anon;
GRANT TRUNCATE ON TABLE public.user_bets TO anon;
GRANT UPDATE ON TABLE public.user_bets TO anon;
GRANT DELETE ON TABLE public.user_bets TO authenticated;
GRANT INSERT ON TABLE public.user_bets TO authenticated;
GRANT REFERENCES ON TABLE public.user_bets TO authenticated;
GRANT SELECT ON TABLE public.user_bets TO authenticated;
GRANT TRIGGER ON TABLE public.user_bets TO authenticated;
GRANT TRUNCATE ON TABLE public.user_bets TO authenticated;
GRANT UPDATE ON TABLE public.user_bets TO authenticated;
GRANT DELETE ON TABLE public.user_watchlist TO authenticated;
GRANT INSERT ON TABLE public.user_watchlist TO authenticated;
GRANT SELECT ON TABLE public.user_watchlist TO authenticated;
REVOKE EXECUTE ON FUNCTION public.win_model_locks_guard() FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.win_model_locks_no_rewrite() FROM PUBLIC, anon, authenticated;

RESET ROLE;
CREATE TRIGGER on_auth_user_created AFTER INSERT ON auth.users FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
SET ROLE postgres;
CREATE VIEW public.v_prop_projections_current WITH (security_invoker = true) AS SELECT * FROM public.prop_projections;
CREATE VIEW public.v_events_public AS SELECT id, name, event_date FROM public.events;
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON public.v_prop_projections_current, public.v_events_public TO anon, authenticated;
GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role; GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO service_role;
RESET ROLE;
