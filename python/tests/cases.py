"""Hand-computed cases for the Python unit tests (T1). Inputs and expected outputs are written out by hand.

Bridge toy case (T-BR-05). Current period (1) and base period (0), brand and category:

    brand  1: value 300, base value 240, base units 120, TDP 60, units 150
    cat    1: value 1000, base value 900, base units 450, TDP 200, units 500
    brand  0: value 250, base value 225, base units 100, TDP 50, units 125
    cat    0: value 1250, base value 1100, base units 500, TDP 200, units 600

    share       s1 = 300/1000 = 0.30          s0 = 250/1250 = 0.20          change = +10.00 pts
    LMDI weight L = (0.30 - 0.20) / ln(0.30/0.20) = 0.1 / 0.405465 = 0.246630
    distribution share  60/200 = 0.300   vs 50/200 = 0.250           ln ratio = +0.182322  -> +4.4966 pts
    base velocity (A)   (120/60)/(450/200) = 0.8889 vs (100/50)/(500/200) = 0.8000
                                                                     ln ratio = +0.105361  -> +2.5985 pts
    base price (A)      (240/120)/(900/450) = 1.0000 vs (225/100)/(1100/500) = 1.0227
                                                                     ln ratio = -0.022473  -> -0.5542 pts
    promo (A)           (300/240)/(1000/900) = 1.1250 vs (250/225)/(1250/1100) = 0.9778
                                                                     ln ratio = +0.140256  -> +3.4591 pts
    sum of terms = 4.4966 + 2.5985 - 0.5542 + 3.4591 = 10.0000 pts, residual 0

    Mode B (unit velocity, average price), same inputs:
    unit velocity       (150/60)/(500/200) = 1.0000 vs (125/50)/(600/200) = 0.8333   -> +4.4966 pts
    average price       (300/150)/(1000/500) = 1.0000 vs (250/125)/(1250/600) = 0.9600 -> +1.0068 pts
    distribution        +4.4966 pts; sum 10.0000 pts

    Mode C (value velocity): (300/60)/(1000/200) = 1.0 vs (250/50)/(1250/200) = 0.8   -> +5.5034 pts
    distribution        +4.4966 pts; sum 10.0000 pts
"""

BRIDGE_TOY = {
    "cur": dict(s=300.0, cs=1000.0, tdp=60.0, ctdp=200.0, u=150.0, cu=500.0, b=240.0, cb=900.0, bu=120.0, cbu=450.0),
    "base": dict(s=250.0, cs=1250.0, tdp=50.0, ctdp=200.0, u=125.0, cu=600.0, b=225.0, cb=1100.0, bu=100.0, cbu=500.0),
    "expected": {
        "A": {"d_share_pts": 10.0, "dist_pts": 4.4966028678679155, "velocity_pts": 2.5985100456466297,
              "price_pts": -0.5542488219741867, "promo_pts": 3.4591359084596407},
        "B": {"d_share_pts": 10.0, "dist_pts": 4.4966028678679155, "velocity_pts": 4.4966028678679155,
              "price_pts": 1.0067942642641716, "promo_pts": None},
        "C": {"d_share_pts": 10.0, "dist_pts": 4.4966028678679155, "velocity_pts": 5.503397132132087,
              "price_pts": None, "promo_pts": None},
    },
}

