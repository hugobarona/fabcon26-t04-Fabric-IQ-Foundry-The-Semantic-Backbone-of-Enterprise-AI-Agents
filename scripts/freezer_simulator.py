"""
Lakeshore Retail freezer telemetry simulator — FabCon 26 demo.

Streams freezer readings into a Fabric Eventstream custom endpoint, matching the
FreezerTelemetry schema:
    timestamp, storeId, freezerId, temperatureC, humidityPct, doorOpen

Normal readings hold around -19 C. Type `breach` (+ Enter) to warm one freezer
past its -18 C safe threshold, which is what the operations agent watches for.

Setup:
    pip install azure-eventhub
    set FREEZER_ES_CONNECTION_STRING=Endpoint=sb://eventstream-....;EntityPath=es_...

The connection string comes from the Eventstream Live view: select the custom
endpoint -> Details -> Event Hub tab -> SAS Key Authentication ->
"Connection string-primary key".

Commands (type + Enter):
    breach [freezerId]   warm a freezer past its threshold
    recover              return all freezers to normal
    status               print current state
    quit                 stop
"""

import json
import os
import queue
import random
import sys
import threading
import time
from datetime import datetime, timezone

from azure.eventhub import EventData, EventHubProducerClient
from azure.eventhub.exceptions import EventHubError

# Freezer roster — matches Freezer.csv / the `freezer` lakehouse table exactly.
# All five must stream, or the freezers left out will flatline in the ontology
# time-series tiles while the others stay live.
FREEZERS = [
    {"freezerId": "F-PAR-01", "storeId": "S-PAR-01", "minSafeTempC": -18.0},
    {"freezerId": "F-PAR-02", "storeId": "S-PAR-01", "minSafeTempC": -18.0},
    {"freezerId": "F-BER-02", "storeId": "S-BER-01", "minSafeTempC": -18.0},
    {"freezerId": "F-BER-03", "storeId": "S-BER-01", "minSafeTempC": -18.0},
    {"freezerId": "F-AMS-03", "storeId": "S-AMS-01", "minSafeTempC": -18.0},
]

SEND_INTERVAL_SECONDS = 30.0
RETRY_BACKOFF_MAX_SECONDS = 20.0
NOMINAL_TEMP_C = -19.8

# Must match generate_lakeshore_data.py. Normal humidity sits clearly ABOVE the
# 46% threshold used in the canonical demo question, so "which freezers ever had
# humidity below 46%?" keeps returning F-BER-03 and F-AMS-03 only. Streaming at
# 45% would drag every freezer under the threshold and destroy that answer.
NOMINAL_HUMIDITY_PCT = 49.5

# How far above the safe threshold a breaching freezer climbs, and how fast.
# The ramp is PER TICK, not per second - it must be retuned whenever
# SEND_INTERVAL_SECONDS changes, or the breach takes too long to land on stage.
# At 30s ticks, 2.7 C/tick reaches -14.5 C from -19.8 C in ~2 ticks (~60s).
BREACH_TARGET_OFFSET_C = 3.5
BREACH_RAMP_C_PER_TICK = 2.7

commands: "queue.Queue[str]" = queue.Queue()


def read_commands() -> None:
    """Read operator commands on a background thread so sending never blocks."""
    for line in sys.stdin:
        commands.put(line.strip().lower())


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_reading(freezer: dict, state: dict) -> dict:
    """Produce one telemetry row, ramping toward a breach if one is active."""
    if state["breaching"]:
        target = freezer["minSafeTempC"] + BREACH_TARGET_OFFSET_C
        state["temp"] = min(target, state["temp"] + BREACH_RAMP_C_PER_TICK)
        humidity = NOMINAL_HUMIDITY_PCT + random.uniform(6.0, 12.0)
        door_open = 1
    else:
        # Drift gently around nominal so the chart looks alive, not flat.
        # Upper clamp is -19.0, well clear of the -18.0 threshold, so a breach
        # reads as an obvious spike from the back of a conference room.
        state["temp"] += random.uniform(-0.25, 0.25)
        state["temp"] = max(-21.0, min(-19.0, state["temp"]))
        humidity = NOMINAL_HUMIDITY_PCT + random.uniform(-1.6, 1.6)
        door_open = 1 if random.random() < 0.05 else 0

    return {
        "timestamp": utc_now_iso(),
        "storeId": freezer["storeId"],
        "freezerId": freezer["freezerId"],
        "temperatureC": round(state["temp"], 2),
        "humidityPct": round(humidity, 1),
        "doorOpen": door_open,
    }


