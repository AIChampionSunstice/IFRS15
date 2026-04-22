import datetime
from pathlib import Path

def mock_analyze_contract_folder(contract_dir: Path, agi_threshold: float, contract_label: str | None):
    today = datetime.date.today().strftime("%d/%m/%Y")
    row = {
        "Client Name": contract_label or "UNKNOWN",
        "Contract": "SaaS",
        "Format FM": "Yes",
        "Signature Date": today,
        "Scope": "Demand",
        "Contract Time": "3 ans",
        "Price Ramp up": "Yes",
        "Ramp up Price": "Demand (M1–M6) puis Demand+Supply (M7–M36)",
        "Ramp up price euros vs TCV": 30000,
        "Ramp up price % TCV": 9.0,
        "IFRS 15 Agi": "Yes" if 9.0 > agi_threshold else "No",
        "Option sortie avant terme du contrat": "A la convenance du client (mock)",
        "SAAS START Date": today,
        "Start date ignition": today,
        "Setup fees": "Yes",
        "Setup fees euros": 3000
    }

    evidence = {
        "mode": "mock",
        "documents_seen": [p.name for p in contract_dir.rglob("*") if p.is_file()],
        "notes": "Preuves simulées. Quand Bedrock sera branché, on mettra ici doc + page + extrait."
    }

    return row, evidence
