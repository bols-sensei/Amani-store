/* Amani — navigation partagée.
 * Charger en fin de <body>, après routes.js :
 *   <script src="../shared/js/routes.js"></script>
 *   <script src="../shared/js/app.js"></script>
 *
 * Ce script :
 *  1. calcule la page courante à partir de l'URL ;
 *  2. rend la barre d'onglets du bas (identique sur toutes les pages d'un espace) ;
 *  3. applique les liaisons bouton/carte -> page déclarées dans routes.js ;
 *  4. branche les boutons « retour » (historique, sinon page parente) ;
 *  5. ajoute les cartes d'accès rapides sur les pages « Plus ».
 */
(function () {
  'use strict';

  var R = window.AmaniRoutes;
  if (!R) { console.error('[Amani] routes.js doit être chargé avant app.js'); return; }

  /* ---------- Racine du frontend, déduite de l'emplacement de ce script ---------- */
  var BASE = (document.currentScript && document.currentScript.src || '').replace(/shared\/js\/app\.js.*$/, '');

  function url(key) {
    var p = R.pages[key];
    return p ? BASE + p.path : '#';
  }

  /* ---------- Page courante : "espace/page" ---------- */
  function currentKey() {
    var parts = location.pathname.split('/').filter(Boolean);
    var file = parts.pop() || '';
    var dir = parts.pop() || '';
    if (!/\.html?$/i.test(file)) { dir = file; file = 'index.html'; }
    var key = dir + '/' + file.replace(/\.html?$/i, '');
    return R.pages[key] ? key : null;
  }

  var CUR = currentKey();
  var ROLE = CUR ? CUR.split('/')[0] : null;
  var PAGE = CUR ? R.pages[CUR] : null;

  /* ---------- Utilitaires ---------- */
  function fold(s) {
    return String(s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/\s+/g, ' ').trim().toLowerCase();
  }

  function iconOf(el) {
    var i = el.querySelector('.material-symbols-outlined');
    return i ? i.textContent.trim() : '';
  }

  function textOf(el) {
    var clone = el.cloneNode(true);
    var icons = clone.querySelectorAll('.material-symbols-outlined');
    for (var i = 0; i < icons.length; i++) icons[i].remove();
    return fold(clone.textContent);
  }

  function labelOf(el) {
    var clone = el.cloneNode(true);
    var icons = clone.querySelectorAll('.material-symbols-outlined');
    for (var i = 0; i < icons.length; i++) icons[i].remove();
    return fold(clone.textContent + ' ' + (el.getAttribute('aria-label') || '') + ' ' + (el.getAttribute('title') || ''));
  }

  function clickables() {
    var all = document.querySelectorAll('a, button');
    var out = [];
    for (var i = 0; i < all.length; i++) if (!all[i].closest('nav')) out.push(all[i]);
    return out;
  }

  var CARD_SEL = 'article, li, [class*="rounded-2xl"], [class*="rounded-xl"]';

  function bind(el, key, rule) {
    if (!el || el.hasAttribute('data-href') || !R.pages[key]) return;
    el.setAttribute('data-href', url(key));
    if (rule && rule.card) el.setAttribute('data-card', '');
    if (rule && rule.delay) el.setAttribute('data-delay', String(rule.delay));
    if (el.tagName === 'A') el.setAttribute('href', url(key));
    el.classList.add('cursor-pointer');
  }

  /* ---------- 1. Barre d'onglets ---------- */
  var NAV_STYLE = {
    customer: {
      wrap: 'h-16 px-gutter-mobile flex justify-around items-center',
      item: 'relative flex flex-col items-center justify-center min-w-[56px] min-h-[44px] transition-colors',
      icon: 'text-[24px]', active: 'text-primary font-semibold', idle: 'text-on-surface-variant',
      badge: 'bg-primary text-on-primary'
    },
    vendor: {
      wrap: 'flex justify-around items-center h-16 px-space-xs',
      item: 'relative flex flex-col items-center justify-center min-w-[56px] h-12 transition-colors hover:text-primary',
      icon: 'text-[24px]', active: 'text-primary font-bold', idle: 'text-on-surface-variant',
      badge: 'bg-error text-on-error'
    },
    courier: {
      wrap: 'flex items-center justify-around h-20 px-space-xs',
      item: 'min-h-[44px] min-w-[44px] flex-1 flex flex-col items-center justify-center py-1 transition-all',
      icon: 'text-[24px]', active: 'text-primary-container font-semibold scale-105', idle: 'text-on-surface-variant',
      badge: 'bg-error text-on-error', labelExtra: ' mt-1'
    },
    superadmin: {
      wrap: 'flex items-center justify-around h-16 px-1',
      item: 'relative flex-1 flex flex-col items-center justify-center min-h-[44px] min-w-[44px] transition-colors',
      icon: 'text-[22px]', active: 'text-primary font-semibold', idle: 'text-on-surface-variant',
      badge: 'bg-tertiary text-on-tertiary'
    }
  };

  function renderNav() {
    var nav = document.querySelector('nav[data-active-classes]') || document.querySelector('body > nav');
    var items = ROLE && R.nav[ROLE];
    var st = ROLE && NAV_STYLE[ROLE];
    if (!nav || !items || !st) return;

    var html = '<div class="' + st.wrap + '">';
    items.forEach(function (it) {
      var badge = it.badge
        ? '<span class="absolute -top-1 -right-2 ' + st.badge + ' font-label-sm text-[10px] leading-tight px-1.5 py-0.5 rounded-full min-w-[16px] text-center">' + it.badge + '</span>'
        : '';
      html += '<a href="' + url(it.to) + '" data-path="' + it.path + '" data-nav="' + it.to + '" class="' + st.item + '">' +
        '<span class="relative flex items-center justify-center"><span class="material-symbols-outlined ' + st.icon + '">' + it.icon + '</span>' + badge + '</span>' +
        '<span class="font-label-sm text-label-sm' + (st.labelExtra || '') + '">' + it.label + '</span></a>';
    });
    nav.innerHTML = html + '</div>';
    setActive();
  }

  /* Réapplique l'onglet actif (écrase les surlignages ad hoc des anciens scripts de page). */
  function setActive() {
    var nav = document.querySelector('nav[data-active-classes]') || document.querySelector('body > nav');
    var st = ROLE && NAV_STYLE[ROLE];
    if (!nav || !st || !PAGE) return;
    var active = PAGE.tab || CUR;
    var links = nav.querySelectorAll('a[data-nav]');
    for (var i = 0; i < links.length; i++) {
      var on = links[i].getAttribute('data-nav') === active;
      links[i].className = st.item + ' ' + (on ? st.active : st.idle);
      if (on) links[i].setAttribute('aria-current', 'page'); else links[i].removeAttribute('aria-current');
    }
  }

  /* ---------- 2. Liaisons déclarées ---------- */
  var unmatched = [];   // règles sans élément correspondant (utile pour le débogage)

  function applyBindings() {
    var rules = (CUR && R.bindings[CUR]) || [];
    var cands = clickables();

    rules.forEach(function (rule) {
      var found = [];
      if (rule.id) {
        var byId = document.getElementById(rule.id);
        if (byId) found.push(byId);
      } else if (rule.sel) {
        found = [].slice.call(document.querySelectorAll(rule.sel));
        if (rule.match) found = found.filter(function (el) { return fold(el.textContent).indexOf(fold(rule.match)) !== -1; });
      } else if (rule.heading) {
        var needle = fold(rule.heading);
        [].slice.call(document.querySelectorAll('h1, h2, h3, h4')).forEach(function (h) {
          if (fold(h.textContent).indexOf(needle) !== -1) found.push(h);
        });
      } else if (rule.icon) {
        found = cands.filter(function (c) { return iconOf(c) === rule.icon; });
      } else if (rule.eq) {
        var exact = fold(rule.eq);
        found = cands.filter(function (c) { return textOf(c) === exact; });
      } else if (rule.text) {
        var sub = fold(rule.text);
        found = cands.filter(function (c) { return labelOf(c).indexOf(sub) !== -1; });
      }

      if (!found.length) unmatched.push(rule);

      found.forEach(function (el) {
        var target = rule.card ? (el.closest(CARD_SEL) || el) : el;
        bind(target, rule.to, rule);
      });
    });
  }

  /* ---------- 3. Boutons « retour » ---------- */
  var BACK_ICONS = { arrow_back: 1, arrow_back_ios: 1, arrow_back_ios_new: 1, chevron_left: 1 };

  function applyBack() {
    clickables().forEach(function (el) {
      if (el.hasAttribute('data-href') || el.hasAttribute('data-back')) return;
      var ic = iconOf(el);
      var lbl = labelOf(el);
      if (BACK_ICONS[ic] || /^retour\b/.test(lbl)) el.setAttribute('data-back', '');
    });
  }

  function goBack() {
    var sameSite = document.referrer && /^https?:/.test(document.referrer) && document.referrer.indexOf(location.origin) === 0;
    if (sameSite && history.length > 1 && document.referrer !== location.href) { history.back(); return; }
    if (PAGE && PAGE.parent) { location.href = url(PAGE.parent); return; }
    history.back();
  }

  /* ---------- 4. Accès rapides ---------- */
  function renderHub() {
    var hub = CUR && R.hubs[CUR];
    var main = document.querySelector('main');
    if (!hub || !main || main.querySelector('[data-hub]')) return;

    var rows = hub.items.map(function (k) {
      var p = R.pages[k];
      return '<a href="' + url(k) + '" class="flex items-center gap-3 py-3 min-h-[44px] active:bg-surface-container-low rounded-lg">' +
        '<span class="material-symbols-outlined text-primary">' + p.i + '</span>' +
        '<span class="flex-1 font-body-md text-body-md text-on-surface">' + p.t + '</span>' +
        '<span class="material-symbols-outlined text-outline">chevron_right</span></a>';
    }).join('');

    var card = document.createElement('section');
    card.setAttribute('data-hub', '');
    card.className = 'bg-surface-container-lowest rounded-2xl p-4 shadow-sm mb-4';
    card.innerHTML = '<h2 class="font-headline-md text-headline-md text-on-surface mb-1">' + hub.title + '</h2>' +
      '<div class="divide-y divide-outline-variant/40">' + rows + '</div>';
    main.insertBefore(card, main.firstChild);
  }

  /* ---------- Gestionnaire de clics (phase de capture) ---------- */
  var pending = false;

  document.addEventListener('click', function (e) {
    var t = e.target.closest ? e.target.closest('[data-href], [data-back]') : null;

    if (!t) {
      var dead = e.target.closest && e.target.closest('a[href="#"]');
      if (dead) e.preventDefault();               // évite le saut en haut de page
      return;
    }

    // Carte cliquable : on laisse vivre les boutons/liens internes non liés.
    if (t.hasAttribute('data-card')) {
      var inner = e.target.closest('button, a, input, select, textarea, label');
      if (inner && inner !== t && t.contains(inner)) return;
    }

    if (t.hasAttribute('data-back')) {
      e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation();
      goBack();
      return;
    }

    var dest = t.getAttribute('data-href');
    var delay = parseInt(t.getAttribute('data-delay') || '0', 10);

    if (delay) {                                  // laisse l'animation existante se jouer
      if (pending) return;
      pending = true;
      setTimeout(function () { location.href = dest; }, delay);
      return;
    }

    e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation();
    location.href = dest;
  }, true);

  /* ---------- Démarrage ---------- */
  function init() {
    renderNav();
    applyBindings();
    applyBack();
    renderHub();
    if (CUR === 'customer/splash') setTimeout(function () { location.href = url('customer/index'); }, 3200);
  }

  init();
  // Dernier mot sur l'onglet actif, après les DOMContentLoaded des anciens scripts de page.
  document.addEventListener('DOMContentLoaded', setActive);
  window.addEventListener('load', setActive);

  window.Amani = { url: url, current: CUR, role: ROLE, goBack: goBack, unmatched: unmatched };
})();
