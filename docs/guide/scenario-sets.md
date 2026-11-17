# Scenario sets

HANI2 groups its scenario types into *scenario sets*. This page lists every bundled set and every scenario in it. See [Scenarios](scenarios.md#scenario-sets) for how the active set is chosen and how to define your own sets.

Every scenario type has a fixed story: the same title, descriptions, issues and roles in every generated scenario. What changes from one scenario to the next is the utility functions: how much each issue matters to each side and how each side values the options, always in the direction the story gives. Each side's hints show its most and least important issues, its ideal deal and any drawn facts (such as an estimate or a power need).

## HAN2026

The scenarios of the ANAC 2026 Human-Agent Negotiation league.

| Type | Title | Roles (participant first) |
|------|-------|-------|
| [`Trade`](#trade) | Simple Trading Scenario | Buyer or Seller (index 1) |
| [`Island`](#island) | Island Survival Scenario | human, agent |
| [`Grocery`](#grocery) | Groceries Distribution | human, agent |

## MIT2025

Adapted from the MIT AI Negotiation Competition (2025): a used-furniture sale, a rental contract and a consulting contract.

| Type | Title | Roles (participant first) |
|------|-------|-------|
| [`Furniture`](#furniture) | Used Armchair Sale | Buyer, Seller |
| [`Lease`](#lease) | Apartment Lease | Tenant, Landlord |
| [`Consulting`](#consulting) | Summer Consulting Contract | Consultant, Client |

## PieArena2026

Adapted from the MBA negotiation cases of the PieArena benchmark (2026): a job offer, a license with a payment on regulatory approval, and a service quote.

| Type | Title | Roles (participant first) |
|------|-------|-------|
| [`JobOffer`](#joboffer) | Job Offer | Candidate, Recruiter |
| [`License`](#license) | Medical Device License | Inventor, Firm |
| [`HomeRepair`](#homerepair) | Roof Repair Quote | Homeowner, Contractor |

## ANL

Adapted from domains of the ANAC Automated Negotiation League (2010-2026), plus the HAN2026 and other types that match ANL domains (Grocery, Trade as the target-quantity case of 2025, JobOffer as the job hunt of 2025, Lease as the rental house of 2012).

| Type | Title | Roles (participant first) |
|------|-------|-------|
| [`Supply`](#supply) | Bicycle Parts Supply | Maker, Supplier |
| [`Acquisition`](#acquisition) | Startup Acquisition | Founders, Acquirer |
| [`Chores`](#chores) | Sharing the Housework | human, agent |
| [`Energy`](#energy) | Day-Ahead Power Plan | Bakery, Supplier |
| [`HealthFund`](#healthfund) | Tobacco Control Fund | Recipient, Donor |
| [`UsedCar`](#usedcar) | Used Car Purchase | Buyer, Dealer |
| [`CityTrip`](#citytrip) | Weekend City Trip | Visitor, Host |
| [`LaborContract`](#laborcontract) | Police Labor Contract | Union, City |
| [`Grocery`](#grocery) | Groceries Distribution | human, agent |
| [`Trade`](#trade) | Simple Trading Scenario | Buyer or Seller (index 1) |
| [`JobOffer`](#joboffer) | Job Offer | Candidate, Recruiter |
| [`Lease`](#lease) | Apartment Lease | Tenant, Landlord |

## ANL2010

ANL 2010 (the first ANAC): the bicycle-parts supply and tobacco-control fund domains.

| Type | Title | Roles (participant first) |
|------|-------|-------|
| [`Supply`](#supply) | Bicycle Parts Supply | Maker, Supplier |
| [`HealthFund`](#healthfund) | Tobacco Control Fund | Recipient, Donor |

## ANL2011

ANL 2011: the acquisition, energy, car, city-trip (Amsterdam) and grocery domains.

| Type | Title | Roles (participant first) |
|------|-------|-------|
| [`Acquisition`](#acquisition) | Startup Acquisition | Founders, Acquirer |
| [`Energy`](#energy) | Day-Ahead Power Plan | Bakery, Supplier |
| [`UsedCar`](#usedcar) | Used Car Purchase | Buyer, Dealer |
| [`CityTrip`](#citytrip) | Weekend City Trip | Visitor, Host |
| [`Grocery`](#grocery) | Groceries Distribution | human, agent |

## ANL2012

ANL 2012: the 2010 and 2011 domains plus housekeeping and the rental house.

| Type | Title | Roles (participant first) |
|------|-------|-------|
| [`Supply`](#supply) | Bicycle Parts Supply | Maker, Supplier |
| [`Acquisition`](#acquisition) | Startup Acquisition | Founders, Acquirer |
| [`Chores`](#chores) | Sharing the Housework | human, agent |
| [`Energy`](#energy) | Day-Ahead Power Plan | Bakery, Supplier |
| [`HealthFund`](#healthfund) | Tobacco Control Fund | Recipient, Donor |
| [`UsedCar`](#usedcar) | Used Car Purchase | Buyer, Dealer |
| [`CityTrip`](#citytrip) | Weekend City Trip | Visitor, Host |
| [`Lease`](#lease) | Apartment Lease | Tenant, Landlord |
| [`Grocery`](#grocery) | Groceries Distribution | human, agent |

## ANL2013

ANL 2013: the acquisition and housekeeping domains.

| Type | Title | Roles (participant first) |
|------|-------|-------|
| [`Acquisition`](#acquisition) | Startup Acquisition | Founders, Acquirer |
| [`Chores`](#chores) | Sharing the Housework | human, agent |

## ANL2025

ANL 2025 (multi-deal): the bilateral cores of the target-quantity and job-hunt scenarios.

| Type | Title | Roles (participant first) |
|------|-------|-------|
| [`Trade`](#trade) | Simple Trading Scenario | Buyer or Seller (index 1) |
| [`JobOffer`](#joboffer) | Job Offer | Candidate, Recruiter |

## ANL2026

ANL 2026 (deception): the reused 2011 domains.

| Type | Title | Roles (participant first) |
|------|-------|-------|
| [`Acquisition`](#acquisition) | Startup Acquisition | Founders, Acquirer |
| [`UsedCar`](#usedcar) | Used Car Purchase | Buyer, Dealer |
| [`CityTrip`](#citytrip) | Weekend City Trip | Visitor, Host |
| [`Grocery`](#grocery) | Groceries Distribution | human, agent |

## IAGO

Item splits in the style of the IAGO human-agent negotiation platform.

| Type | Title | Roles (participant first) |
|------|-------|-------|
| [`Resources`](#resources) | Resource Exchange | human, agent |
| [`Estate`](#estate) | Dividing an Estate | human, agent |
| [`Grocery`](#grocery) | Groceries Distribution | human, agent |

## ANAC2027

A short list with the most varied structures: an apartment lease with an issue both sides may agree on, a supply contract, a startup acquisition, a license with a contingent payment, sharing chores, matching a power profile, splitting piles of different sizes, and planning a trip together.

| Type | Title | Roles (participant first) |
|------|-------|-------|
| [`Lease`](#lease) | Apartment Lease | Tenant, Landlord |
| [`Supply`](#supply) | Bicycle Parts Supply | Maker, Supplier |
| [`Acquisition`](#acquisition) | Startup Acquisition | Founders, Acquirer |
| [`License`](#license) | Medical Device License | Inventor, Firm |
| [`Chores`](#chores) | Sharing the Housework | human, agent |
| [`Energy`](#energy) | Day-Ahead Power Plan | Bakery, Supplier |
| [`Estate`](#estate) | Dividing an Estate | human, agent |
| [`CityTrip`](#citytrip) | Weekend City Trip | Visitor, Host |

## The scenarios

### Trade

A buyer and a seller agree on a quantity and a unit price. Each has a target quantity, penalties for too little or too much, and a non-linear value for money.

See the generator's own description in the *Scenario Info* tool.

### Island

Two people stranded on an island divide eight survival items.

See the generator's own description in the *Scenario Info* tool.

### Grocery

Two people who bought fruit together divide it.

See the generator's own description in the *Scenario Info* tool.

### Furniture

**Used Armchair Sale.** In this scenario, a buyer and a seller negotiate the sale of a used armchair: the price, who moves it and how it is paid.

**The Domain** There are three issues: the price of the armchair, who moves it to the buyer's home and how the buyer pays.

| Role | Description |
|------|-------------|
| Buyer (participant by default) | the person who wants to buy the armchair |
| Seller | the person selling the armchair |

| Issue | Options | Description |
|-------|---------|-------------|
| Price | $50, $65, $80, $95, $110, $125, $140, $155 | The price of the armchair |
| Pickup | Buyer collects, Seller delivers | Who moves the chair to the buyer's home |
| Payment | Cash on pickup, Transfer this week, Two instalments | How the buyer pays |

*No deal:* Without a deal the buyer buys a chair elsewhere and the seller sells to a second-hand shop.

*Source:* Adapted from the MIT AI Negotiation Competition (2025).

### Lease

**Apartment Lease.** In this scenario, a landlord and a tenant negotiate the lease of an apartment: the rent, the deposit, the move-in date and the lease length.

**The Domain** There are four issues: the monthly rent, the security deposit, the move-in date and how long the lease runs.

| Role | Description |
|------|-------------|
| Landlord | the owner of the apartment |
| Tenant (participant by default) | the person who wants to rent the apartment |

| Issue | Options | Description |
|-------|---------|-------------|
| Rent | $2,800/month, $3,000/month, $3,200/month, $3,400/month, $3,600/month | Monthly rent |
| Deposit | $0, $1,000, $2,000, $3,000, $4,000 | Security deposit paid at signing |
| Move-in date | 1 May, 15 May, 1 June, 15 June, 1 July | When the lease starts (rent is paid from this date) |
| Lease length | Month to month, 6 months, 1 year, 18 months, 2 years | How long the lease runs |

*No deal:* Without a deal the tenant keeps looking and the landlord keeps advertising the apartment.

*Source:* Adapted from the MIT AI Negotiation Competition (2025). The rental-house domain of ANAC 2012 is a similar case.

### Consulting

**Summer Consulting Contract.** In this scenario, a consultant and a client negotiate a summer consulting contract: the fee, the expense budget, the travel policy and how often the consultant invoices.

**The Domain** There are four issues: the fee for the summer, the expense budget, how the consultant may travel and how often the consultant sends an invoice.

| Role | Description |
|------|-------------|
| Client | the startup hiring the consultant |
| Consultant (participant by default) | the freelance consultant |

| Issue | Options | Description |
|-------|---------|-------------|
| Fee | $25,000, $30,000, $35,000, $40,000, $45,000 | Lump-sum fee for the summer |
| Expense budget | $0, $5,000, $10,000, $15,000, $20,000 | Money the consultant may spend on research and help |
| Travel | Train or bus only, Economy flights, Premium economy, Business class | How the consultant may travel to client sites |
| Invoicing | Weekly, Every two weeks, Monthly, At the end | How often the consultant sends an invoice |

*No deal:* Without a deal the startup hires another consultant and the consultant takes other work.

*Source:* Adapted from the MIT AI Negotiation Competition (2025).

### JobOffer

**Job Offer.** In this scenario, a recruiter and a candidate negotiate a job offer: salary, signing bonus, start date, work location and vacation days.

**The Domain** There are five issues: the yearly salary, a signing bonus, the start date, where the candidate works and the number of vacation days.

| Role | Description |
|------|-------------|
| Candidate (participant by default) | the person the company wants to hire |
| Recruiter | the person hiring for the company |

| Issue | Options | Description |
|-------|---------|-------------|
| Salary | $90,000, $97,500, $105,000, $112,500, $120,000 | Yearly base salary |
| Signing bonus | $0, $5,000, $10,000, $15,000, $20,000 | One-time bonus paid when the candidate starts |
| Start date | In 2 weeks, In 1 month, In 2 months, In 3 months | When the candidate starts |
| Location | Headquarters, Regional office, Mostly remote | Where the candidate works |
| Vacation days | 15 days, 20 days, 25 days, 30 days | Paid vacation days per year |

*No deal:* Without a deal the company hires its second choice and the candidate keeps looking.

*Source:* Adapted from the MBA negotiation cases of the PieArena benchmark (2026). Job offers also appear in ANAC 2025 (job hunt) and the MIT competition.

### License

**Medical Device License.** In this scenario, an inventor and a firm negotiate a license for a medical device: an upfront payment, a payment if regulators approve the device, a royalty and exclusivity.

**The Domain** There are four issues: the payment at signing, a payment made only if regulators approve the device, the royalty on sales and how exclusive the license is. The two sides may estimate the chance of approval differently (see your hints).

| Role | Description |
|------|-------------|
| Firm | the firm that wants to develop and sell the device |
| Inventor (participant by default) | the inventor who owns the patent |

| Issue | Options | Description |
|-------|---------|-------------|
| Upfront payment | $0.5M, $1.0M, $1.5M, $2.0M, $2.5M | Paid at signing |
| Approval payment | $0M, $2M, $4M, $6M, $8M | Paid only if regulators approve the device |
| Royalty | 0%, 2%, 4%, 6% | Share of sales paid to the inventor |
| Exclusivity | Non-exclusive, Exclusive in one region, Worldwide exclusive | Whether the inventor may license the device to others |

*No deal:* Without a deal the inventor keeps looking for a partner and the firm drops the project.

*Source:* Adapted from the MBA negotiation cases of the PieArena benchmark (2026).

### HomeRepair

**Roof Repair Quote.** In this scenario, a homeowner and a contractor negotiate a roof repair: the price, the start, the warranty and who clears up.

**The Domain** There are four issues: the price of the job, when the work starts, how long the work is guaranteed and who removes the debris.

| Role | Description |
|------|-------------|
| Contractor | the roofer who does the job |
| Homeowner (participant by default) | the owner of the house |

| Issue | Options | Description |
|-------|---------|-------------|
| Price | $4,000, $4,500, $5,000, $5,500, $6,000, $6,500 | Total price of the job |
| Start | This week, Next week, In two weeks, Next month | When the work starts |
| Warranty | No warranty, 6 months, 1 year, 2 years | How long the contractor guarantees the work |
| Cleanup | Homeowner clears up, Contractor clears up | Who removes the old roofing and debris |

*No deal:* Without a deal the homeowner hires another contractor and the contractor takes other jobs.

*Source:* Adapted from the MBA negotiation cases of the PieArena benchmark (2026). (the service-quote case).

### Supply

**Bicycle Parts Supply.** In this scenario, a bicycle maker and a parts supplier negotiate a supply contract: the unit price, the delivery time, the payment terms and how defects are handled.

**The Domain** There are four issues: the price per part, the delivery time, when the maker pays and how defective parts are handled.

| Role | Description |
|------|-------------|
| Maker (participant by default) | the company that builds bicycles and buys the parts |
| Supplier | the company that makes and sells the parts |

| Issue | Options | Description |
|-------|---------|-------------|
| Unit price | $3.50, $3.70, $3.90, $4.10, $4.30 | Price per part |
| Delivery | 20 days, 30 days, 45 days, 60 days | Days from order to delivery |
| Payment | On delivery, 30 days after delivery, 60 days after delivery | When the maker pays |
| Returns | Full refund for defects, 5% defects tolerated, 10% defects tolerated | How defective parts are handled |

*No deal:* Without a deal the maker buys from another supplier at a higher price and the supplier sells its capacity elsewhere.

*Source:* Adapted from a domain of the ANAC Automated Negotiation League (ANAC 2010, the bicycle-parts supply domain).

### Acquisition

**Startup Acquisition.** In this scenario, a company and the founders of a startup negotiate the sale of the startup: the price, the intellectual property, the founders' equity and roles, the staff's terms and past liability.

**The Domain** There are six issues: the price, who owns the intellectual property, the founders' shares in the buyer, the founders' jobs after the sale, the terms for the startup's staff and who answers for claims from before the sale.

| Role | Description |
|------|-------------|
| Acquirer | the company buying the startup |
| Founders (participant by default) | the founders selling the startup |

| Issue | Options | Description |
|-------|---------|-------------|
| Price | $1M, $2.5M, $5M, $8M | Price paid for the company |
| IP | Buyer gets all IP, Buyer gets patents, founders keep know-how, Founders keep IP, buyer licenses it | Who owns the intellectual property |
| Founders' equity | 0%, 2%, 5% | Shares of the buyer given to the founders |
| Founders' roles | No roles, Advisory roles, Leadership roles | Jobs for the founders after the deal |
| Staff terms | Same terms, Retention bonuses, 15% raise, Restructuring | What happens to the startup's employees |
| Liability | Founders keep past liability, Buyer takes all liability | Who answers for claims from before the sale |

*No deal:* Without a deal the buyer develops the technology itself and the founders raise money from investors.

*Source:* Adapted from a domain of the ANAC Automated Negotiation League (ANAC 2011 and 2012, the company-acquisition domain).

### Chores

**Sharing the Housework.** In this scenario, two flatmates negotiate who does each of five chores: one of them, both taking turns, or paid help whose cost they split.

**The Domain** There are five issues, one per chore. Each chore can be done by you, by your partner, by both taking turns (*Shared*) or by paid help whose cost you split. The options *human* and *agent* mean you and your partner.

| Role | Description |
|------|-------------|
| agent | one of the two flatmates |
| human (participant by default) | one of the two flatmates |

| Issue | Options | Description |
|-------|---------|-------------|
| Cooking | human, agent, Shared, Paid help | Who does the cooking |
| Dishes | human, agent, Shared, Paid help | Who does the dishes |
| Laundry | human, agent, Shared, Paid help | Who does the laundry |
| Cleaning | human, agent, Shared, Paid help | Who does the cleaning |
| Groceries | human, agent, Shared, Paid help | Who does the groceries |

*No deal:* Without a deal the chores keep piling up and the two of you keep arguing.

*Source:* Adapted from a domain of the ANAC Automated Negotiation League (ANAC 2012, the housekeeping domain).

### Energy

**Day-Ahead Power Plan.** In this scenario, a bakery and its power supplier negotiate tomorrow's power plan: how many kW are reserved in each part of the day and the price per kWh.

**The Domain** There are five issues: the power reserved for the night, the morning, the afternoon and the evening (0 to 100 kW each), and the price per kWh.

| Role | Description |
|------|-------------|
| Bakery (participant by default) | the bakery that needs power tomorrow |
| Supplier | the company that supplies the power |

| Issue | Options | Description |
|-------|---------|-------------|
| Night | 0 kW, 25 kW, 50 kW, 75 kW, 100 kW | Power reserved for the night |
| Morning | 0 kW, 25 kW, 50 kW, 75 kW, 100 kW | Power reserved for the morning |
| Afternoon | 0 kW, 25 kW, 50 kW, 75 kW, 100 kW | Power reserved for the afternoon |
| Evening | 0 kW, 25 kW, 50 kW, 75 kW, 100 kW | Power reserved for the evening |
| Price | $0.10/kWh, $0.12/kWh, $0.14/kWh, $0.16/kWh, $0.18/kWh | Price per kWh for all reserved power |

*No deal:* Without a deal the bakery buys on the spot market at a much higher price and the supplier sells less.

*Source:* Adapted from a domain of the ANAC Automated Negotiation League (ANAC 2011 and 2012, the energy domain; reduced to four blocks).

### HealthFund

**Tobacco Control Fund.** In this scenario, a donor country and a recipient country negotiate a tobacco-control fund and the aid and trade terms that come with it.

**The Domain** There are five issues: the size of the fund, whether the donor cuts its other aid, the recipient's import tariffs, the donor's tobacco imports and the forum that follows up on other health issues.

| Role | Description |
|------|-------------|
| Donor | the country that pays into the fund |
| Recipient (participant by default) | the tobacco-growing country that receives the fund |

| Issue | Options | Description |
|-------|---------|-------------|
| Fund size | $10B, $50B, $100B | Money paid into the health fund |
| Other aid | No cut to other aid, Cut by half the fund, Cut by the whole fund | Whether the donor cuts its other aid to the recipient |
| Recipient's tariffs | Lower tariffs, Unchanged tariffs, Higher tariffs | The recipient's tariffs on imports from the donor |
| Donor's imports | Fewer tobacco imports, Unchanged imports, More tobacco imports | The donor's tobacco imports from the recipient |
| Health forum | A new health fund, A committee to plan a fund, A committee to set an agenda, No forum | What follows up on other health issues |

*No deal:* Without a deal there is no fund, and the two countries keep their current policies.

*Source:* Adapted from a domain of the ANAC Automated Negotiation League (ANAC 2010, the tobacco-control domain).

### UsedCar

**Used Car Purchase.** In this scenario, a buyer and a dealer negotiate the purchase of a used car: the price and the extras that come with it.

**The Domain** There are five issues: the price, the infotainment system, the air conditioning, a tow hitch and the warranty.

| Role | Description |
|------|-------------|
| Buyer (participant by default) | the person who wants to buy the car |
| Dealer | the dealer selling the car |

| Issue | Options | Description |
|-------|---------|-------------|
| Price | $13,000, $15,000, $17,000, $19,000, $21,000 | Price of the car |
| Infotainment | Basic radio, Touchscreen, Touchscreen with navigation | The audio and navigation system |
| Air conditioning | Manual air conditioning, Climate control | The air conditioning |
| Tow hitch | No tow hitch, Tow hitch fitted | Whether a tow hitch is fitted |
| Warranty | No warranty, 6 months, 1 year | How long the dealer guarantees the car |

*No deal:* Without a deal the buyer looks at other dealers and the dealer waits for another buyer.

*Source:* Adapted from a domain of the ANAC Automated Negotiation League (ANAC 2011, the car domain).

### CityTrip

**Weekend City Trip.** In this scenario, a host and a visiting friend plan a weekend trip: the main activity, the start day, the length of the visit, transport and food.

**The Domain** There are five issues: the main activity, the day the visit starts, how long it lasts, how to get around and where to eat.

| Role | Description |
|------|-------------|
| Host | the friend who lives in the city |
| Visitor (participant by default) | the friend who visits |

| Issue | Options | Description |
|-------|---------|-------------|
| Activity | Museums, Shopping, Canal tour, Live music | The main thing to do |
| Day | Friday, Saturday, Sunday | The day the visit starts |
| Length | One day, Two days, Three days | How long the visit lasts |
| Transport | Public transport, Rented bikes, Car | How to get around |
| Food | Street food, Local restaurants, Fine dining | Where to eat |

*No deal:* Without a plan the visit is cancelled.

*Source:* Adapted from a domain of the ANAC Automated Negotiation League (ANAC 2011, the city-trip domain).

### LaborContract

**Police Labor Contract.** In this scenario, a police union and a city negotiate a labor contract: pay, vacation, patrols, promotions and the civilian review board.

**The Domain** There are five issues: the pay raise, extra vacation days, how many officers ride in a patrol car, new sergeant positions and the civilian review board.

| Role | Description |
|------|-------------|
| City | the city |
| Union (participant by default) | the police officers' union |

| Issue | Options | Description |
|-------|---------|-------------|
| Pay raise | 0%, 2%, 4%, 6%, 8% | Pay raise for all officers |
| Extra vacation | 0 days, 2 days, 4 days | Extra vacation days per year |
| Patrols | Unchanged, Two-officer patrols at night, Two-officer patrols always | How many officers ride in a patrol car |
| New sergeants | 0, 4, 8 | New sergeant positions |
| Review board | Keep the civilian review board, Add officers to the board, Disband the board | The civilian board that reviews complaints |

*No deal:* Without a deal the dispute goes to arbitration, which neither side controls.

*Source:* Adapted from the police-union domain shipped with the Genius platform used by the ANAC Automated Negotiation League (reduced to five issues).

### Resources

**Resource Exchange.** In this scenario, two traders split a shipment of gold, iron, bananas and spices (five items of each).

**The Domain** There are four issues, one per good: how many of its five items you get; your partner gets the rest. Each item is worth some points to you (see your hints) and different points to your partner.

| Role | Description |
|------|-------------|
| agent | one of the two traders |
| human (participant by default) | one of the two traders |

| Issue | Options | Description |
|-------|---------|-------------|
| Gold | 0, 1, 2, 3, 4, 5 | How many of the 5 gold bars you get |
| Iron | 0, 1, 2, 3, 4, 5 | How many of the 5 iron bars you get |
| Bananas | 0, 1, 2, 3, 4, 5 | How many of the 5 crates of bananas you get |
| Spices | 0, 1, 2, 3, 4, 5 | How many of the 5 sacks of spices you get |

*No deal:* Without a deal the shipment is sold off at a loss.

*Source:* Adapted from the item-split games of the IAGO platform (ANAC Human-Agent League). (the resource-exchange demonstration game).

### Estate

**Dividing an Estate.** In this scenario, two heirs divide a collection: six vinyl records, three clocks, two paintings and three books.

**The Domain** There are four issues, one per kind of item: how many you get; your partner gets the rest. The piles have different sizes. Each item is worth some points to you (see your hints) and different points to your partner.

| Role | Description |
|------|-------------|
| agent | one of the two heirs |
| human (participant by default) | one of the two heirs |

| Issue | Options | Description |
|-------|---------|-------------|
| Records | 0, 1, 2, 3, 4, 5, 6 | How many of the 6 vinyl records you get |
| Clocks | 0, 1, 2, 3 | How many of the 3 antique clocks you get |
| Paintings | 0, 1, 2 | How many of the 2 paintings you get |
| Books | 0, 1, 2, 3 | How many of the 3 rare books you get |

*No deal:* Without a deal the collection is auctioned and the money split, which neither of you wants.

*Source:* Adapted from the item-split games of the IAGO platform (ANAC Human-Agent League). (the piles of different sizes follow the 2017 ANAC Human-Agent League game).
