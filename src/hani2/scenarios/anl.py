"""Scenarios adapted from domains of the ANAC Automated Negotiation League (ANL).

From 2010 to 2019 the league ran on the Genius platform with named two-party
domains (a bicycle-parts supply deal, a company acquisition, sharing the
housework, a day-ahead energy plan, a health fund between two countries, a
used car, a city trip, and a police-union contract shipped with the
platform). These stories rework those domains with our own names, wording
and numbers.

The texts, issues and roles of every type are in its template folder,
``hani2/sample_scenarios/Default/<Type>/`` (YAML, editable without code); this
module only holds the functions that draw each role's preferences.
"""

from __future__ import annotations

from .story import Side, Story, down, peak, scores, taste, up, weights


# --------------------------------------------------------------------------- #
# Supply: a parts supplier and a bicycle maker (ANAC 2010)                    #
# --------------------------------------------------------------------------- #
UNIT_PRICES = [3.50, 3.70, 3.90, 4.10, 4.30]
DELIVERY = [20, 30, 45, 60]
PAYMENT = ["On delivery", "30 days after delivery", "60 days after delivery"]
RETURNS = ["Full refund for defects", "5% defects tolerated", "10% defects tolerated"]


def _maker(rng, ctx):
    launch = rng.random() < 0.5
    cash = rng.random() < 0.5
    return Side(
        values={
            "Unit price": down(UNIT_PRICES, rng),
            "Delivery": down(DELIVERY, rng, (1.2, 2.2) if launch else (0.4, 0.9)),
            "Payment": up(PAYMENT, rng),
            "Returns": down(RETURNS, rng),
        },
        weights=weights(rng, **{"Unit price": (3, 5), "Delivery": (2.5, 4) if launch else (0.5, 1.5),
                                "Payment": (2, 3.5) if cash else (0.4, 1.2), "Returns": (1, 2.5)}),
    )


def _supplier(rng, ctx):
    full = rng.random() < 0.5
    loan = rng.random() < 0.5
    return Side(
        values={
            "Unit price": up(UNIT_PRICES, rng),
            "Delivery": up(DELIVERY, rng, (0.8, 1.6)) if full else scores(DELIVERY, [0.8, 1.0, 0.9, 0.7], rng),
            "Payment": down(PAYMENT, rng),
            "Returns": up(RETURNS, rng),
        },
        weights=weights(rng, **{"Unit price": (3, 5), "Delivery": (2, 3.5) if full else (0.3, 1),
                                "Payment": (2, 3.5) if loan else (0.4, 1.2), "Returns": (1, 2.5)}),
    )


SUPPLY = Story.from_folder("Supply", roles={"Maker": _maker, "Supplier": _supplier})

# --------------------------------------------------------------------------- #
# Acquisition: a large company buys a biotech startup (ANAC 2011/2012)         #
# --------------------------------------------------------------------------- #
PRICE_M = [1.0, 2.5, 5.0, 8.0]
IP = ["Buyer gets all IP", "Buyer gets patents, founders keep know-how", "Founders keep IP, buyer licenses it"]
EQUITY = [0, 2, 5]
ROLES = ["No roles", "Advisory roles", "Leadership roles"]
STAFF = ["Same terms", "Retention bonuses", "15% raise", "Restructuring"]
LIABILITY = ["Founders keep past liability", "Buyer takes all liability"]


def _acquirer(rng, ctx):
    kind = rng.choice(["talent", "technology", "cost"])
    staff = {"talent": [0.6, 1.0, 0.8, 0.0], "technology": [0.8, 0.5, 0.3, 1.0], "cost": [0.8, 0.4, 0.0, 1.0]}[kind]
    return Side(
        values={
            "Price": down(PRICE_M, rng),
            "IP": down(IP, rng, (0.5, 1.0) if kind == "technology" else (1.0, 2.0)),
            "Founders' equity": down(EQUITY, rng),
            "Founders' roles": scores(ROLES, [0.0, 0.5, 1.0] if kind == "talent" else [1.0, 0.7, 0.2], rng),
            "Staff terms": scores(STAFF, staff, rng),
            "Liability": {"Founders keep past liability": 1.0, "Buyer takes all liability": 0.0},
        },
        weights=weights(rng, Price=(3, 5) if kind == "cost" else (2, 3.5),
                        IP=(3, 5) if kind == "technology" else (1, 2),
                        **{"Founders' equity": (0.5, 1.5),
                           "Founders' roles": (1.5, 3) if kind == "talent" else (0.5, 1),
                           "Staff terms": (2, 3.5) if kind != "technology" else (0.5, 1.5),
                           "Liability": (0.8, 2)}),
    )


