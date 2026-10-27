"""
The fuel types of the reimbursement API against the product names printed on a receipt.

Darwinbox sends a BBM item's product as the fuel type its employee picked from a list ("Pertamax 92", "Performa > 92",
"Diesel/Dex"), not as the receipt prints it ("PERTAMAX", "PERTAMAX TURBO", "DEXLITE"). A fuel type listed in
KNOWN_NAMES matches the names listed for it (and itself); one not listed must equal the name on the receipt
(receipt_evaluation.names_match).

Names are compared as receipt_evaluation.normalize_name gives them, without spaces: "Pertamax Turbo",
"PERTAMAX_TURBO" and "PertamaxTurbo" are the same name. Anything else read with the name (a pump number, "Hose 10.3")
does not match: a reviewer checks it.
"""

from backend.jobs.bbm_ocr.receipt_evaluation import names_match, normalize_name

# Fuel type as the reimbursement API sends it -> the names receipts print for it
KNOWN_NAMES = {
    "Pertamax 92": ["Pertamax", "Pertamax 92"],
    "Pertalite 90": ["Pertalite", "Pertalite 90"],
    "Shell Super 92": ["Shell Super", "Super", "Shell Super 92", "Super 92"],
    "BP 92": ["BP 92"],
    "BP 90": ["BP 90"],
    "Vivo Ron 92": ["Revvo 92", "Vivo Revvo 92"],
    "Performa > 92": [
        "Pertamax Turbo", "Pertamax Green", "Pertamax Green 95",
        "Shell V-Power", "V-Power", "Shell V-Power Nitro+", "V-Power Nitro+",
        "BP Ultimate", "Ultimate",
        "Revvo 95",
    ],
    "Diesel/Dex": [
        "Pertamina Dex", "Dex", "Dexlite", "Pertamina Dexlite", "Biosolar", "Solar",
        "Shell V-Power Diesel", "V-Power Diesel",
        "BP Ultimate Diesel", "Ultimate Diesel",
        "Diesel Primus Plus", "Primus Plus",
    ],
}


# The fuel (fuel_product's merchant and name, seeds/fuel_product.sql) each name is, for the fuel price page's prices:
# the fuel types that name one fuel, and the names receipts print. "Performa > 92" and "Diesel/Dex" name several: the
# receipt tells which (fuel_product_of).
FUEL_PRODUCTS = {
    ("pertamina", "Pertalite"): ["Pertalite 90"],
    ("pertamina", "Pertamax"): ["Pertamax 92"],
    ("pertamina", "Pertamax Green 95"): ["Pertamax Green"],
    ("pertamina", "Pertamax Turbo"): [],
    ("pertamina", "Biosolar"): ["Solar"],
    ("pertamina", "Dexlite"): ["Pertamina Dexlite"],
    ("pertamina", "Pertamina Dex"): ["Dex"],
    ("shell", "Shell Super"): ["Super", "Shell Super 92", "Super 92"],
    ("shell", "Shell V-Power"): ["V-Power"],
    ("shell", "Shell V-Power Nitro+"): ["V-Power Nitro+"],
    ("shell", "Shell V-Power Diesel"): ["V-Power Diesel"],
    ("bp", "BP 90"): [],
    ("bp", "BP 92"): [],
    ("bp", "BP Ultimate"): ["Ultimate"],
    ("bp", "BP Ultimate Diesel"): ["Ultimate Diesel"],
    ("vivo", "Revvo 90"): [],
    ("vivo", "Revvo 92"): ["Vivo Ron 92", "Vivo Revvo 92"],
    ("vivo", "Revvo 95"): [],
    ("vivo", "Diesel Primus Plus"): ["Primus Plus"],
}


def _compact(name):
    return normalize_name(name).replace(" ", "")


_KNOWN = {_compact(fuel_type): {_compact(name) for name in [fuel_type, *names]}
          for fuel_type, names in KNOWN_NAMES.items()}
_FUELS = {_compact(name): fuel for fuel, names in FUEL_PRODUCTS.items() for name in [fuel[1], *names]}


def fuel_product_of(fuel_type, read_names):
    """The fuel (merchant, name) a BBM item is: the one its fuel type names; or else (Performa > 92, Diesel/Dex) the
    one the product names read on its receipts (read_names) give, when those that match the fuel type all give the
    same. None when it can't be told."""
    fuel = _FUELS.get(_compact(fuel_type))
    if fuel:
        return fuel
    found = {_FUELS.get(_compact(name)) for name in read_names if name and matches_fuel_type(name, fuel_type)}
    return found.pop() if len(found) == 1 else None


def matches_fuel_type(read_name, fuel_type):
    """Whether the product name read on a receipt is the fuel type submitted (the name matcher of
    receipt_validation.validate_receipts: the OCR's name first)."""
    known = _KNOWN.get(_compact(fuel_type))
    if known is None:
        return names_match(read_name, fuel_type)
    return _compact(read_name) in known
