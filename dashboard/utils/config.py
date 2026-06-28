# utils/config.py
# Unstructured Alpha — Signal Library Configuration
# Maps directly to the Project Bible signal definitions

# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL DEFINITIONS
# Each signal maps to a data source (FRED series ID, yfinance ticker, or basket)
# lag_weeks: how many weeks the signal leads the associated ticker price
# inverse: True if a rising signal is bearish for the ticker
# ─────────────────────────────────────────────────────────────────────────────

SIGNALS = {

    # ── TIER 1 — MACRO / TRADITIONAL ──────────────────────────────────────────

    "ata_trucking": {
        "name": "ATA Trucking Tonnage Index",
        "tier": 1,
        "pcs": 9,
        "source": "fred",
        "series_id": "TRUCKD11",
        "frequency": "monthly",
        "lag_weeks": 6,
        "inverse": False,
        "unit": "Index (2015=100)",
        "description": "Weight of freight moved by US trucking. Covers ~70% of all domestic freight. Formally included in the Conference Board Leading Economic Indicators.",
        "causal_mechanism": "Trucks move almost everything. A drop precedes inventory drawdowns and spending slowdowns by 6–8 weeks.",
        "documented_cases": [
            "ATA tonnage peaked March 2018, 14 months before manufacturing ISM entered contraction (Aug 2019)",
            "Index fell 5.7% in Feb 2020 — first month of COVID disruption — before any official data reflected the downturn",
        ],
        "relevant_tickers": ["JBHT", "ODFL", "SAIA", "WERN", "UPS", "FDX", "XLI", "SPY"],
        "category": "macro",
        "color": "#1C2B4A",
        "source_url": "https://www.trucking.org/economics-and-industry-data",
    },

    "rail_traffic": {
        "name": "AAR Rail Traffic (Intermodal)",
        "tier": 1,
        "pcs": 9,
        "source": "fred",
        "series_id": "RAILFRTINTERMODAL",
        "frequency": "weekly",
        "lag_weeks": 4,
        "inverse": False,
        "unit": "Thousand Carloads",
        "description": "Volume of intermodal container freight moved by rail. Signals import demand before it appears in trade statistics.",
        "causal_mechanism": "Rail is how America moves physical goods. Intermodal container volume = import demand 4–8 weeks early.",
        "documented_cases": [
            "Rail carloads dropped 8% YoY in Q4 2007 — two quarters before NBER declared recession",
            "Auto loadings collapsed 34% in Jan–Feb 2020 before automaker earnings reflected COVID demand destruction",
        ],
        "relevant_tickers": ["UNP", "CSX", "NSC", "CP", "CNI", "XLI"],
        "category": "macro",
        "color": "#1B5E20",
        "source_url": "https://www.aar.org/data/weekly-railroad-traffic/",
    },

    "jobless_claims": {
        "name": "Initial Jobless Claims (WARN Proxy)",
        "tier": 1,
        "pcs": 9,
        "source": "fred",
        "series_id": "IC4WSA",
        "frequency": "weekly",
        "lag_weeks": 4,
        "inverse": True,
        "unit": "Number of Claims",
        "description": "Weekly initial unemployment claims. Acts as a real-time proxy for WARN Act mass layoff activity. Higher claims = bearish.",
        "causal_mechanism": "Companies file WARN notices 60 days before layoffs. Jobless claims are the downstream confirmation. Rising claims precede consumer spending contractions.",
        "documented_cases": [
            "WARN filings in retail spiked 3x in January 2020, a full 60 days before COVID-related jobless claims hit record highs",
            "Sears WARN notices (Oct 2018) gave investors 60 days lead time before bankruptcy announcement",
        ],
        "relevant_tickers": ["SPY", "QQQ", "XLY", "IWM", "XLP", "HD", "AMZN"],
        "category": "macro",
        "color": "#7B1010",
        "source_url": "https://www.dol.gov/ui/data.pdf",
    },

    "layoffs_rate": {
        "name": "Layoffs & Discharges Rate (BLS JOLTS)",
        "tier": 1,
        "pcs": 8,
        "source": "fred",
        "series_id": "JTSLDR",
        "frequency": "monthly",
        "lag_weeks": 6,
        "inverse": True,
        "unit": "Rate (%)",
        "description": "Layoffs and discharges as % of total employment from BLS JOLTS. Higher rate = bearish for consumer stocks.",
        "causal_mechanism": "Rising layoff rate directly reduces consumer disposable income. Leads consumer spending data by 6–8 weeks.",
        "documented_cases": [
            "JOLTS layoff rate spiked in March 2020 preceding the consumer spending collapse in Q2 2020",
            "Layoff rate elevated in 2023 tech sector preceded consumer discretionary underperformance by 6–8 weeks",
        ],
        "relevant_tickers": ["XLY", "XLP", "HD", "TGT", "WMT", "AMZN", "COST", "LOW"],
        "category": "macro",
        "color": "#B34700",
        "source_url": "https://www.bls.gov/jlt/",
    },

    "jolts_openings": {
        "name": "JOLTS Job Openings (Labor Demand)",
        "tier": 1,
        "pcs": 8,
        "source": "fred",
        "series_id": "JTSJOL",
        "frequency": "monthly",
        "lag_weeks": 6,
        "inverse": False,
        "unit": "Thousands of Openings",
        "description": "Total job openings from BLS JOLTS. Strong labor demand = bullish for consumer spending and broad market.",
        "causal_mechanism": "Job openings lead hiring by 4–8 weeks. More openings = wage growth = consumer spending. Dropping openings signal employer caution before layoffs materialize.",
        "documented_cases": [
            "JOLTS openings peaked at 12M in March 2022 — declining openings preceded rate-sensitive sector selloff",
            "Openings collapse in H2 2022 led consumer discretionary underperformance by ~2 quarters",
        ],
        "relevant_tickers": ["SPY", "XLY", "WMT", "TGT", "COST", "HD", "LOW", "IWM"],
        "category": "macro",
        "color": "#0D4F5C",
        "source_url": "https://www.bls.gov/jlt/",
    },

    "ism_pmi": {
        # NOTE: this signal used to point at FRED series "NAPM" (ISM Manufacturing
        # PMI). Verified directly against FRED's API on 2026-06-20: NAPM was
        # removed from FRED entirely on 2016-06-24 when ISM pulled all 22 of its
        # series — confirmed via FRED's own announcement
        # (https://news.research.stlouisfed.org/2016/06/institute-for-supply-management-data-to-be-removed-from-fred/).
        # ISM PMI itself is no longer freely available anywhere (ISM now licenses
        # it). Replaced with the Philadelphia Fed Manufacturing Business Outlook
        # Survey's General Activity Index — the standard analyst substitute when
        # ISM isn't available: same diffusion-index design (rising = more firms
        # reporting expansion), just centered at 0 instead of 50.
        "name": "Philly Fed Manufacturing Index (ISM PMI proxy)",
        "tier": 1,
        "pcs": 7,
        "source": "fred",
        "series_id": "GACDFSA066MSFRBPHI",
        "frequency": "monthly",
        "lag_weeks": 4,
        "inverse": False,
        "unit": "Diffusion Index (0 = expansion/contraction line)",
        "description": "Philadelphia Fed Manufacturing Business Outlook Survey, General Activity Index. Above 0 = more manufacturers reporting expansion than contraction; below 0 = contraction. Used here in place of the ISM Manufacturing PMI, which the Institute for Supply Management pulled from FRED's free distribution in 2016.",
        "causal_mechanism": "Monthly survey of manufacturers in the Philadelphia Fed district (PA/NJ/DE) on new orders, shipments, employment, and general activity. Regional Fed manufacturing surveys (Philly, Richmond, Dallas, Kansas City) are watched as early reads ahead of the national ISM PMI release and lead industrial earnings by roughly the same window ISM PMI historically did.",
        "documented_cases": [
            "Philly Fed General Activity fell sharply into negative territory in mid-2022 ahead of broader manufacturing-sector earnings downgrades later that year",
            "The index's deep negative readings in April 2020 mirrored ISM PMI's COVID-era collapse to 41.5 the same month",
        ],
        "relevant_tickers": ["XLI", "CAT", "DE", "MMM", "HON", "ETN", "EMR", "ROK", "ITW"],
        "category": "macro",
        "color": "#4A1B6B",
        "source_url": "https://fred.stlouisfed.org/series/GACDFSA066MSFRBPHI",
    },

    "yield_curve": {
        "name": "Yield Curve Spread (10Y–2Y)",
        "tier": 1,
        "pcs": 9,
        "source": "fred",
        "series_id": "T10Y2Y",
        "frequency": "daily",
        "lag_weeks": 52,
        "inverse": True,
        "unit": "Percentage Points",
        "description": "10-year minus 2-year Treasury yield spread. Inversion (negative) has preceded every recession since 1955 with a 6–18 month lead time.",
        "causal_mechanism": "Inverted yield curve signals market expects Fed to cut rates as growth slows. Banks earn less on lending (borrow short, lend long) → credit tightening → recession.",
        "documented_cases": [
            "Curve inverted in Aug 2019 → recession began Feb 2020",
            "Curve inverted in Apr 2022 → growth stocks peaked May 2022, small caps underperformed for 18 months",
        ],
        "relevant_tickers": ["SPY", "XLF", "IWM", "KRE", "TLT", "TBF", "SHY"],
        "category": "macro",
        "color": "#8B7355",
        "source_url": "https://fred.stlouisfed.org/series/T10Y2Y",
    },

    "housing_starts": {
        "name": "Housing Starts (New Residential Construction)",
        "tier": 1,
        "pcs": 8,
        "source": "fred",
        "series_id": "HOUST",
        "frequency": "monthly",
        "lag_weeks": 12,
        "inverse": False,
        "unit": "Thousands of Units (Annual Rate)",
        "description": "Monthly new housing starts. Leading indicator for homebuilder stocks, building materials, appliances, and mortgage lending.",
        "causal_mechanism": "Permits precede starts by 1–3 months. Starts precede home sales by 3–6 months. Material intensity: each new home requires ~13,000 board-ft of lumber, 400lbs of copper.",
        "documented_cases": [
            "Housing starts peaked Feb 2006 at 2.27M units — 21 months before S&P homebuilder index bottomed",
            "Starts collapsed from 1.7M to 0.48M during GFC — DHI/LEN/PHM fell 85%+ from peak",
        ],
        "relevant_tickers": ["DHI", "LEN", "PHM", "TOL", "NVR", "HD", "LOW", "MAS", "LPX"],
        "category": "macro",
        "color": "#5D4037",
        "source_url": "https://fred.stlouisfed.org/series/HOUST",
    },

    "retail_sales": {
        "name": "Retail Sales ex. Auto & Gas",
        "tier": 1,
        "pcs": 8,
        "source": "fred",
        "series_id": "RSXFS",
        "frequency": "monthly",
        "lag_weeks": 4,
        "inverse": False,
        "unit": "Billions of USD",
        "description": "Advance retail sales excluding autos and gas. The cleanest read on discretionary consumer spending health.",
        "causal_mechanism": "Retail sales ex-auto/gas = pure discretionary spending signal. When this accelerates, consumer stock revenues follow in the next 1–2 earnings quarters.",
        "documented_cases": [
            "Retail sales turned negative in Dec 2019 for three consecutive months — early signal of pre-COVID consumer caution",
            "April 2020 crash (-16.4% MoM) confirmed COVID demand destruction before Q2 earnings season",
        ],
        "relevant_tickers": ["XLY", "AMZN", "WMT", "TGT", "COST", "HD", "LOW", "KSS", "M"],
        "category": "macro",
        "color": "#1C2B4A",
        "source_url": "https://fred.stlouisfed.org/series/RSXFS",
    },

    "consumer_sentiment": {
        "name": "U. Michigan Consumer Sentiment",
        "tier": 2,
        "pcs": 7,
        "source": "fred",
        "series_id": "UMCSENT",
        "frequency": "monthly",
        "lag_weeks": 6,
        "inverse": False,
        "unit": "Index (1966=100)",
        "description": "University of Michigan Consumer Sentiment survey. Tracks 500 households on financial conditions and business expectations.",
        "causal_mechanism": "Consumer sentiment leads spending by 1–2 months. It's a sentiment proxy that institutional investors watch for forward earnings guidance risk.",
        "documented_cases": [
            "Sentiment crashed to 71.8 in June 2022 (lowest since 1980) — consumer discretionary underperformed for 12 months",
            "Sentiment collapse in Feb–March 2020 front-ran Q1 2020 retail sales disaster",
        ],
        "relevant_tickers": ["XLY", "COST", "TGT", "HD", "LOW", "DPZ", "MCD", "SBUX"],
        "category": "macro",
        "color": "#B34700",
        "source_url": "https://fred.stlouisfed.org/series/UMCSENT",
    },

    "hy_spread": {
        "name": "High-Yield Credit Spread (ICE BofA)",
        "tier": 1,
        "pcs": 9,
        "source": "fred",
        "series_id": "BAMLH0A0HYM2",
        "frequency": "daily",
        "lag_weeks": 4,
        "inverse": True,
        "unit": "Percentage Points",
        "description": "ICE BofA US High Yield Option-Adjusted Spread. The credit market's forward-looking recession signal. Widening = financial stress. Rising spread = bearish for equities.",
        "causal_mechanism": "HY spreads widen when credit markets price in default risk. This transmission channel hits leveraged companies, banks, and growth stocks first — typically 4–8 weeks before equity repricing.",
        "documented_cases": [
            "HY spreads widened 800bps in Q4 2008 — equities followed with accelerating selloff in same period",
            "HY spreads spiked to 1100bps in March 2020 — Fed intervention followed within 2 weeks (SMCCF)",
        ],
        "relevant_tickers": ["SPY", "XLF", "HYG", "JNK", "TLT", "KRE", "LQD"],
        "category": "macro",
        "color": "#7B1010",
        "source_url": "https://fred.stlouisfed.org/series/BAMLH0A0HYM2",
    },

    "durable_goods": {
        "name": "Durable Goods Orders ex. Defense",
        "tier": 2,
        "pcs": 7,
        "source": "fred",
        "series_id": "DGORDER",
        "frequency": "monthly",
        "lag_weeks": 8,
        "inverse": False,
        "unit": "Billions of USD",
        "description": "New factory orders for goods lasting 3+ years, excluding volatile defense orders. Tracks business investment intentions.",
        "causal_mechanism": "Capital goods orders (a subset) are the best gauge of business capex intentions. Leads industrial production by 2–3 quarters.",
        "documented_cases": [
            "Durable goods orders declined 6 consecutive months before Q4 2015 industrial recession",
            "Core capex orders (non-defense, non-aircraft) turned negative in 2019 before manufacturing PMI fell below 50",
        ],
        "relevant_tickers": ["XLI", "CAT", "DE", "HON", "ETN", "ROK", "EMR", "GE", "PH"],
        "category": "macro",
        "color": "#0D4F5C",
        "source_url": "https://fred.stlouisfed.org/series/DGORDER",
    },

    "crude_oil": {
        "name": "WTI Crude Oil (Daily)",
        "tier": 1,
        "pcs": 8,
        "source": "fred",
        "series_id": "DCOILWTICO",
        "frequency": "daily",
        "lag_weeks": 2,
        "inverse": False,
        "unit": "USD per Barrel",
        "description": "WTI crude oil spot price. Tracks energy demand and implied economic activity.",
        "causal_mechanism": "Oil demand tracks industrial activity and transportation. Gasoline demand (implied from EIA data) is a real-time economic activity proxy.",
        "documented_cases": [
            "Gasoline demand fell in March 2020 — two weeks before stay-at-home orders were broadly announced",
            "Distillate demand fell 15% in Q4 2008 ahead of official GDP contraction",
        ],
        # NOTE: PXD (Pioneer Natural Resources) removed — acquired by ExxonMobil,
        # deal closed 2024-05-03, ticker delisted. Verified via ExxonMobil's own
        # press release before removing rather than guessing it still trades.
        "relevant_tickers": ["XOM", "CVX", "OXY", "COP", "XLE", "HAL", "SLB", "BKR"],
        "category": "macro",
        "color": "#5D4037",
        "source_url": "https://www.eia.gov/petroleum/",
    },

    "food_cpi": {
        "name": "CPI: Food at Home (USDA Proxy)",
        "tier": 2,
        "pcs": 7,
        "source": "fred",
        "series_id": "CPIUFDSL",
        "frequency": "monthly",
        "lag_weeks": 8,
        "inverse": True,
        "unit": "Index (1982-84=100)",
        "description": "CPI for food purchased at home. Proxies for agricultural supply pressure feeding through to grocery margins. Rising food CPI = bearish for food-cost-exposed stocks.",
        "causal_mechanism": "Food CPI reflects crop supply disruptions 8–12 weeks after they occur in USDA data. Leads grocery chain margin compression.",
        "documented_cases": [
            "2021 food CPI acceleration preceded Kroger, Albertsons margin guidance cuts by 6–8 weeks",
            "2012 corn drought: crop ratings fell before food CPI reflected supply destruction",
        ],
        "relevant_tickers": ["KR", "ACI", "SJM", "CAG", "ADM", "BG", "MOS", "NTR"],
        "category": "macro",
        "color": "#1B5E20",
        "source_url": "https://www.bls.gov/cpi/",
    },

    # ── TIER 1 — ENERGY ───────────────────────────────────────────────────────

    "crude_inventories": {
        "name": "US Crude Oil Inventories (EIA Weekly)",
        "tier": 1,
        "pcs": 8,
        "source": "eia",
        "series_id": "PET.WCESTUS1.W",  # verified live against api.eia.gov/v2/seriesid/ with real key, 2026-06-20 (bare "WCESTUS1" 404s — endpoint needs the full category-prefixed id)
        "frequency": "weekly",
        "lag_weeks": 1,
        "inverse": True,
        "unit": "Thousand Barrels",
        "description": "EIA weekly crude oil stocks excluding SPR. Inventory draws signal strong demand or supply tightness; builds signal oversupply or weak demand. The single fastest-moving oil price signal — released every Wednesday.",
        "causal_mechanism": "Crude stocks are a direct supply/demand balancing item. A draw of >3M barrels vs. expectations historically moves WTI +$1–2/bbl. Sustained draws for 4+ weeks confirm a bullish supply/demand balance.",
        "documented_cases": [
            "Consecutive 8-week draw in summer 2021 preceded WTI rally from $65 to $85/bbl",
            "Inventory builds of +5M bbls/week in Q1 2020 preceded WTI going negative in April 2020",
        ],
        "relevant_tickers": ["XOM", "CVX", "OXY", "COP", "XLE", "PSX", "VLO", "MPC"],
        "category": "energy",
        "color": "#5D4037",
        "source_url": "https://www.eia.gov/petroleum/supply/weekly/",
    },

    # NOTE: "oil_rig_count" (Baker Hughes US Oil Rig Count, series RIGSNNUS) was
    # removed entirely. RIGSNNUS does not exist on FRED, and EIA's own Drilling
    # Productivity Report documentation confirms EIA does not run an independent
    # rig survey — its rig count figure is licensed from Baker Hughes and only
    # published inside static PDF/Excel reports, never exposed as an open API
    # series. There is no free, real, API-queryable source for this signal, so
    # it was dropped rather than faked. Tickers that listed it (HAL, SLB, BKR,
    # XOM) were remapped to crude_inventories/natural_gas/dollar_index instead.

    "gas_storage": {
        "name": "US Natural Gas Storage (EIA Weekly)",
        "tier": 2,
        "pcs": 7,
        "source": "eia",
        "series_id": "NG.NW2_EPG0_SWO_R48_BCF.W",  # Lower-48 weekly working gas, verified live against api.eia.gov/v2/seriesid/ with real key, 2026-06-20
        "frequency": "weekly",
        "lag_weeks": 2,
        "inverse": True,
        "unit": "Billion Cubic Feet",
        "description": "EIA weekly working natural gas in underground storage. Below 5-year average signals supply tightness; well above average signals oversupply. Critical for gas price forecasting — storage deficits drive winter gas price spikes.",
        "causal_mechanism": "Gas storage vs. 5-year average is the primary determinant of Henry Hub spot price direction. Deficits below 200 Bcf have historically produced 30–50% price spikes into winter withdrawal season.",
        "documented_cases": [
            "Gas storage deficit of -350 Bcf vs. 5yr avg in Nov 2022 preceded Henry Hub spike to $9/MMBtu",
            "Storage surplus of +500 Bcf in spring 2024 preceded gas price collapse to $1.50/MMBtu",
        ],
        # NOTE: SWN (Southwestern Energy) removed — merged with Chesapeake Energy,
        # deal closed 2024-10-01, rebranded as Expand Energy (ticker EXE on
        # NASDAQ), SWN delisted from NYSE. Verified via the merger completion
        # press release before swapping rather than guessing. EXE is now the
        # largest independent US natural gas producer — a stronger fit anyway.
        "relevant_tickers": ["EQT", "AR", "EXE", "CTRA", "RRC", "CNX", "WMB", "KMI"],
        "category": "energy",
        "color": "#B8860B",
        "source_url": "https://www.eia.gov/naturalgas/storage/dashboard/",
    },

    # ── TIER 1 — POWER & NUCLEAR ───────────────────────────────────────────────

    "natural_gas": {
        "name": "Henry Hub Natural Gas Spot",
        "tier": 1,
        "pcs": 8,
        "source": "fred",
        "series_id": "MHHNGSP",
        "frequency": "monthly",
        "lag_weeks": 3,
        "inverse": False,
        "unit": "USD per MMBtu",
        "description": "Henry Hub natural gas spot price. Key fuel for data center co-located gas turbines and grid peakers. Data centers could add 6.1 Bcf/d of US demand by 2030.",
        "causal_mechanism": "Rising gas prices signal tightening supply vs. demand from power sector. Data center buildout is locking in 20+ year gas demand in Virginia/Texas corridors.",
        "documented_cases": [
            "Natural gas spiked in 2021-2022 as LNG exports + cold weather reduced domestic supply",
            "Gas demand from power sector grew 4% in 2025 driven by AI data center load additions",
        ],
        "relevant_tickers": ["WMB", "KMI", "OKE", "ET", "EQT", "AR", "LNG", "CTRA"],
        "category": "ai_infrastructure",
        "color": "#B8860B",
        "source_url": "https://www.eia.gov/naturalgas/",
    },

    "uranium_proxy": {
        "name": "Uranium Market (URA ETF Proxy)",
        "tier": 1,
        "pcs": 8,
        "source": "yfinance",
        "series_id": "URA",
        "frequency": "daily",
        "lag_weeks": 8,
        "inverse": False,
        "unit": "USD (ETF Price)",
        "description": "Global X Uranium ETF — proxy for uranium spot price (U₃O₈). Spot hit $99/lb in Jan 2026 (17-month high). SWU enrichment capacity is now the binding constraint in Western nuclear fuel supply.",
        "causal_mechanism": "Rising uranium signals utility demand for nuclear fuel, which precedes reactor commitments by 12–24 months. SWU above $175/SWU historically signals accelerating reactor commitments.",
        "documented_cases": [
            "Uranium spot hit $106/lb in Feb 2024 — highest in 17 years — preceding CCJ, LEU outperformance",
            "Physical uranium funds (Sprott) began accumulating spot supply in 2021, tightening market ahead of utility contracting cycle",
        ],
        "relevant_tickers": ["CCJ", "LEU", "UEC", "UUUU", "NLR", "CEG", "VST", "SMR"],
        "category": "nuclear",
        "color": "#4A1B6B",
        "source_url": "https://www.uranium.info/",
    },

    # NOTE: enrichment_proxy (LEU+UUUU basket) and smr_sentiment (SMR+OKLO+BWXT
    # basket) were removed — both were equity-basket ETF/stock prices being used
    # to "predict" the price of the nearly-identical stocks inside them. That's
    # circular, not alternative data. Real catalysts for these tickers (NRC
    # licensing, DoE contracts) aren't captured by any free public time series
    # we have — tracked instead via real federal contract award data on the
    # Ticker Deep Dive page, which is genuine alt-data with no circularity issue.

    "nuclear_generation": {
        # NOTE: previously pointed at FRED series "NUPUGNUS", which does not
        # exist — confirmed via FRED's own search API (0 results for any
        # phrasing of "nuclear electricity net generation") on 2026-06-20.
        # Replaced with the Federal Reserve's G.17 Industrial Production index
        # for the nuclear electric power utility subsector (NAICS 221113) —
        # a real, currently-updating FRED series, verified live through
        # 2026-03-01 as of this fix. It's an output-volume INDEX (2017=100),
        # not raw generation in watt-hours like the EIA data this was meant to
        # track, but it moves with the same underlying nuclear output.
        "name": "Industrial Production: Nuclear Electric Power (Fed G.17)",
        "tier": 2,
        "pcs": 6,
        "source": "fred",
        "series_id": "IPN221113S",
        "frequency": "monthly",
        "lag_weeks": 8,
        "inverse": False,
        "unit": "Index (2017=100)",
        "description": "Federal Reserve G.17 Industrial Production index for the nuclear electric power utility subsector (NAICS 221113). Capacity factor proxy — sustained high output means the fleet is running near full capacity, tightening uranium demand. Declining = outages or early closures reducing fuel demand.",
        "causal_mechanism": "US nuclear fleet runs at ~93% capacity factor when all units are online. Upticks in this output index signal new plant startups (Vogtle Unit 4, Palisades restart). Sustained output confirms uranium fuel consumption pace.",
        "documented_cases": [
            "Vogtle Unit 3 commercial operation (Jul 2023) added ~1,100 MW, increasing annual uranium demand by ~500K lbs U3O8",
            "Nuclear capacity factors rose to record 92.7% in 2023, signaling maximum fuel consumption rates",
        ],
        "relevant_tickers": ["CCJ", "LEU", "UUUU", "CEG", "EXC", "D", "SO", "DUK"],
        "category": "nuclear",
        "color": "#4A1B6B",
        "source_url": "https://fred.stlouisfed.org/series/IPN221113S",
    },

    "power_demand_growth": {
        # NOTE: previously pointed at FRED series "USEPUOUT", which does not
        # exist — confirmed via FRED's search API on 2026-06-20. Replaced with
        # the Fed's G.17 Industrial Production index for the entire electric
        # power generation/transmission/distribution utility sector (NAICS
        # 2211) — real, verified live through 2026-05-01.
        "name": "Industrial Production: Electric Power Utilities (Fed G.17)",
        "tier": 1,
        "pcs": 7,
        "source": "fred",
        "series_id": "IPG2211S",
        "frequency": "monthly",
        "lag_weeks": 6,
        "inverse": False,
        "unit": "Index (2017=100)",
        "description": "Federal Reserve G.17 Industrial Production index for the electric power generation, transmission, and distribution utility sector (NAICS 2211). The top-level demand signal for the power sector supercycle thesis. Data center additions (AI) are visible as deviations above the seasonal trend.",
        "causal_mechanism": "US electricity demand was flat for 15 years. AI data centers are breaking the trend: NERC projects 122 GW of new load by 2028. Sustained above-trend output in this index confirms grid buildout acceleration.",
        "documented_cases": [
            "Electricity demand growth turned positive in 2024 for first time since 2007 — driven by AI and manufacturing reshoring",
            "PJM (Mid-Atlantic grid) revised 5-year demand forecast up 40% in 2024 due to data center additions in Virginia",
        ],
        "relevant_tickers": ["CEG", "VST", "NEE", "AES", "ETN", "VRT", "PWR", "FCX", "CCJ"],
        "category": "nuclear",
        "color": "#1C2B4A",
        "source_url": "https://www.eia.gov/electricity/",
    },

    "copper": {
        "name": "Copper Futures (COMEX HG)",
        "tier": 1,
        "pcs": 8,
        "source": "yfinance",
        "series_id": "HG=F",
        "frequency": "daily",
        "lag_weeks": 4,
        "inverse": False,
        "unit": "USD per Pound",
        "description": "COMEX copper futures. The single most important material input for grid buildout, data centers, and electrification. Grid modernization has overtaken EVs as copper's primary demand engine (June 2026). Structural supply deficit projected starting 2026.",
        "causal_mechanism": "Every MW of new power infrastructure requires copper. AI data centers projected to drive 400K tonnes of additional annual demand, peaking ~572K tonnes in 2028. LME stocks below 200K tonnes = physical tightness.",
        "documented_cases": [
            "Copper surged from $3.50 to $5.00/lb in 2021 preceding grid investment acceleration",
            "COMEX copper in backwardation (Jun 2024) confirmed physical tightness ahead of data center buildout",
        ],
        "relevant_tickers": ["FCX", "SCCO", "COPX", "TECK", "BHP", "SBSW", "CAT"],
        "category": "ai_infrastructure",
        "color": "#B34700",
        "source_url": "https://www.lme.com/Metals/Non-ferrous/LME-Copper",
    },

    # ── TIER 1 — MARKET STRESS SIGNALS ────────────────────────────────────────

    "vix": {
        "name": "CBOE Volatility Index (VIX)",
        "tier": 1,
        "pcs": 8,
        "source": "yfinance",
        "series_id": "^VIX",
        "frequency": "daily",
        "lag_weeks": 2,
        "inverse": True,
        "unit": "Index",
        "description": "The 'fear gauge' — measures implied 30-day volatility of S&P 500 options. VIX >30 = elevated fear. VIX >40 = crisis level. Sustained low VIX = complacency risk.",
        "causal_mechanism": "VIX spikes precede forced deleveraging by hedge funds. High VIX = risk-off regime. Contrarian: VIX >40 often marks capitulation lows.",
        "documented_cases": [
            "VIX hit 66 in March 2020 — peak marked a generational buying opportunity within 3 days",
            "VIX above 30 for 6 consecutive months in 2022 corresponded with growth stock bear market",
        ],
        "relevant_tickers": ["SPY", "QQQ", "IWM", "XLF", "VIXY", "UVXY"],
        "category": "macro",
        "color": "#7B1010",
        "source_url": "https://finance.yahoo.com/quote/%5EVIX",
    },

    "dollar_index": {
        "name": "US Dollar Index (DXY)",
        "tier": 2,
        "pcs": 7,
        "source": "yfinance",
        "series_id": "DX-Y.NYB",
        "frequency": "daily",
        "lag_weeks": 4,
        "inverse": True,
        "unit": "Index",
        "description": "Value of USD vs. basket of 6 major currencies. Strong dollar = bearish for commodities, EM stocks, and US multinationals. Weak dollar = bullish for gold, copper, oil.",
        "causal_mechanism": "Dollar is the global reserve currency for commodity pricing. DXY up → commodity prices down in USD terms. Dollar strength also compresses multinational earnings when repatriated.",
        "documented_cases": [
            "DXY rallied from 95 to 114 in 2022 — commodity ETFs (DJP) fell 15% despite high underlying prices",
            "DXY weakness in 2020–2021 (from 103 to 90) coincided with copper/gold supercycle highs",
        ],
        "relevant_tickers": ["GLD", "GOLD", "FCX", "SCCO", "EEM", "EFA", "XOM", "CVX"],
        "category": "macro",
        "color": "#0D4F5C",
        "source_url": "https://finance.yahoo.com/quote/DX-Y.NYB",
    },

    "ten_year_yield": {
        "name": "10-Year Treasury Yield",
        "tier": 1,
        "pcs": 8,
        "source": "yfinance",
        "series_id": "^TNX",
        "frequency": "daily",
        "lag_weeks": 3,
        "inverse": True,
        "unit": "Percent",
        "description": "10-year US Treasury yield. Rising rates = headwind for growth stocks, real estate, and rate-sensitive sectors. Falling rates = tailwind for utilities, REITs, long-duration assets.",
        "causal_mechanism": "Discount rate for all equity valuations. When 10Y rises above ~4.5%, growth stock multiples compress because risk-free rate competes with equity risk premium.",
        "documented_cases": [
            "10Y rose from 1.5% to 4.0% in 2022 — QQQ/ARKK fell 30–60%; utilities initially fell then outperformed",
            "10Y at 5%+ in Oct 2023 briefly triggered equity selloff before reversal",
        ],
        "relevant_tickers": ["TLT", "TBF", "TMF", "XLU", "VNQ", "KRE", "SPY", "QQQ"],
        "category": "macro",
        "color": "#4A1B6B",
        "source_url": "https://finance.yahoo.com/quote/%5ETNX",
    },

    # ── TIER 2 — LIQUIDITY & CREDIT SIGNALS ──────────────────────────────────

    "m2_money_supply": {
        "name": "M2 Money Supply Growth",
        "tier": 2,
        "pcs": 8,
        "source": "fred",
        "series_id": "M2SL",
        "frequency": "monthly",
        "lag_weeks": 12,
        "inverse": False,
        "unit": "Billions USD",
        "description": "US M2 money supply (cash + checking + savings + money markets). When M2 grows rapidly, excess liquidity flows into risk assets. When M2 contracts, equity markets tend to follow with a 3–6 month lag.",
        "causal_mechanism": "M2 contraction was -$900B in 2022-2023 — the first YoY M2 decline since the 1930s — and corresponded with the worst bear market since 2008. Liquidity is the fuel for equity returns.",
        "documented_cases": [
            "M2 surged 26% YoY in 2020-2021 → S&P 500 +100% from COVID lows",
            "First YoY M2 decline since 1930s in 2022 preceded and accompanied -20% S&P drawdown",
        ],
        "relevant_tickers": ["SPY", "QQQ", "GLD", "BTC-USD", "IWM", "XLF"],
        "category": "macro",
        "color": "#1C2B4A",
        "source_url": "https://fred.stlouisfed.org/series/M2SL",
    },

    "ig_credit": {
        "name": "Investment Grade Credit (LQD ETF)",
        "tier": 2,
        "pcs": 7,
        "source": "yfinance",
        "series_id": "LQD",
        "frequency": "daily",
        "lag_weeks": 3,
        "inverse": False,
        "unit": "Price",
        "description": "iShares iBoxx Investment Grade Corporate Bond ETF. Broader credit conditions signal than HY; IG deterioration affects a larger swath of corporate America. IG spreads widening = systemic credit stress.",
        "causal_mechanism": "Investment-grade bonds are held by pension funds and insurance companies. IG spread widening shows institutional risk appetite is falling — a leading indicator for equity multiple compression.",
        "documented_cases": [
            "LQD fell 25% in 2022 as IG spreads widened with rate hikes — preceded industrials/financials selloff",
            "IG spreads at March 2020 lows bottomed same week as equity markets, confirming Fed backstop",
        ],
        "relevant_tickers": ["XLF", "KRE", "SPY", "IWM", "HYG", "TLT"],
        "category": "macro",
        "color": "#1C2B4A",
        "source_url": "https://finance.yahoo.com/quote/LQD",
    },

    "lumber_futures": {
        "name": "Lumber Futures (Housing Proxy)",
        "tier": 2,
        "pcs": 7,
        "source": "yfinance",
        "series_id": "LBR=F",  # was "LBS=F" — verified dead/frozen on a May-2023 contract (CME's
        # old lumber futures symbol; the contract was redesigned). LBR=F is the current generic
        # front-month symbol, verified live 2026-06-21 (showing Jul-2026 contract, updating same-day).
        "frequency": "daily",
        "lag_weeks": 8,
        "inverse": False,
        "unit": "USD per MBF",
        "description": "CME lumber futures. One of the most visceral leading indicators for US housing and construction activity. Lumber demand tracks new home starts with a 2-month lead. Also tracks DIY/home improvement spending.",
        "causal_mechanism": "Builders and contractors buy lumber 6–8 weeks before construction starts. Rising prices → home builders are increasing production. Crashing lumber signals housing bust before permit data confirms it.",
        "documented_cases": [
            "Lumber surged 400% May 2020–May 2021, preceding a massive housing boom and Home Depot/Lowe's earnings beats",
            "Lumber collapsed 70% in 2022, leading homebuilder stocks lower by 3–4 months",
        ],
        "relevant_tickers": ["DHI", "LEN", "PHM", "TOL", "ITB", "HD", "LOW"],
        "category": "macro",
        "color": "#5D4037",
        "source_url": "https://finance.yahoo.com/quote/LBS%3DF",
    },

    "retail_gasoline": {
        "name": "US Retail Gasoline Price",
        "tier": 2,
        "pcs": 6,
        "source": "fred",
        "series_id": "GASREGCOVW",
        "frequency": "weekly",
        "lag_weeks": 4,
        "inverse": True,
        "unit": "Dollars per Gallon",
        "description": "Average US retail price of regular grade gasoline. Acts as a direct consumer income tax. Each +10¢/gallon costs US consumers ~$14B/year. High gas prices divert spending from discretionary goods.",
        "causal_mechanism": "Gas price spikes directly reduce consumer discretionary spending within 4–6 weeks. Disproportionate impact on lower-income households who spend larger % of income on gas.",
        "documented_cases": [
            "Gas at $5/gallon in June 2022 coincided with -21% XLY drawdown vs -13% XLP",
            "Gas price collapse in 2015-2016 boosted consumer confidence and drove retail spending rebound",
        ],
        "relevant_tickers": ["XLY", "AMZN", "TGT", "WMT", "MCD", "XOM", "CVX"],
        "category": "energy",
        "color": "#5D4037",
        "source_url": "https://fred.stlouisfed.org/series/GASREGCOVW",
    },

    # NOTE: "consumer_confidence" (FRED series CSCICP03USM665S, OECD Composite
    # Consumer Confidence for the US) was removed. The series ID is technically
    # valid, but verified via FRED's API on 2026-06-20 that OECD stopped
    # updating it — last observation 2024-01-01, last_updated 2025-11-17,
    # "Next Release Date: Not Available". A signal frozen for 2+ years can't
    # produce a meaningful current reading. consumer_sentiment (UMCSENT,
    # University of Michigan, updates monthly and is live) already covers the
    # same concept, so this wasn't worth chasing a replacement for.

    # ── TIER 2 — AI INFRASTRUCTURE ────────────────────────────────────────────

    "hyperscaler_capex": {
        "name": "Hyperscaler CapEx (MSFT+AMZN+GOOGL+META)",
        "tier": 2,
        "pcs": 8,
        "source": "yfinance_multi",
        "series_ids": ["MSFT", "AMZN", "GOOGL", "META"],
        "frequency": "quarterly",
        "lag_weeks": 26,
        "inverse": False,
        "unit": "Composite Index",
        "description": "Composite index of trailing capital expenditure from the four major hyperscalers. Data center electricity consumption surged 50% in 2025. AI-focused data centers consuming power at 2.94x overall data center growth rate.",
        "causal_mechanism": "Hyperscaler capex is the cleanest demand signal for power infrastructure. Filing-to-delivery lag is 2–5 years — today's announcements forecast 2027–2030 power demand.",
        "documented_cases": [
            "Microsoft $80B data center capex commitment (Jan 2025) preceded utility stock outperformance in PJM territory by 3–6 months",
            "Amazon $75B+ infrastructure commitment drove transformer and grid equipment order backlogs to 2–3 years",
        ],
        "relevant_tickers": ["NVDA", "AMD", "SMCI", "DELL", "VRT", "ETN", "PWR", "EQIX", "DLR"],
        "category": "ai_infrastructure",
        "color": "#1C2B4A",
        "source_url": "https://www.sec.gov/cgi-bin/browse-edgar",
    },

    "semiconductor_etf": {
        "name": "SOXX Semiconductor ETF",
        "tier": 2,
        "pcs": 7,
        "source": "yfinance",
        "series_id": "SOXX",
        "frequency": "daily",
        "lag_weeks": 8,
        "inverse": False,
        "unit": "USD (ETF Price)",
        "description": "iShares Semiconductor ETF. Semiconductors lead the tech cycle by 2–3 quarters. SOXX is a proxy for the global AI infrastructure build.",
        "causal_mechanism": "Semiconductor cycle historically leads broad tech earnings by 6–9 months. SOXX book-to-bill ratio above 1.1 signals accelerating orders.",
        "documented_cases": [
            "SOXX bottomed Nov 2022, 5 months before QQQ bottomed (Jan 2023) — confirmed the semiconductor leading indicator thesis",
            "SOXX rally in H2 2023 preceded AI infrastructure earnings upgrades across the supply chain",
        ],
        "relevant_tickers": ["NVDA", "AMD", "AVGO", "AMAT", "LRCX", "KLAC", "MRVL", "SMCI"],
        "category": "ai_infrastructure",
        "color": "#B8860B",
        "source_url": "https://finance.yahoo.com/quote/SOXX",
    },

    "shipping_index": {
        "name": "Breakwave Dry Bulk Shipping ETF (BDRY)",
        "tier": 3,
        "pcs": 6,
        "source": "yfinance",
        "series_id": "BDRY",
        "frequency": "daily",
        "lag_weeks": 6,
        "inverse": False,
        "unit": "USD (ETF Price)",
        "description": "Proxy for Baltic Dry Index — shipping rates for iron ore, grain, and coal. Leading indicator for global industrial demand and commodity flows.",
        "causal_mechanism": "Shipping rates are set daily in a spot market. They reflect physical trade flows 4–6 weeks before official trade data is published.",
        "documented_cases": [
            "Baltic Dry Index collapsed 90% in 2008 before official GDP data showed global trade contraction",
            "Shipping rates spiked 500% in 2021 — signaled supply chain disruption before consumer goods inflation peaked",
        ],
        "relevant_tickers": ["CAT", "DE", "FCX", "VALE", "BHP", "CLF", "NUE", "XLI"],
        "category": "macro",
        "color": "#5D4037",
        "source_url": "https://finance.yahoo.com/quote/BDRY",
    },

    # ── TIER 2 — QUANTUM ─────────────────────────────────────────────────────

    # NOTE: quantum_proxy (IONQ+RGTI+QBTS equity basket) was removed — it was an
    # equity basket "predicting" the same stocks inside it. Replaced below with
    # arXiv paper publication velocity, which is genuine non-price alternative
    # data: real research output counts, not a relabeled stock chart.

    "quantum_arxiv_velocity": {
        "name": "Quantum Computing arXiv Paper Velocity",
        "tier": 2,
        "pcs": 5,
        "source": "arxiv",
        "series_id": "qubit error correction fault tolerant quantum computing",
        "frequency": "weekly",
        "lag_weeks": 4,
        "inverse": False,
        "unit": "Papers per Week",
        "description": "Weekly count of arXiv quant-ph preprints on qubit error correction and fault-tolerant quantum computing. This is genuine alternative data — actual research output, not a stock price — though it is a thin, unbacktested signal with a short documented track record. PCS is intentionally low until enough history accumulates to test it properly.",
        "causal_mechanism": "Peer-reviewed papers from Google Quantum AI, IBM Research, and Microsoft Station Q appear on arXiv 2–6 weeks before press releases. A sustained spike in publication velocity from major labs has, in a small number of observed cases, preceded institutional rotation into quantum stocks.",
        "documented_cases": [
            "Google's Willow chip paper (Dec 2024) on below-threshold error correction preceded a quantum-stock rotation within weeks of the preprint appearing",
            "This is a single-digit number of documented cases — treat the causal claim as a hypothesis being tracked, not an established pattern",
        ],
        "relevant_tickers": ["IONQ", "RGTI", "QBTS", "IBM", "MSFT", "GOOGL"],
        "category": "macro",
        "color": "#4A1B6B",
        "source_url": "https://arxiv.org/list/quant-ph/recent",
    },

    # ── TIER 1-2 — FINANCIALS, HEALTHCARE, CONSUMER, INDUSTRIALS ──────────────
    # Added to close out sector coverage gaps flagged in a credibility review:
    # the signal library was almost entirely macro/energy/nuclear/AI before
    # this. Two of these (SLOOS, FDA approval velocity) are genuine alt-data
    # differentiators — real datasets institutional credit/healthcare analysts
    # use that essentially no retail dashboard surfaces. The other three are
    # solid, verified, real FRED series rather than novel alt-data, and are
    # labeled that way rather than oversold.

    "bank_lending_standards": {
        "name": "Senior Loan Officer Survey — C&I Lending Standards",
        "tier": 1,
        "pcs": 8,
        "source": "fred",
        "series_id": "DRTSCILM",
        "frequency": "quarterly",
        "lag_weeks": 8,
        "inverse": True,
        "unit": "Net % of Banks Tightening",
        "description": "Net percentage of domestic banks reporting tighter standards on C&I loans to large/middle-market firms, from the Fed's quarterly Senior Loan Officer Opinion Survey (SLOOS). INVERSE: rising tightening = bearish for credit-sensitive equities. This is the genuine alt-data differentiator for financials — credit desks watch SLOOS closely; it almost never appears on retail-facing platforms because it's quarterly and easy to overlook, not because it isn't predictive.",
        "causal_mechanism": "Banks tighten lending standards 1-3 quarters before loan growth actually slows, because underwriting changes affect new originations before they affect outstanding balances. A sharp SLOOS tightening reading has historically preceded recessions and regional-bank credit stress by 2-4 quarters.",
        "documented_cases": [
            "SLOOS tightening spiked to ~45% in Q1 2023 — preceded the regional bank stress visible later that spring (SVB, Signature, First Republic)",
            "SLOOS tightening exceeded 60% in Q4 2008 — coincided with the sharpest phase of the financial crisis credit crunch",
        ],
        "relevant_tickers": ["JPM", "BAC", "WFC", "C", "KRE", "GS"],
        "category": "financials",
        "color": "#2E5266",
        "source_url": "https://www.federalreserve.gov/data/sloos.htm",
    },

    "credit_card_delinquency": {
        "name": "Credit Card Delinquency Rate (All Commercial Banks)",
        "tier": 2,
        "pcs": 7,
        "source": "fred",
        "series_id": "DRCCLACBS",
        "frequency": "quarterly",
        "lag_weeks": 4,
        "inverse": True,
        "unit": "Percent",
        "description": "Quarterly delinquency rate on credit card loans across all commercial banks. INVERSE: rising delinquencies = consumer credit stress = bearish for card issuers and consumer discretionary names.",
        "causal_mechanism": "Delinquency rates are a coincident-to-slightly-leading read on consumer financial health — they tend to inflect before charge-off rates and issuer earnings guidance catch up, since issuers build loss reserves ahead of recognizing actual charge-offs.",
        "documented_cases": [
            "Card delinquencies bottomed near 1.5% in 2021 (stimulus-driven) and have risen steadily back toward pre-pandemic norms — issuers built reserves ahead of this in 2022-2023 guidance",
        ],
        "relevant_tickers": ["COF", "SYF", "AXP", "JPM", "BAC"],
        "category": "financials",
        "color": "#2E5266",
        "source_url": "https://fred.stlouisfed.org/series/DRCCLACBS",
    },

    "fda_approval_velocity": {
        "name": "FDA Drug Approval Velocity (openFDA)",
        "tier": 1,
        "pcs": 6,
        "source": "fda",
        "series_id": "drugsfda_AP_velocity",
        "frequency": "weekly",
        "lag_weeks": 4,
        "inverse": False,
        "unit": "Approvals per Week",
        "description": "Weekly count of FDA drug application approvals (NDA/ANDA/BLA) pulled live from openFDA's free, keyless drugsfda endpoint. This is the genuine alt-data differentiator for healthcare: regulatory tailwind/headwind across the industry, sourced the same way analysts manually track FDA press releases, but live and aggregated instead. PCS is moderate, not high — this is industry-wide approval cadence, not a single company's pipeline, so the read-through to any one stock is noisier than a company-specific catalyst.",
        "causal_mechanism": "Aggregate approval velocity reflects FDA throughput and regulatory posture — a slowdown (e.g. during a government shutdown or leadership transition) creates industry-wide pipeline delay risk; a pickup signals smoother regulatory conditions for the whole sector's news flow.",
        "documented_cases": [
            "FDA approval throughput slowed measurably during the 2018-2019 government shutdown, delaying several pending biotech catalysts industry-wide",
        ],
        "relevant_tickers": ["LLY", "NVO", "REGN", "VRTX", "PFE", "MRK", "BMY", "GILD", "AMGN", "XBI"],
        "category": "healthcare",
        "color": "#6B2E5F",
        "source_url": "https://open.fda.gov/apis/drug/drugsfda/",
    },

    "retail_job_openings": {
        "name": "Job Openings: Retail Trade",
        "tier": 2,
        "pcs": 6,
        "source": "fred",
        "series_id": "JTS4400JOL",
        "frequency": "monthly",
        "lag_weeks": 6,
        "inverse": False,
        "unit": "Thousands of Openings",
        "description": "Monthly job openings specifically within the retail trade sector (JOLTS, sector-level). A sector-specific labor-demand read rather than the headline aggregate jobs number most platforms show — retailers ramp hiring ahead of demand they're forecasting, so this is a real-time read on retailer confidence, especially ahead of peak seasons.",
        "causal_mechanism": "Retailers post seasonal and structural openings ahead of realized demand; a pullback in retail-sector openings has historically preceded softer same-store-sales guidance by one to two quarters.",
        "documented_cases": [
            "Retail job openings declined sharply through 2022-2023 as retailers pulled back hiring ahead of a slower consumer spending environment",
        ],
        "relevant_tickers": ["WMT", "TGT", "COST", "HD", "LOW", "AMZN"],
        "category": "consumer",
        "color": "#8B5E34",
        "source_url": "https://fred.stlouisfed.org/series/JTS4400JOL",
    },

    "ecommerce_share": {
        "name": "E-Commerce Share of Total Retail Sales",
        "tier": 2,
        "pcs": 5,
        "source": "fred",
        "series_id": "ECOMPCTSA",
        "frequency": "quarterly",
        "lag_weeks": 8,
        "inverse": False,
        "unit": "Percent of Total Sales",
        "description": "E-commerce sales as a percentage of total US retail sales. A structural-trend signal, not a tactical one — useful for the multi-year online-vs-brick-and-mortar share shift rather than short-term trading. Labeled as a standard FRED series, not alternative data, to avoid overselling it.",
        "causal_mechanism": "A sustained rise in e-commerce share is a structural headwind for physical-footprint retailers and a tailwind for online-native and logistics-heavy names; the relationship plays out over years, not weeks.",
        "documented_cases": [
            "E-commerce share jumped from ~11% to ~16% during 2020 pandemic lockdowns, then partially normalized — large-format physical retailers underperformed online-native peers through that shift",
        ],
        "relevant_tickers": ["AMZN", "SHOP", "EBAY", "WMT", "TGT"],
        "category": "consumer",
        "color": "#8B5E34",
        "source_url": "https://fred.stlouisfed.org/series/ECOMPCTSA",
    },

    "construction_spending": {
        "name": "Total US Construction Spending",
        "tier": 2,
        "pcs": 6,
        "source": "fred",
        "series_id": "TTLCONS",
        "frequency": "monthly",
        "lag_weeks": 8,
        "inverse": False,
        "unit": "Millions of USD (SAAR)",
        "description": "Total monthly US construction spending (Census Bureau, seasonally adjusted annual rate), covering residential, nonresidential, and public construction combined. A broad industrials-sector demand gauge for materials, equipment rental, and heavy-construction names.",
        "causal_mechanism": "Construction spending reflects committed project starts; equipment and materials demand (cement, aggregates, rental fleets) tracks it with a short lag as projects move from permitting into active build phases.",
        "documented_cases": [
            "Construction spending growth decelerated through 2023 as higher financing costs slowed nonresidential project starts, weighing on materials and equipment-rental names with a one-to-two-quarter lag",
        ],
        "relevant_tickers": ["CAT", "DE", "HON", "MMM", "VMC", "MLM", "URI"],
        "category": "industrials",
        "color": "#3D4F2E",
        "source_url": "https://fred.stlouisfed.org/series/TTLCONS",
    },

    # ── Social & Sentiment Signals ────────────────────────────────────────────
    "retail_fear_gauge": {
        "name": "Retail Fear Index (Google Trends)",
        "tier": 2,
        "pcs": 5,
        "source": "google_trends",
        "series_id": "market crash,recession,stock market crash",
        "frequency": "weekly",
        "lag_weeks": 0,
        "inverse": False,
        "unit": "Search Interest (0-100, relative)",
        "description": (
            "Weekly Google Trends search intensity for 'market crash', 'recession', and "
            "'stock market crash' in the US — a real-time retail fear gauge. Used as a "
            "CONTRARIAN signal: spikes in fear searches have historically coincided with "
            "short-term market bottoms rather than tops, because retail investors tend to "
            "search frantically during selling climaxes. Low fear = complacency = mild "
            "bearish lean. PCS is deliberately modest — Google Trends can reflect "
            "media-driven panic that doesn't correspond to actual price turns, and the "
            "series is only 90 days deep per pull, limiting historical validation."
        ),
        "causal_mechanism": (
            "Retail search panic tends to cluster at capitulation moments — when "
            "unsophisticated investors are most frightened, institutional buyers are often "
            "accumulating. The contrarian read is structural: retail sells into fear, "
            "institutions buy. High fear → more supply absorbed → price floor. "
            "Note: this is a sentiment-momentum signal, not a fundamental one."
        ),
        "documented_cases": [
            "Google Trends 'stock market crash' searches spiked in March 2020 within days "
            "of the pandemic low — the S&P 500 bottomed while search volume peaked",
            "Similar fear-search spikes occurred in Oct 2022 (near the bear-market low) "
            "and Aug 2024 (yen carry-trade unwind — brief but sharp)",
        ],
        "relevant_tickers": ["SPY", "QQQ", "IWM", "VIX"],
        "category": "macro",
        "color": "#7B5EA7",
        "source_url": "https://trends.google.com/trends/",
    },

    "fedspeaks_hawkishness": {
        "name": "Fed Policy Hawkishness (FOMC AI Score)",
        "tier": 1,
        "pcs": 7,
        "source": "fedspeaks",
        "series_id": "fomc_hawkishness",
        "frequency": "monthly",
        "lag_weeks": 0,
        "inverse": True,
        "unit": "Hawkishness Score (0=Dovish, 100=Very Hawkish)",
        "description": (
            "AI-scored hawkishness of the most recent FOMC monetary policy statement, "
            "fetched from federalreserve.gov and analyzed by Claude Haiku. Scored 0-100 "
            "where 0 = maximally dovish (rate cuts, accommodation language) and 100 = "
            "maximally hawkish (rate hike bias, inflation focus, restrictive language). "
            "Inverse signal: high hawkishness = bearish for equities (rising rates compress "
            "multiples). Updates after each FOMC meeting (~8×/year). PCS is intentionally "
            "higher than the social sentiment signals because Fed policy is the single most "
            "studied equity-return predictor at 0-6 month horizons."
        ),
        "causal_mechanism": (
            "Fed rate policy directly affects the discount rate used in equity valuation. "
            "Hawkish language reliably forecasts higher short-term rates, which (1) compress "
            "PE multiples via the Gordon Growth Model, (2) increase the cost of corporate "
            "debt, and (3) strengthen the dollar which weighs on multinational earnings. "
            "The language itself is leading because the Fed often signals intentions before "
            "acting — markets price the signal, not just the rate move."
        ),
        "documented_cases": [
            "FOMC statements in late 2021 shifted from 'transitory' inflation language to "
            "explicit rate-hike intent 3-4 months before the first hike — equities peaked "
            "Jan 2022 as the language hardened",
            "The July 2023 statement's 'data dependent' softening preceded the rate pause "
            "that coincided with the 2H 2023 equity rally",
            "March 2024 statement dropped 'further policy firming' language; equities "
            "continued rallying through the year as rate-cut expectations solidified",
        ],
        "relevant_tickers": ["SPY", "QQQ", "TLT", "GLD", "JPM", "BAC", "GS"],
        "category": "macro",
        "color": "#1A3A5C",
        "source_url": "https://www.federalreserve.gov/newsevents/pressreleases.htm",
    },

    # NOTE: lithium_battery_proxy (LIT), rare_earth_proxy (REMX),
    # defense_aerospace_proxy (ITA), biotech_innovation_proxy (XBI),
    # cybersecurity_proxy (CIBR), robotics_automation_proxy (BOTZ), and
    # water_infrastructure_proxy (PHO) were all removed. Each was an equity
    # ETF price being used to "predict" the price of its own near-identical
    # holdings (e.g. ITA's price predicting LMT/RTX/NOC/GD/LHX, which ARE
    # ITA's top holdings) — that's circular, not alternative data, no matter
    # how good the underlying 20-year thematic story is. The tickers below
    # are kept and instead mapped to real macro signals (copper, dollar
    # index, ISM PMI, yield, credit spreads, hyperscaler capex) that have
    # genuine, testable causal mechanisms independent of the ticker's own
    # price. See TICKERS below for the remapped signal lists.
}