def _founders(rng, ctx):
    kind = rng.choice(["cash out", "stay", "team"])
    return Side(
        values={
            "Price": up(PRICE_M, rng),
            "IP": up(IP, rng),
            "Founders' equity": up(EQUITY, rng),
            "Founders' roles": scores(ROLES, [1.0, 0.6, 0.0] if kind == "cash out" else [0.0, 0.4, 1.0], rng),
            "Staff terms": scores(STAFF, [0.4, 0.8, 1.0, 0.0], rng),
            "Liability": {"Founders keep past liability": 0.0, "Buyer takes all liability": 1.0},
        },
        weights=weights(rng, Price=(3, 5) if kind == "cash out" else (1.5, 3), IP=(1, 2),
                        **{"Founders' equity": (2, 3) if kind == "stay" else (0.5, 1.2),
                           "Founders' roles": (2, 3.5) if kind == "stay" else (0.5, 1.5),
                           "Staff terms": (2.5, 4) if kind == "team" else (0.8, 1.8),
                           "Liability": (2, 3) if kind == "cash out" else (0.5, 1.5)}),
    )


ACQUISITION = Story.from_folder("Acquisition", roles={"Acquirer": _acquirer, "Founders": _founders})

# --------------------------------------------------------------------------- #
# Chores: two flatmates share the housework (ANAC 2012)                       #
# --------------------------------------------------------------------------- #
CHORES = ["Cooking", "Dishes", "Laundry", "Cleaning", "Groceries"]
WHO = ["human", "agent", "Shared", "Paid help"]
PAID_COST = {"Cooking": 0.9, "Dishes": 0.6, "Laundry": 0.5, "Cleaning": 0.7, "Groceries": 0.3}


def _flatmate(me: str):
    other = "agent" if me == "human" else "human"

    def draw(rng, ctx):
        dislike = {c: rng.random() for c in CHORES}
        frugal = rng.random()
        hated = max(CHORES, key=lambda c: dislike[c])
        liked = min(CHORES, key=lambda c: dislike[c])
        values, ws = {}, {}
        for c in CHORES:
            d = dislike[c]
            values[c] = {
                me: 1.0 - d,                               # I do it myself
                other: 1.0,                                # my flatmate does it
                "Shared": 1.0 - d / 2,                     # we take turns
                "Paid help": 1.0 - frugal * PAID_COST[c],  # we split the cost
            }
            ws[c] = 0.5 + d * rng.uniform(1.0, 2.0) + frugal * PAID_COST[c] * 0.5
        return Side(values=values, weights=ws,
                    hints={"Chore you hate most": hated, "Chore you mind least": liked,
                           "Paying for help": "a last resort" if frugal > 0.6
                           else "fine for chores you hate" if frugal < 0.3 else "fine now and then"})

    return draw


CHORES_STORY = Story.from_folder("Chores", roles={"agent": _flatmate("agent"), "human": _flatmate("human")})

# --------------------------------------------------------------------------- #
# Energy: a day-ahead power plan (ANAC 2011/2012)                              #
# --------------------------------------------------------------------------- #
BLOCKS = ["Night", "Morning", "Afternoon", "Evening"]
KW = [0, 25, 50, 75, 100]
TARIFF = [0.10, 0.12, 0.14, 0.16, 0.18]  # dollars per kWh
# Need per block (index into KW) of a bakery whose ovens run at night and in the morning.
_NEED = [3, 4, 2, 1]


def _consumer(rng, ctx):
    need = [max(0, min(4, n + rng.choice([-1, 0, 0, 1]))) for n in _NEED]
    values, ws = {}, {}
    for b, n in zip(BLOCKS, need):
        # Short supply stops the ovens; unused power is only money lost.
        values[b] = peak(KW, n, rng, below=(0.3, 0.5), above=(0.1, 0.25))
        ws[b] = 0.5 + n * rng.uniform(0.4, 0.8)
    values["Price"] = down(TARIFF, rng)
    ws["Price"] = rng.uniform(2.5, 4.5)
    return Side(values=values, weights=ws,
                hints={"Power you need": ", ".join(f"{b} {KW[n]} kW" for b, n in zip(BLOCKS, need))})


def _energy_supplier(rng, ctx):
    values = {
        "Night": peak(KW, rng.choice([1, 2]), rng),        # limited cheap night capacity
        "Morning": down(KW, rng, (0.6, 1.2)),              # the grid's peak: every kW costs more than it earns
        "Afternoon": up(KW, rng, (0.6, 1.2)),              # surplus solar power to sell
        "Evening": peak(KW, rng.choice([2, 3]), rng),
        "Price": up(TARIFF, rng),
    }
    ws = {"Night": rng.uniform(0.8, 2), "Morning": rng.uniform(2, 3.5), "Afternoon": rng.uniform(1, 2.5),
          "Evening": rng.uniform(0.5, 1.5), "Price": rng.uniform(2.5, 4.5)}
    return Side(values=values, weights=ws)


