"""Static reference data and the hand-designed demand profile of every product.

Everything here is fixed by design. The random parts (promotion windows, supply
shocks, Poisson noise, order splitting) are drawn in ground_truth.py / generate.py
from a seeded RNG. Company, customer and plant names are fictional.
"""

from dataclasses import dataclass, field
from datetime import date

KITCHEN = "Kitchen Appliances"
COOLING = "Cooling"
FOODS = "Packaged Foods"
INDUSTRIAL = "Industrial Components"
CATEGORIES = (KITCHEN, COOLING, FOODS, INDUSTRIAL)
CONSUMER = (KITCHEN, COOLING, FOODS)

# (code, name, level, parent_code). Sales are recorded at city level.
REGIONS: list[tuple[str, str, str, str | None]] = [
    ("IN", "India", "country", None),
    ("IN-MH", "Maharashtra", "state", "IN"),
    ("IN-GJ", "Gujarat", "state", "IN"),
    ("IN-DL", "Delhi", "state", "IN"),
    ("IN-KA", "Karnataka", "state", "IN"),
    ("IN-TN", "Tamil Nadu", "state", "IN"),
    ("IN-TG", "Telangana", "state", "IN"),
    ("IN-WB", "West Bengal", "state", "IN"),
    ("IN-KL", "Kerala", "state", "IN"),
    ("IN-MH-MUM", "Mumbai", "city", "IN-MH"),
    ("IN-MH-PUN", "Pune", "city", "IN-MH"),
    ("IN-GJ-AMD", "Ahmedabad", "city", "IN-GJ"),
    ("IN-DL-NDL", "New Delhi", "city", "IN-DL"),
    ("IN-KA-BLR", "Bengaluru", "city", "IN-KA"),
    ("IN-TN-CHE", "Chennai", "city", "IN-TN"),
    ("IN-TG-HYD", "Hyderabad", "city", "IN-TG"),
    ("IN-WB-KOL", "Kolkata", "city", "IN-WB"),
    ("IN-KL-KOC", "Kochi", "city", "IN-KL"),
]
CITIES = [code for code, _, level, _ in REGIONS if level == "city"]

PLANTS = [
    dict(code="PUN", name="Pune Works (Chakan)", city="Pune", state="Maharashtra", country="IN",
         latitude=18.7606, longitude=73.8636, timezone="Asia/Kolkata"),
    dict(code="CHN", name="Chennai Works (Sriperumbudur)", city="Sriperumbudur", state="Tamil Nadu",
         country="IN", latitude=12.9675, longitude=79.9419, timezone="Asia/Kolkata"),
    dict(code="MNS", name="Manesar Foods Plant", city="Manesar", state="Haryana", country="IN",
         latitude=28.3540, longitude=76.9366, timezone="Asia/Kolkata"),
]

LINES = [
    dict(code="PUN-L1", name="Kitchen Appliance Assembly", plant="PUN", units_per_hour=40,
         changeover_minutes=45, operating_hours_per_day=16),
    dict(code="PUN-L2", name="Fan & Cooler Assembly", plant="PUN", units_per_hour=60,
         changeover_minutes=60, operating_hours_per_day=16),
    dict(code="CHN-L1", name="Precision Machining & Motors", plant="CHN", units_per_hour=120,
         changeover_minutes=90, operating_hours_per_day=22),
    dict(code="MNS-L1", name="Food Processing & Packing", plant="MNS", units_per_hour=150,
         changeover_minutes=30, operating_hours_per_day=16),
]

# (line, sku, units_per_hour_override or None = line base rate)
CAPABILITIES: list[tuple[str, str, int | None]] = [
    ("PUN-L1", "KIT-MXG-750", None),
    ("PUN-L1", "KIT-IND-2000", 48),
    ("PUN-L1", "KIT-AFR-45", 32),
    ("PUN-L2", "COL-ACL-70", 22),
    ("PUN-L2", "COL-CFN-1200", None),
    ("PUN-L2", "COL-TFN-400", 75),
    ("CHN-L1", "COL-CFN-1200", 30),  # second source for ceiling fans, slower
    ("CHN-L1", "IND-BRG-6205", 420),
    ("CHN-L1", "IND-MTR-1HP", 14),
    ("CHN-L1", "IND-PMP-05", 12),
    ("MNS-L1", "FDS-GFB-1KG", 70),
    ("MNS-L1", "FDS-SWT-500", None),
    ("MNS-L1", "FDS-NMK-200", 420),
]