# ─────────────────────────────────────────────────────────────────────────────
# TICKER CONFIGURATIONS
# Maps tickers to their relevant signals + metadata
# ─────────────────────────────────────────────────────────────────────────────

TICKERS = {

    # ── BROAD MARKET / ETFs ────────────────────────────────────────────────────
    "SPY":  {"name": "SPDR S&P 500 ETF Trust",               "sector": "ETF",               "signals": ["ata_trucking", "jobless_claims", "crude_oil", "layoffs_rate", "hy_spread", "yield_curve"], "theme": "macro"},
    "QQQ":  {"name": "Invesco QQQ Trust (Nasdaq-100)",        "sector": "ETF",               "signals": ["jobless_claims", "hyperscaler_capex", "ten_year_yield"],                                  "theme": "macro"},
    "IWM":  {"name": "iShares Russell 2000 ETF",             "sector": "ETF",               "signals": ["jobless_claims", "hy_spread", "ism_pmi"],                                                 "theme": "macro"},
    "XLI":  {"name": "Industrial Select Sector SPDR",        "sector": "ETF",               "signals": ["ata_trucking", "rail_traffic", "ism_pmi", "durable_goods"],                               "theme": "macro"},
    "XLE":  {"name": "Energy Select Sector SPDR",            "sector": "ETF",               "signals": ["crude_oil", "natural_gas"],                                                                "theme": "macro"},
    "XLY":  {"name": "Consumer Discretionary SPDR",          "sector": "ETF",               "signals": ["jobless_claims", "ata_trucking", "layoffs_rate", "consumer_sentiment", "retail_sales"],   "theme": "macro"},
    "XLP":  {"name": "Consumer Staples SPDR",                "sector": "ETF",               "signals": ["jobless_claims", "food_cpi"],                                                              "theme": "macro"},
    "XLF":  {"name": "Financial Select Sector SPDR",         "sector": "ETF",               "signals": ["yield_curve", "hy_spread", "ten_year_yield"],                                             "theme": "macro"},
    "XLU":  {"name": "Utilities Select Sector SPDR",         "sector": "ETF",               "signals": ["ten_year_yield", "natural_gas", "uranium_proxy"],                                         "theme": "nuclear"},
    "HYG":  {"name": "iShares iBoxx High Yield ETF",         "sector": "ETF",               "signals": ["hy_spread", "vix"],                                                                       "theme": "macro"},
    "TLT":  {"name": "iShares 20+ Year Treasury ETF",        "sector": "ETF",               "signals": ["ten_year_yield", "yield_curve"],                                                          "theme": "macro"},
    "GLD":  {"name": "SPDR Gold Shares ETF",                 "sector": "ETF",               "signals": ["dollar_index", "vix", "ten_year_yield"],                                                  "theme": "macro"},

    # ── RAILROADS ──────────────────────────────────────────────────────────────
    "UNP":  {"name": "Union Pacific Corporation",            "sector": "Transportation",    "signals": ["rail_traffic", "crude_oil", "ata_trucking", "ism_pmi"],                                   "theme": "macro"},
    "CSX":  {"name": "CSX Corporation",                      "sector": "Transportation",    "signals": ["rail_traffic", "ata_trucking", "ism_pmi", "hy_spread"],                                  "theme": "macro"},
    "NSC":  {"name": "Norfolk Southern Corporation",         "sector": "Transportation",    "signals": ["rail_traffic", "crude_oil", "ism_pmi"],                                                   "theme": "macro"},
    "CP":   {"name": "Canadian Pacific Kansas City",         "sector": "Transportation",    "signals": ["rail_traffic", "ata_trucking", "ism_pmi", "crude_oil"],                                   "theme": "macro"},
    "CNI":  {"name": "Canadian National Railway",            "sector": "Transportation",    "signals": ["rail_traffic", "ata_trucking", "ism_pmi"],                                                "theme": "macro"},

    # ── TRUCKING / LOGISTICS ───────────────────────────────────────────────────
    "ODFL": {"name": "Old Dominion Freight Line",            "sector": "Transportation",    "signals": ["ata_trucking", "ism_pmi", "crude_oil"],                                                   "theme": "macro"},
    "JBHT": {"name": "J.B. Hunt Transport Services",         "sector": "Transportation",    "signals": ["ata_trucking", "crude_oil", "ism_pmi", "rail_traffic"],                                  "theme": "macro"},
    "SAIA": {"name": "Saia Inc.",                            "sector": "Transportation",    "signals": ["ata_trucking", "ism_pmi", "hy_spread"],                                                   "theme": "macro"},
    "WERN": {"name": "Werner Enterprises",                   "sector": "Transportation",    "signals": ["ata_trucking", "crude_oil", "ism_pmi"],                                                   "theme": "macro"},
    "UPS":  {"name": "United Parcel Service",                "sector": "Transportation",    "signals": ["ata_trucking", "crude_oil", "ism_pmi", "retail_sales"],                                  "theme": "macro"},
    "FDX":  {"name": "FedEx Corporation",                    "sector": "Transportation",    "signals": ["ata_trucking", "crude_oil", "ism_pmi", "hy_spread"],                                     "theme": "macro"},

    # ── INDUSTRIAL / MANUFACTURING ─────────────────────────────────────────────
    "CAT":  {"name": "Caterpillar Inc.",                     "sector": "Industrial",        "signals": ["ism_pmi", "durable_goods", "construction_spending"],                                      "theme": "industrials"},
    "DE":   {"name": "Deere & Company",                      "sector": "Industrial",        "signals": ["ism_pmi", "food_cpi"],                                                                    "theme": "industrials"},
    "HON":  {"name": "Honeywell International",              "sector": "Industrial",        "signals": ["ism_pmi", "durable_goods", "construction_spending"],                                      "theme": "industrials"},
    "ETN":  {"name": "Eaton Corporation",                    "sector": "Power Management",  "signals": ["copper", "hyperscaler_capex", "ism_pmi"],                                                "theme": "ai_infrastructure"},
    "EMR":  {"name": "Emerson Electric",                     "sector": "Industrial",        "signals": ["ism_pmi", "durable_goods"],                                                               "theme": "macro"},
    "ROK":  {"name": "Rockwell Automation",                  "sector": "Industrial",        "signals": ["ism_pmi", "durable_goods"],                                                               "theme": "macro"},
    "ITW":  {"name": "Illinois Tool Works",                  "sector": "Industrial",        "signals": ["ism_pmi", "durable_goods"],                                                               "theme": "macro"},
    "GE":   {"name": "GE Aerospace",                         "sector": "Industrial",        "signals": ["ism_pmi", "durable_goods"],                                                               "theme": "macro"},
    "MMM":  {"name": "3M Company",                           "sector": "Industrial",        "signals": ["ism_pmi", "construction_spending"],                                                       "theme": "industrials"},

    # ── HOMEBUILDERS ───────────────────────────────────────────────────────────
    "DHI":  {"name": "D.R. Horton Inc.",                     "sector": "Homebuilders",      "signals": ["housing_starts", "ten_year_yield", "consumer_sentiment", "lumber_futures"],            "theme": "macro"},
    "LEN":  {"name": "Lennar Corporation",                   "sector": "Homebuilders",      "signals": ["housing_starts", "ten_year_yield", "lumber_futures"],                                     "theme": "macro"},
    "PHM":  {"name": "PulteGroup Inc.",                      "sector": "Homebuilders",      "signals": ["housing_starts", "consumer_sentiment", "lumber_futures"],                                 "theme": "macro"},
    "TOL":  {"name": "Toll Brothers Inc.",                   "sector": "Homebuilders",      "signals": ["housing_starts", "ten_year_yield", "lumber_futures"],                                     "theme": "macro"},
    "NVR":  {"name": "NVR Inc.",                             "sector": "Homebuilders",      "signals": ["housing_starts"],                                                                         "theme": "macro"},

    # ── CONSUMER / RETAIL ──────────────────────────────────────────────────────
    "COST": {"name": "Costco Wholesale Corporation",         "sector": "Consumer Staples",  "signals": ["consumer_sentiment", "retail_sales", "layoffs_rate", "retail_job_openings"],             "theme": "consumer"},
    "TGT":  {"name": "Target Corporation",                   "sector": "Consumer Disc.",    "signals": ["retail_sales", "consumer_sentiment", "layoffs_rate", "retail_job_openings", "ecommerce_share"], "theme": "consumer"},
    "WMT":  {"name": "Walmart Inc.",                         "sector": "Consumer Staples",  "signals": ["retail_sales", "jolts_openings", "retail_job_openings", "ecommerce_share"],              "theme": "consumer"},
    "HD":   {"name": "Home Depot Inc.",                      "sector": "Consumer Disc.",    "signals": ["housing_starts", "retail_sales", "consumer_sentiment", "lumber_futures"],             "theme": "consumer"},
    "LOW":  {"name": "Lowe's Companies Inc.",                "sector": "Consumer Disc.",    "signals": ["housing_starts", "retail_sales", "lumber_futures"],                                      "theme": "consumer"},
    "AMZN": {"name": "Amazon.com Inc.",                      "sector": "Technology",        "signals": ["retail_sales", "hyperscaler_capex", "jobless_claims", "ecommerce_share"],                "theme": "ai_infrastructure"},

    # ── FINANCIAL ─────────────────────────────────────────────────────────────
    "JPM":  {"name": "JPMorgan Chase & Co.",                 "sector": "Banking",           "signals": ["yield_curve", "hy_spread", "bank_lending_standards", "credit_card_delinquency"],          "theme": "financials"},
    "BAC":  {"name": "Bank of America Corporation",          "sector": "Banking",           "signals": ["yield_curve", "hy_spread", "bank_lending_standards", "credit_card_delinquency"],          "theme": "financials"},
    "GS":   {"name": "Goldman Sachs Group",                  "sector": "Banking",           "signals": ["vix", "hy_spread", "bank_lending_standards"],                                            "theme": "financials"},
    "KRE":  {"name": "SPDR S&P Regional Banking ETF",        "sector": "Banking ETF",       "signals": ["yield_curve", "hy_spread", "ten_year_yield", "bank_lending_standards"],                   "theme": "financials"},

    # ── ENERGY / OIL ──────────────────────────────────────────────────────────
    "XOM":  {"name": "Exxon Mobil Corporation",              "sector": "Energy",            "signals": ["crude_oil", "crude_inventories", "dollar_index", "hy_spread"],          "theme": "energy"},
    "CVX":  {"name": "Chevron Corporation",                  "sector": "Energy",            "signals": ["crude_oil", "crude_inventories", "dollar_index", "natural_gas"],                         "theme": "energy"},
    "OXY":  {"name": "Occidental Petroleum",                 "sector": "Energy",            "signals": ["crude_oil", "crude_inventories", "dollar_index", "hy_spread", "vix"],                   "theme": "energy"},
    "COP":  {"name": "ConocoPhillips",                       "sector": "Energy",            "signals": ["crude_oil", "crude_inventories", "natural_gas", "dollar_index"],                         "theme": "energy"},
    "HAL":  {"name": "Halliburton Company",                  "sector": "Oil Services",      "signals": ["crude_oil", "crude_inventories", "natural_gas", "hy_spread"],                          "theme": "energy"},
    "SLB":  {"name": "Schlumberger (SLB)",                   "sector": "Oil Services",      "signals": ["crude_oil", "crude_inventories", "natural_gas", "dollar_index"],                             "theme": "energy"},
    "BKR":  {"name": "Baker Hughes Company",                 "sector": "Oil Services",      "signals": ["crude_oil", "crude_inventories", "natural_gas", "dollar_index", "hy_spread"],                "theme": "energy"},
    "EQT":  {"name": "EQT Corporation",                      "sector": "Natural Gas E&P",   "signals": ["natural_gas", "gas_storage", "dollar_index", "hy_spread"],                               "theme": "energy"},
    "AR":   {"name": "Antero Resources Corp.",               "sector": "Natural Gas E&P",   "signals": ["natural_gas", "gas_storage", "crude_oil", "hy_spread"],                                  "theme": "energy"},
    "LNG":  {"name": "Cheniere Energy Inc.",                 "sector": "LNG Export",        "signals": ["natural_gas", "gas_storage", "dollar_index", "hy_spread"],                               "theme": "energy"},

    # ── NUCLEAR ────────────────────────────────────────────────────────────────
    "CCJ":  {"name": "Cameco Corporation",                   "sector": "Uranium Mining",    "signals": ["uranium_proxy", "nuclear_generation", "power_demand_growth", "dollar_index", "vix"], "theme": "nuclear"},
    "LEU":  {"name": "Centrus Energy Corp.",                  "sector": "Nuclear Enrichment","signals": ["uranium_proxy", "nuclear_generation", "hyperscaler_capex", "vix"],        "theme": "nuclear"},
    "UEC":  {"name": "Uranium Energy Corp.",                  "sector": "Uranium Mining",    "signals": ["uranium_proxy", "nuclear_generation", "dollar_index", "vix"],        "theme": "nuclear"},
    "UUUU": {"name": "Energy Fuels Inc.",                    "sector": "Uranium Mining",    "signals": ["uranium_proxy", "nuclear_generation", "dollar_index"],                "theme": "nuclear"},
    "URA":  {"name": "Global X Uranium ETF",                 "sector": "ETF",               "signals": ["uranium_proxy", "nuclear_generation", "power_demand_growth", "vix"],  "theme": "nuclear"},
    "NLR":  {"name": "VanEck Uranium+Nuclear Energy ETF",    "sector": "ETF",               "signals": ["uranium_proxy", "nuclear_generation", "natural_gas", "ten_year_yield"],  "theme": "nuclear"},
    "CEG":  {"name": "Constellation Energy Corporation",     "sector": "Utilities/Nuclear", "signals": ["uranium_proxy", "power_demand_growth", "nuclear_generation", "hyperscaler_capex", "ten_year_yield"], "theme": "nuclear"},
    "VST":  {"name": "Vistra Corp.",                         "sector": "Utilities",         "signals": ["uranium_proxy", "power_demand_growth", "natural_gas", "copper", "hyperscaler_capex"],     "theme": "nuclear"},
    "SMR":  {"name": "NuScale Power Corporation",            "sector": "Nuclear (SMR)",     "signals": ["uranium_proxy", "power_demand_growth", "hyperscaler_capex", "vix"],      "theme": "nuclear"},
    "OKLO": {"name": "Oklo Inc.",                            "sector": "Nuclear (SMR)",     "signals": ["uranium_proxy", "power_demand_growth", "hyperscaler_capex"],              "theme": "nuclear"},
    "BWXT": {"name": "BWX Technologies Inc.",                "sector": "Nuclear Services",  "signals": ["uranium_proxy", "nuclear_generation", "ism_pmi"],                        "theme": "nuclear"},

    # ── UTILITIES ─────────────────────────────────────────────────────────────
    "NEE":  {"name": "NextEra Energy Inc.",                  "sector": "Utilities",         "signals": ["ten_year_yield", "natural_gas", "power_demand_growth", "copper"],                         "theme": "nuclear"},
    "D":    {"name": "Dominion Energy Inc.",                 "sector": "Utilities",         "signals": ["ten_year_yield", "natural_gas", "nuclear_generation"],                                    "theme": "nuclear"},
    "EXC":  {"name": "Exelon Corporation",                   "sector": "Utilities/Nuclear", "signals": ["ten_year_yield", "uranium_proxy", "nuclear_generation", "power_demand_growth"],           "theme": "nuclear"},
    "DUK":  {"name": "Duke Energy Corporation",              "sector": "Utilities",         "signals": ["ten_year_yield", "natural_gas", "power_demand_growth"],                                   "theme": "nuclear"},
    "SO":   {"name": "Southern Company",                     "sector": "Utilities",         "signals": ["ten_year_yield", "natural_gas", "nuclear_generation"],                   "theme": "nuclear"},

    # ── AI INFRASTRUCTURE — Copper/Mining ─────────────────────────────────────
    "FCX":  {"name": "Freeport-McMoRan Inc.",                "sector": "Copper Mining",     "signals": ["copper", "dollar_index"],                                                                 "theme": "ai_infrastructure"},
    "SCCO": {"name": "Southern Copper Corporation",          "sector": "Copper Mining",     "signals": ["copper"],                                                                                 "theme": "ai_infrastructure"},
    "COPX": {"name": "Global X Copper Miners ETF",           "sector": "ETF",               "signals": ["copper"],                                                                                 "theme": "ai_infrastructure"},
    "TECK": {"name": "Teck Resources Limited",               "sector": "Diversified Mining","signals": ["copper"],                                                                                 "theme": "ai_infrastructure"},
    "BHP":  {"name": "BHP Group Limited",                    "sector": "Diversified Mining","signals": ["copper", "dollar_index"],                                                                 "theme": "ai_infrastructure"},

    # ── AI INFRASTRUCTURE — Gas Pipelines ─────────────────────────────────────
    "WMB":  {"name": "Williams Companies Inc.",              "sector": "Energy/Pipelines",  "signals": ["natural_gas"],                                                                            "theme": "ai_infrastructure"},
    "KMI":  {"name": "Kinder Morgan Inc.",                   "sector": "Energy/Pipelines",  "signals": ["natural_gas", "crude_oil"],                                                               "theme": "ai_infrastructure"},
    "OKE":  {"name": "ONEOK Inc.",                           "sector": "Energy/Pipelines",  "signals": ["natural_gas"],                                                                            "theme": "ai_infrastructure"},
    "ET":   {"name": "Energy Transfer LP",                   "sector": "Energy/Pipelines",  "signals": ["natural_gas", "crude_oil"],                                                               "theme": "ai_infrastructure"},
    "LNG":  {"name": "Cheniere Energy Inc.",                 "sector": "LNG Export",        "signals": ["natural_gas"],                                                                            "theme": "ai_infrastructure"},

    # ── AI INFRASTRUCTURE — Grid & Power ──────────────────────────────────────
    "PWR":  {"name": "Quanta Services Inc.",                 "sector": "Grid Construction", "signals": ["copper", "hyperscaler_capex"],                                                            "theme": "ai_infrastructure"},
    "VRT":  {"name": "Vertiv Holdings Co.",                  "sector": "Data Center Infra", "signals": ["hyperscaler_capex", "copper"],                                                            "theme": "ai_infrastructure"},
    "ACLS": {"name": "Axcelis Technologies Inc.",            "sector": "Semiconductors",    "signals": ["semiconductor_etf", "hyperscaler_capex"],                                                 "theme": "ai_infrastructure"},
    "EQIX": {"name": "Equinix Inc.",                         "sector": "Data Centers REIT", "signals": ["hyperscaler_capex", "ten_year_yield"],                                                    "theme": "ai_infrastructure"},
    "DLR":  {"name": "Digital Realty Trust",                 "sector": "Data Centers REIT", "signals": ["hyperscaler_capex", "ten_year_yield"],                                                    "theme": "ai_infrastructure"},

    # ── AI INFRASTRUCTURE — AI Servers & Hardware ──────────────────────────────
    "NVDA": {"name": "NVIDIA Corporation",                   "sector": "Semiconductors",    "signals": ["hyperscaler_capex", "copper", "semiconductor_etf"],                                       "theme": "ai_infrastructure"},
    "AMD":  {"name": "Advanced Micro Devices",               "sector": "Semiconductors",    "signals": ["hyperscaler_capex", "semiconductor_etf"],                                                 "theme": "ai_infrastructure"},
    "AVGO": {"name": "Broadcom Inc.",                        "sector": "Semiconductors",    "signals": ["hyperscaler_capex", "semiconductor_etf"],                                                 "theme": "ai_infrastructure"},
    "SMCI": {"name": "Super Micro Computer Inc.",            "sector": "AI Servers",        "signals": ["hyperscaler_capex", "copper"],                                                            "theme": "ai_infrastructure"},
    "DELL": {"name": "Dell Technologies Inc.",               "sector": "AI Servers",        "signals": ["hyperscaler_capex"],                                                                      "theme": "ai_infrastructure"},
    "HPE":  {"name": "Hewlett Packard Enterprise",           "sector": "AI Servers",        "signals": ["hyperscaler_capex"],                                                                      "theme": "ai_infrastructure"},
    "MSFT": {"name": "Microsoft Corporation",                "sector": "Technology",        "signals": ["hyperscaler_capex", "quantum_arxiv_velocity"],                                            "theme": "ai_infrastructure"},

    # ── QUANTUM ────────────────────────────────────────────────────────────────
    "IONQ": {"name": "IonQ Inc.",                            "sector": "Quantum Computing", "signals": ["quantum_arxiv_velocity", "ten_year_yield", "vix"],                                         "theme": "quantum"},
    "RGTI": {"name": "Rigetti Computing Inc.",               "sector": "Quantum Computing", "signals": ["quantum_arxiv_velocity", "ten_year_yield", "vix"],                                         "theme": "quantum"},
    "QBTS": {"name": "D-Wave Quantum Inc.",                  "sector": "Quantum Computing", "signals": ["quantum_arxiv_velocity", "ten_year_yield", "vix"],                                         "theme": "quantum"},
    "IBM":  {"name": "International Business Machines",      "sector": "Technology",        "signals": ["quantum_arxiv_velocity", "hyperscaler_capex", "ten_year_yield"],                          "theme": "quantum"},
    "GOOGL":{"name": "Alphabet Inc.",                        "sector": "Technology",        "signals": ["quantum_arxiv_velocity", "hyperscaler_capex", "semiconductor_etf"],                        "theme": "quantum"},

    # ── AGRICULTURE / FERTILIZERS ─────────────────────────────────────────────
    "ADM":  {"name": "Archer-Daniels-Midland Company",       "sector": "Agriculture",       "signals": ["food_cpi", "dollar_index", "retail_sales", "ata_trucking"],                              "theme": "macro"},
    "BG":   {"name": "Bunge Global SA",                      "sector": "Agriculture",       "signals": ["food_cpi", "dollar_index", "hy_spread"],                                                  "theme": "macro"},
    "MOS":  {"name": "Mosaic Company",                       "sector": "Fertilizers",       "signals": ["food_cpi", "natural_gas", "dollar_index", "hy_spread"],                                  "theme": "macro"},
    "NTR":  {"name": "Nutrien Ltd.",                         "sector": "Fertilizers",       "signals": ["food_cpi", "natural_gas", "dollar_index", "ata_trucking"],                               "theme": "macro"},
    "KR":   {"name": "Kroger Company",                       "sector": "Consumer Staples",  "signals": ["food_cpi", "consumer_sentiment", "retail_sales", "layoffs_rate"],                        "theme": "macro"},

    # ── CRITICAL MINERALS — Lithium / Rare Earths ─────────────────────────────
    # Real drivers: industrial demand (ISM PMI), USD strength (commodities price
    # in USD), and actual copper futures as the closest real commodity proxy for
    # broad electrification/grid metals demand. Not a lithium/rare-earth-specific
    # commodity series — that's a genuine gap, flagged honestly rather than
    # papered over with a circular ETF-price "signal."
    "ALB":  {"name": "Albemarle Corporation",                "sector": "Lithium Mining",    "signals": ["copper", "dollar_index", "ism_pmi"],                                                     "theme": "critical_minerals"},
    "SQM":  {"name": "Sociedad Quimica y Minera",            "sector": "Lithium Mining",    "signals": ["copper", "dollar_index", "ism_pmi"],                                                     "theme": "critical_minerals"},
    "LAC":  {"name": "Lithium Americas Corp.",               "sector": "Lithium Mining",    "signals": ["copper", "dollar_index", "ism_pmi"],                                                     "theme": "critical_minerals"},
    "PLL":  {"name": "Piedmont Lithium Inc.",                "sector": "Lithium Mining",    "signals": ["copper", "dollar_index", "ism_pmi"],                                                     "theme": "critical_minerals"},
    "LIT":  {"name": "Global X Lithium & Battery Tech ETF",  "sector": "ETF",               "signals": ["copper", "dollar_index", "ism_pmi"],                                                     "theme": "critical_minerals"},
    "MP":   {"name": "MP Materials Corp.",                   "sector": "Rare Earth Mining", "signals": ["dollar_index", "ism_pmi", "durable_goods"],                                              "theme": "critical_minerals"},
    "USAR": {"name": "USA Rare Earth Inc.",                  "sector": "Rare Earth Mining", "signals": ["dollar_index", "ism_pmi", "durable_goods"],                                              "theme": "critical_minerals"},
    "TMC":  {"name": "TMC the metals company Inc.",          "sector": "Deep-Sea Minerals", "signals": ["copper", "dollar_index", "ism_pmi"],                                                     "theme": "critical_minerals"},
    "REMX": {"name": "VanEck Rare Earth/Strategic Metals ETF","sector": "ETF",              "signals": ["dollar_index", "ism_pmi", "durable_goods"],                                              "theme": "critical_minerals"},

    # ── DEFENSE & AEROSPACE ───────────────────────────────────────────────────
    # Real drivers: capex/durable-goods orders (a real proxy for the broader
    # capital-spending environment defense budgets compete within), long-duration
    # discount rate (10Y yield), and overall industrial conditions (ISM PMI).
    "LMT":  {"name": "Lockheed Martin Corporation",          "sector": "Defense",           "signals": ["durable_goods", "ten_year_yield", "ism_pmi"],                                            "theme": "defense_aerospace"},
    "RTX":  {"name": "RTX Corporation",                      "sector": "Defense",           "signals": ["durable_goods", "ten_year_yield", "ism_pmi"],                                            "theme": "defense_aerospace"},
    "NOC":  {"name": "Northrop Grumman Corporation",         "sector": "Defense",           "signals": ["durable_goods", "ten_year_yield", "ism_pmi"],                                            "theme": "defense_aerospace"},
    "GD":   {"name": "General Dynamics Corporation",         "sector": "Defense",           "signals": ["durable_goods", "ten_year_yield", "ism_pmi"],                                            "theme": "defense_aerospace"},
    "LHX":  {"name": "L3Harris Technologies Inc.",           "sector": "Defense",           "signals": ["durable_goods", "ten_year_yield", "ism_pmi"],                                            "theme": "defense_aerospace"},
    "ITA":  {"name": "iShares U.S. Aerospace & Defense ETF", "sector": "ETF",               "signals": ["durable_goods", "ten_year_yield", "ism_pmi"],                                            "theme": "defense_aerospace"},

    # ── BIOTECH & LONGEVITY ───────────────────────────────────────────────────
    # Real drivers: long-duration discount rate (biotech cash flows are far out),
    # credit conditions for growth-stage biotech funding (HY spread), and broad
    # risk appetite (VIX).
    "LLY":  {"name": "Eli Lilly and Company",                "sector": "Pharmaceuticals",   "signals": ["ten_year_yield", "hy_spread", "fda_approval_velocity"],                                 "theme": "healthcare"},
    "NVO":  {"name": "Novo Nordisk A/S",                     "sector": "Pharmaceuticals",   "signals": ["ten_year_yield", "hy_spread", "fda_approval_velocity"],                                  "theme": "healthcare"},
    "REGN": {"name": "Regeneron Pharmaceuticals Inc.",       "sector": "Biotechnology",     "signals": ["ten_year_yield", "hy_spread", "fda_approval_velocity"],                                  "theme": "healthcare"},
    "VRTX": {"name": "Vertex Pharmaceuticals Inc.",          "sector": "Biotechnology",     "signals": ["ten_year_yield", "hy_spread", "fda_approval_velocity"],                                  "theme": "healthcare"},
    "XBI":  {"name": "SPDR S&P Biotech ETF",                 "sector": "ETF",               "signals": ["ten_year_yield", "hy_spread", "fda_approval_velocity"],                                  "theme": "healthcare"},

    # ── CYBERSECURITY ──────────────────────────────────────────────────────────
    # Real drivers: enterprise/hyperscaler capex (cyber budgets ride the same
    # wave), the semiconductor cycle as a broader tech-capex proxy, and discount
    # rate for growth-tech valuations.
    "CRWD": {"name": "CrowdStrike Holdings Inc.",            "sector": "Cybersecurity",     "signals": ["hyperscaler_capex", "semiconductor_etf", "ten_year_yield"],                             "theme": "cybersecurity"},
    "PANW": {"name": "Palo Alto Networks Inc.",              "sector": "Cybersecurity",     "signals": ["hyperscaler_capex", "semiconductor_etf", "ten_year_yield"],                             "theme": "cybersecurity"},
    "FTNT": {"name": "Fortinet Inc.",                        "sector": "Cybersecurity",     "signals": ["hyperscaler_capex", "semiconductor_etf", "ten_year_yield"],                             "theme": "cybersecurity"},
    "ZS":   {"name": "Zscaler Inc.",                         "sector": "Cybersecurity",     "signals": ["hyperscaler_capex", "semiconductor_etf", "ten_year_yield"],                             "theme": "cybersecurity"},
    "CIBR": {"name": "First Trust NASDAQ Cybersecurity ETF", "sector": "ETF",               "signals": ["hyperscaler_capex", "semiconductor_etf", "ten_year_yield"],                             "theme": "cybersecurity"},

    # ── ROBOTICS & AUTOMATION ──────────────────────────────────────────────────
    # Real drivers: industrial production conditions (ISM PMI), capex orders
    # (durable goods), and the semiconductor cycle (automation hardware tracks chips).
    "ISRG": {"name": "Intuitive Surgical Inc.",              "sector": "Medical Robotics",  "signals": ["ism_pmi", "durable_goods", "semiconductor_etf"],                                        "theme": "robotics_automation"},
    "ABB":  {"name": "ABB Ltd.",                             "sector": "Industrial Automation","signals": ["ism_pmi", "durable_goods", "semiconductor_etf"],                                      "theme": "robotics_automation"},
    "TER":  {"name": "Teradyne Inc.",                        "sector": "Automation Equip.", "signals": ["ism_pmi", "durable_goods", "semiconductor_etf"],                                        "theme": "robotics_automation"},
    "BOTZ": {"name": "Global X Robotics & AI ETF",           "sector": "ETF",               "signals": ["ism_pmi", "durable_goods", "semiconductor_etf"],                                        "theme": "robotics_automation"},

    # ── WATER SECURITY ─────────────────────────────────────────────────────────
    # Real drivers: discount rate (utility-like long-duration assets), industrial
    # production (treatment chemical/equipment demand), and natural gas (a real
    # input-cost proxy — water treatment is energy-intensive).
    "AWK":  {"name": "American Water Works Company",        "sector": "Water Utilities",   "signals": ["ten_year_yield", "ism_pmi", "natural_gas"],                                              "theme": "water_security"},
    "WTRG": {"name": "Essential Utilities Inc.",             "sector": "Water Utilities",   "signals": ["ten_year_yield", "ism_pmi", "natural_gas"],                                              "theme": "water_security"},
    "XYL":  {"name": "Xylem Inc.",                           "sector": "Water Technology",  "signals": ["ten_year_yield", "ism_pmi", "natural_gas"],                                              "theme": "water_security"},
    "ECL":  {"name": "Ecolab Inc.",                          "sector": "Water Technology",  "signals": ["ten_year_yield", "ism_pmi", "natural_gas"],                                              "theme": "water_security"},
    "PHO":  {"name": "Invesco Water Resources ETF",          "sector": "ETF",               "signals": ["ten_year_yield", "ism_pmi", "natural_gas"],                                              "theme": "water_security"},

    # ── BACKFILL: tickers that signals already listed as "relevant" but that
    # were missing from this dict entirely (caught by tests/test_config_integrity.py
    # ::test_no_signal_references_a_nonexistent_relevant_ticker). Without an entry
    # here, ticker_label() silently shows the bare symbol with no company name —
    # exactly the inconsistency the "full company name everywhere" fix was
    # supposed to close. Each name/sector verified, not guessed.
    "TBF":  {"name": "ProShares Short 20+ Year Treasury",     "sector": "ETF",               "signals": ["yield_curve", "ten_year_yield"],                                                         "theme": "macro"},
    "SHY":  {"name": "iShares 1-3 Year Treasury Bond ETF",    "sector": "ETF",               "signals": ["yield_curve", "ten_year_yield"],                                                         "theme": "macro"},
    "TMF":  {"name": "Direxion Daily 20+ Yr Treasury Bull 3X","sector": "ETF",               "signals": ["ten_year_yield", "yield_curve"],                                                         "theme": "macro"},
    "VNQ":  {"name": "Vanguard Real Estate ETF",              "sector": "ETF",               "signals": ["ten_year_yield"],                                                                        "theme": "macro"},
    "MAS":  {"name": "Masco Corporation",                     "sector": "Building Products", "signals": ["housing_starts", "lumber_futures"],                                                      "theme": "macro"},
    "LPX":  {"name": "Louisiana-Pacific Corporation",         "sector": "Building Products", "signals": ["housing_starts", "lumber_futures"],                                                      "theme": "macro"},
    "ITB":  {"name": "iShares U.S. Home Construction ETF",    "sector": "ETF",               "signals": ["lumber_futures", "housing_starts"],                                                      "theme": "macro"},
    "KSS":  {"name": "Kohl's Corporation",                    "sector": "Retail",            "signals": ["retail_sales", "consumer_sentiment"],                                                    "theme": "macro"},
    "M":    {"name": "Macy's Inc.",                           "sector": "Retail",            "signals": ["retail_sales", "consumer_sentiment"],                                                    "theme": "macro"},
    "DPZ":  {"name": "Domino's Pizza Inc.",                   "sector": "Restaurants",       "signals": ["consumer_sentiment", "retail_sales"],                                                    "theme": "macro"},
    "MCD":  {"name": "McDonald's Corporation",                "sector": "Restaurants",       "signals": ["consumer_sentiment", "retail_gasoline"],                                                 "theme": "macro"},
    "SBUX": {"name": "Starbucks Corporation",                 "sector": "Restaurants",       "signals": ["consumer_sentiment", "retail_sales"],                                                    "theme": "macro"},
    "JNK":  {"name": "SPDR Bloomberg High Yield Bond ETF",    "sector": "ETF",               "signals": ["hy_spread"],                                                                             "theme": "macro"},
    "LQD":  {"name": "iShares iBoxx IG Corp Bond ETF",        "sector": "ETF",               "signals": ["hy_spread", "ten_year_yield"],                                                           "theme": "macro"},
    "PH":   {"name": "Parker Hannifin Corporation",           "sector": "Industrials",       "signals": ["durable_goods", "ism_pmi"],                                                              "theme": "macro"},
    "ACI":  {"name": "Albertsons Companies Inc.",             "sector": "Grocery",           "signals": ["food_cpi", "retail_sales"],                                                              "theme": "macro"},
    "SJM":  {"name": "The J. M. Smucker Company",             "sector": "Packaged Foods",    "signals": ["food_cpi"],                                                                              "theme": "macro"},
    "CAG":  {"name": "Conagra Brands Inc.",                   "sector": "Packaged Foods",    "signals": ["food_cpi"],                                                                              "theme": "macro"},
    "PSX":  {"name": "Phillips 66",                           "sector": "Energy",            "signals": ["crude_inventories", "crude_oil"],                                                        "theme": "energy"},
    "VLO":  {"name": "Valero Energy Corporation",             "sector": "Energy",            "signals": ["crude_inventories", "crude_oil"],                                                        "theme": "energy"},
    "MPC":  {"name": "Marathon Petroleum Corporation",        "sector": "Energy",            "signals": ["crude_inventories", "crude_oil"],                                                        "theme": "energy"},
    "CTRA": {"name": "Coterra Energy Inc.",                   "sector": "Natural Gas E&P",   "signals": ["natural_gas", "gas_storage"],                                                            "theme": "energy"},
    "RRC":  {"name": "Range Resources Corporation",           "sector": "Natural Gas E&P",   "signals": ["natural_gas", "gas_storage"],                                                            "theme": "energy"},
    "CNX":  {"name": "CNX Resources Corporation",             "sector": "Natural Gas E&P",   "signals": ["natural_gas", "gas_storage"],                                                            "theme": "energy"},
    "EXE":  {"name": "Expand Energy Corporation",             "sector": "Natural Gas E&P",   "signals": ["natural_gas", "gas_storage"],                                                            "theme": "energy"},
    "AES":  {"name": "The AES Corporation",                   "sector": "Utilities",         "signals": ["power_demand_growth", "natural_gas"],                                                    "theme": "nuclear"},
    "SBSW": {"name": "Sibanye Stillwater Limited",            "sector": "Mining",            "signals": ["copper"],                                                                                "theme": "macro"},
    "VIXY": {"name": "ProShares VIX Short-Term Futures ETF",  "sector": "ETF",               "signals": ["vix"],                                                                                   "theme": "macro"},
    "UVXY": {"name": "ProShares Ultra VIX Short-Term Futures","sector": "ETF",               "signals": ["vix"],                                                                                   "theme": "macro"},
    "GOLD": {"name": "Barrick Gold Corporation",              "sector": "Mining",            "signals": ["dollar_index"],                                                                          "theme": "macro"},
    "EEM":  {"name": "iShares MSCI Emerging Markets ETF",     "sector": "ETF",               "signals": ["dollar_index"],                                                                          "theme": "macro"},
    "EFA":  {"name": "iShares MSCI EAFE ETF",                 "sector": "ETF",               "signals": ["dollar_index"],                                                                          "theme": "macro"},
    "BTC-USD": {"name": "Bitcoin / USD",                      "sector": "Cryptocurrency",    "signals": ["m2_money_supply"],                                                                       "theme": "macro"},
    "AMAT": {"name": "Applied Materials Inc.",                "sector": "Semiconductors",    "signals": ["semiconductor_etf", "hyperscaler_capex"],                                                "theme": "ai_infrastructure"},
    "LRCX": {"name": "Lam Research Corporation",              "sector": "Semiconductors",    "signals": ["semiconductor_etf", "hyperscaler_capex"],                                                "theme": "ai_infrastructure"},
    "KLAC": {"name": "KLA Corporation",                       "sector": "Semiconductors",    "signals": ["semiconductor_etf"],                                                                     "theme": "ai_infrastructure"},
    "MRVL": {"name": "Marvell Technology Inc.",               "sector": "Semiconductors",    "signals": ["semiconductor_etf", "hyperscaler_capex"],                                                "theme": "ai_infrastructure"},
    "VALE": {"name": "Vale S.A.",                             "sector": "Mining",            "signals": ["shipping_index", "copper"],                                                              "theme": "macro"},
    "CLF":  {"name": "Cleveland-Cliffs Inc.",                 "sector": "Steel",             "signals": ["shipping_index"],                                                                        "theme": "macro"},
    "NUE":  {"name": "Nucor Corporation",                     "sector": "Steel",             "signals": ["shipping_index", "durable_goods"],                                                       "theme": "macro"},

    # ── FINANCIALS, HEALTHCARE, CONSUMER, INDUSTRIALS — new sector tickers ──────
    "WFC":  {"name": "Wells Fargo & Company",                 "sector": "Banking",           "signals": ["bank_lending_standards", "yield_curve", "credit_card_delinquency"],                      "theme": "financials"},
    "C":    {"name": "Citigroup Inc.",                        "sector": "Banking",           "signals": ["bank_lending_standards", "yield_curve", "credit_card_delinquency"],                      "theme": "financials"},
    "COF":  {"name": "Capital One Financial Corporation",     "sector": "Consumer Finance",  "signals": ["credit_card_delinquency", "bank_lending_standards"],                                     "theme": "financials"},
    "SYF":  {"name": "Synchrony Financial",                   "sector": "Consumer Finance",  "signals": ["credit_card_delinquency", "retail_sales"],                                               "theme": "financials"},
    "AXP":  {"name": "American Express Company",              "sector": "Consumer Finance",  "signals": ["credit_card_delinquency", "consumer_sentiment"],                                        "theme": "financials"},
    "PFE":  {"name": "Pfizer Inc.",                           "sector": "Pharmaceuticals",   "signals": ["fda_approval_velocity"],                                                                  "theme": "healthcare"},
    "MRK":  {"name": "Merck & Co. Inc.",                      "sector": "Pharmaceuticals",   "signals": ["fda_approval_velocity"],                                                                  "theme": "healthcare"},
    "BMY":  {"name": "Bristol-Myers Squibb Company",          "sector": "Pharmaceuticals",   "signals": ["fda_approval_velocity"],                                                                  "theme": "healthcare"},
    "GILD": {"name": "Gilead Sciences Inc.",                  "sector": "Biotechnology",     "signals": ["fda_approval_velocity"],                                                                  "theme": "healthcare"},
    "AMGN": {"name": "Amgen Inc.",                            "sector": "Biotechnology",     "signals": ["fda_approval_velocity"],                                                                  "theme": "healthcare"},
    "SHOP": {"name": "Shopify Inc.",                          "sector": "E-Commerce",        "signals": ["ecommerce_share", "retail_sales"],                                                       "theme": "consumer"},
    "EBAY": {"name": "eBay Inc.",                             "sector": "E-Commerce",        "signals": ["ecommerce_share", "retail_sales"],                                                       "theme": "consumer"},
    "VMC":  {"name": "Vulcan Materials Company",              "sector": "Construction Materials", "signals": ["construction_spending", "durable_goods"],                                          "theme": "industrials"},
    "MLM":  {"name": "Martin Marietta Materials Inc.",        "sector": "Construction Materials", "signals": ["construction_spending", "durable_goods"],                                          "theme": "industrials"},
    "URI":  {"name": "United Rentals Inc.",                   "sector": "Equipment Rental",  "signals": ["construction_spending", "ism_pmi"],                                                      "theme": "industrials"},
}

