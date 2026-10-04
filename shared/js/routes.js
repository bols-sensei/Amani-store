/* Amani — table de routes centrale.
 *
 * Source unique de vérité pour la navigation :
 *  - pages     : toutes les pages (clé "espace/page" -> chemin, titre, icône, parent, onglet actif)
 *  - nav       : barre d'onglets du bas, par espace
 *  - bindings  : liaisons "bouton/carte -> page" (les écrans Stitch n'ont aucun lien réel)
 *  - hubs      : cartes d'accès rapides pour les pages secondaires qui n'ont pas d'onglet
 *
 * Les chemins sont relatifs à la racine du dossier frontend/ ; shared/js/app.js
 * calcule la racine à partir de son propre emplacement (marche en file://, en sous-dossier, etc.).
 */
(function (root) {
  'use strict';

  var pages = {
    /* ---------- Client ---------- */
    'customer/splash':        { path: 'customer/splash.html',        t: 'Démarrage',          i: 'hourglass_top' },
    'customer/login':         { path: 'customer/login.html',         t: 'Connexion',          i: 'login',            parent: 'customer/index',   tab: 'customer/account' },
    'customer/index':         { path: 'customer/index.html',         t: 'Accueil',            i: 'home',             tab: 'customer/index' },
    'customer/search':        { path: 'customer/search.html',        t: 'Recherche',          i: 'search',           tab: 'customer/search' },
    'customer/shop':          { path: 'customer/shop.html',          t: 'Boutique',           i: 'storefront',       parent: 'customer/index',   tab: 'customer/index' },
    'customer/product':       { path: 'customer/product.html',       t: 'Produit',            i: 'shopping_bag',     parent: 'customer/index',   tab: 'customer/index' },
    'customer/favorites':     { path: 'customer/favorites.html',     t: 'Favoris',            i: 'favorite',         parent: 'customer/account', tab: 'customer/account' },
    'customer/cart':          { path: 'customer/cart.html',          t: 'Panier',             i: 'shopping_bag',     tab: 'customer/cart' },
    'customer/checkout':      { path: 'customer/checkout.html',      t: 'Paiement',           i: 'payments',         parent: 'customer/cart',    tab: 'customer/cart' },
    'customer/order-confirm': { path: 'customer/order-confirm.html', t: 'Commande confirmée', i: 'task_alt',         parent: 'customer/index',   tab: 'customer/orders' },
    'customer/orders':        { path: 'customer/orders.html',        t: 'Commandes',          i: 'inventory_2',      tab: 'customer/orders' },
    'customer/track':         { path: 'customer/track.html',         t: 'Suivi de livraison', i: 'near_me',          parent: 'customer/orders',  tab: 'customer/orders' },
    'customer/receipt':       { path: 'customer/receipt.html',       t: 'Reçu',               i: 'receipt_long',     parent: 'customer/orders',  tab: 'customer/orders' },
    'customer/documents':     { path: 'customer/documents.html',     t: 'Mes documents',      i: 'description',      parent: 'customer/account', tab: 'customer/account' },
    'customer/account':       { path: 'customer/account.html',       t: 'Compte',             i: 'person',           tab: 'customer/account' },
    'customer/addresses':     { path: 'customer/addresses.html',     t: 'Mes adresses',       i: 'location_on',      parent: 'customer/account', tab: 'customer/account' },
    'customer/address-edit':  { path: 'customer/address-edit.html',  t: 'Adresse',            i: 'edit_location',    parent: 'customer/addresses', tab: 'customer/account' },
    'customer/notifications': { path: 'customer/notifications.html', t: 'Notifications',      i: 'notifications',    parent: 'customer/account', tab: 'customer/account' },
    'customer/install':       { path: 'customer/install.html',       t: "Installer l'appli",  i: 'download',         parent: 'customer/index',   tab: 'customer/index' },
    'customer/offline':       { path: 'customer/offline.html',       t: 'Hors connexion',     i: 'cloud_off',        parent: 'customer/index',   tab: 'customer/index' },

    /* ---------- Vendeur ---------- */
    'vendor/login':           { path: 'vendor/login.html',           t: 'Connexion vendeur',  i: 'login' },
    'vendor/index':           { path: 'vendor/index.html',           t: 'Dashboard',          i: 'dashboard',        tab: 'vendor/index' },
    'vendor/products':        { path: 'vendor/products.html',        t: 'Produits',           i: 'inventory_2',      tab: 'vendor/products' },
    'vendor/product-edit':    { path: 'vendor/product-edit.html',    t: 'Fiche produit',      i: 'edit',             parent: 'vendor/products' },
    'vendor/orders':          { path: 'vendor/orders.html',          t: 'Commandes',          i: 'shopping_bag',     tab: 'vendor/orders' },
    'vendor/order-detail':    { path: 'vendor/order-detail.html',    t: 'Détail commande',    i: 'receipt_long',     parent: 'vendor/orders' },
    'vendor/customers':       { path: 'vendor/customers.html',       t: 'Clients',            i: 'group',            tab: 'vendor/customers' },
    'vendor/customer-detail': { path: 'vendor/customer-detail.html', t: 'Fiche client',       i: 'person',           parent: 'vendor/customers' },
    'vendor/shipments':       { path: 'vendor/shipments.html',       t: 'Colis & expéditions', i: 'local_shipping',  parent: 'vendor/settings',  tab: 'vendor/settings' },
    'vendor/shipment-detail': { path: 'vendor/shipment-detail.html', t: 'Détail du colis',    i: 'package_2',        parent: 'vendor/shipments', tab: 'vendor/settings' },
    'vendor/couriers':        { path: 'vendor/couriers.html',        t: 'Livreurs',           i: 'two_wheeler',      parent: 'vendor/settings',  tab: 'vendor/settings' },
    'vendor/finances':        { path: 'vendor/finances.html',        t: 'Finances & caisse',  i: 'account_balance_wallet', parent: 'vendor/settings', tab: 'vendor/settings' },
    'vendor/invoices':        { path: 'vendor/invoices.html',        t: 'Factures SaaS',      i: 'receipt',          parent: 'vendor/settings',  tab: 'vendor/settings' },
    'vendor/delivery-zones':  { path: 'vendor/delivery-zones.html',  t: 'Zones & tarifs',     i: 'map',              parent: 'vendor/settings',  tab: 'vendor/settings' },
    'vendor/settings':        { path: 'vendor/settings.html',        t: 'Plus',               i: 'grid_view',        tab: 'vendor/settings' },

    /* ---------- Livreur ---------- */
    'courier/login':          { path: 'courier/login.html',          t: 'Connexion livreur',  i: 'login' },
    'courier/index':          { path: 'courier/index.html',          t: 'Livraisons',         i: 'home',             tab: 'courier/index' },
    'courier/shipments':      { path: 'courier/shipments.html',      t: 'En cours',           i: 'local_shipping',   tab: 'courier/shipments' },
    'courier/shipment-detail':{ path: 'courier/shipment-detail.html',t: 'Détail course',      i: 'package_2',        parent: 'courier/shipments' },
    'courier/qr-display':     { path: 'courier/qr-display.html',     t: 'Remise (QR)',        i: 'qr_code_2',        parent: 'courier/shipment-detail' },
    'courier/photo-capture':  { path: 'courier/photo-capture.html',  t: 'Photo de preuve',    i: 'photo_camera',     parent: 'courier/qr-display' },
    'courier/delivery-success':{ path: 'courier/delivery-success.html', t: 'Livraison réussie', i: 'task_alt',       parent: 'courier/index' },
    'courier/earnings':       { path: 'courier/earnings.html',       t: 'Gains',              i: 'account_balance_wallet', tab: 'courier/earnings' },
    'courier/profile':        { path: 'courier/profile.html',        t: 'Profil',             i: 'two_wheeler',      tab: 'courier/profile' },

    /* ---------- Super-admin ---------- */
    'superadmin/login':          { path: 'superadmin/login.html',          t: 'Connexion admin',   i: 'login' },
    'superadmin/index':          { path: 'superadmin/index.html',          t: 'Dashboard',         i: 'dashboard',  tab: 'superadmin/index' },
    'superadmin/tenants':        { path: 'superadmin/tenants.html',        t: 'Vendeurs',          i: 'storefront', tab: 'superadmin/tenants' },
    'superadmin/tenant-detail':  { path: 'superadmin/tenant-detail.html',  t: 'Fiche vendeur',     i: 'store',      parent: 'superadmin/tenants', tab: 'superadmin/tenants' },
    'superadmin/approvals':      { path: 'superadmin/approvals.html',      t: 'À valider',         i: 'verified',   tab: 'superadmin/approvals' },
    'superadmin/finance-stats':  { path: 'superadmin/finance-stats.html',  t: 'Finances',          i: 'payments',   tab: 'superadmin/finance-stats' },
    'superadmin/commissions':    { path: 'superadmin/commissions.html',    t: 'Commissions',       i: 'percent',    parent: 'superadmin/finance-stats', tab: 'superadmin/finance-stats' },
    'superadmin/commission-rules':{ path: 'superadmin/commission-rules.html', t: 'Règles de commission', i: 'rule', parent: 'superadmin/finance-stats', tab: 'superadmin/finance-stats' },
    'superadmin/invoices':       { path: 'superadmin/invoices.html',       t: 'Factures SaaS',     i: 'receipt_long', parent: 'superadmin/finance-stats', tab: 'superadmin/finance-stats' },
    'superadmin/invoice-detail': { path: 'superadmin/invoice-detail.html', t: 'Détail facture',    i: 'receipt',    parent: 'superadmin/invoices', tab: 'superadmin/finance-stats' },
    'superadmin/exchange-rates': { path: 'superadmin/exchange-rates.html', t: 'Taux de change',    i: 'currency_exchange', parent: 'superadmin/finance-stats', tab: 'superadmin/finance-stats' },
    'superadmin/plans':          { path: 'superadmin/plans.html',          t: 'Plans SaaS',        i: 'workspace_premium', parent: 'superadmin/config', tab: 'superadmin/config' },
    'superadmin/kimia':          { path: 'superadmin/kimia.html',          t: 'Kimia (fiscal)',    i: 'sync_alt',   parent: 'superadmin/config', tab: 'superadmin/config' },
    'superadmin/audit':          { path: 'superadmin/audit.html',          t: "Journal d'audit",   i: 'history',    parent: 'superadmin/config', tab: 'superadmin/config' },
    'superadmin/config':         { path: 'superadmin/config.html',         t: 'Plus',              i: 'tune',       tab: 'superadmin/config' }
  };

  /* Barre d'onglets du bas : un seul jeu d'onglets par espace (les écrans Stitch en avaient plusieurs, incohérents). */
  var nav = {
    customer: [
      { to: 'customer/index',   path: 'accueil',   label: 'Accueil',   icon: 'home' },
      { to: 'customer/search',  path: 'recherche', label: 'Recherche', icon: 'search' },
      { to: 'customer/cart',    path: 'panier',    label: 'Panier',    icon: 'shopping_bag', badge: 3 },
      { to: 'customer/orders',  path: 'commandes', label: 'Commandes', icon: 'inventory_2' },
      { to: 'customer/account', path: 'compte',    label: 'Compte',    icon: 'person' }
    ],
    vendor: [
      { to: 'vendor/index',     path: 'dashboard', label: 'Dashboard', icon: 'dashboard' },
      { to: 'vendor/products',  path: 'produits',  label: 'Produits',  icon: 'inventory_2' },
      { to: 'vendor/orders',    path: 'commandes', label: 'Commandes', icon: 'shopping_bag', badge: 1 },
      { to: 'vendor/customers', path: 'clients',   label: 'Clients',   icon: 'group' },
      { to: 'vendor/settings',  path: 'plus',      label: 'Plus',      icon: 'grid_view' }
    ],
    courier: [
      { to: 'courier/index',     path: 'livraisons', label: 'Livraisons', icon: 'home' },
      { to: 'courier/shipments', path: 'en-cours',   label: 'En cours',   icon: 'local_shipping' },
      { to: 'courier/earnings',  path: 'gains',      label: 'Gains',      icon: 'account_balance_wallet' },
      { to: 'courier/profile',   path: 'profil',     label: 'Profil',     icon: 'two_wheeler' }
    ],
    superadmin: [
      { to: 'superadmin/index',         path: 'dashboard', label: 'Dashboard', icon: 'dashboard' },
      { to: 'superadmin/tenants',       path: 'vendeurs',  label: 'Vendeurs',  icon: 'storefront' },
      { to: 'superadmin/approvals',     path: 'a-valider', label: 'À valider', icon: 'verified', badge: 8 },
      { to: 'superadmin/finance-stats', path: 'finances',  label: 'Finances',  icon: 'payments' },
      { to: 'superadmin/config',        path: 'plus',      label: 'Plus',      icon: 'tune' }
    ]
  };

  /* Pages d'entrée et de déconnexion par espace. */
  var entries = {
    customer:   { home: 'customer/index',   login: 'customer/login',   label: 'Espace client',      icon: 'shopping_bag', desc: 'Marketplace, panier, suivi de livraison' },
    vendor:     { home: 'vendor/index',     login: 'vendor/login',     label: 'Espace vendeur',     icon: 'storefront',   desc: 'Produits, commandes, clients, caisse' },
    courier:    { home: 'courier/index',    login: 'courier/login',    label: 'Espace livreur',     icon: 'two_wheeler',  desc: 'Courses, remise QR, gains du jour' },
    superadmin: { home: 'superadmin/index', login: 'superadmin/login', label: 'Super-admin',        icon: 'shield_person', desc: 'Vendeurs, validations, finances, Kimia' }
  };

  /* Liaisons bouton/carte -> page, par page.
   *   text   : le libellé contient ce texte (insensible à la casse/accents)
   *   eq     : le libellé est exactement ce texte
   *   id     : id de l'élément
   *   icon   : nom de l'icône Material Symbols du bouton
   *   sel    : sélecteur CSS (+ match : ne garde que les éléments dont le texte contient cette chaîne)
   *   card   : true -> toute la carte parente devient cliquable
   *   delay  : ms ; si présent, on laisse l'animation existante se jouer puis on navigue
   * Par défaut le clic est intercepté et on navigue immédiatement. */
  var bindings = {
    'customer/splash':  [],
    'customer/login': [
      { eq: 'Se connecter', to: 'customer/index' },
      { id: 'btn-whatsapp-auth', to: 'customer/index' }
    ],
    'customer/index': [
      { eq: 'Installer', to: 'customer/install' },
      { text: 'Livrer à', to: 'customer/addresses' },
      { text: 'Mode & Wax', to: 'customer/search' },
      { text: 'Électronique', to: 'customer/search' },
      { text: 'Chaussures', to: 'customer/search' },
      { text: 'Maison & Déco', to: 'customer/search' },
      { text: 'Beauté & Soins', to: 'customer/search' },
      { icon: 'tune', to: 'customer/search' },
      { sel: 'article', card: true, to: 'customer/product' },
      { heading: 'Chez Awa', card: true, to: 'customer/shop' },
      { heading: 'ÉlectroMoussa', card: true, to: 'customer/shop' }
    ],
    'customer/search': [
      { sel: 'article', card: true, to: 'customer/product' }
    ],
    'customer/shop': [
      { sel: 'main h2.line-clamp-1', card: true, to: 'customer/product' }
    ],
    'customer/product': [
      { id: 'add-to-cart-cta', to: 'customer/cart' },
      { eq: 'Boutique', to: 'customer/shop' },
      { text: 'Tout voir', to: 'customer/shop' }
    ],
    'customer/favorites': [
      { sel: 'main h3', card: true, to: 'customer/product' },
      { id: 'btn-add-all-cart', to: 'customer/cart' }
    ],
    'customer/cart': [
      { text: 'Commander •', to: 'customer/checkout' },
      { text: 'Gombe, Kin', to: 'customer/addresses' }
    ],
    'customer/checkout': [
      { id: 'confirmOrderBtn', to: 'customer/order-confirm', delay: 3200 },
      { eq: 'Modifier', to: 'customer/addresses' }
    ],
    'customer/order-confirm': [
      { text: "Suivre l'acheminement", to: 'customer/track' },
      { text: 'Continuer mes achats', to: 'customer/index' },
      { text: 'Télécharger le reçu', to: 'customer/receipt' }
    ],
    'customer/orders': [
      { text: 'Suivre la livraison', to: 'customer/track' },
      { text: 'Facture PDF', to: 'customer/documents' },
      { text: 'Reçu PDF', to: 'customer/receipt' },
      { text: 'Commander à nouveau', to: 'customer/cart' },
      { text: 'Voir articles similaires', to: 'customer/search' }
    ],
    'customer/account': [
      { text: 'Suivre la livraison', to: 'customer/track' },
      { text: 'Détails de commande', to: 'customer/orders' },
      { text: 'Historique', to: 'customer/orders' },
      { text: 'Facture PDF', to: 'customer/documents' },
      { text: 'Commander à nouveau', to: 'customer/cart' },
      { eq: 'Ajouter', to: 'customer/address-edit' },
      { eq: 'Modifier', to: 'customer/addresses' },
      { text: 'Se déconnecter', to: 'customer/login' }
    ],
    'customer/addresses': [
      { text: "Modifier l'adresse", to: 'customer/address-edit' },
      { text: 'Ajouter une nouvelle adresse', to: 'customer/address-edit' }
    ],
    'customer/address-edit': [
      { text: 'Enregistrer cette adresse', to: 'customer/addresses' },
      { eq: 'Annuler', to: 'customer/addresses' }
    ],
    'customer/notifications': [
      { text: 'Suivre en direct', to: 'customer/track' },
      { text: 'Détails commande', to: 'customer/orders' },
      { eq: 'Voir', to: 'customer/shop' }
    ],
    'customer/install': [
      { id: 'btn-understood', to: 'customer/index' },
      { id: 'btn-dismiss-browser', to: 'customer/index' }
    ],
    'customer/offline': [
      { text: 'Voir mes commandes enregistrées', to: 'customer/orders' }
    ],

    'vendor/login': [
      { text: 'Accéder à mon tableau de bord', to: 'vendor/index' },
      { text: 'Connexion WhatsApp Business', to: 'vendor/index' },
      { text: 'Biométrie ou code SMS', to: 'vendor/index' },
      { text: 'Accueil client', to: 'customer/index' }
    ],
    'vendor/index': [
      { text: 'Retrait MoMo', to: 'vendor/finances' },
      { text: 'Clôture Express', to: 'vendor/finances' },
      { text: 'Journal', to: 'vendor/finances' },
      { text: '+ Produit', to: 'vendor/product-edit' },
      { text: 'Scan Colis', to: 'vendor/shipments' },
      { text: 'Appel Moto', to: 'vendor/couriers' },
      { text: 'Voir les 23', to: 'vendor/orders' },
      { text: 'Réappro', to: 'vendor/products' },
      { icon: 'near_me', to: 'vendor/shipment-detail' },
      { icon: 'chevron_right', to: 'vendor/order-detail' }
    ],
    'vendor/products': [
      { icon: 'edit', to: 'vendor/product-edit' },
      { eq: 'Nouveau', to: 'vendor/product-edit' },
      { text: 'Réapprovisionner', to: 'vendor/product-edit' }
    ],
    'vendor/product-edit': [
      { eq: 'Annuler', to: 'vendor/products' },
      { id: 'topSaveBtn', to: 'vendor/products', delay: 1200 },
      { id: 'saveActionBtn', to: 'vendor/products', delay: 1200 }
    ],
    'vendor/orders': [
      { text: 'Préparer', to: 'vendor/order-detail' },
      { text: 'Suivi GPS motard', to: 'vendor/shipment-detail' },
      { text: 'Assigner un motard', to: 'vendor/couriers' },
      { text: 'Exporter bordereau', to: 'vendor/shipments' },
      { sel: 'article', card: true, to: 'vendor/order-detail' }
    ],
    'vendor/customers': [
      { text: 'Voir la fiche client', to: 'vendor/customer-detail' },
      { sel: 'main h2', card: true, to: 'vendor/customer-detail' }
    ],
    'vendor/shipments': [
      { text: 'Suivi direct', to: 'vendor/shipment-detail' },
      { text: 'Bordereau / QR', to: 'vendor/shipment-detail' },
      { text: 'Confier à Moussa', to: 'vendor/shipment-detail' },
      { text: 'Générer étiquette', to: 'vendor/shipment-detail' },
      { text: 'Préparer colis', to: 'vendor/orders' },
      { sel: 'main span', match: '#PKG', card: true, to: 'vendor/shipment-detail' }
    ],
    'vendor/couriers': [
      { text: "Valider l'encaissement", to: 'vendor/finances' },
      { text: "Consulter l'historique complet", to: 'vendor/finances' },
      { text: 'Suivi GPS', to: 'vendor/shipment-detail' },
      { text: 'Assigner Colis', to: 'vendor/shipments' }
    ],
    'vendor/finances': [
      { text: 'Suivre Course', to: 'vendor/shipment-detail' }
    ],
    'vendor/settings': [
      { text: 'Voir ma boutique publique', to: 'customer/shop' },
      { text: "Gérer l'abonnement", to: 'vendor/invoices' },
      { text: 'Consulter les factures SaaS', to: 'vendor/invoices' },
      { text: 'Configurer les zones', to: 'vendor/delivery-zones' },
      { text: "Se déconnecter", to: 'vendor/login' }
    ],

    'courier/login': [
      { text: 'Se connecter à ma tournée', to: 'courier/index' },
      { text: 'Connexion rapide par SMS', to: 'courier/index' }
    ],
    'courier/index': [
      { id: 'btn-demarrer', to: 'courier/shipment-detail' },
      { text: 'Toutes mes livraisons', to: 'courier/shipments' },
      { text: 'Mes gains du jour', to: 'courier/earnings' }
    ],
    'courier/shipments': [
      { eq: 'Détail', to: 'courier/shipment-detail' },
      { eq: 'Démarrer', to: 'courier/shipment-detail' },
      { sel: 'article', card: true, to: 'courier/shipment-detail' }
    ],
    'courier/shipment-detail': [
      { text: 'Valider la remise', to: 'courier/qr-display' }
    ],
    'courier/qr-display': [
      { text: 'Prendre une photo', to: 'courier/photo-capture' },
      { text: 'Retour à mes livraisons', to: 'courier/shipments' }
    ],
    'courier/photo-capture': [
      { id: 'submit-proof-btn', to: 'courier/delivery-success', delay: 900 }
    ],
    'courier/delivery-success': [
      { id: 'nextRideBtn', to: 'courier/shipment-detail' }
    ],
    'courier/profile': [
      { text: "Déconnexion de l'Espace Livreur", to: 'courier/login' }
    ],

    'superadmin/login': [
      { id: 'submitLoginBtn', to: 'superadmin/index' }
    ],
    'superadmin/index': [
      { eq: 'Traiter', to: 'superadmin/approvals' },
      { text: 'Classement complet', to: 'superadmin/tenants' },
      { eq: 'Auditer', to: 'superadmin/audit' },
      { text: 'Relancer le sync', to: 'superadmin/kimia' }
    ],
    'superadmin/tenants': [
      { text: 'Examiner dossier', to: 'superadmin/tenant-detail' },
      { text: 'Détails litige', to: 'superadmin/tenant-detail' },
      { sel: 'main h2', card: true, to: 'superadmin/tenant-detail' }
    ],
    'superadmin/commissions': [
      { text: 'Voir détail', to: 'superadmin/tenant-detail' }
    ],
    'superadmin/invoices': [
      { text: 'Reçu & Détail', to: 'superadmin/invoice-detail' },
      { eq: 'Détail', to: 'superadmin/invoice-detail' },
      { text: 'Enregistrer paiement', to: 'superadmin/invoice-detail' }
    ]
  };

  /* Cartes d'accès rapides (pages secondaires sans onglet dédié). */
  var hubs = {
    'customer/account':      { title: 'Raccourcis', items: ['customer/favorites', 'customer/documents', 'customer/addresses', 'customer/notifications', 'customer/install'] },
    'vendor/settings':       { title: 'Gérer ma boutique', items: ['vendor/finances', 'vendor/couriers', 'vendor/shipments', 'vendor/invoices', 'vendor/delivery-zones'] },
    'superadmin/finance-stats': { title: 'Finances — détail', items: ['superadmin/commissions', 'superadmin/invoices', 'superadmin/commission-rules', 'superadmin/exchange-rates', 'superadmin/plans'] },
    'superadmin/config':     { title: 'Administration', items: ['superadmin/kimia', 'superadmin/audit', 'superadmin/plans', 'superadmin/exchange-rates', 'superadmin/commission-rules'] }
  };

  root.AmaniRoutes = { pages: pages, nav: nav, entries: entries, bindings: bindings, hubs: hubs };
})(window);
