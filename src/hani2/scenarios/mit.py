"""Scenarios adapted from the MIT AI Negotiation Competition (2025).

The competition used a used-furniture sale (one price issue), a rental
contract and a consulting contract (four issues each, with one issue both
sides see the same way). The stories and numbers here are our own.
"""

from __future__ import annotations

from .story import Issue, Side, Story, down, peak, scores, up, weights

SOURCE_MIT = "Adapted from the MIT AI Negotiation Competition (2025)."

# --------------------------------------------------------------------------- #
# Furniture: a used leather armchair changes hands                            #
# --------------------------------------------------------------------------- #
CHAIR_PRICES = [50, 65, 80, 95, 110, 125, 140, 155]
PICKUP = ["Buyer collects", "Seller delivers"]
PAY = ["Cash on pickup", "Transfer this week", "Two instalments"]


def _furniture_buyer(rng, ctx):
    no_car = rng.random() < 0.5
    tight = rng.random() < 0.5
    return Side(
        values={
            "Price": down(CHAIR_PRICES, rng),
            "Pickup": {"Buyer collects": 0.0, "Seller delivers": 1.0 if no_car else 0.3},
            "Payment": scores(PAY, [0.2, 0.5, 1.0] if tight else [0.6, 1.0, 0.4], rng),
        },
        weights=weights(rng, Price=(4, 7), Pickup=(1.5, 3) if no_car else (0.3, 1),
                        Payment=(1, 2.5) if tight else (0.2, 0.8)),
    )


def _furniture_seller(rng, ctx):
    moving = rng.random() < 0.5
    return Side(
        values={
            "Price": up(CHAIR_PRICES, rng),
            "Pickup": {"Buyer collects": 1.0, "Seller delivers": rng.uniform(0.0, 0.4)},
            "Payment": scores(PAY, [1.0, 0.6, 0.0] if moving else [0.8, 1.0, 0.2], rng),
        },
        weights=weights(rng, Price=(4, 7), Pickup=(1, 2.5) if moving else (0.5, 1.5), Payment=(0.5, 2)),
    )


FURNITURE = Story(
    type="Furniture",
    title="Used Armchair Sale",
    short_description='In this scenario, a buyer and a seller negotiate the sale of a used armchair: the price, who moves it and how it is paid.',
    long_description="**The Domain** There are three issues: the price of the armchair, who moves it to the buyer's home and how the buyer pays.",
    roles={"Buyer": _furniture_buyer, "Seller": _furniture_seller},
    role_descriptions={"Buyer": "the person who wants to buy the armchair",
                       "Seller": "the person selling the armchair"},
    issues=[
        Issue("Price", CHAIR_PRICES, "The price of the armchair", fmt="${:,}"),
        Issue("Pickup", PICKUP, "Who moves the chair to the buyer's home"),
        Issue("Payment", PAY, "How the buyer pays"),
    ],
    disagreement="Without a deal the buyer buys a chair elsewhere and the seller sells to a second-hand shop.",
    human_role="Buyer",
    source=SOURCE_MIT,
    band=(0.35, 0.92),
)

# --------------------------------------------------------------------------- #
# Lease: a landlord and a prospective tenant                                  #
# --------------------------------------------------------------------------- #
RENTS = [2800, 3000, 3200, 3400, 3600]
DEPOSITS = [0, 1000, 2000, 3000, 4000]
MOVE_IN = ["1 May", "15 May", "1 June", "15 June", "1 July"]
LENGTHS = ["Month to month", "6 months", "1 year", "18 months", "2 years"]

# kind: (best lease length, best move-in) — what the tenant's situation favours
_TENANT_KINDS = {"relocating": (0, 4), "settling": (4, 1), "student": (3, 2), "budget": (2, 2)}
_LANDLORD_KINDS = {"selling": (0, 0), "stable": (4, 0), "renovating": (2, 2), "mortgage": (2, 0)}


def _lease_tenant(rng, ctx):
    kind = rng.choice(list(_TENANT_KINDS))
    best_len, best_move = _TENANT_KINDS[kind]
    budget = kind == "budget"
    return Side(
        values={
            "Rent": down(RENTS, rng),
            "Deposit": down(DEPOSITS, rng),
            "Move-in date": peak(MOVE_IN, best_move, rng, (0.15, 0.35), (0.15, 0.35)),
            "Lease length": peak(LENGTHS, best_len, rng, (0.15, 0.35), (0.15, 0.35)),
        },
        weights=weights(rng, Rent=(4, 6) if budget else (2.5, 4.5), Deposit=(1.5, 3) if budget else (0.8, 2),
                        **{"Move-in date": (1, 2.5), "Lease length": (2, 3.5) if not budget else (0.5, 1.5)}),
    )


