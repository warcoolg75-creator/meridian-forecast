"""GET /api/v1/products and GET /api/v1/regions: pagination and filters."""


def test_products_paginate_in_sku_order(client, ids):
    first = client.get("/api/v1/products", params={"limit": 2}).json()
    second = client.get("/api/v1/products", params={"limit": 2, "offset": 2}).json()

    assert first["total"] == second["total"] == 4
    assert [p["sku"] for p in first["items"]] == ["COL-OLD-300", "FDS-GFB-1KG"]
    assert [p["sku"] for p in second["items"]] == ["IND-BRG-6205", "KIT-AFR-45"]
    assert (first["limit"], first["offset"], second["offset"]) == (2, 0, 2)


def test_products_filter_by_category_activity_and_search(client, ids):
    by_category = client.get("/api/v1/products", params={"category": "Packaged Foods"}).json()
    inactive = client.get("/api/v1/products", params={"is_active": "false"}).json()
    search = client.get("/api/v1/products", params={"q": "bEaRiNg"}).json()

    assert [p["sku"] for p in by_category["items"]] == ["FDS-GFB-1KG"]
    assert [p["sku"] for p in inactive["items"]] == ["COL-OLD-300"]
    assert [p["sku"] for p in search["items"]] == ["IND-BRG-6205"]
    product = by_category["items"][0]
    assert product["launched_on"] == "2019-09-01" and product["unit_price_minor"] == 1000


def test_products_rejects_bad_pagination(client, ids):
    assert client.get("/api/v1/products", params={"limit": 0}).status_code == 422
    assert client.get("/api/v1/products", params={"offset": -1}).status_code == 422


def test_regions_filter_by_level(client, ids):
    body = client.get("/api/v1/regions", params={"level": "city"}).json()
    assert body["total"] == 3
    assert [(r["code"], r["parent_code"]) for r in body["items"]] == [
        ("IN-DL-NDL", "IN-DL"), ("IN-MH-MUM", "IN-MH"), ("IN-MH-PUN", "IN-MH")]


def test_regions_filter_by_parent_and_paginate(client, ids):
    body = client.get("/api/v1/regions", params={"parent_code": "IN", "limit": 1, "offset": 1}).json()
    assert body["total"] == 2
    assert [r["code"] for r in body["items"]] == ["IN-MH"]
    assert body["items"][0]["level"] == "state"


def test_regions_unknown_parent_is_404(client, ids):
    response = client.get("/api/v1/regions", params={"parent_code": "XX"})
    assert response.status_code == 404
    assert response.json() == {"detail": "Unknown region code: XX"}
