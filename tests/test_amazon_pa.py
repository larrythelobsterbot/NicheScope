"""Amazon collector handles Creators API and legacy PA-API item shapes."""
from types import SimpleNamespace


def _base_item():
    return SimpleNamespace(
        asin="B0TEST0001",
        item_info=SimpleNamespace(
            title=SimpleNamespace(display_value="Test Serum 1oz"),
            by_line_info=SimpleNamespace(brand=SimpleNamespace(display_value="Acme")),
        ),
        images=SimpleNamespace(
            primary=SimpleNamespace(large=SimpleNamespace(url="https://img/x.jpg"))
        ),
    )


def test_item_to_product_creators_flavor():
    from amazon_pa import _item_to_product

    item = _base_item()
    item.offers_v2 = SimpleNamespace(
        listings=[
            SimpleNamespace(
                price=SimpleNamespace(money=SimpleNamespace(amount=19.99))
            )
        ]
    )
    p = _item_to_product(item, "creators")
    assert p["asin"] == "B0TEST0001"
    assert p["price"] == 19.99
    assert p["brand"] == "Acme"
    assert p["image_url"] == "https://img/x.jpg"


def test_item_to_product_paapi_flavor():
    from amazon_pa import _item_to_product

    item = _base_item()
    item.offers = SimpleNamespace(
        listings=[SimpleNamespace(price=SimpleNamespace(amount=12.50))]
    )
    p = _item_to_product(item, "paapi")
    assert p["price"] == 12.50


def test_item_to_product_handles_missing_offers():
    from amazon_pa import _item_to_product

    item = _base_item()
    item.offers_v2 = None
    p = _item_to_product(item, "creators")
    assert p["price"] is None


def test_collect_skips_with_reason_when_unconfigured(temp_db, monkeypatch):
    import amazon_pa

    monkeypatch.setattr(amazon_pa, "AMAZON_CREATORS_CREDENTIAL_ID", "")
    monkeypatch.setattr(amazon_pa, "AMAZON_ACCESS_KEY", "")
    success, items, err = amazon_pa.collect_amazon_products()
    assert success is True
    assert items == 0
    assert "credentials not configured" in (err or "")