ENERGY = Story.from_folder("Energy", roles={"Bakery": _consumer, "Supplier": _energy_supplier})

# --------------------------------------------------------------------------- #
# HealthFund: two countries agree on a tobacco-control fund (ANAC 2010)       #
# --------------------------------------------------------------------------- #
FUND = [10, 50, 100]
AID = ["No cut to other aid", "Cut by half the fund", "Cut by the whole fund"]
TARIFFS = ["Lower tariffs", "Unchanged tariffs", "Higher tariffs"]
IMPORTS = ["Fewer tobacco imports", "Unchanged imports", "More tobacco imports"]
FORUM = ["A new health fund", "A committee to plan a fund", "A committee to set an agenda", "No forum"]


def _donor(rng, ctx):
    budget = rng.random() < 0.5
    lobby = rng.random() < 0.5
    return Side(
        values={
            "Fund size": down(FUND, rng, (0.4, 0.9)) if budget else peak(FUND, 1, rng),
            "Other aid": up(AID, rng) if budget else scores(AID, [1.0, 0.7, 0.4], rng),
            "Recipient's tariffs": down(TARIFFS, rng),
            "Donor's imports": down(IMPORTS, rng),
            "Health forum": scores(FORUM, [1.0, 0.7, 0.4, 0.0], rng),
        },
        weights=weights(rng, **{"Fund size": (2, 3.5), "Other aid": (2, 3.5) if budget else (0.5, 1.5),
                                "Recipient's tariffs": (1.5, 3) if lobby else (0.3, 1),
                                "Donor's imports": (1.5, 3), "Health forum": (0.5, 1.5)}),
    )


def _recipient(rng, ctx):
    farmers = rng.random() < 0.5
    return Side(
        values={
            "Fund size": up(FUND, rng),
            "Other aid": down(AID, rng),
            "Recipient's tariffs": up(TARIFFS, rng),
            "Donor's imports": up(IMPORTS, rng),
            "Health forum": scores(FORUM, [0.6, 1.0, 0.7, 0.0], rng),
        },
        weights=weights(rng, **{"Fund size": (2.5, 4), "Other aid": (2.5, 4), "Recipient's tariffs": (0.8, 2),
                                "Donor's imports": (2.5, 4) if farmers else (0.5, 1.5),
                                "Health forum": (0.3, 1.2)}),
    )


HEALTH_FUND = Story.from_folder("HealthFund", roles={"Donor": _donor, "Recipient": _recipient})

# --------------------------------------------------------------------------- #
# UsedCar: a dealer and a buyer (ANAC 2011 car domain)                        #
# --------------------------------------------------------------------------- #
CAR_PRICES = [13000, 15000, 17000, 19000, 21000]
MEDIA = ["Basic radio", "Touchscreen", "Touchscreen with navigation"]
CLIMATE = ["Manual air conditioning", "Climate control"]
HITCH = ["No tow hitch", "Tow hitch fitted"]
CAR_WARRANTY = ["No warranty", "6 months", "1 year"]


def _car_buyer(rng, ctx):
    kind = rng.choice(["family", "caravan", "commuter", "student"])
    return Side(
        values={
            "Price": down(CAR_PRICES, rng),
            "Infotainment": up(MEDIA, rng, (0.5, 1.0) if kind == "commuter" else (1.0, 2.0)),
            "Air conditioning": {"Manual air conditioning": 0.0, "Climate control": 1.0},
            "Tow hitch": {"No tow hitch": 0.0, "Tow hitch fitted": 1.0 if kind == "caravan" else rng.uniform(0, 0.3)},
            "Warranty": up(CAR_WARRANTY, rng),
        },
        weights=weights(rng, Price=(5, 8) if kind == "student" else (3, 5),
                        Infotainment=(1.5, 3) if kind == "commuter" else (0.3, 1),
                        **{"Air conditioning": (1, 2) if kind == "family" else (0.3, 1),
                           "Tow hitch": (3, 4.5) if kind == "caravan" else (0.1, 0.4),
                           "Warranty": (1.5, 3) if kind == "family" else (0.5, 1.5)}),
    )


