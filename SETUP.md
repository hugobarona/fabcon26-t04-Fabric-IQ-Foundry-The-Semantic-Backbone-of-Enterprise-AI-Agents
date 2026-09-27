# Setup guide — build the Lakeshore Retail demo yourself

This guide takes you from an empty Fabric workspace to a working ontology with three agents
consuming it. Allow **3–4 hours** the first time.

The scenario: a fictional ice-cream retailer with three European stores. A freezer warms above
−18 °C, and the question you want answered in one sentence is:

> *"Which products are at risk right now, in which freezer and store, and worth how much?"*

---

## Contents

1. [What you'll build](#1-what-youll-build)
2. [Prerequisites](#2-prerequisites)
3. [Generate the sample data](#3-generate-the-sample-data)
4. [Create the lakehouse](#4-create-the-lakehouse)
5. [Create the eventhouse](#5-create-the-eventhouse)
6. [Stream live telemetry](#6-stream-live-telemetry)
7. [Create the semantic model](#7-create-the-semantic-model)
8. [Generate the ontology](#8-generate-the-ontology)
9. [Bind the live telemetry](#9-bind-the-live-telemetry)
10. [Create the Fabric data agents](#10-create-the-fabric-data-agents)
11. [Create the Foundry agent](#11-create-the-foundry-agent)
12. [Create the operations agent](#12-create-the-operations-agent)
13. [Verify everything](#13-verify-everything)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. What you'll build

```
LakeshoreRetailLH  (lakehouse, static)  ─┐
                                         ├─→  LakeshoreRetailOntology  ─┬─→  3 Fabric data agents
LakeshoreRetailEH  (eventhouse, live)   ─┘    Store · Products          ├─→  Foundry agent (Foundry IQ)
        ▲                                     SaleEvent · Freezer       └─→  Operations agent → Teams
        │                                     InventoryItem
LakeshoreRetailStream  (eventstream)
        ▲
freezer_simulator.py
```

Five entity types, five relationships (`from`, `sold`, `of`, `storedIn`, `operatedBy`), and one
`Freezer` entity bound to **two different engines** — a lakehouse table for its static properties and
an eventhouse table for its live telemetry. That dual binding is the point of the whole demo.

---

## 2. Prerequisites

| | Requirement |
|---|---|
| **Fabric capacity** | **Paid F2 or higher.** A trial capacity blocks AI features (data agents, Copilot). F2 works but is tight — see [capacity notes](#capacity-and-throttling). |
| **Workspace** | A normal workspace, **not My Workspace** — ontology generation is blocked there. |
| **Region** | Keep the workspace, its capacity and all items in **one region**. A data agent cannot query a source whose capacity is in a different region. |
| **Tenant settings** | Enabled by a Fabric administrator (below). |
| **Azure** | An Azure subscription with **Microsoft Foundry** for the Foundry agent (optional — sections 1–10 work without it). |
| **Local** | Python 3.9+ and `pip install azure-eventhub`. |

### Tenant settings a Fabric admin must enable

- **Enable Ontology item (preview)**
- **Users can use Copilot and other features powered by Azure OpenAI**
- **Data sent to Azure OpenAI can be processed outside your capacity's geographic region**
- **Data sent to Azure OpenAI can be stored outside your capacity's geographic region**

### Also check

- **Inbound public access** must be **enabled** on the workspace holding the lakehouse. If it's
  disabled, the ontology is created successfully but **entity types get no data bindings** — a silent
  failure that looks like an empty ontology.

---

## 3. Generate the sample data

```bash
cd scripts
python generate_lakeshore_data.py
```

Stdlib only, no dependencies. Writes six CSVs to `lakeshore_data/`:

| File | Rows | Notes |
|---|---|---|
| `DimStore.csv` | 3 | Paris, Berlin, Amsterdam |
| `DimProducts.csv` | 15 | |
| `Freezer.csv` | 5 | All with `minSafeTempC = -18.0` |
| `FactSales.csv` | ~3,000 | 90 days |
| `FactInventory.csv` | 45 | Stock per freezer |
| `FreezerTelemetry.csv` | 43,200 | 30 days at 5-minute intervals, ending **now** |

The generator is seeded, so the data is reproducible apart from dates. Two freezers have a defrost
fault (humidity below 46%) and two have historical temperature excursions — those make the demo
questions return meaningful subsets rather than everything.

---

## 4. Create the lakehouse

1. **+ New item → Lakehouse**, named `LakeshoreRetailLH`.
2. **Get data → Upload files**, and upload **five** CSVs — everything except `FreezerTelemetry.csv`.
3. For each file: **… → Load to Tables → New table**, keeping defaults.

You should end up with five tables, lowercased: `dimstore`, `dimproducts`, `factsales`,
`factinventory`, `freezer`.

> **Check the data types.** `RevenueUSD`, `ValueUSD`, `UnitCostUSD` and `minSafeTempC` must load as
> **double**. Fabric Graph doesn't support the `Decimal` type, and decimal columns come back as
> **nulls** in every ontology query. The generator writes these values with decimal points
> specifically to avoid that.

---

## 5. Create the eventhouse

1. **+ New item → Eventhouse**, named `LakeshoreRetailEH`. A KQL database of the same name is created.
2. Open the KQL database → **Get data → Local file**.
3. Create a **new table** called `FreezerTelemetry` from `FreezerTelemetry.csv`, keeping defaults.

Verify:

```kql
FreezerTelemetry
| summarize Rows = count(), Freezers = dcount(freezerId), Latest = max(timestamp)
```

Expect ~43,200 rows and 5 freezers.

---

## 6. Stream live telemetry

Historical data alone can't show that the ontology queries live. The simulator fixes that.

1. **+ New item → Eventstream**, named `LakeshoreRetailStream`.
2. Add a source: **Custom endpoint**.
3. Add a destination: **Eventhouse** → `LakeshoreRetailEH` → **existing table** `FreezerTelemetry`.
   Map the columns by name.
4. From the Eventstream **Live view**, select the custom endpoint → **Details** → **Event Hub** tab →
   **SAS Key Authentication** → copy *Connection string-primary key*.
5. Run the simulator:

```powershell
$env:FREEZER_ES_CONNECTION_STRING = "<the connection string>"
python scripts/freezer_simulator.py
```

```bash
export FREEZER_ES_CONNECTION_STRING="<the connection string>"
python scripts/freezer_simulator.py
```

It streams all five freezers every 30 seconds. Commands:

| Command | Effect |
|---|---|
| `breach [freezerId]` | Warms one freezer past −18 °C (defaults to the first) |
| `recover` | Returns all freezers to normal |
| `status` | Prints current state |
| `quit` | Stops |

> **Never commit the connection string.** It contains a live SAS key. Use the environment variable.

---

## 7. Create the semantic model

1. From `LakeshoreRetailLH`, select **New semantic model**.
2. Name it `LakeshoreRetailModel`, and select **all five tables**.
3. **Confirm.**

> **It must be Direct Lake.** The creation dialogue says "Direct Lake semantic model name" — that's
> your confirmation; the mode isn't shown in settings afterwards. **Import mode generates ontology
> definitions but no data bindings**, and DirectQuery generates neither.

Open the model in **Editing** mode → **Manage relationships** → create five:

| From | To | Cardinality | Cross-filter | Active |
|---|---|---|---|---|
| `factsales.StoreId` | `dimstore.StoreId` | Many to one | Single | Yes |
| `factsales.ProductId` | `dimproducts.ProductId` | Many to one | Single | Yes |
| `factinventory.ProductId` | `dimproducts.ProductId` | Many to one | Single | Yes |
| `factinventory.FreezerId` | `freezer.FreezerId` | Many to one | Single | Yes |
| `freezer.StoreId` | `dimstore.StoreId` | Many to one | Single | Yes |

> **Do not add `factinventory → dimstore`.** It looks natural but creates a second path to `dimstore`,
> Power BI deactivates one relationship to resolve the ambiguity, and **inactive relationships don't
> generate into the ontology**. Inventory reaches Store through Freezer, which is also the more
> truthful statement: stock sits in a freezer, and the freezer belongs to a store.

All five must show as **active** (solid lines).

---

## 8. Generate the ontology

From the semantic model, select **Generate Ontology**. Name it `LakeshoreRetailOntology` —
letters, numbers and underscores only.

### Rename the entity types

Generated names match the table names, lowercased. For each: select it → **View Entity Type details**
→ **… → Rename**.

| Generated | Rename to | Why |
|---|---|---|
| `dimstore` | `Store` | |
| `dimproducts` | **`Products`** | **Plural.** `PRODUCT` is a GQL reserved word |
| `factsales` | `SaleEvent` | |
| `factinventory` | `InventoryItem` | |
| `freezer` | `Freezer` | |

### Add the missing keys

The three dimension tables get keys automatically because they sit on the "one" side of a
relationship. The two fact tables don't:

- `SaleEvent` → add **`SaleId`**
- `InventoryItem` → add **`InventoryId`**

**Configure → Define entity type key → select the column → Save.**

### Bind the relationships

Generated relationships arrive **defined but not bound**. Select each on the canvas and complete it:

| Generated name | Rename to | Mapping table | Origin key | Target key |
|---|---|---|---|---|
| `factsales_has_dimstore` | `from` | `factsales` | `SaleId` | `StoreId` |
| `factsales_has_dimproducts` | `sold` | `factsales` | `SaleId` | `ProductId` |
| `factinventory_has_dimproducts` | `of` | `factinventory` | `InventoryId` | `ProductId` |
| `factinventory_has_freezer` | `storedIn` | `factinventory` | `InventoryId` | `FreezerId` |
| `freezer_has_dimstore` | `operatedBy` | `freezer` | `FreezerId` | `StoreId` |

### Resulting model

```
                 Store
                ▲     ▲
       from     │     │  operatedBy
                │     │
          SaleEvent  Freezer
                │     ▲
        sold    │     │  storedIn
                ▼     │
             Products ◄── of ── InventoryItem
```

---

## 9. Bind the live telemetry

This is the step that makes the demo worth watching — one entity, two engines.

1. Open **`Freezer`** → **View Entity Type details** → **Configure**
2. **Manage property bindings → Add binding and properties**
3. **Add data binding → Eventhouse table or materialized view**
4. Select `LakeshoreRetailEH` → **Add** → table `FreezerTelemetry` → **Add**
5. A **Timeseries data** section appears. Set **Timestamp column** = `timestamp`
6. In **Properties** you'll see an error on `storeId` — it duplicates the existing static `StoreId`.
   **Delete it** with the trash icon.
   > Watch the casing: telemetry uses `freezerId` / `storeId` lowercase; the static binding uses
   > `FreezerId` / `StoreId`. Property names must be unique across entity types and consistent in type.
7. Keep `temperatureC`, `humidityPct`, `doorOpen`
8. **Save** → confirm → **Cancel** to close

`Freezer` now has **two bindings**. Confirm on **Manage property bindings → Manage bindings**, which
shows both sources and their column mapping side by side.

### Refresh the graph

Workspace → the **graph model** child item of the ontology → **… → Refresh now**.

> **Two data planes, and the difference matters.** Static lakehouse bindings are **materialised into
> the graph** and need a refresh when the data changes. Eventhouse time-series bindings are **queried
> live with KQL at question time** and need no refresh. That's why the agent returns a temperature
> from seconds ago while the store and threshold come from the last rebuild.

There is **no Publish action** for ontology items, and none is needed.

---

## 10. Create the Fabric data agents

Create three: `LakeshoreSalesAgent`, `LakeshoreInventoryAgent`, `LakeshoreMaintenanceAgent`.

For each: **+ New item → Data agent** → add the data source `LakeshoreRetailOntology` → select the
entity types it needs → paste its instructions → **Publish**.

| Agent | Entity types | Instructions |
|---|---|---|
| Maintenance | Freezer, Store | [`agents/maintenance-agent.md`](agents/maintenance-agent.md) |
| Inventory | InventoryItem, Products, Freezer, Store | [`agents/inventory-agent.md`](agents/inventory-agent.md) |
| Sales | SaleEvent, Products, Store | [`agents/sales-agent.md`](agents/sales-agent.md) |

> **Publish after every change.** The published version is what gets consumed; edits sitting in the
> draft have no effect on answers.

> **Scope is two-layered.** Entity selection narrows what the agent can see; instructions shape how
> it behaves. Use both — instructions alone are a request, not a boundary.

---

## 11. Create the Foundry agent

In the [Microsoft Foundry portal](https://ai.azure.com):

1. Create a **knowledge base** — this is Foundry IQ.
2. Add a **knowledge source** of type **Fabric IQ (remote)** → **Ontology**.
3. Pick `LakeshoreRetailOntology` from the OneLake catalog.
4. Create an **agent** and attach the knowledge base.
5. Set the retrieval reasoning effort to **low** or **medium** — `minimal` is not supported for
   Fabric sources.

**No code, no SDK, no app registration** for the portal path.

### Identity, and its consequence

The ontology knowledge source uses **on-behalf-of (OBO)**: the query runs as the **signed-in user**.
There is **no service principal option** on this path.

That means every consumer needs their own access to the ontology in Fabric. This pattern is for
**your own people** — employees who never open the Fabric portal. To serve customers, partners or
an application, use a **published data agent's MCP endpoint**, which accepts a service principal.

### Nothing is indexed

The Fabric Ontology knowledge source is a **remote** knowledge source: *"Content is never ingested
into Azure AI Search. Instead, it's retrieved at query time via each platform's native APIs."* The
definition stores only a workspace ID and an ontology ID. That's why live telemetry appears with no
refresh anywhere in the chain.

---

## 12. Create the operations agent

**+ New item → Real-Time Intelligence → Operations agent**, named `ColdChainMonitor`, with data
source `LakeshoreRetailOntology`.

Paste the instruction from [`agents/operations-agent.md`](agents/operations-agent.md), then
**Generate Playbook**.

**Before triggering anything, check the generated result:**

1. The **business term glossary** lists **four classes** — Freezer, Store, InventoryItem, Products.
   If it shows only Freezer, regenerate. This is far faster feedback than waiting for an alert.
2. The rule property is **`temperatureC`**, not `Freezer_json`.
3. There are **no duplicate rules** — regeneration adds rather than replaces.

Then start the agent, trigger `breach F-PAR-02` in the simulator, and wait for the Teams message.

> **Playbook generation is non-deterministic.** Once the rules are correct, **stop regenerating** and
> screenshot the working configuration so you can rebuild it by hand.

> **Cost.** An operations agent bills **0.46 CU hours per hour while active**, about 23% of an F2,
> whether or not anything ever breaches. Stop it when you're not using it.

---

## 13. Verify everything

### The data

```kql
// Lowest humidity per freezer -> two freezers below 46%
FreezerTelemetry | summarize Lowest = round(min(humidityPct),1) by freezerId | order by freezerId asc

// Historical excursions -> two freezers only
FreezerTelemetry | where temperatureC > -18.0
| summarize Breaches = count(), Warmest = round(max(temperatureC),2) by freezerId

// Coverage -> five rows, Latest within the last minute while the simulator runs
FreezerTelemetry
| summarize Readings = count(), Latest = max(timestamp) by freezerId, storeId | order by freezerId asc

// No duplicates -> 0
FreezerTelemetry | summarize n = count() by freezerId, timestamp | where n > 1 | count
```

### The agents

Ask the Foundry agent, each in a **new chat**:

| Question | Expect |
|---|---|
| What is the top product by revenue across all stores? | A single product and a revenue figure |
| What is the lowest humidity ever recorded for each freezer, and which store operates it? | Five rows; two below 46% |
| What is the most recent temperature for F-PAR-01, when was it recorded, and which store operates it? | A reading seconds old, with a timestamp and a store |
| Which freezer has its current temperature above the -18C? | The freezer you breached |

Then, **in the same chat**, follow the last one with:

> Which freezer and store have products at risk right now, how many products, and what is the total
> value at risk?

Corroborate against the source:

```sql
SELECT COUNT(DISTINCT ProductId) AS Products,
       SUM(UnitsOnHand)          AS Units,
       CAST(SUM(ValueUSD) AS DECIMAL(12,2)) AS ValueUSD
FROM factinventory
WHERE FreezerId = 'F-PAR-02';
```

The lakehouse SQL analytics endpoint is a **child item of the lakehouse** in the workspace list, or
the mode switcher at the top-right of the lakehouse explorer. It is *not* under "Analyze data with" —
that's the eventhouse pattern.

---

## 14. Troubleshooting

Everything below was hit while building this. Each entry is the symptom, the cause, and the fix.

### Ontology and bindings

**The ontology generates but entity types have no data bindings.**
Either the semantic model isn't **Direct Lake**, or the lakehouse workspace has **inbound public
access disabled**. Import mode produces definitions only; DirectQuery produces neither. There's a
second reason Import fails even if you bind by hand: import-mode tables are written to OneLake with
**column mapping** enabled, and the ontology graph doesn't support column-mapped delta tables.

**Every query returns nulls for money or temperature columns.**
Those columns loaded as `Decimal`. Fabric Graph doesn't support the `Decimal` type. Reload them as
`double`.

**A relationship is missing from the generated ontology.**
It was **inactive** in the semantic model. Power BI deactivates relationships that create ambiguous
paths, and inactive relationships don't generate. Remove the ambiguity instead.

**Entity type named `Product` behaves strangely.**
`PRODUCT` is a **GQL reserved word**. Use `Products`.

**Shortcuts don't work as binding sources.**
Ontology supports **managed** lakehouse tables only — *"not external tables that show in the
lakehouse but reside in a different location"*. A lakehouse with **OneLake security enabled** can't
be used as a binding source at all.

**New rows don't appear in answers.**
Static bindings are materialised. Refresh the graph model. Time-series bindings don't need this.

**Renaming a lakehouse table breaks the entity type.**
Documented behaviour. Don't rename bound tables.

### Agents

**The agent answers from earlier conversation when retrieval fails.**
Add an instruction: *"If you cannot retrieve current data, say so and stop. Never present an earlier
reading as if it were current."* Without it, a failed retrieval produces a confident wrong answer —
in a breach demo, a cheerful "no breaches".

**A list question drops rows and totals what's left.**
Asking "which products… and what is each worth" returned 8 of 9 and 10 of 11 products in testing,
with a total that was internally consistent and wrong. **Ask for aggregates**: "how many products,
and what is the total value". Verify any number you intend to say out loud.

**"Which freezer is above its minimum safe temperature" returns nothing.**
That's a **field-to-field comparison** (`temperatureC > minSafeTempC`) and NL2Ontology handles it
inconsistently. Name the threshold instead: *"above the -18C"*. Same limitation stops the operations
agent trigger comparing two fields — triggers compare a field against a **constant only**.

**"Which products are at risk right now…" is rejected as an invalid query.**
The ontology has no concept of "at risk". Ask which freezer is above the threshold **first**, in the
same chat, then ask the follow-up. Retrieval instructions don't help: the question is passed to
NL2Ontology **verbatim**, and with the knowledge base in *extract data* mode there's no synthesis
step to instruct.

**A yes/no question errors.**
*"Is 45795 the total revenue for P-ICE-001?"* returns `InvalidAgentRetrievalRequest`. NL2Ontology
translates questions into graph queries, and a verification has nothing to retrieve. Ask
"what is the total revenue for P-ICE-001?" instead.

**Aggregations fail on a data agent.**
Add `Support group by in GQL` to the instructions — a documented workaround.

**Responses are truncated.**
Fabric data agent responses are capped at **25 rows × 25 columns**.

**An agent answers questions it should refuse.**
Check it was **published** after you changed the entity selection or instructions. The published
version is what's consumed.

### Operations agent

**"No playbook generated."**
The instruction asked for a field-to-field comparison. Triggers compare against a **constant**.
Write `-18`, not "its minimum safe temperature".

**The alert names one product instead of totals.**
The generated query returns one row per `InventoryItem` and the message renders a single row. Ask
for **three totals only** and add *"Do not list individual products."* Name the entity and the
relationship explicitly — "aggregated across all **InventoryItem rows stored in** that freezer" —
not "all products".

**The glossary collapses to one class.**
Naming only the trigger class in the instruction loses the others. Add an explicit
"DATA THE AGENT NEEDS" section listing entity types and how each is reached.

**The rule fires repeatedly during one breach.**
The generated condition may be **Is Above** rather than a transition. It re-evaluates each cycle.
Harmless — it reads as persistent monitoring — but recover promptly if you don't want repeats.

**"I don't have any actions available to recommend."**
No action is wired to the agent. Attach a Power Automate flow, or ignore it — posting unprompted is
already acting.

### Capacity and throttling

**Queries start failing; the portal says capacity has exceeded its limits.**
Check the Capacity Metrics app on the **Last 1 hour** view, not Last 24 hours — a 24-hour average
can read healthy while the capacity is exhausted right now.

**Fastest way out of throttling:** **pause and resume the capacity.** Microsoft documents this:
*"If your capacity is being throttled, pausing it stops the throttling and returns your capacity to a
healthy state immediately."* The outstanding smoothed usage is billed immediately.

**After a pause/resume:** the operations agent may come back in a dead state — stop and start it. The
Eventstream's managed namespace also stops resolving while suspended, which surfaces in the simulator
as `getaddrinfo failed` and looks exactly like a network outage.

#### Capacity and throttling

Ontology AI has its **own meter**, four times the general Copilot rate:

| Meter | Rate |
|---|---|
| Ontology AI Operations | **400 CU s** per 1,000 input tokens · **1,600 CU s** per 1,000 output tokens |
| Ontology Modeling | 0.0039 CU/hour per definition, in 30-minute windows after any edit |
| Operations agent compute | 0.46 CU hours per hour while active |
| Eventhouse | Eventhouse UpTime — seconds active × virtual cores |

A request with 2,000 input and 500 output tokens costs **1,600 CU seconds — 0.44 CU hours**. On an
F2 that's roughly **108 questions per day** before the capacity is exhausted, with nothing else
running. AI operations are **background jobs, smoothed over 24 hours**, so overspend appears as a
stubborn baseline rather than a spike.

**Practical advice:** build on F2 if you must, but stop the simulator and the operations agent when
you aren't using them, and expect to scale up for a live demo.

### Simulator

**`getaddrinfo failed` / `ConnectError`.**
DNS can't resolve the Event Hubs endpoint. Either the network dropped, or **the capacity is paused**
and the Eventstream's managed namespace has been deallocated. Check the capacity first.

**The simulator dies on a transient network blip.**
The version in this repo retries with exponential backoff and rebuilds the producer, so it survives
a Wi-Fi drop. It retries forever — if the endpoint is genuinely gone, it will keep trying.

**Telemetry is missing for some freezers.**
All five must stream, or the missing ones flatline in the ontology's time-series tiles.

---

## Licence and attribution

The Lakeshore Retail scenario is adapted from Microsoft's own
[ontology tutorial](https://learn.microsoft.com/fabric/iq/ontology/tutorial-0-introduction).
Sample data here is generated, not Microsoft's.
