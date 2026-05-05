/* ==========================================================================
   Cannon Fight Lab — auth module (_auth.js)
   Loaded after _shared.js on every page.

   Provides:
     - window.cflAuth.getUser()       → Supabase user object or null
     - window.cflAuth.getProfile()    → profile row from public.profiles or null
     - window.cflAuth.getTier()       → 'free' | 'premium' (default 'free')
     - window.cflAuth.isPremium()     → boolean
     - window.cflAuth.signUp(email, password)
     - window.cflAuth.signIn(email, password)
     - window.cflAuth.signOut()
     - window.cflAuth.resetPassword(email)
     - window.cflAuth.updateProfile({ display_name })
     - window.cflAuth.onAuthChange(callback)
     - window.cflAuth.requireAuth()   → redirects to /login.html if not signed in
     - window.cflAuth.joinWaitlist(email, source)
     - window.cflAuth.ready()         → promise that resolves once initial auth state is known

   IMPORTANT: This module only handles UI-level auth state. The real security
   enforcement happens in Postgres RLS policies. Never trust the tier returned
   here for anything beyond presentation.
   ========================================================================== */

(function () {
  if (!window.cflSupabase) {
    console.error('[auth] cflSupabase not initialized — load _shared.js first');
    return;
  }

  const sb = window.cflSupabase;
  const auth = {};

  // -------- internal state --------
  let _currentUser = null;
  let _currentProfile = null;
  let _profileFetchPromise = null;
  let _readyResolve;
  const _readyPromise = new Promise(r => { _readyResolve = r; });
  const _changeListeners = new Set();

  // -------- profile fetch (with single-flight) --------
  // We deduplicate concurrent profile fetches so multiple components asking
  // for the tier don't all hit the DB.
  async function _fetchProfile(userId) {
    if (_profileFetchPromise) return _profileFetchPromise;
    _profileFetchPromise = (async () => {
      try {
        const { data, error } = await sb
          .from('profiles')
          .select('id, email, display_name, tier, tier_expires_at, beta_premium, created_at')
          .eq('id', userId)
          .single();
        if (error) {
          // If profile doesn't exist (e.g. trigger didn't fire), assume free
          console.warn('[auth] profile fetch failed', error.message);
          return null;
        }
        // Check expiry on premium
        if (data.tier === 'premium' && data.tier_expires_at) {
          const expiry = new Date(data.tier_expires_at);
          if (expiry < new Date()) {
            data.tier = 'free';  // Expired — treat as free in UI
          }
        }
        return data;
      } finally {
        // Clear the in-flight promise so future fetches can re-run
        setTimeout(() => { _profileFetchPromise = null; }, 0);
      }
    })();
    return _profileFetchPromise;
  }

  function _emitChange() {
    _changeListeners.forEach(fn => {
      try { fn(_currentUser, _currentProfile); } catch (e) { console.error('[auth] listener error', e); }
    });
  }

  // -------- initial session bootstrap --------
  async function _bootstrap() {
    try {
      const { data: { session } } = await sb.auth.getSession();
      if (session && session.user) {
        _currentUser = session.user;
        _currentProfile = await _fetchProfile(session.user.id);
      }
    } catch (e) {
      console.error('[auth] bootstrap error', e);
    } finally {
      _readyResolve();
      _emitChange();
    }
  }

  // -------- Supabase auth state changes (signin / signout / token refresh) --------
  sb.auth.onAuthStateChange(async (event, session) => {
    if (event === 'SIGNED_IN' || event === 'TOKEN_REFRESHED' || event === 'USER_UPDATED') {
      _currentUser = session?.user || null;
      if (_currentUser) {
        _currentProfile = await _fetchProfile(_currentUser.id);
      }
    } else if (event === 'SIGNED_OUT') {
      _currentUser = null;
      _currentProfile = null;
    }
    _emitChange();
  });

  // -------- public API --------

  auth.ready = function () { return _readyPromise; };

  auth.getUser = function () { return _currentUser; };
  auth.getProfile = function () { return _currentProfile; };
  // getTier returns the EFFECTIVE tier — what the UI should treat the user as.
  // During beta, all account holders effectively have premium access via the
  // beta_premium flag. The underlying paid tier is still on the profile object
  // (use getPaidTier() if you need to distinguish a beta user from a true
  // paying customer once payments launch).
  auth.getTier = function () {
    if (!_currentProfile) return 'free';
    if (_currentProfile.beta_premium) return 'premium';
    return _currentProfile.tier || 'free';
  };
  auth.getPaidTier = function () {
    if (!_currentProfile) return 'free';
    return _currentProfile.tier || 'free';
  };
  auth.isPremium = function () { return auth.getTier() === 'premium'; };
  auth.isBetaPremium = function () {
    return !!(_currentProfile && _currentProfile.beta_premium);
  };
  auth.isSignedIn = function () { return !!_currentUser; };

  auth.onAuthChange = function (cb) {
    _changeListeners.add(cb);
    // Fire once with current state so caller doesn't need to handle initial render separately
    if (_currentUser !== null || _currentProfile !== null || _readyPromise) {
      _readyPromise.then(() => cb(_currentUser, _currentProfile));
    }
    return () => _changeListeners.delete(cb);
  };

  auth.signUp = async function (email, password, opts = {}) {
    const { data, error } = await sb.auth.signUp({
      email,
      password,
      options: {
        emailRedirectTo: window.location.origin + '/login.html?confirmed=1',
        data: { display_name: opts.display_name || null }
      }
    });
    return { data, error };
  };

  auth.signIn = async function (email, password) {
    const { data, error } = await sb.auth.signInWithPassword({ email, password });
    if (!error && data?.user) {
      _currentUser = data.user;
      _currentProfile = await _fetchProfile(data.user.id);
      _emitChange();
    }
    return { data, error };
  };

  auth.signOut = async function () {
    const { error } = await sb.auth.signOut();
    _currentUser = null;
    _currentProfile = null;
    _emitChange();
    return { error };
  };

  auth.resetPassword = async function (email) {
    const { data, error } = await sb.auth.resetPasswordForEmail(email, {
      redirectTo: window.location.origin + '/account.html?reset=1'
    });
    return { data, error };
  };

  auth.updatePassword = async function (newPassword) {
    const { data, error } = await sb.auth.updateUser({ password: newPassword });
    return { data, error };
  };

  auth.updateProfile = async function (updates) {
    if (!_currentUser) return { error: { message: 'Not signed in' } };
    // Strip fields users aren't allowed to change (RLS will reject anyway)
    const allowed = {};
    if ('display_name' in updates) allowed.display_name = updates.display_name;
    const { data, error } = await sb
      .from('profiles')
      .update(allowed)
      .eq('id', _currentUser.id)
      .select()
      .single();
    if (!error && data) {
      _currentProfile = data;
      _emitChange();
    }
    return { data, error };
  };

  auth.requireAuth = function (redirectTo) {
    return _readyPromise.then(() => {
      if (!_currentUser) {
        const next = redirectTo || (window.location.pathname + window.location.search);
        window.location.href = '/login.html?next=' + encodeURIComponent(next);
        return false;
      }
      return true;
    });
  };

  auth.joinWaitlist = async function (email, source) {
    const { data, error } = await sb
      .from('premium_waitlist')
      .insert({ email, source: source || 'unknown' });
    return { data, error };
  };

  // -------- nav integration helpers --------
  // Returns the HTML for the "auth slot" in the nav — either signed-in user
  // initials with dropdown, or "Sign in / Sign up" links. Pages call this
  // after the nav renders to inject the right state.
  auth.renderNavSlot = function (containerEl) {
    if (!containerEl) return;
    function paint() {
      if (_currentUser && _currentProfile) {
        const initials = (_currentProfile.display_name || _currentProfile.email || '?')
          .split(/[\s@]+/).filter(Boolean).map(w => w[0]).join('').slice(0, 2).toUpperCase();
        const tierBadge = _currentProfile.tier === 'premium'
          ? '<span class="cfl-tier-badge premium">Premium</span>'
          : '';
        containerEl.innerHTML = `
          <a href="/account.html" class="cfl-nav-user" title="Account">
            <span class="cfl-nav-avatar">${initials}</span>
            ${tierBadge}
          </a>
        `;
      } else {
        containerEl.innerHTML = `
          <a href="/login.html" class="cfl-nav-link">Sign in</a>
          <a href="/signup.html" class="cfl-nav-cta">Sign up</a>
        `;
      }
    }
    paint();
    auth.onAuthChange(paint);
  };

  // Kick off bootstrap
  _bootstrap();

  window.cflAuth = auth;
})();
