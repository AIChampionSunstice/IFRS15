def classify_document(filename: str) -> str:
    name = filename.lower()
    
    if "order form" in name or "subscription services order form" in name:
        return "ORDER_FORM"
    if "sow" in name or "statement of work" in name:
        return "SOW"
    if "sla" in name:
        return "SLA"
    if "support" in name:
        return "SUPPORT"
    if "subscription agreement" in name or "saas subscription agreement" in name or "msa" in name or "master" in name:
        return "MASTER"
    return "OTHER"
