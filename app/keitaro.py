"""Thin client for the Keitaro Admin API: one function per endpoint we use."""

import httpx

from app.config import settings


class KeitaroError(Exception):
    pass


client = httpx.Client(
    base_url=settings.keitaro_url,
    headers={"Api-Key": settings.keitaro_api_key},
    timeout=20,
)


def _request(method: str, path: str, json: dict | None = None):
    response = client.request(method, path, json=json)
    if response.is_error:
        raise KeitaroError(f"Keitaro {method} {path} -> {response.status_code}: {response.text}")
    return response.json()


# Catalogs (read-only)


def list_offers() -> list[dict]:
    return _request("GET", "/offers")


def get_offer(offer_id: int) -> dict:
    return _request("GET", f"/offers/{offer_id}")


def list_domains() -> list[dict]:
    return _request("GET", "/domains")


def list_groups() -> list[dict]:
    return _request("GET", "/groups")


def list_traffic_sources() -> list[dict]:
    return _request("GET", "/traffic_sources")


# Campaigns


def list_campaigns() -> list[dict]:
    return _request("GET", "/campaigns")


def get_campaign(campaign_id: int) -> dict:
    return _request("GET", f"/campaigns/{campaign_id}")


def create_campaign(payload: dict) -> dict:
    return _request("POST", "/campaigns", payload)


def delete_campaign(campaign_id: int) -> dict:
    return _request("DELETE", f"/campaigns/{campaign_id}")


# Streams (flows)


def list_streams(campaign_id: int) -> list[dict]:
    return _request("GET", f"/campaigns/{campaign_id}/streams")


def create_stream(payload: dict) -> dict:
    return _request("POST", "/streams", payload)


def update_stream(stream_id: int, payload: dict) -> dict:
    return _request("PUT", f"/streams/{stream_id}", payload)