# (code, name, channel, city, categories bought)
CUSTOMERS: list[tuple[str, str, str, str, tuple[str, ...]]] = [
    ("C01", "Sahyadri Distributors", "distributor", "IN-MH-MUM", CATEGORIES),
    ("C02", "Deccan Supply Co", "distributor", "IN-MH-PUN", CATEGORIES),
    ("C03", "Sabarmati Agencies", "distributor", "IN-GJ-AMD", CATEGORIES),
    ("C04", "Yamuna Trade Links", "distributor", "IN-DL-NDL", CATEGORIES),
    ("C05", "Cauvery Distribution", "distributor", "IN-KA-BLR", CATEGORIES),
    ("C06", "Coromandel Traders", "distributor", "IN-TN-CHE", CATEGORIES),
    ("C07", "Charminar Distributors", "distributor", "IN-TG-HYD", CATEGORIES),
    ("C08", "Hooghly Wholesale", "distributor", "IN-WB-KOL", CATEGORIES),
    ("C09", "Lotus Home Stores", "retail", "IN-DL-NDL", CONSUMER),
    ("C10", "Metro Value Mart", "retail", "IN-MH-MUM", CONSUMER),
    ("C11", "Kaveri Electronics", "retail", "IN-KA-BLR", CONSUMER),
    ("C12", "Marina Home Centre", "retail", "IN-TN-CHE", CONSUMER),
    ("C13", "Esplanade Stores", "retail", "IN-WB-KOL", CONSUMER),
    ("C14", "Malabar Home Needs", "retail", "IN-KL-KOC", CONSUMER),
    ("C15", "Navrang Retail", "retail", "IN-GJ-AMD", CONSUMER),
    ("C16", "ShopSetu Online", "ecommerce", "IN-KA-BLR", CONSUMER),
    ("C17", "QuickCart India", "ecommerce", "IN-MH-MUM", CONSUMER),
    ("C18", "DesiBasket", "ecommerce", "IN-DL-NDL", CONSUMER),
    ("C19", "Chakan Auto Components", "direct", "IN-MH-PUN", (INDUSTRIAL,)),
    ("C20", "Sriperumbudur Pumpsets", "direct", "IN-TN-CHE", (INDUSTRIAL,)),
    ("C21", "Naroda Textile Machinery", "direct", "IN-GJ-AMD", (INDUSTRIAL,)),
    ("C22", "Capital Corporate Gifting", "direct", "IN-DL-NDL", (FOODS,)),
    ("C23", "Gulf Gateway Trading (via Mumbai)", "export", "IN-MH-MUM", (FOODS, KITCHEN)),
    ("C24", "Lanka Industrial Imports (via Chennai)", "export", "IN-TN-CHE", (INDUSTRIAL, FOODS)),
    ("C25", "East Africa Machinery (via Mumbai)", "export", "IN-MH-MUM", (INDUSTRIAL,)),
]

# Ecommerce customers ship to every city; each takes a fixed share of the ecommerce
# channel. Every other customer only buys in its own city.
ECOMMERCE_SHARES = {"C16": 0.5, "C17": 0.3, "C18": 0.2}

# Net price as a fraction of list price, by channel.
CHANNEL_PRICE_FACTOR = {"distributor": 0.82, "retail": 0.90, "ecommerce": 0.95, "direct": 0.88, "export": 0.85}

# Mean 1.0 over Mon..Sun. B2B dips hard at weekends; retail peaks at weekends.
WEEKLY_PROFILES = {
    "b2b": [1.22, 1.26, 1.26, 1.24, 1.22, 0.55, 0.25],
    "retail": [0.86, 0.84, 0.86, 0.90, 1.04, 1.24, 1.26],
}

# Yearly bumps: multiplier = 1 + sum(amplitude * exp(-0.5 * (days_to_center / width_days)^2)).
# Narrow festive windows are centred late October with width ~11-14 days, so the
# season is roughly the six weeks from early October to mid November.
FESTIVE = "10-24"


@dataclass(frozen=True)
class DemandDesign:
    base_level: float  # mean units/day at window start, off-season, before weekly/holiday effects
    trend: dict  # {"type": "exponential", "annual_growth": g} | {"type": "launch_ramp", ...}
    weekly_profile: str
    yearly: list[dict] = field(default_factory=list)  # [{"center": "MM-DD", "width_days", "amplitude"}]
    region_weights: dict[str, float] = field(default_factory=dict)  # city code -> share
    channel_weights: dict[str, float] = field(default_factory=dict)  # preferred channel mix
    lifecycle: str = "mature"


@dataclass(frozen=True)
class ProductSpec:
    sku: str
    name: str
    category: str
    subcategory: str
    unit_cost_minor: int
    unit_price_minor: int
    unit_of_measure: str
    shelf_life_days: int | None
    launched_on: date | None  # None = launched LAUNCH_MONTHS_AGO before the window end
    demand: DemandDesign


LAUNCH_MONTHS_AGO = 8


