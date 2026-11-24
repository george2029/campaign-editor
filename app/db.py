from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

from app.config import settings

engine = create_engine(settings.database_url)


def get_session():
    with Session(engine) as session:
        yield session


class Base(DeclarativeBase):
    pass


class Campaign(Base):
    """A campaign created through this app (Keitaro keeps the real thing)."""

    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    keitaro_id: Mapped[int] = mapped_column(unique=True)
    name: Mapped[str] = mapped_column(String(255))
    alias: Mapped[str] = mapped_column(String(64))
    url: Mapped[str] = mapped_column(String(512))
    geo: Mapped[list[str]] = mapped_column(JSON)
    offer_id: Mapped[int]
    geo_stream_id: Mapped[int]
    offers_stream_id: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)

    changes: Mapped[list["OfferChange"]] = relationship(back_populates="campaign")


class OfferChange(Base):
    """One "Push to KT" from the editor: the offer shares before and after."""

    __tablename__ = "offer_changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Campaigns made outside this app can be edited too, so this link is optional.
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id"))
    keitaro_campaign_id: Mapped[int]
    stream_id: Mapped[int]
    before: Mapped[list[dict]] = mapped_column(JSON)  # [{"offer_id": 1, "share": 50}, ...]
    after: Mapped[list[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)

    campaign: Mapped[Campaign | None] = relationship(back_populates="changes")


class FlowOffer(Base):
    """Every offer this app has ever seen in a flow.

    Keitaro forgets an offer once it's removed from a flow (by this app or by
    someone in the Keitaro admin). We remember it here, so an offer that is in
    this table but not in Keitaro anymore is shown as removed, with "Bring back".
    """

    __tablename__ = "flow_offers"
    __table_args__ = (UniqueConstraint("stream_id", "offer_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    keitaro_campaign_id: Mapped[int]
    stream_id: Mapped[int]
    offer_id: Mapped[int]
    last_share: Mapped[int]  # share it had the last time we saw it in the flow
    last_seen_at: Mapped[datetime] = mapped_column(default=datetime.now)