# ─────────────────────────────────────────────────────────────────────────────
# 13F INSTITUTIONAL POSITIONING — curated funds + hand-verified CUSIP map
# ─────────────────────────────────────────────────────────────────────────────
# Why this exists as a hand-verified whitelist, not algorithmic fuzzy matching:
# SEC Form 13F filings report holdings by abbreviated company name + CUSIP --
# there is NO ticker symbol field anywhere in a 13F (confirmed live, 2026-06-21,
# by reading Berkshire Hathaway's, Pershing Square's, and Scion Asset
# Management's actual most-recent information tables). A free, reliable,
# keyless CUSIP->ticker lookup doesn't exist (OpenFIGI requires registration).
# Rather than fuzzy-match company names algorithmically -- which risks both
# false negatives (e.g. "ALLY FINL INC" vs "Ally Financial Inc") and, worse,
# false positives (two different companies sharing a generic first word) --
# every mapping below was built by manually reading each fund's real filing
# and confirming the CUSIP against this product's existing TICKERS universe.
# This trades coverage (only tickers already in TICKERS, and only positions
# these specific funds happen to currently hold) for actual correctness.
#
# CURATED_FUNDS: well-known, publicly notable institutional managers chosen
# for filing-size feasibility (small enough to fully fetch and verify by
# hand) and style diversity, not for being the "best" funds to track.
# Bridgewater Associates was deliberately excluded after live-checking their
# actual filing: it runs an extremely diversified macro/options-overlay book
# (largest 13F infotable.xml file checked ran ~600KB, alphabetically still
# only through "ATI" after the the portion fetched) -- far too large to read
# in full and hand-verify, and a single name appearing in a 3000+ position
# book is a much weaker "smart money" signal than a concentrated holding.
CURATED_FUNDS = [
    {"cik": "1067983",  "name": "Berkshire Hathaway",          "style": "Value / conglomerate"},
    {"cik": "1336528",  "name": "Pershing Square Capital Mgmt", "style": "Concentrated activist"},
    {"cik": "1649339",  "name": "Scion Asset Management",       "style": "Contrarian (Michael Burry)"},
    {"cik": "1167483",  "name": "Tiger Global Management",      "style": "Growth / tech-focused"},
    {"cik": "1536411",  "name": "Duquesne Family Office",        "style": "Macro (Stanley Druckenmiller)"},
]
# Funds investigated and deliberately NOT added, for the record:
#   - Bridgewater Associates: too large/diversified to hand-verify (see note
#     in fetch_13f_holdings' docstring).
#   - Greenlight Capital (David Einhorn): most recent 13F-HR on file is
#     2024-02-14 -- over 2 years stale as of this writing, likely
#     deregistered or restructured its filer entity. Stale data presented
#     as current would be worse than no data.
#   - Third Point, Appaloosa Management: could not resolve a working CIK via
#     EDGAR's company-name search at the time this was built (that search
#     endpoint was intermittently returning empty results live, separate
#     from these specific funds' actual filing status -- worth retrying
#     later rather than concluding they don't exist on EDGAR).

