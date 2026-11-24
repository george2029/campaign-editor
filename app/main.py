import re
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import keitaro
from app.config import settings
from app.db import Campaign, FlowOffer, OfferChange, get_session
from app.shares import OfferShare, SharesError, check_ready_to_push, rebalance

STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Keitaro campaign tool")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.exception_handler(keitaro.KeitaroError)
def keitaro_error(request: Request, exc: keitaro.KeitaroError):
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(SharesError)
def shares_error(request: Request, exc: SharesError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# Pages


@app.get("/")
def page_campaigns():
    return FileResponse(STATIC / "index.html")


@app.get("/campaigns/{campaign_id}")
def page_editor(campaign_id: int):
    return FileResponse(STATIC / "editor.html")


# Offers


@app.get("/api/offers")
def offers():
    """All offers, short form. The page loads them once and searches locally."""
    return [
        {"id": o["id"], "name": o["name"], "country": o["country"]}
        for o in keitaro.list_offers()
        if o["state"] == "active"
    ]


# Campaigns


class NewCampaign(BaseModel):
    name: str
    geo: list[str]
    offer_id: int

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Campaign name is required")
        return value

    @field_validator("geo")
    @classmethod
    def geo_codes(cls, value: list[str]) -> list[str]:
        codes = []
        for code in value:
            code = code.strip().upper()
            if not re.fullmatch(r"[A-Z]{2}", code):
                raise ValueError(f"'{code}' is not a 2-letter country code")
            if code not in codes:
                codes.append(code)
        if not codes:
            raise ValueError("At least one country is required")
        return codes


def find_by_name(items: list[dict], name: str, what: str) -> dict:
    for item in items:
        if item["name"] == name:
            return item
    raise HTTPException(500, f"{what} '{name}' not found in Keitaro")


@app.get("/api/campaigns")
def campaigns(session: Session = Depends(get_session)):
    """Campaigns from Keitaro, marked if they were created here."""
    ours = set(session.scalars(select(Campaign.keitaro_id)))
    result = []
    for c in keitaro.list_campaigns():
        result.append(
            {
                "id": c["id"],
                "name": c["name"],
                "url": c["domain"] + c["alias"],
                "group": c.get("group"),
                "state": c["state"],
                "created_at": c["created_at"],
                "created_here": c["id"] in ours,
            }
        )
    result.sort(key=lambda c: c["id"], reverse=True)
    return result


@app.post("/api/campaigns")
def create_campaign(data: NewCampaign, session: Session = Depends(get_session)):
    try:
        keitaro.get_offer(data.offer_id)
    except keitaro.KeitaroError:
        raise HTTPException(400, f"Offer {data.offer_id} not found in Keitaro")

    domains = keitaro.list_domains()
    if settings.campaign_domain:
        domain = find_by_name(domains, settings.campaign_domain, "Domain")
    else:
        domain = domains[0]
    group = find_by_name(keitaro.list_groups(), settings.campaign_group, "Group")
    source = find_by_name(keitaro.list_traffic_sources(), settings.campaign_source, "Traffic source")

    campaign = keitaro.create_campaign(
        {
            "name": data.name,
            "type": "position",  # flows are checked top to bottom
            "state": "active",
            "domain_id": domain["id"],
            "group_id": group["id"],
            "traffic_source_id": source["id"],
            "cost_type": "CPC",
            "cost_value": 0,
            "cost_currency": "USD",
        }
    )

    try:
        geo_stream = keitaro.create_stream(
            {
                "campaign_id": campaign["id"],
                "name": "Geo " + ", ".join(data.geo) + " -> Google",
                "type": "regular",
                "position": 1,
                "state": "active",
                "schema": "redirect",
                "action_type": "http",
                "action_payload": settings.geo_redirect_url,
                "filters": [{"name": "country", "mode": "accept", "payload": data.geo}],
            }
        )
        offers_stream = keitaro.create_stream(
            {
                "campaign_id": campaign["id"],
                "name": "Offers",
                "type": "regular",
                "position": 2,
                "state": "active",
                "schema": "landings",
                "action_type": "http",
                "offers": [{"offer_id": data.offer_id, "share": 100, "state": "active"}],
            }
        )
    except keitaro.KeitaroError:
        # Don't leave a half-made campaign behind.
        keitaro.delete_campaign(campaign["id"])
        raise

    row = Campaign(
        keitaro_id=campaign["id"],
        name=campaign["name"],
        alias=campaign["alias"],
        url=campaign["domain"] + campaign["alias"],
        geo=data.geo,
        offer_id=data.offer_id,
        geo_stream_id=geo_stream["id"],
        offers_stream_id=offers_stream["id"],
    )
    session.add(row)
    remember_offers(session, campaign["id"], offers_stream["id"], offers_stream["offers"])
    session.commit()

    return {"id": row.keitaro_id, "name": row.name, "url": row.url}


# Editor


def remember_offers(session: Session, campaign_id: int, stream_id: int, offers: list[dict]) -> None:
    """Save the offers that are in a flow in Keitaro right now (see FlowOffer)."""
    known = {r.offer_id: r for r in session.scalars(select(FlowOffer).where(FlowOffer.stream_id == stream_id))}
    for o in offers:
        row = known.get(o["offer_id"])
        if row is None:
            row = FlowOffer(keitaro_campaign_id=campaign_id, stream_id=stream_id, offer_id=o["offer_id"])
            session.add(row)
        row.last_share = o["share"]
        row.last_seen_at = datetime.now()


@app.get("/api/campaigns/{campaign_id}")
def campaign_details(campaign_id: int, session: Session = Depends(get_session)):
    campaign = keitaro.get_campaign(campaign_id)
    streams = sorted(keitaro.list_streams(campaign_id), key=lambda s: s["position"])

    for s in streams:
        remember_offers(session, campaign_id, s["id"], s["offers"])
    session.commit()

    known = session.scalars(
        select(FlowOffer)
        .where(FlowOffer.keitaro_campaign_id == campaign_id)
        .order_by(FlowOffer.last_seen_at.desc())
    ).all()

    result = []
    for s in streams:
        offers = [{"offer_id": o["offer_id"], "share": o["share"]} for o in s["offers"]]
        in_flow = {o["offer_id"] for o in offers}
        result.append(
            {
                "id": s["id"],
                "name": s["name"],
                "position": s["position"],
                "schema": s["schema"],
                "action_payload": s["action_payload"],
                "filters": [{"name": f["name"], "mode": f["mode"], "payload": f["payload"]} for f in s["filters"]],
                "offers": offers,
                # Offers that were in this flow before but aren't in Keitaro now,
                # whether removed here or in the Keitaro admin.
                "removed_offers": [
                    {"offer_id": r.offer_id, "last_share": r.last_share}
                    for r in known
                    if r.stream_id == s["id"] and r.offer_id not in in_flow
                ],
            }
        )

    return {
        "id": campaign["id"],
        "name": campaign["name"],
        "url": campaign["domain"] + campaign["alias"],
        "streams": result,
    }


@app.post("/api/rebalance")
def rebalance_shares(offers: list[OfferShare]):
    """Used by the editor on every change; the math lives in app/shares.py."""
    return rebalance(offers)


class PushOffers(BaseModel):
    campaign_id: int
    offers: list[OfferShare]


@app.put("/api/streams/{stream_id}/offers")
def push_offers(stream_id: int, data: PushOffers, session: Session = Depends(get_session)):
    check_ready_to_push(data.offers)

    # Re-read the flow from Keitaro so the log has what was really there before.
    old = keitaro.list_streams(data.campaign_id)
    old_stream = next((s for s in old if s["id"] == stream_id), None)
    if old_stream is None:
        raise HTTPException(404, f"Flow {stream_id} not found in campaign {data.campaign_id}")

    new_offers = [{"offer_id": o.offer_id, "share": o.share} for o in data.offers if not o.removed]
    updated = keitaro.update_stream(
        stream_id,
        {"offers": [{**o, "state": "active"} for o in new_offers]},
    )

    our_campaign = session.scalar(select(Campaign).where(Campaign.keitaro_id == data.campaign_id))
    session.add(
        OfferChange(
            campaign=our_campaign,
            keitaro_campaign_id=data.campaign_id,
            stream_id=stream_id,
            before=[{"offer_id": o["offer_id"], "share": o["share"]} for o in old_stream["offers"]],
            after=new_offers,
        )
    )

    # Remember what was there before (in case it changed in Keitaro since the
    # last fetch), then what is there now.
    remember_offers(session, data.campaign_id, stream_id, old_stream["offers"])
    session.flush()
    remember_offers(session, data.campaign_id, stream_id, updated["offers"])
    session.commit()

    return [{"offer_id": o["offer_id"], "share": o["share"]} for o in updated["offers"]]


@app.get("/api/campaigns/{campaign_id}/changes")
def changes(campaign_id: int, session: Session = Depends(get_session)):
    rows = session.scalars(
        select(OfferChange)
        .where(OfferChange.keitaro_campaign_id == campaign_id)
        .order_by(OfferChange.id.desc())
    )
    return [
        {"id": r.id, "stream_id": r.stream_id, "before": r.before, "after": r.after, "created_at": r.created_at}
        for r in rows
    ]
