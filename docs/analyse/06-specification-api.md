# 06 — Spécification de l'API (contrat REST)

Base : `https://api.{domain}/v1` · Auth : cookie `refresh` httpOnly + header `Authorization: Bearer <access>` · Toutes les réponses d'erreur au format `{ "code": "...", "message": "...", "details": [] }`.

## 1. Conventions
- Pagination : `?page=1&limit=20` → `{ data, meta: { total, page, limit } }`
- Idempotence écritures sensibles : header `Idempotency-Key` (checkout, remboursements)
- Rôles : 🌍 public · 👤 client · 🏪 vendeur (owner only) · 🛡️ admin

## 2. Endpoints par domaine

### 2.1 Auth & utilisateurs
| Méthode | Route | Rôle | Description |
|---|---|---|---|
| POST | /auth/register | 🌍 | inscription (email, mdp, nom) |
| POST | /auth/login | 🌍 | → access + refresh |
| POST | /auth/refresh | 🌍 | rotation refresh |
| POST | /auth/logout | 👤 | révocation |
| GET | /auth/oauth/google/start, /callback | 🌍 | OAuth |
| GET | /me | 👤 | profil + rôles + boutiques du user |
| PATCH | /me | 👤 | maj profil |
| GET/POST/PATCH/DELETE | /me/addresses[/{id}] | 👤 | carnet d'adresses |

### 2.2 Boutiques & plan vendeur
| Méthode | Route | Rôle | Description |
|---|---|---|---|
| POST | /stores | 🏪 flow | créer boutique (draft) pour le user courant |
| GET | /stores/{slug} | 🌍 | vitrine publique (infos + produits actifs) |
| PATCH | /vendor/store | 🏪 | maj logo/bannière/description |
| POST | /vendor/store/submit | 🏪 | soumettre à validation admin |
| GET | /plans | 🌍 | catalogue des abonnements |
| POST | /vendor/subscription/checkout | 🏪 | Stripe Checkout subscription → success_url |
| POST | /vendor/stripe-connect/onboard | 🏪 | crée account connecté → retour onboarding URL |
| GET | /vendor/dashboard | 🏪 | KPIs (CA 30j, commandes à traiter, stock bas) |

### 2.3 Catalogue (public)
| Méthode | Route | Rôle | Description |
|---|---|---|---|
| GET | /products | 🌍 | recherche/filtres : `q, category, store, price_min/max, rating, sort(new\|price\|sales), page` |
| GET | /products/{storeId}/{slug} | 🌍 | fiche produit (variantes, images, avis agrégés) |
| GET | /categories/tree | 🌍 | arborescence |

### 2.4 Gestion produits (vendeur)
| Méthode | Route | Rôle | Description |
|---|---|---|---|
| GET | /vendor/products | 🏪 | liste + filtres statut |
| POST | /vendor/products | 🏪 | création (quota plan vérifié) |
| PATCH/DELETE | /vendor/products/{id} | 🏪 | maj / soft delete |
| POST | /vendor/products/{id}/variants | 🏪 | ajouter variante |
| PATCH | /vendor/variants/{id}/stock | 🏪 | ajustement stock (+ reason audit) |
| POST | /vendor/products/{id}/images | 🏪 | presigned URL upload S3 puis callback |
| PATCH | /vendor/products/{id}/status | 🏪 | draft ↔ active ↔ paused |

### 2.5 Panier & checkout
| Méthode | Route | Rôle | Description |
|---|---|---|---|
| GET | /cart | 👤/🌍 | contenu groupé par vendeur + totaux recalculés |
| POST | /cart/items | 👤/🌍 | `{variantId, qty}` (validation stock) |
| PATCH | /cart/items/{id} | | quantité |
| DELETE | /cart/items/{id} | | retirer |
| POST | /cart/merge | 👤 | fusion panier anonyme → compte à la connexion |
| POST | /checkout | 👤 | `{addressId, shippingMethod}` → réserve stock, crée order PENDING_PAYMENT + PaymentIntent → `{clientSecret}` |
| POST | /checkout/cancel | 👤 | annulation explicite + libération stock |

### 2.6 Commandes
| Méthode | Route | Rôle | Description |
|---|---|---|---|
| GET | /orders | 👤 | mes commandes (avec sous-commandes & statuts) |
| GET | /orders/{id} | 👤 | détail + timeline |
| POST | /orders/{id}/reviews-invite | système | (interne) déclenche email post-livraison |
| GET | /vendor/orders | 🏪 | file de travail (`?status=new,processing…`) |
| PATCH | /vendor/orders/{suborderId}/confirm | 🏪 | → PROCESSING |
| PATCH | /vendor/orders/{suborderId}/ship | 🏪 | `{carrier, trackingNumber}` → SHIPPED |
| PATCH | /vendor/orders/{suborderId}/cancel | 🏪 | `{reason}` → remboursement ligne auto |
| POST | /orders/{id}/items/{itemId}/return-request | 👤 | demande de retour |

### 2.7 Webhooks paiement (interne)
| Événement Stripe | Action |
|---|---|
| payment_intent.succeeded | order → PAID, suborders → notifiées vendeurs, ledger commission |
| payment_intent.payment_failed | order → CANCELLED, libère stock, email |
| charge.refunded | maj refund_status, reversal ledger |
| customer.subscription.updated/deleted | maj plan/grace → suspension boutique |
| account.updated (Connect) | maj éligibilité payouts |

### 2.8 Avis
| Méthode | Route | Rôle |
|---|---|---|
| POST | /products/{id}/reviews | 👤 (achat vérifié uniquement) |
| GET | /products/{id}/reviews?page= | 🌍 |
| DELETE | /reviews/{id} | 🛡️ ou auteur (modération) |

### 2.9 Admin
| Méthode | Route | Description |
|---|---|---|
| GET | /admin/stats/overview | GMV, MRR, comptes, files |
| GET | /admin/vendors?status=pending | file KYC |
| POST | /admin/vendors/{id}/approve \| reject \| suspend | `{reason?}` |
| GET | /admin/moderation/queue | produits nouveaux/signalés |
| POST | /admin/products/{id}/approve \| remove | modération |
| CRUD | /admin/categories, /admin/plans | référentiel |
| PATCH | /admin/settings/commission | taux global |
| GET | /admin/orders?q= | supervision globale |
| POST | /admin/disputes/{id}/resolve | arbitrage litige (refund forcé…) |
| GET | /admin/audit-logs | traçabilité |

## 3. Exemple de contrat — POST /checkout

Requête :
```json
{ "addressId": "uuid", "shippingMethod": "standard" }
```
Réponse 201 :
```json
{
  "orderId": "uuid",
  "orderNumber": "CMD-2026-000123",
  "amountDue": 8490,
  "currency": "eur",
  "paymentClientSecret": "pi_..._secret",
  "subordersPreview": [
    { "storeName": "Atlas Ceramics", "subtotal": 5900 },
    { "storeName": "Karim Mode", "subtotal": 2590 }
  ]
}
```
Erreurs : `CART_EMPTY`, `STOCK_INSUFFICIENT` (détail par ligne), `ADDRESS_REQUIRED`, `STORE_NOT_ACTIVE`.
