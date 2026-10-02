# 🇨🇩 Kimia — SaaS e-commerce multi-tenant (RDC)

Plateforme de mise en relation **vendeurs ↔ clients** pour la République Démocratique du Congo.
Nous ne vendons rien : c'est le vendeur qui encaisse le cash à la livraison (COD).
La plateforme prend une commission et facture les abonnements mensuellement.

## Principes fondateurs

1. **Intermédiaire uniquement** — l'argent des ventes ne transite jamais par la plateforme.
2. **Config-driven** — aucune valeur métier codée en dur : plans, devises, règles et statuts vivent en base (`business_rules`, `settings`, `currencies`). Ajouter une donnée = un `INSERT`, zéro ligne de code.
3. **Modularité sans code** — 3 niveaux de configuration : système (superadmin), tenant (vendeur), utilisateur (préférences).
4. **Mobile-first** — PWA partout, les vendeurs n'ont que des smartphones.

## Stack technique

| Couche | Technologie |
|---|---|
| Backend | FastAPI (async) + Python 3.12 |
| Templates | Jinja2 (rendu côté serveur) |
| Base de données | PostgreSQL 18 + SQLAlchemy 2.0 async (asyncpg) |
| Migrations | Alembic |
| Cache / Queue | Redis 7 + ARQ |
| Auth | JWT HS256 + Argon2id + refresh tokens opaques rotatifs |
| Frontend | HTML / CSS / JS vanilla + PWA |
| SMS | Kimia (stub pour l'instant) |
| Push / Erreurs | OneSignal / Sentry |
| Déploiement | Oracle Cloud Free Tier (VPS) |

## Structure du projet

```
backend/
├── app/
│   ├── main.py            # App FastAPI + middlewares
│   ├── core/              # config, security, deps, events, exceptions, middlewares
│   ├── db/                # Base déclarative + session async
│   ├── models/            # 15 modèles SQLAlchemy (users, tenants, currencies…)
│   ├── schemas/           # Pydantic v2 (strict)
│   ├── crud/              # accès DB
│   ├── services/          # logique métier (auth, tenants, permissions, seed…)
│   ├── seed_data.py       # Seeds idempotents (devises, règles, permissions…)
│   ├── api/v1/            # auth, superadmin/tenants, vendor/staff
│   ├── tasks/             # worker ARQ (stub)
│   └── web/               # templates Jinja2 + static (PWA, à venir)
├── alembic/               # migrations 0001→0004 (config, auth/tenant, perms, seed)
└── tests/                 # pytest + httpx AsyncClient (SQLite aiosqlite)
```

## 🚀 Lancer le projet

### Prérequis
- Python 3.12+
- PostgreSQL 18
- Redis 7

### 1. Installation

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env        # puis adapter DATABASE_URL / REDIS_URL / SECRET_KEY / JWT_SECRET
```

> En production : régénérer les secrets (`openssl rand -hex 32`) et passer `APP_ENV=production`
> (active HSTS, cookie `Secure`, désactive la doc Swagger).

### 2. Base de données

```bash
createdb kimia                                   # ou via psql
alembic upgrade head                             # schéma + seed (devises, règles, permissions)
```

Les seeds sont **idempotents** : relancer `upgrade head` ou le script seed ne duplique rien.

### 3. Démarrer

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- API : http://localhost:8000/api/v1
- Docs interactives (dev uniquement) : http://localhost:8000/docs
- Santé : http://localhost:8000/healthz

### 4. Worker ARQ (stub pour l'instant)

```bash
arq app.tasks.worker.WorkerSettings
```

### 5. Tests

```bash
cd backend
pytest -v          # SQLite in-memory (aiosqlite) + rate-limiter en mémoire — aucun service externe requis
```

## 🔌 API disponibles (Prompt 1)

### Auth — `/api/v1/auth`
| Méthode | Route | Description |
|---|---|---|
| POST | `/register/vendor` | Crée le vendor + son tenant (statut `pending` si règle `tenant.validation_required=true`) |
| POST | `/register/customer` | Crée un client (illimité, jamais compté dans les plans) |
| POST | `/login` | Email **ou** téléphone + mot de passe (Argon2id), lockout config-driven |
| POST | `/refresh` | Rotation du refresh token (cookie httpOnly), nouvel access token |
| POST | `/logout` | Révoque la session + blackliste le JWT courant |
| GET/PATCH | `/me` | Profil courant (langue, devise d'affichage USD/CDF…) |
| GET | `/sessions` | Liste des sessions actives (multi-device) |
| DELETE | `/sessions/{id}` | Révoque une session précise |
| POST | `/verify-phone` | Vérification par token (lien SMS — stub loggé) |
| POST | `/resend-verification` | Renvoie le lien de vérification |
| POST | `/forgot-password` | Génère un token de reset (SMS stub) |
| POST | `/reset-password` | Réinitialise + blacklist toutes les sessions |

### Superadmin — `/api/v1/superadmin/tenants` *(JWT role `superadmin`)*
| Méthode | Route | Description |
|---|---|---|
| GET | `/` | Liste paginée (filtres `status`, `plan`, `search`) |
| GET | `/pending` | File d'attente de validation |
| GET | `/{id}` | Détail d'un tenant |
| POST | `/{id}/approve` | `pending → active` |
| POST | `/{id}/reject` | `pending → rejected` (avec raison) |
| POST | `/{id}/suspend` | `active → suspended` (avec raison) |
| POST | `/{id}/reactivate` | `suspended → active` |
| PATCH | `/{id}` | Modifier plan, commission_rate, etc. |

Toutes les actions superadmin sont tracées dans `audit_logs`.

### Vendor — `/api/v1/vendor` *(JWT role `vendor` ou `staff` avec permission)*
| Méthode | Route | Permission | Description |
|---|---|---|---|
| POST | `/staff` | `staff.manage` | Créer un employé rattaché au tenant |
| GET | `/staff` | `staff.manage` | Lister le personnel |
| GET | `/staff/{id}` | `staff.manage` | Détail |
| PUT | `/staff/{id}/permissions` | `staff.manage` | Assigner des permissions (wildcards `products.*`) |
| GET | `/me/permissions` | authentifié | Permissions effectives du user courant |

## 🔒 Isolation multi-tenant (règle d'or)

- Le `tenant_id` est **toujours déduit du JWT**, jamais du body de la requête.
- Chaque requête `/vendor/*` est filtrée automatiquement sur le tenant du token.
- `TenantStatusMiddleware` renvoie `403` si le tenant n'est pas `active` sur `/vendor/*` et `/shop/*`.
- Un vendor A ne peut **jamais** lire les données d'un vendor B (testé dans `tests/test_isolation.py`).

## 💱 Devises

- Stockage & facturation : **USD** uniquement.
- Affichage : USD (`$20.00`) ou CDF (`50 000 FC`) selon la préférence utilisateur.
- Taux de change **snapshoté à la commande**, mis à jour manuellement par le superadmin (`exchange_rates`).
- Tout est en table `currencies` : ajouter une devise = un `INSERT`.

## 🧩 Config-driven — ce qui vit en base

| Table | Rôle |
|---|---|
| `currencies` | Devises + formatage local (symbole, position, séparateurs) |
| `exchange_rates` | Taux de change historisés |
| `business_rules` | `order.auto_cancel_hours=48`, `login.max_attempts=5`, `rate_limit.*`, `commission.calculation_base=products_only`… |
| `settings` | Clés génériques (publiques/privées) |
| `permissions` | 26 clés granulaires (`products.create`, `finances.export`…) avec `plan_min` |
| `role_templates` | Manager, stock_manager, order_manager, accountant, marketing, support |

## 🛡️ Sécurité implémentée

- Argon2id (m=64 Mo, t=3, p=4) · JWT HS256 15 min · refresh opaque 30 j **rotatif** (SHA-256 en base)
- Cookie refresh `httpOnly + Secure + SameSite=Strict`, access token en mémoire JS
- Rate limiting Redis par IP/user (60/min public, 5/min login, 300/min API) — configurable via `business_rules`
- Lockout brute-force (`login.max_attempts` / `login.lockout_minutes`) tracé dans `login_attempts`
- Politique mot de passe (min 8, majuscule, minuscule, chiffre) → `422`
- Headers : `X-Content-Type-Options`, `X-Frame-Options: DENY`, CSP, `Referrer-Policy`, HSTS (prod)
- Audit trail JSONB (`before`/`after`) sur les actions sensibles
- Zéro secret en code, zéro log de données sensibles, entrées validées Pydantic v2 strict

## 🗺️ Prochaines étapes (Prompts suivants)

- [ ] Module produits/boutique (CRUD vendor + vitrine publique `/shop/*`)
- [ ] Commandes COD + machine à états + QR de confirmation courier
- [ ] Commissions & facturation mensuelle (abonnement + commissions cumulées)
- [ ] Intégration SMS Kimia réelle (remplacer le stub) + notifications OneSignal
- [ ] Dashboard PWA (templates Jinja2 dans `app/web/`)
- [ ] Multi-devises d'entrée vendeur (`currency_input=CDF` → conversion USD au stockage)
- [ ] CI GitHub Actions (lint + tests + build) et déploiement Oracle Cloud

## Licence

Propriétaire — Kimia © 2026.