# CUSIP -> ticker, hand-verified against each curated fund's most recent
# real 13F-HR information table. As of 2026-06-21: Berkshire & Pershing
# Square & Tiger Global period 2026-03-31 (filed 2026-05-15); Duquesne
# period 2025-12-31 (filed 2026-02-17); Scion period 2025-09-30 (filed
# 2025-11-03) -- Scion's is the most recent filing that fund has on record,
# so their data is genuinely older/staler than the others; this is
# disclosed in the UI, not hidden.
THIRTEENF_CUSIP_TO_TICKER = {
    "02079K305": "GOOGL",   # Alphabet Inc Class A
    "02079K107": "GOOGL",   # Alphabet Inc Class C
    "025816109": "AXP",     # American Express Co
    "060505104": "BAC",     # Bank of America Corp
    "14040H105": "COF",     # Capital One Financial Corp
    "166764100": "CVX",     # Chevron Corporation
    "501044101": "KR",      # Kroger Co
    "526057104": "LEN",     # Lennar Corp Class A
    "526057302": "LEN",     # Lennar Corp Class B
    "546347105": "LPX",     # Louisiana-Pacific Corp
    "55616P104": "M",       # Macy's Inc
    "62944T105": "NVR",     # NVR Inc
    "670346105": "NUE",     # Nucor Corp
    "674599105": "OXY",     # Occidental Petroleum Corp
    "023135106": "AMZN",    # Amazon.com Inc
    "594918104": "MSFT",    # Microsoft Corp
    "406216101": "HAL",     # Halliburton Co
    "67066G104": "NVDA",    # NVIDIA Corporation
    "717081103": "PFE",     # Pfizer Inc
    # Added from Tiger Global Management's filing:
    "11135F101": "AVGO",    # Broadcom Inc
    "038222105": "AMAT",    # Applied Materials Inc
    "512807306": "LRCX",    # Lam Research Corp
    "98980G102": "ZS",      # Zscaler Inc
    # Added from Duquesne Family Office's filing:
    "38141G104": "GS",      # Goldman Sachs Group Inc
    "84265V105": "SCCO",    # Southern Copper Corp
    "185899101": "CLF",     # Cleveland-Cliffs Inc
    "78462F103": "SPY",     # SPDR S&P 500 ETF Trust
}

