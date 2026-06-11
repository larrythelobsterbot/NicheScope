"""Best-seller scraper extracts prices and stores product snapshots."""
import sqlite3

from bs4 import BeautifulSoup


def _item(html):
    return BeautifulSoup(html, "html.parser").find("div")


def test_extract_price_simple():
    from amazon_bestsellers import _extract_price

    item = _item(
        '<div><span class="_cDEzb_p13n-sc-price_3mJ9Z">$13.98</span></div>'
    )
    assert _extract_price(item) == 13.98


def test_extract_price_range_takes_low_end():
    from amazon_bestsellers import _extract_price

    item = _item(
        '<div><span class="p13n-sc-price">$10.99 - $19.99</span></div>'
    )
    assert _extract_price(item) == 10.99


def test_extract_price_with_thousands_separator():
    from amazon_bestsellers import _extract_price

    item = _item('<div><span class="p13n-sc-price">$1,299.00</span></div>')
    assert _extract_price(item) == 1299.0


def test_extract_price_missing():
    from amazon_bestsellers import _extract_price

    assert _extract_price(_item("<div><span>no price here</span></div>")) is None


def test_store_bestseller_products_writes_history(temp_db):
    from amazon_bestsellers import store_bestseller_products

    conn = sqlite3.connect(temp_db)
    conn.row_factory = sqlite3.Row

    products = [
        {"title": "Acme Vitamin C Serum 1oz", "rank": 1, "asin": "B0AAAA0001", "price": 19.99},
        {"title": "No-ASIN product", "rank": 2, "asin": None, "price": 9.99},
        {"title": "No-price product", "rank": 3, "asin": "B0AAAA0002", "price": None},
    ]
    written = store_bestseller_products(conn, products, "beauty")
    assert written == 1

    # Idempotent within the same day
    written_again = store_bestseller_products(conn, products, "beauty")
    assert written_again == 0

    row = conn.execute(
        """SELECT p.asin, p.category, ph.price, ph.sales_rank
           FROM products p JOIN product_history ph ON ph.product_id = p.id"""
    ).fetchone()
    conn.close()
    assert row["asin"] == "B0AAAA0001"
    assert row["category"] == "beauty"
    assert row["price"] == 19.99
    assert row["sales_rank"] == 1


def test_price_map_from_raw_html_fallback():
    from amazon_bestsellers import _price_map_from_html

    html = (
        '<a href="/dp/B0AAAA0001?ref=x">item1</a>'
        '<span class="_cDEzb_p13n-sc-price_3mJ9Z">$18.90</span>'
        '<a href="/dp/B0AAAA0002?ref=x">item2</a>'
        '<span class="p13n-sc-price">$1,299.00</span>'
        '<a href="/dp/B0AAAA0003?ref=x">no price item</a>'
    )
    prices = _price_map_from_html(html)
    assert prices == {"B0AAAA0001": 18.9, "B0AAAA0002": 1299.0}
