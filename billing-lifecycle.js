/* ==========================================================================
   billing-lifecycle.js — what a Stripe event means for a member's access.

   This is a PURE function of the event. No network, no database, no clock it
   does not receive. That is the whole point: the subscription lifecycle is the
   part of a payment system that is hardest to test and most expensive to get
   wrong, so it lives here, where `tests/billing-lifecycle.test.js` can drive
   every state — signup, renewal, cancellation, expiry, failed payment,
   reinstatement, refund — without a Stripe account existing.

   The edge function is a thin wrapper: verify the signature, dedupe on the
   event id, call decide(), write what it says.

   ------------------------------------------------------------------------
   ONE ENTITLEMENT RULE, AND THIS IS NOT IT
   ------------------------------------------------------------------------
   `current_user_entitlement()` in Postgres decides who is Pro, by reading
   `profiles.tier` and `profiles.tier_expires_at`. This module's only job is to
   keep those two columns true to Stripe. It does not answer "is this member
   Pro" and must never be asked to.

   That has a useful consequence: **expiry does the work of a grace period.**
   A subscription that goes `past_due` keeps its expiry at Stripe's
   `current_period_end`, so the member keeps access while Stripe retries the
   card and loses it automatically when the period ends. There is no separate
   grace timer to drift, and no cron to forget.

   ------------------------------------------------------------------------
   THE RULES, AND WHY EACH ONE
   ------------------------------------------------------------------------
   active, trialing      -> Pro until current_period_end.
   past_due              -> Pro until current_period_end. Stripe is still
                            retrying; cutting access off at the first failed
                            charge punishes an expired card, and the period
                            end removes it anyway if the retries fail.
   canceled              -> Pro until current_period_end IF the member
                            cancelled and the period is still running (they
                            paid for it). Immediately free if the period has
                            already ended, or if Stripe cancelled for non-
                            payment (unpaid).
   unpaid                -> free now. Stripe has given up retrying.
   incomplete            -> free. The first payment never succeeded.
   incomplete_expired    -> free. It never will.
   paused                -> free. No money is flowing.

   A `canceled` subscription whose period has NOT ended is the case most often
   got wrong: the member has paid through a date and is owed access until it,
   even though the subscription object says cancelled.
   ========================================================================== */
