# backend/anomaly.py
import json
from hashlib import sha256
from typing import List

# Configurable thresholds
MAX_REASONABLE_QUANTITY = 100     # <--- change this if your domain needs a different limit
QUANTITY_SPIKE_FACTOR = 5         # if new quantity > prev_quantity * factor -> spike anomaly

def canonical_json_from_obj(data_obj):
    """Return deterministic JSON string for hashing from a python dict/object."""
    return json.dumps(data_obj, sort_keys=True, separators=(',', ':'))

def canonical_json_from_str(maybe_json_str):
    """If it's JSON, return canonical form. Otherwise return stripped string."""
    try:
        obj = json.loads(maybe_json_str)
        return canonical_json_from_obj(obj)
    except Exception:
        return maybe_json_str.strip()

def compute_hash_hex_from_canonical(canonical_str):
    return sha256(canonical_str.encode('utf-8')).hexdigest().lower()

def check_tamper(onchain_hash_hex: str, local_json_str: str):
    """
    Returns (ok:bool, local_hash_hex, onchain_hash_hex_clean)
    Both hashes are lowercase, no 0x.
    """
    canonical = canonical_json_from_str(local_json_str)
    local_hash = compute_hash_hex_from_canonical(canonical)
    onchain_clean = onchain_hash_hex.lower().replace('0x', '').strip()
    ok = (local_hash == onchain_clean)
    return ok, local_hash, onchain_clean


def detect_anomalies(prev_record_dict: dict, new_record_dict: dict) -> List[str]:
    """
    Enhanced anomaly detection.
    - Enforces quantity limits (no more than MAX_REASONABLE_QUANTITY)
    - Detects negative/zero/non-numeric quantities
    - Detects large spikes versus previous record (if prev_record_dict provided)
    - Keeps previous simple checks (timestamp, missing fields, etc.)

    Returns a list of descriptive anomaly strings.
    """
    anomalies = []

    # 1) Timestamp checks
    try:
        ts = int(new_record_dict.get("timestamp", 0))
        if ts <= 0:
            anomalies.append("invalid_timestamp: timestamp <= 0")
        elif ts > 2147483647:
            anomalies.append("invalid_timestamp: timestamp too large")
    except Exception:
        anomalies.append("timestamp_parse_error: timestamp not integer")

    # 2) Core required fields
    for field in ["product_id", "name", "description"]:
        if not new_record_dict.get(field):
            anomalies.append(f"missing_field: {field}")

    # 3) Quantity checks (strong rules)
    if "quantity" in new_record_dict:
        q_raw = new_record_dict.get("quantity")
        try:
            # allow ints or numeric-strings
            q = float(q_raw)
            # integer-like quantities are expected — treat fractional as anomaly but continue
            if q < 0:
                anomalies.append("negative_quantity: quantity below zero")
            elif q == 0:
                anomalies.append("zero_quantity: possible empty batch")
            # primary rule you asked for
            if q > MAX_REASONABLE_QUANTITY:
                anomalies.append(f"unrealistic_quantity: {q} > {MAX_REASONABLE_QUANTITY}")
            # spike vs previous record
            if prev_record_dict and "quantity" in prev_record_dict:
                try:
                    prev_q = float(prev_record_dict.get("quantity", 0))
                    if prev_q >= 0 and q > prev_q * QUANTITY_SPIKE_FACTOR:
                        anomalies.append(f"quantity_spike: {q} > {QUANTITY_SPIKE_FACTOR}x previous ({prev_q})")
                except Exception:
                    # if prev quantity not numeric, skip spike comparison
                    pass
        except Exception:
            anomalies.append("quantity_not_numeric")
    else:
        # optionally flag missing quantity if your domain requires it
        # anomalies.append("missing_field: quantity")
        pass

    # 4) Location / route anomalies (if previous available)
    if prev_record_dict:
        prev_loc = prev_record_dict.get("location")
        new_loc = new_record_dict.get("location")
        if prev_loc and new_loc and prev_loc != new_loc:
            anomalies.append(f"unexpected_location_change: {prev_loc} -> {new_loc}")

        try:
            prev_ts = int(prev_record_dict.get("timestamp", 0))
            new_ts = int(new_record_dict.get("timestamp", 0))
            # large time gap (configurable): > 7 days
            if prev_ts and abs(new_ts - prev_ts) > 7 * 24 * 3600:
                anomalies.append("timestamp_jump_gt_7days")
        except Exception:
            pass

    # 5) Manufacturer / supplier checks
    manu = new_record_dict.get("manufacturer")
    if manu is not None and len(str(manu).strip()) < 2:
        anomalies.append("invalid_manufacturer_name")

    # 6) Sensor/environment checks (optional)
    if "temperature" in new_record_dict:
        try:
            t = float(new_record_dict["temperature"])
            if t < -20 or t > 60:
                anomalies.append(f"temperature_out_of_range: {t}°C")
        except Exception:
            anomalies.append("temperature_not_numeric")

    return anomalies
