# Operations agent playbook instruction

**Item:** `ColdChainMonitor` · Real-Time Intelligence → Operations agent
**Data source:** `LakeshoreRetailOntology`

This exact wording has been verified to produce correct aggregated totals. Earlier phrasings failed
in four different ways — see below.

```
TRIGGER: Monitor the Freezer class, temperatureC property. Alert when
temperatureC rises above -18.

DATA THE AGENT NEEDS: use these ontology entity types and relationships.
- Freezer (FreezerId, Model, minSafeTempC, temperatureC)
- Store (StoreId, StoreName, City) — reached from Freezer via operatedBy
- InventoryItem (UnitsOnHand, UnitCostUSD, ValueUSD) — reached from Freezer
  via storedIn
- Products (ProductId, ProductName) — reached from InventoryItem via of

MESSAGE: in every alert, name the freezer, the store that operates it, the
temperatureC value that triggered it, and when it was recorded.
Then state the stock at risk as THREE TOTALS ONLY, aggregated across all
InventoryItem rows stored in that freezer: the number of distinct products,
the total UnitsOnHand, and the total ValueUSD.
Do not list individual products. Do not name any single product.

RECOMMENDATION: suggest moving the stock to another freezer in the same store
if one is operating normally.
```

## Four failure modes this wording fixes

1. **"above its minimum safe temperature"** → *"No playbook generated."* Triggers compare a field
   against a **constant only**. Write the number.
2. **Asking for a product list** → the alert named **one arbitrary product**, a different one each
   run. The generated query returns one row per `InventoryItem` and the message renders a single row.
   Asking for three totals, with "do not list individual products", is what makes it aggregate.
3. **Naming only the Freezer class** → the **business term glossary collapsed to Freezer alone**,
   losing Store, InventoryItem and Products. The DATA section restores them.
4. **Prose instead of entity names** — "aggregated across all products in that freezer" instead of
   "all InventoryItem rows stored in that freezer" — produced single-row output again.

## After every regeneration, check three things

1. The **glossary lists four classes**: Freezer, Store, InventoryItem, Products. Fastest feedback —
   check this before triggering a breach.
2. The rule property is **`temperatureC`**, not `Freezer_json`.
3. There are **no duplicate rules**. Regeneration adds rather than replaces.

Then **stop regenerating** and screenshot the working configuration. Generation is non-deterministic.
