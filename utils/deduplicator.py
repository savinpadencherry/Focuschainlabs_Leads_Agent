import os
import pandas as pd


def load_exclusion_list(filepath: str) -> set:
    """Load previously contacted companies from Excel or CSV."""
    if not filepath or not os.path.exists(filepath):
        return set()
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".csv":
        df = pd.read_csv(filepath)
    else:
        df = pd.read_excel(filepath)
    # Accept column named 'company_name', 'Company', or 'company'
    col = next(
        (c for c in df.columns if "company" in c.lower()),
        df.columns[0]
    )
    return set(df[col].dropna().str.lower().str.strip().tolist())


def deduplicate(companies: list, exclusion_set: set) -> list:
    """Remove companies already in the exclusion list."""
    before = len(companies)
    filtered = [
        c for c in companies
        if c["company_name"].lower().strip() not in exclusion_set
    ]
    removed = before - len(filtered)
    if removed > 0:
        print(f"  Removed {removed} companies already in exclusion list")
    return filtered