def _dealer(rng, ctx):
    slow = rng.random() < 0.5
    return Side(
        values={
            "Price": up(CAR_PRICES, rng),
            "Infotainment": down(MEDIA, rng),
            "Air conditioning": {"Manual air conditioning": 1.0, "Climate control": rng.uniform(0.0, 0.4)},
            "Tow hitch": {"No tow hitch": 1.0, "Tow hitch fitted": rng.uniform(0.0, 0.4)},
            "Warranty": down(CAR_WARRANTY, rng),
        },
        weights=weights(rng, Price=(3, 5) if slow else (4, 6), Infotainment=(1, 2),
                        **{"Air conditioning": (0.5, 1.5), "Tow hitch": (0.5, 1.5), "Warranty": (1, 2.5)}),
    )


USED_CAR = Story.from_folder("UsedCar", roles={"Buyer": _car_buyer, "Dealer": _dealer})

# --------------------------------------------------------------------------- #
# CityTrip: a host and a visiting friend plan a weekend (ANAC 2011)           #
# --------------------------------------------------------------------------- #
ACTIVITY = ["Museums", "Shopping", "Canal tour", "Live music"]
DAY = ["Friday", "Saturday", "Sunday"]
LENGTH = ["One day", "Two days", "Three days"]
TRANSPORT = ["Public transport", "Rented bikes", "Car"]
FOOD = ["Street food", "Local restaurants", "Fine dining"]


def _host(rng, ctx):
    busy = rng.random() < 0.5
    return Side(
        values={
            "Activity": taste(ACTIVITY, rng, favourite=rng.choice(["Canal tour", "Live music"])),
            "Day": scores(DAY, [0.0, 1.0, 0.7] if busy else [0.8, 1.0, 0.6], rng),
            "Length": down(LENGTH, rng) if busy else up(LENGTH, rng),
            "Transport": taste(TRANSPORT, rng, favourite="Rented bikes"),
            "Food": down(FOOD, rng),  # the host pays for most meals
        },
        weights=weights(rng, Activity=(1, 2.5), Day=(1.5, 3) if busy else (0.5, 1.2), Length=(1.5, 3),
                        Transport=(0.5, 1.5), Food=(1, 2.5)),
    )


def _visitor(rng, ctx):
    fav = rng.choice(ACTIVITY)
    flight = rng.choice(DAY)
    return Side(
        values={
            "Activity": taste(ACTIVITY, rng, favourite=fav),
            "Day": scores(DAY, [1.0 if d == flight else 0.3 for d in DAY], rng),
            "Length": up(LENGTH, rng),
            "Transport": taste(TRANSPORT, rng),
            "Food": up(FOOD, rng),
        },
        weights=weights(rng, Activity=(2, 3.5), Day=(1, 2.5), Length=(1.5, 3), Transport=(0.3, 1), Food=(1, 2)),
    )


CITY_TRIP = Story.from_folder("CityTrip", roles={"Host": _host, "Visitor": _visitor})

# --------------------------------------------------------------------------- #
# LaborContract: a police union and the city (Genius police-union domain)     #
# --------------------------------------------------------------------------- #
RAISE = [0, 2, 4, 6, 8]  # percent
VACATION = [0, 2, 4]  # extra days
PATROLS = ["Unchanged", "Two-officer patrols at night", "Two-officer patrols always"]
SERGEANTS = [0, 4, 8]
REVIEW = ["Keep the civilian review board", "Add officers to the board", "Disband the board"]


def _union(rng, ctx):
    safety = rng.random() < 0.5
    return Side(
        values={
            "Pay raise": up(RAISE, rng),
            "Extra vacation": up(VACATION, rng),
            "Patrols": up(PATROLS, rng),
            "New sergeants": up(SERGEANTS, rng),
            "Review board": up(REVIEW, rng),
        },
        weights=weights(rng, **{"Pay raise": (3, 5), "Extra vacation": (1, 2.5),
                                "Patrols": (3, 4.5) if safety else (0.5, 1.5), "New sergeants": (0.8, 2),
                                "Review board": (1, 2.5)}),
    )


def _city(rng, ctx):
    budget = rng.random() < 0.5
    return Side(
        values={
            "Pay raise": down(RAISE, rng),
            "Extra vacation": down(VACATION, rng),
            "Patrols": down(PATROLS, rng),
            "New sergeants": peak(SERGEANTS, 1, rng),
            "Review board": down(REVIEW, rng, (0.4, 0.9)),
        },
        weights=weights(rng, **{"Pay raise": (3, 5) if budget else (1.5, 3), "Extra vacation": (1, 2),
                                "Patrols": (1, 2.5), "New sergeants": (0.5, 1.5),
                                "Review board": (1.5, 3) if not budget else (0.8, 2)}),
    )


LABOR_CONTRACT = Story.from_folder("LaborContract", roles={"City": _city, "Union": _union})

STORIES = [SUPPLY, ACQUISITION, CHORES_STORY, ENERGY, HEALTH_FUND, USED_CAR, CITY_TRIP, LABOR_CONTRACT]
