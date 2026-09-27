# Fabric IQ + Foundry: The Semantic Backbone of Enterprise AI Agents

Everything you need to rebuild the demo from my session at the
**European Microsoft Fabric + SQL Community Conference**, Barcelona 2026 — including every mistake I
made getting there.

---

## The argument

Enterprise AI doesn't fail on model capability. It fails on **shared understanding**. Agents give
inconsistent answers because the systems underneath them interpret business definitions differently,
and no amount of model capability fixes a disagreement about what a word means.

The demo makes that concrete with a cold chain incident at a fictional ice-cream retailer. A freezer
warms above −18 °C on a Saturday afternoon. Facilities sees an alarm. The store manager hears
beeping. Quality finds out if someone phones. Finance finds out as a write-off.

All the data exists. None of it is connected.

**The question the demo answers in one sentence:**

> *"Which products are at risk right now, in which freezer and store, and worth how much?"*

---

## What you'll build

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

One `Freezer` entity bound to **two engines** — a lakehouse table for its static properties, an
eventhouse table for its live telemetry. Three consumers of one definition. Nothing modelled twice.

**→ [Start with SETUP.md](SETUP.md)** · about 3–4 hours the first time.

---

## What's in here

| Path | What it is |
|---|---|
| [`SETUP.md`](SETUP.md) | The full build guide, from empty workspace to working agents, with a **troubleshooting section** at the end |
| [`scripts/generate_lakeshore_data.py`](scripts/generate_lakeshore_data.py) | Deterministic sample data generator — stdlib only |
| [`scripts/freezer_simulator.py`](scripts/freezer_simulator.py) | Streams live telemetry into an Eventstream; type `breach` to warm a freezer |
| [`agents/`](agents/) | The instructions for all four agents, with notes on **why** each block exists |
| [`queries/validation.kql`](queries/validation.kql) | Checks the telemetry loaded correctly |
| [`queries/verification.sql`](queries/verification.sql) | Verifies agent answers against the source |

---

## Quick start

```bash
git clone <this repo>
cd scripts
python generate_lakeshore_data.py          # writes 6 CSVs to lakeshore_data/
pip install -r requirements.txt            # only needed for the simulator
```

Then follow [SETUP.md](SETUP.md) from section 4.

---

## Prerequisites, briefly

- **Paid Fabric capacity, F2 or higher.** A trial capacity blocks AI features.
- A workspace that is **not My Workspace** — ontology generation is blocked there.
- Four **tenant settings** enabled by an admin (listed in SETUP.md).
- **Microsoft Foundry** if you want the Foundry agent. Sections 1–10 work without it.

> **On cost.** Ontology AI has its own meter at four times the general Copilot rate, and an
> operations agent bills 0.46 CU hours per hour while it's running. On an F2 that's roughly **108 AI
> questions a day** before the capacity is exhausted. Build on F2 if you must, but stop the simulator
> and the operations agent when you aren't using them. SETUP.md has the arithmetic.

---

## Honest notes

This is preview software, and the guide says so where it matters:

- **No versioning** for ontology items. One live ontology, edits take effect immediately, no rollback
  and no dev-to-prod promotion.
- **Generation binds data from Direct Lake models only.** Import mode gives you definitions and no
  data. DAX measures don't come across at all.
- **The ontology path through Foundry is delegated-only** — every consumer needs their own access in
  Fabric. There's no service principal option. To serve an application, use a published data agent's
  MCP endpoint instead.
- **Agents can be confidently wrong.** During testing, a list question dropped a row and returned a
  total that was internally consistent and incorrect. `queries/verification.sql` exists for that
  reason. Check any number you intend to say out loud.

The troubleshooting section in SETUP.md has around thirty of these, each with its cause and fix.

---

## Credits

The Lakeshore Retail scenario is adapted from Microsoft's own
[ontology tutorial](https://learn.microsoft.com/fabric/iq/ontology/tutorial-0-introduction).
The sample data here is generated rather than Microsoft's, so the figures differ.

Built by [Hugo Barona](https://www.linkedin.com/in/hugomiguelbarona/) — Cloudnitio, Ireland.

## Licence

[MIT](LICENSE). The sample data is synthetic and the scenario is fictional — use either freely.
