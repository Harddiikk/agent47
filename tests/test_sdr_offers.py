"""Tests for sdr/offers.py — signal → offer matching."""
from sdr.offers import load_offers, match_offer


def test_load_default_catalog():
    offers = load_offers("data/offers.json")
    names = [o["name"] for o in offers]
    assert any("SEO" in n for n in names)
    assert any("Reputation" in n for n in names)


def test_load_missing_file_falls_back():
    offers = load_offers("data/nonexistent.json")
    assert len(offers) >= 5


def test_new_location_maps_to_gbp_seo():
    offer = match_offer("expansion", "opened a new clinic location in Frisco")
    assert "SEO" in offer or "Maps" in offer or "GBP" in offer


def test_new_equipment_maps_to_landing_ads():
    offer = match_offer("expansion", "bought a new laser machine, now offering laser facials")
    assert "Landing" in offer or "Ads" in offer


def test_reviews_map_to_reputation():
    assert "Reputation" in match_offer("risk", "rating fell below 4 stars on Google reviews")


def test_hiring_maps_to_receptionist():
    assert "Receptionist" in match_offer("expansion", "hiring two front desk staff")


def test_fallback_by_signal_type():
    assert match_offer("risk", "something vague") != ""
    assert match_offer("neutral", "nothing in particular") != ""