(function () {
  'use strict';

  const B = {};

  B.PRO_TIER = 'premium';    // the value profiles.tier already uses
  B.FREE_TIER = 'free';

  // Statuses that keep access until the paid period ends.
  B.STATUS_KEEPS_PERIOD = ['active', 'trialing', 'past_due'];
  // Statuses that end access immediately, whatever the dates say.
  B.STATUS_ENDS_NOW = ['unpaid', 'incomplete', 'incomplete_expired', 'paused'];

  // Events we act on. Anything else is acknowledged and ignored — a webhook
  // that 500s on an unexpected event type makes Stripe retry it forever.
  B.HANDLED = [
    'checkout.session.completed',
    'customer.subscription.created',
    'customer.subscription.updated',
    'customer.subscription.deleted',
    'invoice.paid',
    'invoice.payment_succeeded',
    'invoice.payment_failed'
  ];

  function iso(unixSeconds) {
    if (unixSeconds === null || unixSeconds === undefined) return null;
    const n = Number(unixSeconds);
    if (!isFinite(n) || n <= 0) return null;
    return new Date(n * 1000).toISOString();
  }

  function obj(event) {
    return (event && event.data && event.data.object) || {};
  }

  // The user id Stripe is carrying for us. Set at checkout; Stripe echoes it
  // back on the objects it creates. When it is absent the webhook falls back to
  // matching on stripe_customer_id — see §resolving a member in the handler.
  B.userIdFrom = function (o) {
    if (!o) return null;
    if (o.client_reference_id) return String(o.client_reference_id);
    if (o.metadata && o.metadata.cfl_user_id) return String(o.metadata.cfl_user_id);
    if (o.subscription_details && o.subscription_details.metadata &&
        o.subscription_details.metadata.cfl_user_id) {
      return String(o.subscription_details.metadata.cfl_user_id);
    }
    return null;
  };

  function idOf(v) {
    if (!v) return null;
    return typeof v === 'string' ? v : (v.id ? String(v.id) : null);
  }

  /* ----------------------------------------------------------------------
     entitlementFor — status + dates -> tier and expiry. The core rule.
     `nowMs` is injected so tests can stand at any point in time.
     ---------------------------------------------------------------------- */
  B.entitlementFor = function (status, currentPeriodEndIso, nowMs) {
    const now = (nowMs === undefined || nowMs === null) ? Date.now() : nowMs;
    const endMs = currentPeriodEndIso ? Date.parse(currentPeriodEndIso) : NaN;
    const periodStillRunning = isFinite(endMs) && endMs > now;

    if (B.STATUS_ENDS_NOW.indexOf(status) !== -1) {
      return { tier: B.FREE_TIER, expiresAt: null, reason: 'status_' + status + '_ends_access' };
    }
    if (B.STATUS_KEEPS_PERIOD.indexOf(status) !== -1) {
      if (!currentPeriodEndIso) {
        // Active with no period end is not something to guess at. Grant
        // open-ended rather than nothing: Stripe says they are paying.
        return { tier: B.PRO_TIER, expiresAt: null, reason: 'status_' + status + '_no_period_end' };
      }
      return { tier: B.PRO_TIER, expiresAt: currentPeriodEndIso, reason: 'status_' + status };
    }
    if (status === 'canceled') {
      // Paid through a date they have not reached: they are owed it.
      return periodStillRunning
        ? { tier: B.PRO_TIER, expiresAt: currentPeriodEndIso, reason: 'canceled_but_period_paid' }
        : { tier: B.FREE_TIER, expiresAt: null, reason: 'canceled_period_over' };
    }
    // An unknown status is not a reason to grant access.
    return { tier: B.FREE_TIER, expiresAt: null, reason: 'unknown_status_' + String(status) };
  };

  /* ----------------------------------------------------------------------
     decide(event, nowMs) -> what the handler should write.
     Never throws. Always returns an object with an `action`.
     ---------------------------------------------------------------------- */
  B.decide = function (event, nowMs) {
    const type = (event && event.type) || '';
    const o = obj(event);
    const base = {
      action: 'ignore',
      eventId: (event && event.id) || null,
      eventType: type,
      userId: null,
      customerId: null,
      subscriptionId: null,
      tier: null,
      expiresAt: null,
      subscriptionStatus: null,
      cancelAtPeriodEnd: false,
      reason: 'unhandled_event_type'
    };

    if (B.HANDLED.indexOf(type) === -1) return base;

    base.userId = B.userIdFrom(o);
    base.customerId = idOf(o.customer);

    // ---- checkout completed: link the customer to the member -------------
    // Deliberately does NOT set entitlement. The session may arrive before or
    // after the subscription object, and only the subscription carries the
    // period dates. Linking here and entitling there means the two orders of
    // arrival produce the same end state.
    if (type === 'checkout.session.completed') {
      if (o.mode && o.mode !== 'subscription') {
        return Object.assign(base, { reason: 'checkout_not_a_subscription' });
      }
      return Object.assign(base, {
        action: 'link',
        subscriptionId: idOf(o.subscription),
        reason: 'checkout_completed_link_customer'
      });
    }

    // ---- invoices: acknowledge, do not entitle ---------------------------
    // invoice.paid always accompanies a subscription.updated carrying the new
    // period. Acting on both would be two writes racing to say the same thing;
    // acting on the invoice alone would mean reading period dates off the
    // wrong object.
    if (type === 'invoice.paid' || type === 'invoice.payment_succeeded') {
      return Object.assign(base, {
        action: 'note',
        subscriptionId: idOf(o.subscription),
        reason: 'invoice_paid_awaiting_subscription_update'
      });
    }
    if (type === 'invoice.payment_failed') {
      // Access is NOT cut here. Stripe moves the subscription to past_due and
      // sends subscription.updated; the period end still governs.
      return Object.assign(base, {
        action: 'note',
        subscriptionId: idOf(o.subscription),
        reason: 'invoice_payment_failed_awaiting_subscription_update'
      });
    }

    // ---- the subscription itself: the only thing that sets entitlement ---
    const status = type === 'customer.subscription.deleted'
      ? 'canceled'                       // deleted means cancelled, whatever the payload says
      : String(o.status || '');
    const periodEnd = iso(o.current_period_end);
    const ent = B.entitlementFor(status, periodEnd, nowMs);

    return Object.assign(base, {
      action: 'apply',
      subscriptionId: idOf(o.id) || idOf(o.subscription),
      tier: ent.tier,
      expiresAt: ent.expiresAt,
      subscriptionStatus: status,
      cancelAtPeriodEnd: !!o.cancel_at_period_end,
      reason: ent.reason
    });
  };

  /* ----------------------------------------------------------------------
     formatDay — a billing date a person can read.

     PINNED TO UTC, deliberately. Stripe periods land on midnight UTC, and
     formatting one in local time shows a member west of Greenwich the day
     BEFORE their access actually ends. A subscription that appears to expire a
     day early is a support ticket at best and a refund at worst.
     ---------------------------------------------------------------------- */
  B.formatDay = function (iso) {
    if (!iso) return null;
    const ms = Date.parse(iso);
    if (!isFinite(ms)) return null;
    try {
      return new Date(ms).toLocaleDateString('en-US', {
        year: 'numeric', month: 'long', day: 'numeric', timeZone: 'UTC'
      });
    } catch (e) {
      return new Date(ms).toISOString().slice(0, 10);
    }
  };

  /* ----------------------------------------------------------------------
     describe — the member-facing sentence for a billing state. Plain first,
     as COPY_STYLE.md requires, and never implying a payment during beta.
     ---------------------------------------------------------------------- */
  B.describe = function (state, nowMs) {
    const s = state || {};
    if (s.is_beta) {
      return { head: 'Free during beta',
               body: 'You have full access while CFL is in beta. Nothing is charged and no card is on file.' };
    }
    const status = s.subscription_status;
    const endIso = s.current_period_end;
    const now = (nowMs === undefined || nowMs === null) ? Date.now() : nowMs;
    const ends = endIso ? new Date(Date.parse(endIso)) : null;
    const endTxt = B.formatDay(endIso);

    if (!status) {
      return { head: 'Free account',
               body: 'You are on the free plan. Everything CFL publishes about the current card is free.' };
    }
    if (status === 'trialing') {
      return { head: 'Trial', body: endTxt ? 'Your trial runs until ' + endTxt + '.' : 'Your trial is running.' };
    }
    if (status === 'active') {
      return s.cancel_at_period_end
        ? { head: 'Ending ' + (endTxt || 'at the end of the period'),
            body: 'You have cancelled. Access continues until ' + (endTxt || 'the period ends') + ' — you have paid for it.' }
        : { head: 'Pro', body: endTxt ? 'Renews on ' + endTxt + '.' : 'Active.' };
    }
    if (status === 'past_due') {
      return { head: 'Payment failed',
               body: 'We could not take the last payment, so Stripe is retrying. ' +
                     'You keep access until ' + (endTxt || 'the period ends') +
                     '. Updating your card fixes it.' };
    }
    if (status === 'canceled') {
      const stillRunning = ends && ends.getTime() > now;
      return stillRunning
        ? { head: 'Ending ' + endTxt, body: 'Cancelled. Access continues until ' + endTxt + '.' }
        : { head: 'Free account', body: 'Your membership has ended. Everything free is still free.' };
    }
    if (status === 'unpaid') {
      return { head: 'Membership ended',
               body: 'Stripe stopped retrying the payment, so the membership ended. You can start again any time.' };
    }
    return { head: 'Free account', body: 'You are on the free plan.' };
  };

  const api = B;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else if (typeof window !== 'undefined') window.cflBilling = api;
})();