def handle_command(raw: str, states: dict) -> bool:
    """Apply one operator command. Returns False when it's time to stop."""
    if not raw:
        return True

    parts = raw.split()
    verb = parts[0]

    if verb in ("quit", "exit", "q"):
        return False

    if verb == "breach":
        target = parts[1].upper() if len(parts) > 1 else FREEZERS[0]["freezerId"]
        if target not in states:
            print(f"  unknown freezer {target}; known: {', '.join(states)}")
            return True
        states[target]["breaching"] = True
        print(f"  >>> BREACH triggered on {target} — warming past threshold")
        return True

    if verb == "recover":
        for freezer_id, state in states.items():
            state["breaching"] = False
            state["temp"] = NOMINAL_TEMP_C
        print("  <<< all freezers recovered to nominal")
        return True

    if verb == "status":
        for freezer_id, state in states.items():
            flag = "BREACH" if state["breaching"] else "ok"
            print(f"  {freezer_id}  {state['temp']:6.2f} C  [{flag}]")
        return True

    print(f"  unrecognized command: {raw}")
    return True


# The connection string is read from the environment. Never commit it.
#
#   Windows PowerShell:
#     $env:FREEZER_ES_CONNECTION_STRING = "Endpoint=sb://...;EntityPath=es_..."
#   bash / zsh:
#     export FREEZER_ES_CONNECTION_STRING="Endpoint=sb://...;EntityPath=es_..."
#
# Get it from the Eventstream Live view -> select the custom endpoint -> Details
# -> Event Hub tab -> SAS Key Authentication -> "Connection string-primary key".


def main() -> int:
    connection_string = os.environ.get("FREEZER_ES_CONNECTION_STRING")
    if not connection_string:
        print("FREEZER_ES_CONNECTION_STRING is not set. See the comment above main().")
        return 1

    states = {
        f["freezerId"]: {"temp": NOMINAL_TEMP_C, "breaching": False} for f in FREEZERS
    }

    producer = EventHubProducerClient.from_connection_string(connection_string)
    threading.Thread(target=read_commands, daemon=True).start()

    print(f"Streaming {len(FREEZERS)} freezers every {SEND_INTERVAL_SECONDS:g}s.")
    print("Commands: breach [freezerId] | recover | status | quit\n")

    sent = 0
    failures = 0
    try:
        while True:
            while not commands.empty():
                if not handle_command(commands.get_nowait(), states):
                    return 0

            readings = [
                build_reading(f, states[f["freezerId"]]) for f in FREEZERS
            ]

            # Conference Wi-Fi drops. A transient DNS or socket failure must never kill the
            # process mid-demo, so send failures are retried forever with a rebuilt producer.
            try:
                batch = producer.create_batch()
                for reading in readings:
                    batch.add(EventData(json.dumps(reading)))
                producer.send_batch(batch)
                if failures:
                    print(f"[{utc_now_iso()}] reconnected after {failures} failed attempt(s)")
                    failures = 0
            except (EventHubError, OSError) as exc:
                failures += 1
                print(f"[{utc_now_iso()}] send failed ({failures}): {type(exc).__name__}: {exc}")
                try:
                    producer.close()
                except Exception:
                    pass
                time.sleep(min(RETRY_BACKOFF_MAX_SECONDS, 2 ** min(failures, 5)))
                producer = EventHubProducerClient.from_connection_string(connection_string)
                continue

            sent += len(readings)
            summary = "  ".join(
                f"{r['freezerId']}:{r['temperatureC']:>6.2f}C" for r in readings
            )
            print(f"[{utc_now_iso()}] sent={sent:<6} {summary}")

            time.sleep(SEND_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\nstopping")
        return 0
    finally:
        producer.close()


if __name__ == "__main__":
    raise SystemExit(main())