# Fact pack used by the validator, renderer and fallback tests: two shifts, one held back, one watch item.
PACK = {
    "brief_id": "b-0001", "run_id": "r-0001", "as_of_week": "2026-11-07",
    "as_of_src": "OPS.RUN_LOG#RUN_ID=r-0001;col=AS_OF_WEEK",
    "scope": {"category": "Biscuits", "parent_market": "All India", "focus_manufacturer": "Acme Foods"},
    "currency": "INR",
    "facts": {
        "f1": {"v": 0.2341, "u": "share", "d": 1, "src": "APP.SHIFT_CANDIDATE#SHIFT_ID=s1;col=SH1"},
        "f2": {"v": 0.2425, "u": "share", "d": 1, "src": "APP.SHIFT_CANDIDATE#SHIFT_ID=s1;col=SH0"},
        "f3": {"v": -0.84, "u": "pts", "d": 2, "src": "APP.SHARE_BRIDGE#SHIFT_ID=s1;col=D_SHARE*100"},
        "f4": {"v": -1834220.5, "u": "money", "d": 1, "src": "APP.SHIFT_RANKED#SHIFT_ID=s1;col=VALUE_AT_STAKE"},
        "f5": {"v": -0.61, "u": "pts", "d": 2, "src": "APP.SHARE_BRIDGE#SHIFT_ID=s1;col=DIST_PTS"},
        "f6": {"v": -0.30, "u": "pts", "d": 2, "src": "APP.SHARE_BRIDGE#SHIFT_ID=s1;col=VELOCITY_PTS"},
        "f7": {"v": 0.05, "u": "pts", "d": 2, "src": "APP.SHARE_BRIDGE#SHIFT_ID=s1;col=PRICE_PTS"},
        "f8": {"v": 0.02, "u": "pts", "d": 2, "src": "APP.SHARE_BRIDGE#SHIFT_ID=s1;col=PROMO_PTS"},
        "f9": {"v": -0.52, "u": "pts", "d": 2, "src": "APP.SHIFT_WHERE#SHIFT_ID=s1;METHOD=EXACT_RETAILER;RANK_NO=1;col=TOTAL_PTS"},
        "f10": {"v": 0.47, "u": "pts", "d": 2, "src": "APP.SHARE_FLOW#RUN_ID=r-0001;CMP_CODE=L4W_VS_YA;MARKET_ID=M0;FROM_BRAND=Crunchy;TO_BRAND=Golden Bake;col=FLOW_PTS"},
        "f11": {"v": 0.1210, "u": "share", "d": 1, "src": "APP.SHIFT_CANDIDATE#SHIFT_ID=s2;col=SH1"},
        "f12": {"v": 0.1105, "u": "share", "d": 1, "src": "APP.SHIFT_CANDIDATE#SHIFT_ID=s2;col=SH0"},
        "f13": {"v": 1.05, "u": "pts", "d": 2, "src": "APP.SHARE_BRIDGE#SHIFT_ID=s2;col=D_SHARE*100"},
        "f14": {"v": 2290000.0, "u": "money", "d": 1, "src": "APP.SHIFT_RANKED#SHIFT_ID=s2;col=VALUE_AT_STAKE"},
        "f15": {"v": 0.90, "u": "pts", "d": 2, "src": "APP.SHARE_BRIDGE#SHIFT_ID=s2;col=DIST_PTS"},
        "f16": {"v": 0.15, "u": "pts", "d": 2, "src": "APP.SHARE_BRIDGE#SHIFT_ID=s2;col=VELOCITY_PTS"},
        "f20": {"v": -1.70, "u": "pts", "d": 2, "src": "APP.SHIFT_RANKED#SHIFT_ID=s3;col=D_SHARE*100"},
        "f30": {"v": -0.081, "u": "index", "d": 1, "src": "APP.EARLY_WARNING#RUN_ID=r-0001;MARKET_ID=M0;BRAND=Crunchy;SIGNAL=DIST_DROP;col=LEVER_CHG"},
        "f31": {"v": -0.19, "u": "pts", "d": 2, "src": "APP.EARLY_WARNING#RUN_ID=r-0001;MARKET_ID=M0;BRAND=Crunchy;SIGNAL=DIST_DROP;col=PROJECTED_SHARE_PTS"},
    },
    "shifts": [
        {"shift_id": "s1", "rank": 1, "brand": "Crunchy", "manufacturer": "Acme Foods", "market": "All India",
         "cmp_code": "L4W_VS_YA", "label": "MARKET_MOVE", "direction": "LOSS",
         "share_now": "f1", "share_before": "f2", "delta": "f3", "value_at_stake": "f4",
         "bridge": [{"term": "distribution", "fact": "f5"}, {"term": "velocity", "fact": "f6"},
                    {"term": "price", "fact": "f7"}, {"term": "promo", "fact": "f8"}],
         "where": [{"contributor": "MegaMart", "fact": "f9"}],
         "flow": [{"brand": "Golden Bake", "fact": "f10"}]},
        {"shift_id": "s2", "rank": 2, "brand": "Golden Bake", "manufacturer": "Rival Co", "market": "Store 24",
         "cmp_code": "L12W_VS_YA", "label": "MIXED", "direction": "GAIN",
         "share_now": "f11", "share_before": "f12", "delta": "f13", "value_at_stake": "f14",
         "bridge": [{"term": "distribution", "fact": "f15"}, {"term": "velocity", "fact": "f16"}],
         "where": [], "flow": []},
    ],
    "held_back": [{"shift_id": "s3", "brand": "Tea Time", "market": "QuickShop", "delta": "f20", "rules": ["R2_FEED"]}],
    "watchlist": [{"brand": "Crunchy", "market": "All India", "signal": "DIST_DROP", "lever_chg": "f30", "projected": "f31"}],
}

# A reply that passes the validator for PACK.
GOOD_LLM = {
    "headline": "Acme Foods lost ground in All India as Crunchy distribution slipped, {{f3}} on L4W.",
    "shifts": [
        {"shift_id": "s1", "title": "Crunchy lost share in All India",
         "why": "Distribution ({{f5}}) drove most of the {{f3}} change, and MegaMart accounted for {{f9}}.",
         "so_what": "Check listings for Crunchy at MegaMart.",
         "next_question": "Who took the share Crunchy lost in All India?"},
        {"shift_id": "s2", "title": "Golden Bake gained share in Store 24",
         "why": "Wider distribution ({{f15}}) explains most of the {{f13}} gain.",
         "so_what": "Watch Golden Bake's new listings in Store 24.",
         "next_question": "Is the Golden Bake gain in Store 24 real or a data effect?"},
    ],
    "watchlist": ["Crunchy in All India: distribution share {{f30}} in the latest week, about {{f31}} on next L4W share."],
}
