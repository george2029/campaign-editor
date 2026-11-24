# Keitaro campaign tool

A small web app on top of the [Keitaro](https://keitaro.io) Admin API:

1. **Campaign creator**: takes a campaign name, country codes and a Keitaro offer, and creates a campaign with two flows:
   - **Flow 1**: visitors from the chosen countries are redirected to `https://google.com`;
   - **Flow 2**: everyone else goes to the chosen offer (100%).

   The campaign gets its domain, group (`FORTESTS`) and traffic source (`FORTESTS`) set.

2. **Campaign editor**: loads a campaign's flows from Keitaro and lets you add and remove offers in a flow, then push the new split back.

Stack: FastAPI, SQLAlchemy 2 + Alembic (SQLite), httpx; frontend is plain HTML + vanilla JS served by FastAPI (no build step).

## Run

Needs Python 3.12+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # then put your Keitaro API URL and key in .env
alembic upgrade head        # creates app.db with the tables
uvicorn app.main:app --reload
```

Open http://localhost:8000.

## Database and migrations

The app uses SQLite (`app.db` in the project folder) with SQLAlchemy models in `app/db.py`. The tables are created and changed only by [Alembic](https://alembic.sqlalchemy.org) migrations in `alembic/versions/`:

| Migration                                  | What it does                        |
| ------------------------------------------ | ----------------------------------- |
| `a96a4cf33af0` campaigns and offer changes | tables `campaigns`, `offer_changes` |
| `a3f3050d501e` flow offers                 | table `flow_offers`                 |

Alembic takes the database URL from `DATABASE_URL` in `.env` (default `sqlite:///./app.db`), same as the app.

```bash
alembic upgrade head        # apply all migrations (run after every git pull)
alembic current             # which migration the database is at
alembic history             # list of migrations
alembic downgrade -1        # undo the last migration
```

After changing a model in `app/db.py`, generate a new migration, check the file it creates, then apply it:

```bash
alembic revision --autogenerate -m "what changed"
alembic upgrade head
```

To start over with an empty database: `rm app.db && alembic upgrade head`.

## Tests

Offer share math:

```bash
pytest
```

## Settings (`.env`)

| Variable           | Default              | Meaning                                                 |
| ------------------ | -------------------- | ------------------------------------------------------- |
| `KEITARO_URL`      | required             | Admin API base, e.g. `https://example.com/admin_api/v1` |
| `KEITARO_API_KEY`  | required             | API key from the Keitaro admin                          |
| `CAMPAIGN_DOMAIN`  | first domain         | Domain name for new campaigns                           |
| `CAMPAIGN_GROUP`   | `FORTESTS`           | Campaign group name                                     |
| `CAMPAIGN_SOURCE`  | `FORTESTS`           | Traffic source name                                     |
| `GEO_REDIRECT_URL` | `https://google.com` | Where flow 1 sends the chosen countries                 |
| `DATABASE_URL`     | `sqlite:///./app.db` | Any SQLAlchemy URL; Alembic reads it from here too      |

Domain, group and source are looked up by name through the API, so the IDs don't need to be configured.

## How the editor works

- **Fetch flows from KT** loads the campaign's flows. A redirect flow is shown read-only; a flow with offers gets an offers table.
- Every change is a local draft until **Push to KT**; **Cancel** drops it.
- **Shares are whole percents and always add up to 100.**
  - Adding an offer splits the traffic evenly again: 3 offers → 34 / 33 / 33, 4 offers → 25 each. When it doesn't divide evenly, the first offers get the extra percent.
  - **Remove** puts an offer at 0% and greys it out; the others take its traffic. On push it is dropped from the flow in Keitaro.
  - Removed offers stay in the editor with **Bring back**, also after the push and after reloading, and also when the offer was removed in the Keitaro admin, not in this app. Keitaro forgets an offer once it leaves a flow, so the app remembers every offer it has seen in a flow (on create, fetch and push) in the `flow_offers` table, with its last share. An offer in that table but not in Keitaro is shown as removed. Bringing it back and pushing puts it into the flow again.
  - The app can only know about offers it has seen: if an offer is added and removed in the Keitaro admin between two fetches, it won't show up.
  - **📌 Pin** keeps an offer's share fixed, and the other offers split what's left (one pinned at 25% → 38 / 37 / 25).
  - Typing a share pins that offer.
  - Impossible splits (pinned offers over 100%, everything pinned but not adding up to 100, no offers left) are refused with a message.
- Each push is saved to the database (shares before and after) and shown in **Change history**.

The share math is in `app/shares.py` and covered by `tests/test_shares.py`; the editor calls it through `POST /api/rebalance`, so the browser and the server always agree.

## Project layout

```
app/
  main.py        FastAPI routes (pages + JSON API)
  keitaro.py     Keitaro Admin API client
  shares.py      offer share rebalancing
  db.py          SQLAlchemy models: campaigns created here, pushed offer changes, offers seen in each flow
  config.py      settings from .env
  static/        HTML, JS, CSS
alembic/         migrations
tests/
```

## API

| Method | Path                          | What it does                                      |
| ------ | ----------------------------- | ------------------------------------------------- |
| GET    | `/api/offers`                 | Active offers (id, name, countries)               |
| GET    | `/api/campaigns`              | Campaigns in Keitaro, marked if created here      |
| POST   | `/api/campaigns`              | Create a campaign `{name, geo: ["AU"], offer_id}` |
| GET    | `/api/campaigns/{id}`         | Campaign with its flows and offers                |
| POST   | `/api/rebalance`              | Recalculate shares for a draft offers list        |
| PUT    | `/api/streams/{id}/offers`    | Push a flow's offers to Keitaro                   |
| GET    | `/api/campaigns/{id}/changes` | Pushed changes for a campaign                     |

Interactive docs: http://localhost:8000/docs.
