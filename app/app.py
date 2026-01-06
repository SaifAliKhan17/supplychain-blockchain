#!/usr/bin/env python3
from flask import Flask, render_template, request, redirect, url_for,Response
import csv
import io
import os
import json
from datetime import datetime
from pathlib import Path

# local imports
from backend.db import init_db, Session, add_product, list_products, get_product_by_id
from backend.blockchain import load_contract, w3, compute_sha256_hex, register_product_onchain, get_onchain_hash
from backend.anomaly import check_tamper, detect_anomalies, canonical_json_from_obj

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ADDR_FILE = PROJECT_ROOT / 'backend' / 'contract_address.txt'
if not CONTRACT_ADDR_FILE.exists():
    raise SystemExit("Error: contract_address.txt not found. Deploy the contract first with backend/deploy_contract.py")

with open(CONTRACT_ADDR_FILE, 'r') as f:
    CONTRACT_ADDRESS = f.read().strip()

contract = load_contract(CONTRACT_ADDRESS)

app = Flask(__name__, template_folder='templates', static_folder='static')
init_db()
session = Session()



def generate_qr(product_id: str):
    import qrcode
    import socket
    # Get local IP address automatically (so phone on same Wi-Fi can reach)
    local_ip = socket.gethostbyname(socket.gethostname())
    url = f"http://{local_ip}:5000/verify/{product_id}"

    out_dir = PROJECT_ROOT / 'app' / 'static' / 'qrcodes'
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{product_id}.png"
    img = qrcode.make(url)
    img.save(out_path)
    rel = os.path.relpath(out_path, PROJECT_ROOT / 'app' / 'static')
    return rel.replace('\\', '/')

@app.route('/')
def index():
    products = list_products(session)
    product_rows = []
    for p in products:
        # on-chain hash (safe)
        try:
            onchain_hash, ts, submitter = get_onchain_hash(contract, p.product_id)
        except Exception:
            onchain_hash, ts, submitter = ("", None, None)

        # tamper check
        tamper_ok, _, _ = check_tamper(onchain_hash, p.metadata_json)

        # parse record
        try:
            rec = json.loads(p.metadata_json)
        except Exception:
            rec = {}

        # compute anomalies (pass prev_record as None for now)
        anomalies = detect_anomalies(None, rec)

        # decide status: tampered -> anomaly -> ok
        if not tamper_ok:
            status = "FAILED"
        elif anomalies:
            status = "ANOMALY"
        else:
            status = "OK"

        product_rows.append((p, status, anomalies))

    return render_template('index.html', product_rows=product_rows)



@app.route('/add', methods=['GET', 'POST'])
def add():
    if request.method == 'POST':
        product_id = request.form.get('product_id').strip()
        name = request.form.get('name').strip()
        description = request.form.get('description').strip()
        quantity_raw = request.form.get('quantity')
        manufacturer = request.form.get('manufacturer')

        # Parse quantity
        quantity = None
        if quantity_raw and quantity_raw.strip() != '':
            try:
                quantity = int(float(quantity_raw))
            except Exception:
                quantity = quantity_raw

        # Build metadata
        metadata = {
            "product_id": product_id,
            "name": name,
            "description": description,
            "timestamp": int(datetime.utcnow().timestamp())
        }
        if quantity is not None:
            metadata["quantity"] = quantity
        if manufacturer:
            metadata["manufacturer"] = manufacturer.strip()

        canonical = canonical_json_from_obj(metadata)
        qr_rel = generate_qr(product_id)

        # Prevent duplicates
        existing = get_product_by_id(session, product_id)
        if existing:
            # If product ID already exists, redirect to detail page
            return redirect(url_for('product_detail', product_id=product_id))

        # Save to DB
        add_product(session, product_id, name, description, canonical, qr_rel)

        # Save on-chain
        from_addr = w3.eth.accounts[0]
        receipt, hexhash = register_product_onchain(contract, product_id, canonical, from_addr)

        # Redirect to dashboard
        return redirect(url_for('index'))

    return render_template('add_product.html')




@app.route('/product/<product_id>')
def product_detail(product_id):
    p = get_product_by_id(session, product_id)
    if not p:
        return "Product not found", 404

    try:
        onchain_hash, ts, submitter = get_onchain_hash(contract, product_id)
    except Exception:
        onchain_hash, ts, submitter = ("", None, None)

    tamper_ok, local_hash, onchain_hash_clean = check_tamper(onchain_hash, p.metadata_json)

    try:
        rec = json.loads(p.metadata_json)
    except Exception:
        rec = {}

    anomalies = detect_anomalies(None, rec)

    from datetime import datetime

    formatted_ts = None
    if ts:
        formatted_ts = datetime.utcfromtimestamp(ts).strftime(
            "%d %b %Y · %H:%M UTC"
        )

    return render_template(
        'product_detail.html',
        product=p,
        tamper_ok=tamper_ok,
        local_hash=local_hash,
        onchain_hash=onchain_hash_clean,
        timestamp=formatted_ts,
        submitter=submitter,
        anomalies=anomalies
    )

@app.route('/verify/<product_id>')
def verify_product(product_id):
    p = get_product_by_id(session, product_id)
    if not p:
        return "Product not found", 404

    try:
        onchain_hash, ts, submitter = get_onchain_hash(contract, p.product_id)
    except Exception:
        onchain_hash, ts, submitter = ("", None, None)

    tamper_ok, local_hash, onchain_hash_clean = check_tamper(
        onchain_hash,
        p.metadata_json
    )

    from datetime import datetime
    formatted_ts = None
    if ts:
        formatted_ts = datetime.utcfromtimestamp(ts).strftime(
            "%d %b %Y · %H:%M UTC"
        )

    return render_template(
        'verify.html',
        product=p,
        tamper_ok=tamper_ok,
        local_hash=local_hash,
        onchain_hash=onchain_hash_clean,
        timestamp=formatted_ts,
        submitter=submitter
    )

@app.route('/scan_all')
def scan_all():
    session = Session()
    rows = []
    products = list_products(session)

    for p in products:
        onchain_hash, ts, submitter = get_onchain_hash(contract, p.product_id)
        ok, local_hash, onchain_clean = check_tamper(onchain_hash, p.metadata_json)
        rows.append({
            "product": p,
            "tamper_ok": ok,
            "local_hash": local_hash,
            "onchain_hash": onchain_clean
        })

    return render_template('scan_all.html', rows=rows)

@app.route('/export_csv')
def export_csv():
    session = Session()
    products = list_products(session)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Product ID", "Name", "Description", "Created", "Status"])

    for p in products:
        onchain_hash, ts, submitter = get_onchain_hash(contract, p.product_id)
        tamper_ok, _, _ = check_tamper(onchain_hash, p.metadata_json)
        status = "Verified" if tamper_ok else "Tampered"
        writer.writerow([p.product_id, p.name, p.description, p.created_at, status])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=products.csv"}
    )

@app.context_processor
def inject_stats():
    products = list_products(session)
    ok = failed = anomaly = 0
    for p in products:
        onchain_hash, _, _ = get_onchain_hash(contract, p.product_id)
        ok_status, _, _ = check_tamper(onchain_hash, p.metadata_json)
        if ok_status:
            ok += 1
        else:
            failed += 1
        if detect_anomalies(None, json.loads(p.metadata_json)):
            anomaly += 1
    return dict(stat_ok=ok, stat_failed=failed, stat_anomaly=anomaly)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