def _cities(**weights: float) -> dict[str, float]:
    by_suffix = {code.rsplit("-", 1)[1]: code for code in CITIES}
    return {by_suffix[k]: v for k, v in weights.items()}


KITCHEN_CHANNELS = {"distributor": 0.30, "retail": 0.40, "ecommerce": 0.25, "export": 0.05}
COOLING_CHANNELS = {"distributor": 0.45, "retail": 0.40, "ecommerce": 0.15}

PRODUCTS: list[ProductSpec] = [
    ProductSpec(
        "KIT-MXG-750", "Mixer Grinder 750W", KITCHEN, "Food Preparation", 230000, 349900, "each", None,
        date(2016, 6, 1),
        DemandDesign(
            base_level=90, trend={"type": "exponential", "annual_growth": 0.08}, weekly_profile="retail",
            yearly=[{"center": FESTIVE, "width_days": 12, "amplitude": 1.8}],
            region_weights=_cities(MUM=.14, PUN=.06, AMD=.08, NDL=.10, BLR=.16, CHE=.20, HYD=.12, KOL=.04, KOC=.10),
            channel_weights=KITCHEN_CHANNELS,
        ),
    ),
    ProductSpec(
        "KIT-IND-2000", "Induction Cooktop 2000W", KITCHEN, "Cooking", 180000, 279900, "each", None,
        date(2018, 3, 15),
        DemandDesign(
            base_level=70, trend={"type": "exponential", "annual_growth": 0.03}, weekly_profile="retail",
            yearly=[{"center": "12-20", "width_days": 30, "amplitude": 0.3}],
            region_weights=_cities(MUM=.13, PUN=.08, AMD=.10, NDL=.15, BLR=.12, CHE=.10, HYD=.10, KOL=.14, KOC=.08),
            channel_weights=KITCHEN_CHANNELS,
        ),
    ),
    ProductSpec(
        "KIT-AFR-45", "Air Fryer 4.5L", KITCHEN, "Cooking", 410000, 649900, "each", None,
        None,
        DemandDesign(
            base_level=140,
            trend={"type": "launch_ramp", "midpoint_days": 45, "scale_days": 15, "annual_growth": 0.30},
            weekly_profile="retail",
            yearly=[{"center": FESTIVE, "width_days": 15, "amplitude": 0.8}],
            region_weights=_cities(MUM=.22, PUN=.08, AMD=.04, NDL=.18, BLR=.26, CHE=.06, HYD=.12, KOL=.02, KOC=.02),
            channel_weights={"distributor": 0.10, "retail": 0.25, "ecommerce": 0.65},
            lifecycle="new",
        ),
    ),
    ProductSpec(
        "COL-ACL-70", "Desert Air Cooler 70L", COOLING, "Air Coolers", 640000, 999900, "each", None,
        date(2017, 2, 1),
        DemandDesign(
            base_level=25, trend={"type": "exponential", "annual_growth": 0.05}, weekly_profile="retail",
            yearly=[{"center": "05-01", "width_days": 40, "amplitude": 4.0}],
            region_weights=_cities(MUM=.04, PUN=.08, AMD=.28, NDL=.38, BLR=.02, CHE=.03, HYD=.14, KOL=.02, KOC=.01),
            channel_weights=COOLING_CHANNELS,
        ),
    ),
    ProductSpec(
        "COL-CFN-1200", "Ceiling Fan 1200mm", COOLING, "Fans", 140000, 219900, "each", None,
        date(2015, 1, 10),
        DemandDesign(
            base_level=110, trend={"type": "exponential", "annual_growth": 0.06}, weekly_profile="retail",
            yearly=[{"center": "04-25", "width_days": 45, "amplitude": 0.9}],
            region_weights=_cities(MUM=.10, PUN=.06, AMD=.08, NDL=.12, BLR=.12, CHE=.20, HYD=.14, KOL=.10, KOC=.08),
            channel_weights=COOLING_CHANNELS,
        ),
    ),
    ProductSpec(
        "COL-TFN-400", "Table Fan 400mm", COOLING, "Fans", 105000, 159900, "each", None,
        date(2012, 4, 1),
        DemandDesign(
            base_level=120, trend={"type": "exponential", "annual_growth": -0.45}, weekly_profile="retail",
            yearly=[{"center": "05-01", "width_days": 40, "amplitude": 1.4}],
            region_weights=_cities(MUM=.06, PUN=.03, AMD=.05, NDL=.08, BLR=.04, CHE=.22, HYD=.07, KOL=.40, KOC=.05),
            channel_weights=COOLING_CHANNELS,
            lifecycle="phase_out",
        ),
    ),
    ProductSpec(
        "FDS-GFB-1KG", "Dry Fruit Gift Box 1kg", FOODS, "Gifting", 72000, 119900, "box", 180,
        date(2019, 9, 1),
        DemandDesign(
            base_level=6, trend={"type": "exponential", "annual_growth": 0.10}, weekly_profile="retail",
            yearly=[{"center": FESTIVE, "width_days": 11, "amplitude": 14.0}],
            region_weights=_cities(MUM=.24, PUN=.05, AMD=.14, NDL=.40, BLR=.06, CHE=.03, HYD=.04, KOL=.03, KOC=.01),
            channel_weights={"distributor": 0.15, "retail": 0.35, "ecommerce": 0.20, "direct": 0.25, "export": 0.05},
        ),
    ),
    ProductSpec(
        "FDS-SWT-500", "Assorted Mithai 500g", FOODS, "Sweets", 19000, 34900, "pack", 21,
        date(2016, 10, 1),
        DemandDesign(
            base_level=120, trend={"type": "exponential", "annual_growth": 0.04}, weekly_profile="retail",
            yearly=[{"center": FESTIVE, "width_days": 14, "amplitude": 3.0}],
            region_weights=_cities(MUM=.10, PUN=.04, AMD=.08, NDL=.26, BLR=.04, CHE=.02, HYD=.04, KOL=.40, KOC=.02),
            channel_weights={"distributor": 0.30, "retail": 0.45, "ecommerce": 0.10, "direct": 0.10, "export": 0.05},
        ),
    ),
    ProductSpec(
        "FDS-NMK-200", "Namkeen Mix 200g", FOODS, "Snacks", 5200, 9900, "pack", 120,
        date(2018, 7, 1),
        DemandDesign(
            base_level=300, trend={"type": "exponential", "annual_growth": 0.15}, weekly_profile="retail",
            yearly=[{"center": FESTIVE, "width_days": 20, "amplitude": 0.35}],
            region_weights=_cities(MUM=.22, PUN=.10, AMD=.34, NDL=.12, BLR=.06, CHE=.03, HYD=.05, KOL=.06, KOC=.02),
            channel_weights={"distributor": 0.40, "retail": 0.35, "ecommerce": 0.15, "export": 0.10},
        ),
    ),
    ProductSpec(
        "IND-BRG-6205", "Ball Bearing 6205-2RS", INDUSTRIAL, "Bearings", 9600, 18500, "each", None,
        date(2014, 5, 1),
        DemandDesign(
            base_level=450, trend={"type": "exponential", "annual_growth": 0.40}, weekly_profile="b2b",
            yearly=[],  # aseasonal
            region_weights=_cities(MUM=.10, PUN=.30, AMD=.12, NDL=.06, BLR=.14, CHE=.22, HYD=.06),
            channel_weights={"distributor": 0.35, "direct": 0.45, "export": 0.20},
        ),
    ),
    ProductSpec(
        "IND-MTR-1HP", "Induction Motor 1HP", INDUSTRIAL, "Motors", 560000, 845000, "each", None,
        date(2015, 8, 1),
        DemandDesign(
            base_level=55, trend={"type": "exponential", "annual_growth": 0.07}, weekly_profile="b2b",
            yearly=[{"center": "03-20", "width_days": 12, "amplitude": 0.6}],  # financial-year-end push
            region_weights=_cities(MUM=.08, PUN=.22, AMD=.26, NDL=.10, BLR=.08, CHE=.14, HYD=.08, KOL=.04),
            channel_weights={"distributor": 0.50, "direct": 0.35, "export": 0.15},
        ),
    ),
    ProductSpec(
        "IND-PMP-05", "Submersible Pump 0.5HP", INDUSTRIAL, "Pumps", 780000, 1190000, "each", None,
        date(2017, 11, 1),
        DemandDesign(
            base_level=40, trend={"type": "exponential", "annual_growth": 0.04}, weekly_profile="b2b",
            yearly=[{"center": "05-10", "width_days": 30, "amplitude": 1.2}],  # pre-monsoon
            region_weights=_cities(MUM=.06, PUN=.20, AMD=.34, NDL=.06, BLR=.06, CHE=.08, HYD=.16, KOL=.04),
            channel_weights={"distributor": 0.60, "direct": 0.25, "export": 0.15},
        ),
    ),
]

SCRAP_RATE = {KITCHEN: 0.012, COOLING: 0.015, FOODS: 0.02, INDUSTRIAL: 0.008}

# Illustrative annual events with no modelled demand effect: (name, city, MM-DD start, days).
TRADE_SHOWS = [
    ("Industrial Machine Tools Expo", "IN-KA-BLR", "01-22", 6),
    ("Food & Hospitality Expo", "IN-DL-NDL", "03-12", 4),
    ("Consumer Durables Trade Fair", "IN-MH-MUM", "08-06", 3),
]