# ─────────────────────────────────────────────────────────────────────────────
# CATEGORY METADATA
# ─────────────────────────────────────────────────────────────────────────────

CATEGORIES = {
    "macro":              {"name": "Macro & Liquidity",      "icon": "", "color": "#1C2B4A"},
    "energy":             {"name": "Energy & Oil",           "icon": "", "color": "#5D4037"},
    "nuclear":            {"name": "Power & Nuclear",        "icon": "", "color": "#4A1B6B"},
    "ai_infrastructure":  {"name": "AI Infrastructure",      "icon": "", "color": "#B8860B"},
    "financials":         {"name": "Financials & Credit",    "icon": "", "color": "#2E5266"},
    "healthcare":         {"name": "Healthcare & Biotech",   "icon": "", "color": "#6B2E5F"},
    "consumer":           {"name": "Consumer",               "icon": "", "color": "#8B5E34"},
    "industrials":        {"name": "Industrials",            "icon": "", "color": "#3D4F2E"},
}
# NOTE: "quantum", "critical_minerals", "defense_aerospace", "biotech_longevity",
# "cybersecurity", "robotics_automation", and "water_security" categories were
# removed — each had zero genuine signals left in it after the equity-basket
# "proxy" signals were cut. The tickers for those themes still exist in TICKERS
# and are tracked using real macro signals (see notes above); they just don't
# need their own empty signal-category tab on the Signal Dashboard.

# Power Supercycle signal stack — the confluence thesis from the Project Bible
POWER_SUPERCYCLE_SIGNALS = {
    "nuclear_fuel":     ["uranium_proxy", "nuclear_generation"],
    "grid_demand":      ["power_demand_growth"],
    "grid_buildout":    ["copper", "natural_gas", "gas_storage"],
    "ai_demand":        ["hyperscaler_capex", "semiconductor_etf"],
    "macro_health":     ["ata_trucking", "jobless_claims", "ism_pmi"],
}

POWER_SUPERCYCLE_TICKERS = {
    "Nuclear Fuel Chain": ["CCJ", "LEU", "UEC", "URA", "UUUU"],
    "SMR / Advanced Nuclear": ["SMR", "OKLO", "BWXT", "CEG", "EXC"],
    "Grid & Power Infra": ["PWR", "ETN", "VRT", "VST", "NEE"],
    "Copper & Materials": ["FCX", "SCCO", "COPX", "TECK"],
    "Gas Pipelines":      ["WMB", "KMI", "OKE", "ET", "LNG"],
    "AI / Hyperscalers":  ["NVDA", "MSFT", "AMZN", "SMCI", "DELL"],
}
