#!/usr/bin/env python3
"""
Capture ESP32 serial output and append AGENTLOG lines as NDJSON to the debug
session log file. Run this while reproducing the USB net TX issue (e.g. ping).
Usage: python3 serial_to_debug_log.py [serial_device]
Example: python3 serial_to_debug_log.py /dev/ttyUSB0
"""
import json
import re
import sys
import time
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parent.parent / ".cursor" / "debug-4f4624.log"
SESSION_ID = "4f4624"


def main():
    try:
        import serial
    except ImportError:
        print("Install pyserial: pip install pyserial", file=sys.stderr)
        sys.exit(1)

    dev = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    baud = 115200

    # Extract H=X (hypothesisId) from line like "... AGENTLOG H=A loc=..."
    agent_re = re.compile(r"AGENTLOG\s+(.+)")
    h_re = re.compile(r"\bH=([A-E])\b")

    with serial.Serial(dev, baud, timeout=0.1) as ser:
        print(f"Capturing from {dev} -> {LOG_PATH}", file=sys.stderr)
        while True:
            line = ser.readline()
            if not line:
                continue
            try:
                text = line.decode("utf-8", errors="replace").strip()
            except Exception:
                continue
            m = agent_re.search(text)
            if not m:
                continue
            rest = m.group(1).strip()
            h_m = h_re.search(text)
            hypothesis_id = h_m.group(1) if h_m else "D"
            payload = {
                "sessionId": SESSION_ID,
                "timestamp": int(time.time() * 1000),
                "location": "serial",
                "message": rest,
                "data": {"raw": text},
                "hypothesisId": hypothesis_id,
            }
            with open(LOG_PATH, "a") as f:
                f.write(json.dumps(payload) + "\n")


if __name__ == "__main__":
    main()