def _lease_landlord(rng, ctx):
    kind = rng.choice(list(_LANDLORD_KINDS))
    best_len, best_move = _LANDLORD_KINDS[kind]
    mortgage = kind == "mortgage"
    return Side(
        values={
            "Rent": up(RENTS, rng),
            "Deposit": up(DEPOSITS, rng),
            "Move-in date": peak(MOVE_IN, best_move, rng, (0.15, 0.35), (0.15, 0.35)),
            "Lease length": peak(LENGTHS, best_len, rng, (0.15, 0.35), (0.15, 0.35)),
        },
        weights=weights(rng, Rent=(4, 6) if mortgage else (2.5, 4.5), Deposit=(0.8, 2.5),
                        **{"Move-in date": (1.5, 3) if mortgage else (0.8, 2.5), "Lease length": (1, 3)}),
    )


LEASE = Story(
    type="Lease",
    title="Apartment Lease",
    short_description='In this scenario, a landlord and a tenant negotiate the lease of an apartment: the rent, the deposit, the move-in date and the lease length.',
    long_description='**The Domain** There are four issues: the monthly rent, the security deposit, the move-in date and how long the lease runs.',
    roles={"Landlord": _lease_landlord, "Tenant": _lease_tenant},
    role_descriptions={"Landlord": "the owner of the apartment",
                       "Tenant": "the person who wants to rent the apartment"},
    issues=[
        Issue("Rent", RENTS, "Monthly rent", fmt="${:,}/month"),
        Issue("Deposit", DEPOSITS, "Security deposit paid at signing", fmt="${:,}"),
        Issue("Move-in date", MOVE_IN, "When the lease starts (rent is paid from this date)"),
        Issue("Lease length", LENGTHS, "How long the lease runs"),
    ],
    disagreement="Without a deal the tenant keeps looking and the landlord keeps advertising the apartment.",
    human_role="Tenant",
    source=SOURCE_MIT + " The rental-house domain of ANAC 2012 is a similar case.",
)

# --------------------------------------------------------------------------- #
# Consulting: a freelance consultant and a startup                             #
# --------------------------------------------------------------------------- #
FEES = [25000, 30000, 35000, 40000, 45000]
BUDGETS = [0, 5000, 10000, 15000, 20000]
TRAVEL = ["Train or bus only", "Economy flights", "Premium economy", "Business class"]
INVOICING = ["Weekly", "Every two weeks", "Monthly", "At the end"]


def _consultant(rng, ctx):
    cash = rng.random() < 0.5
    flyer = rng.random() < 0.5
    return Side(
        values={
            "Fee": up(FEES, rng),
            "Expense budget": up(BUDGETS, rng),
            "Travel": up(TRAVEL, rng),
            "Invoicing": down(INVOICING, rng) if cash else scores(INVOICING, [0.6, 0.8, 1.0, 0.7], rng),
        },
        weights=weights(rng, Fee=(3, 5), **{"Expense budget": (1.5, 3.5), "Travel": (1.5, 3) if flyer else (0.3, 1),
                                            "Invoicing": (1.5, 3) if cash else (0.2, 0.8)}),
    )


def _client(rng, ctx):
    precedent = rng.random() < 0.5
    admin = rng.random() < 0.5
    return Side(
        values={
            "Fee": down(FEES, rng),
            "Expense budget": down(BUDGETS, rng),
            "Travel": down(TRAVEL, rng),
            "Invoicing": up(INVOICING, rng) if admin else down(INVOICING, rng),
        },
        weights=weights(rng, Fee=(3, 5), **{"Expense budget": (3, 5) if precedent else (1, 2.5), "Travel": (0.8, 2),
                                            "Invoicing": (0.5, 1.5)}),
    )


CONSULTING = Story(
    type="Consulting",
    title="Summer Consulting Contract",
    short_description='In this scenario, a consultant and a client negotiate a summer consulting contract: the fee, the expense budget, the travel policy and how often the consultant invoices.',
    long_description='**The Domain** There are four issues: the fee for the summer, the expense budget, how the consultant may travel and how often the consultant sends an invoice.',
    roles={"Client": _client, "Consultant": _consultant},
    role_descriptions={"Client": "the startup hiring the consultant",
                       "Consultant": "the freelance consultant"},
    issues=[
        Issue("Fee", FEES, "Lump-sum fee for the summer", fmt="${:,}"),
        Issue("Expense budget", BUDGETS, "Money the consultant may spend on research and help", fmt="${:,}"),
        Issue("Travel", TRAVEL, "How the consultant may travel to client sites"),
        Issue("Invoicing", INVOICING, "How often the consultant sends an invoice"),
    ],
    disagreement="Without a deal the startup hires another consultant and the consultant takes other work.",
    human_role="Consultant",
    source=SOURCE_MIT,
)

STORIES = [FURNITURE, LEASE, CONSULTING]
