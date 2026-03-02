"""
SAP Procurement Spend Cube - Master Configuration
====================================================
All business rules, mappings, thresholds, and classification logic.
Single source of truth for the entire analysis skill.
Covers BOTH single-company AND full-dataset (multi-company) analysis.
"""

import datetime

# ============================================================================
# 1. SAP TABLE DEFINITIONS & JOIN LOGIC
# ============================================================================

SAP_TABLES = {
    'RSEG': {'desc': 'Invoice Line Items (MM)', 'role': 'BASE TABLE for MM invoice analysis', 'sep': ','},
    'EKPO': {'desc': 'PO Line Items', 'role': 'Material, PO text, material group', 'sep': ';'},
    'EKKO': {'desc': 'PO Headers', 'role': 'Vendor (LIFNR), PO date, Purch. Org', 'sep': ';'},
    'EKBE': {'desc': 'PO History', 'role': 'Goods Receipt flag (VGABE=1)', 'sep': ';'},
    'EBAN': {'desc': 'Purchase Requisitions', 'role': 'PR flag via EKPO.BANFN', 'sep': ';'},
    'RBKP': {'desc': 'Invoice Headers (MM)', 'role': 'Invoice dates, vendor, payment terms', 'sep': ';'},
    'LFA1': {'desc': 'Vendor Master', 'role': 'Vendor name (NAME1), country (LAND1)', 'sep': ';'},
    'MARA': {'desc': 'Material Master', 'role': 'Material type (MTART), material group', 'sep': ';'},
    'MAKT': {'desc': 'Material Descriptions', 'role': 'Material text (MAKTX)', 'sep': ';'},
    'T001': {'desc': 'Company Codes', 'role': 'Company to country mapping', 'sep': ';'},
    'T001W': {'desc': 'Plant Master', 'role': 'Plant name', 'sep': ';'},
    'BKPF': {'desc': 'Accounting Doc Header', 'role': 'AWKEY linkage to FI, BLART doc type', 'sep': ';'},
    'BSEG': {'desc': 'Accounting Line Items', 'role': 'GL, Profit Center, Cost Center, Tax', 'sep': ';'},
}

# RSEG-based join sequence (used for MM Invoice Verification)
RSEG_JOIN_SEQUENCE = [
    {'step': 1, 'tables': 'RSEG + EKPO', 'keys': 'EBELN + EBELP', 'type': 'LEFT'},
    {'step': 2, 'tables': '+ EKKO', 'keys': 'EBELN', 'type': 'LEFT'},
    {'step': 3, 'tables': '+ EKBE(GR)', 'keys': 'EBELN + EBELP (VGABE=1)', 'type': 'LEFT'},
    {'step': 4, 'tables': '+ RBKP', 'keys': 'BELNR + GJAHR', 'type': 'LEFT'},
    {'step': 5, 'tables': '+ EBAN(PR)', 'keys': 'via EKPO.BANFN', 'type': 'LEFT'},
    {'step': 6, 'tables': '+ LFA1', 'keys': 'LIFNR', 'type': 'LEFT'},
    {'step': 7, 'tables': '+ MARA', 'keys': 'MATNR_ENRICHED', 'type': 'LEFT'},
    {'step': 8, 'tables': '+ MAKT', 'keys': 'MATNR (SPRAS=E)', 'type': 'LEFT'},
    {'step': 9, 'tables': '+ T001', 'keys': 'BUKRS', 'type': 'LEFT'},
    {'step': 10, 'tables': '+ T001W', 'keys': 'WERKS', 'type': 'LEFT'},
    {'step': 11, 'tables': '+ BKPF/BSEG', 'keys': 'AWKEY (BELNR+GJAHR), AWTYP=RMRP', 'type': 'LEFT'},
    {'step': 12, 'tables': '+ EKKO->LFA1', 'keys': 'LIFNR (vendor enrichment)', 'type': 'LEFT'},
]

# BKPF/BSEG join (used for FI direct postings)
BKPF_BSEG_JOIN = {
    'step1': 'BKPF: Filter BUKRS + BLART -> get BELNR/GJAHR',
    'step2': 'BSEG: Match on BELNR + GJAHR + BUKRS',
    'step3': 'LFA1: Match on BSEG.LIFNR for vendor name/country',
}

# BSEG linkage from RSEG
BSEG_LINKAGE = {
    'method': 'RSEG.BELNR + RSEG.GJAHR -> BKPF.AWKEY (where AWTYP=RMRP) -> BKPF.BELNR + BKPF.GJAHR -> BSEG',
    'awkey_format': 'BELNR (10 chars zero-padded) + GJAHR (4 chars)',
}

# BSEG columns to load (reduced for memory)
BSEG_LOAD_COLS = [
    'BUKRS', 'BELNR', 'GJAHR', 'BUZEI', 'BSCHL', 'KOART', 'SHKZG',
    'DMBTR', 'WRBTR', 'MWSKZ', 'HKONT', 'KOSTL', 'PRCTR', 'LIFNR',
    'MATNR', 'WERKS', 'MENGE', 'MEINS', 'EBELN', 'EBELP', 'SGTXT',
]

# BKPF columns to load (reduced for memory)
BKPF_LOAD_COLS = ['BUKRS', 'BELNR', 'GJAHR', 'BLART', 'WAERS', 'BUDAT', 'BLDAT', 'TCODE']

# LFA1 columns to load
LFA1_LOAD_COLS = ['LIFNR', 'NAME1', 'LAND1', 'ORT01', 'STRAS', 'PSTLZ']


# ============================================================================
# 2. COMPANY CODE MAPPINGS
# ============================================================================

COMPANY_CODES = {
    6:   {'name': 'Russia',         'country': 'RU', 'entity': 'Symrise Russia'},
    8:   {'name': 'Egypt',          'country': 'EG', 'entity': 'Symrise Egypt'},
    10:  {'name': 'USA',            'country': 'US', 'entity': 'Symrise Inc.'},
    21:  {'name': 'Spain (ES01)',   'country': 'ES', 'entity': 'Symrise Spain'},
    23:  {'name': 'UK',             'country': 'GB', 'entity': 'Symrise UK'},
    29:  {'name': 'Turkey',         'country': 'TR', 'entity': 'Symrise Turkey'},
    30:  {'name': 'Germany (HQ)',   'country': 'DE', 'entity': 'Symrise AG'},
    46:  {'name': 'Slovenia',       'country': 'SI', 'entity': 'Symrise Slovenia'},
    78:  {'name': 'South Africa',   'country': 'ZA', 'entity': 'Symrise South Africa'},
    113: {'name': 'Granada',        'country': 'ES', 'entity': 'Symrise Granada'},
    117: {'name': 'France',         'country': 'FR', 'entity': 'Symrise France'},
}

BUKRS_NAME_MAP = {k: v['name'] for k, v in COMPANY_CODES.items()}


# ============================================================================
# 3. DIRECT / INDIRECT CLASSIFICATION RULES
# ============================================================================

SPEND_CLASSIFICATION = {
    'flowchart': """
    START
      |
      v
    Has PR/PO/GR? --NO--> INDIRECT ("No PR/PO/GR document reference")
      |
      YES
      v
    Has Material Number? --NO--> INDIRECT ("No material number")
      |
      YES
      v
    Material Digit Count?
      |-- 7+ digits --> INDIRECT ("Material has N digits, 7+ = Indirect")
      |-- 6 digits  --> DIRECT   ("Material has 6 digits")
      |-- <6 digits --> INDIRECT ("Material has N digits, less than 6")
    """,
    'rules': [
        {'condition': 'No PR/PO/GR reference', 'result': 'INDIRECT', 'reason': 'No PR/PO/GR document reference'},
        {'condition': 'No Material Number', 'result': 'INDIRECT', 'reason': 'No material number'},
        {'condition': 'Material digits >= 7', 'result': 'INDIRECT', 'reason': 'Material number has {n} digits (7+ = Indirect)'},
        {'condition': 'Material digits == 6', 'result': 'DIRECT', 'reason': 'Material number has 6 digits (6 = Direct)'},
        {'condition': 'Material digits < 6', 'result': 'INDIRECT', 'reason': 'Material number has {n} digits (less than 6)'},
    ],
    'fi_rules': [
        {'condition': 'No PO reference', 'result': 'INDIRECT', 'reason': 'No PO reference (FI document)'},
        {'condition': 'No Material Number', 'result': 'INDIRECT', 'reason': 'No material number'},
        {'condition': 'Material digits == 6', 'result': 'DIRECT', 'reason': 'Material number has 6 digits (6 = Direct)'},
        {'condition': 'Material digits >= 7', 'result': 'INDIRECT', 'reason': 'Material number has {n} digits (7+ = Indirect)'},
        {'condition': 'Material digits < 6', 'result': 'INDIRECT', 'reason': 'Material number has {n} digits (less than 6)'},
    ],
}


# ============================================================================
# 4. DEBIT / CREDIT (SHKZG) RULES
# ============================================================================

SHKZG_RULES = {
    'S': {'meaning': 'Soll (Debit)', 'type': 'Expense', 'amount_treatment': 'Adds to Gross Spend'},
    'H': {'meaning': 'Haben (Credit)', 'type': 'Reversal', 'amount_treatment': 'Reduces Net Spend (negative)'},
}

AMOUNT_FORMULAS = {
    'Gross_Amount': 'DMBTR where SHKZG = S (debits only)',
    'Credit_Amount': 'DMBTR where SHKZG = H (credits only)',
    'Net_Amount': 'Gross_Amount - Credit_Amount (or: signed amount where S=+, H=-)',
    'Amount_Signed': 'DMBTR * (1 if SHKZG=S else -1)',
}


# ============================================================================
# 5. MAVERICK SPEND DEFINITIONS
# ============================================================================

MAVERICK_TIERS = {
    'CRITICAL': {
        'label': 'Extreme Risk',
        'condition': 'No PR + No GR + No Material Number',
        'description': 'Completely outside procurement - no PR, no GR, no material',
        'color_hex': '#8B0000',
    },
    'HIGH': {
        'label': 'Primary Maverick',
        'condition': 'No PR + No GR',
        'description': 'No Purchase Requisition and No Goods Receipt',
        'color_hex': '#FF8C00',
    },
    'MEDIUM_NO_PR': {
        'label': 'No Purchase Requisition',
        'condition': 'No PR (has GR)',
        'description': 'Missing formal approval before purchase',
        'color_hex': '#FFD700',
    },
    'MEDIUM_NO_GR': {
        'label': 'No Goods Receipt',
        'condition': 'No GR (has PR)',
        'description': 'Goods/services received but not confirmed in SAP',
        'color_hex': '#FFD700',
    },
    'LOW': {
        'label': 'Data Quality',
        'condition': 'No Material Number only (has PR+GR)',
        'description': 'Material master data gap',
        'color_hex': '#4169E1',
    },
}

MAVERICK_FI_TIERS = {
    'PRIMARY': {
        'condition': 'No PO Reference',
        'description': 'FI document without Purchase Order reference',
    },
    'CRITICAL': {
        'condition': 'No PO + No Material',
        'description': 'FI document without PO and without material number',
    },
}


# ============================================================================
# 6. THREE-WAY MATCH LOGIC
# ============================================================================

THREE_WAY_MATCH = {
    'full_match': {'condition': 'Has_PO + Has_PR + Has_GR', 'label': '3-Way Match (Compliant)'},
    'po_only': {'condition': 'Has_PO only (no PR, no GR)', 'label': 'PO Only (Maverick)'},
    'po_pr': {'condition': 'Has_PO + Has_PR (no GR)', 'label': '2-Way Match'},
    'po_gr': {'condition': 'Has_PO + Has_GR (no PR)', 'label': 'PO+GR (No PR)'},
    'no_po': {'condition': 'No PO at all', 'label': 'No PO Reference'},
}


# ============================================================================
# 7. VENDOR RISK THRESHOLDS
# ============================================================================

VENDOR_THRESHOLDS = {
    'credit_heavy_ratio': 0.20,
    'credit_heavy_min_debit_company': 1000,     # EUR 1K for single company
    'credit_heavy_min_debit_full': 50000,        # EUR 50K for full dataset
    'single_source_vendor_count': 1,
    'pareto_pct': 0.80,
    'top_n_vendors': [10, 15, 20],
}


# ============================================================================
# 8. GL ACCOUNT DESCRIPTIONS
# ============================================================================

GL_ACCOUNT_DESCRIPTIONS = {
    2900000: 'GR/IR Clearing',
    2900100: 'GR/IR Clearing (Sub)',
    2900150: 'GR/IR Clearing (Sub)',
    2900300: 'GR/IR Clearing (Sub)',
    3400000: 'Stock Materials',
    4400000: 'Cost of Materials',
    4400100: 'Raw Materials',
    4400200: 'Packaging Materials',
    4400300: 'Material / Freight',
    4401800: 'Freight Inbound',
    4700000: 'Freight / Transport',
    4800000: 'Services',
    6023800: 'Other Operating Expenses',
    6200000: 'External Services',
    6300000: 'Maintenance & Repair',
    6400000: 'Rent & Lease',
    6500000: 'Insurance',
    6600000: 'Travel Expenses',
    6700000: 'Office Supplies',
    6722000: 'External Services',
    6722100: 'External Services (Sub)',
    6800000: 'Communication',
    6900000: 'Other Operating Expenses',
}

GL_PATTERN_INSIGHTS = {
    '29xxxxx': 'GR/IR Clearing - Invoices posted to clearing without proper GR',
    '44xxxxx': 'Materials/Freight - Direct cost leakage, material purchases bypassing 3-way match',
    '67xxxxx': 'External Services - Third-party services without proper controls',
}


# ============================================================================
# 9. DOCUMENT TYPE DEFINITIONS
# ============================================================================

RBKP_DOC_TYPES = {
    'RE': 'Invoice (Standard)',
    'RI': 'Invoice (Internal)',
    'RC': 'Invoice (Credit Memo)',
    'KP': 'Account Maintenance',
}

BKPF_DOC_TYPES = {
    'EC': 'Invoice Correction',
    'KR': 'Vendor Invoice (FI)',
    'KG': 'Vendor Credit Memo',
    'KE': 'Vendor Credit Note',
    'KX': 'Vendor Special Credit',
    'RE': 'Invoice (via MM)',
    'RI': 'Invoice Internal (via MM)',
    'RC': 'Credit Memo (via MM)',
    'KP': 'Account Maintenance',
    'SA': 'GL Account Document',
    'AB': 'Accounting Document',
    'WA': 'Goods Issue',
    'WE': 'Goods Receipt',
    'KZ': 'Vendor Payment',
    'DZ': 'Customer Payment',
    'KH': 'Vendor Credit Memo (clearing)',
    'KA': 'Vendor Document',
    'KC': 'Vendor Credit',
}


# ============================================================================
# 10. ACCOUNT TYPE (KOART) MAPPINGS
# ============================================================================

KOART_MAPPINGS = {
    'K': 'Vendor',
    'S': 'GL Account',
    'D': 'Customer',
    'M': 'Material',
    'A': 'Asset',
}


# ============================================================================
# 11. PACKAGING CLASSIFICATION RULES
# ============================================================================

PACKAGING_RULES = {
    'method': 'Hybrid UOM + Keyword logic',
    'description': 'Weight-based UOM items excluded unless packaging keywords override',
    'weight_uoms': ['KG', 'G', 'LB', 'OZ', 'T', 'MT', 'TON'],
    'packaging_keywords': [
        'carton', 'box', 'drum', 'barrel', 'pallet', 'bag', 'sack',
        'bottle', 'container', 'can', 'tin', 'jar', 'tube', 'pouch',
        'label', 'lid', 'cap', 'closure', 'wrap', 'film', 'foil',
        'shrink', 'stretch', 'corrugat', 'cardboard', 'crate',
        'packaging', 'pack', 'blister', 'tray', 'insert', 'divider',
    ],
    'categories': {
        'Cartons/Boxes': ['carton', 'box', 'corrugat', 'cardboard'],
        'Drums/Barrels': ['drum', 'barrel', 'keg'],
        'Labels': ['label'],
        'Pallets': ['pallet'],
        'Cans': ['can', 'tin'],
        'General': ['packaging', 'pack'],
        'Crates': ['crate'],
        'Bottles/Containers': ['bottle', 'container', 'jar'],
        'Closures': ['lid', 'cap', 'closure'],
        'Bags': ['bag', 'sack', 'pouch'],
        'Film/Wrap': ['wrap', 'film', 'foil', 'shrink', 'stretch'],
        'Tubes': ['tube'],
        'Blister/Tray': ['blister', 'tray'],
    },
}


# ============================================================================
# 12. CURRENCY CONVERSION (APPROXIMATE FY2025)
# ============================================================================

FX_RATES_TO_EUR = {
    'EUR': 1.0, 'USD': 0.92, 'GBP': 1.16, 'CHF': 1.04, 'JPY': 0.0062,
    'CNY': 0.13, 'TRY': 0.028, 'RUB': 0.010, 'ZAR': 0.051, 'EGP': 0.019,
    'BRL': 0.18, 'INR': 0.011, 'PLN': 0.23, 'CZK': 0.040, 'HUF': 0.0025,
    'SEK': 0.088, 'DKK': 0.134, 'NOK': 0.086, 'MXN': 0.054, 'AUD': 0.60,
    'CAD': 0.68, 'SGD': 0.69, 'MYR': 0.21, 'THB': 0.026,
}


# ============================================================================
# 13. SAVINGS OPPORTUNITY ESTIMATES
# ============================================================================

SAVINGS_ESTIMATES = {
    'maverick_compliance': {'rate': 0.05, 'label': 'Maverick Compliance', 'base': 'maverick_spend'},
    'vendor_consolidation': {'rate': 0.03, 'label': 'Vendor Consolidation', 'base': 'total_gross'},
    'credit_recovery': {'rate': None, 'label': 'Credit Recovery', 'base': 'credit_heavy_credits'},
    'dual_source': {'rate': 0.02, 'label': 'Dual-Source Leverage', 'base': 'single_source_spend'},
    'indirect_optimization': {'rate': 0.07, 'label': 'Indirect Optimization', 'base': 'indirect_spend'},
}


# ============================================================================
# 14. POWERPOINT STYLING
# ============================================================================

PPTX_DIMENSIONS = {
    'width_inches': 13.333,
    'height_inches': 7.5,
}

PPTX_COLORS = {
    'DARK_BLUE':    (0, 51, 102),
    'LIGHT_BLUE':   (0, 112, 192),
    'ACCENT_GREEN': (0, 128, 0),
    'SPAIN_RED':    (200, 16, 46),
    'SPAIN_YELLOW': (255, 196, 0),
    'WHITE':        (255, 255, 255),
    'DARK_GRAY':    (64, 64, 64),
    'LIGHT_GRAY':   (240, 240, 240),
    'RED':          (200, 0, 0),
    'DARK_RED':     (139, 0, 0),
    'PURPLE':       (128, 0, 128),
    'ORANGE':       (255, 140, 0),
    'GOLD':         (218, 165, 32),
    'KPI_BG':       (250, 250, 255),
    'KPI_RED_BG':   (255, 250, 250),
    'INSIGHT_BG':   (255, 248, 235),
    'BSEG_BG':      (230, 245, 255),
    'FILES_BG':     (240, 245, 255),
    'REC_BG':       (255, 245, 245),
    'KEY_FIND_BG':  (255, 240, 240),
    'SAVINGS_BG':   (240, 255, 240),
}

PPTX_KPI_LAYOUT = {
    'width': 3.0,
    'height': 0.8,
    'title_font_size': 9,
    'value_font_size': 16,
    'border_width_pt': 2,
}

PPTX_SLIDE_STRUCTURE = {
    'title_bar_height': 0.9,
    'title_font_size': 26,
    'subtitle_font_size': 12,
    'table_font_size': 9,
    'footer_font_size': 9,
    'footer_y': 7.1,
    'content_start_y': 1.1,
    'left_margin': 0.5,
    'right_margin': 0.5,
}


# ============================================================================
# 15. WORD DOCUMENT STYLING
# ============================================================================

DOCX_STYLES = {
    'normal_font': 'Calibri',
    'normal_size_pt': 10,
    'code_font': 'Consolas',
    'code_size_pt': 8.5,
    'code_color_rgb': (0, 0, 128),
    'heading_color_rgb': (0, 51, 102),
    'table_style': 'Light Grid Accent 1',
    'table_header_font_size_pt': 9,
    'table_body_font_size_pt': 9,
    'cover_title_size_pt': 36,
    'cover_subtitle_size_pt': 24,
    'cover_sub2_size_pt': 18,
    'cover_info_size_pt': 12,
    'toc_item_size_pt': 11,
}


# ============================================================================
# 16. DERIVED FLAGS & CALCULATED FIELDS
# ============================================================================

DERIVED_FLAGS = {
    'Has_PO': 'EBELN not null/empty',
    'Has_PR': 'EKPO.BANFN not null (for RSEG) / False for FI docs',
    'Has_GR': 'EKBE.VGABE="1" match (for RSEG) / False for FI docs',
    'Has_Material_Number': 'Material_Digit_Count > 0',
    'Has_PR_PO_GR': 'Has_PO AND Has_PR AND Has_GR',
    'Is_Debit': 'SHKZG == "S"',
    'Material_Digit_Count': 'Count of digits in MATNR after cleaning',
    'Spend_Type': 'DIRECT or INDIRECT per classification flowchart',
    'Spend_Type_Reason': 'Text explanation of classification',
    'Gross_Amount': 'DMBTR where Is_Debit (or WRBTR for doc currency)',
    'Credit_Amount': 'DMBTR where NOT Is_Debit',
    'Net_Amount': 'Signed amount (positive for debit, negative for credit)',
    'Country': 'BUKRS mapped via COMPANY_CODES lookup',
    'Maverick_Category': 'Risk label for maverick classification',
}


# ============================================================================
# 17. ANALYSIS MODES
# ============================================================================

ANALYSIS_MODES = {
    'full': {
        'description': 'Full dataset spend cube + maverick deep dive (all companies)',
        'input': 'Pre-built comprehensive BSEG+Vendor CSV',
        'filter_by': None,
        'pptx_slides': 8,
        'docx_sections': 22,
    },
    'company': {
        'description': 'Single company RSEG analysis with BSEG enrichment',
        'input': 'Pre-built comprehensive BSEG+Vendor CSV, filtered by BUKRS',
        'filter_by': 'BUKRS (Company Code)',
        'pptx_slides': 5,
        'docx_sections': 19,
    },
    'fi': {
        'description': 'FI document type analysis from BKPF/BSEG raw files',
        'input': 'BKPF + BSEG raw files, filtered by BUKRS + BLART',
        'filter_by': 'BUKRS + BLART',
        'pptx_slides': 5,
        'docx_sections': 19,
    },
}


# ============================================================================
# 18. OUTPUT FILE NAMING
# ============================================================================

OUTPUT_FILES = {
    'csv_full': 'SAP_SpendCube_Full_Dataset.csv',
    'csv_maverick': 'SAP_Maverick_Spend_Full_Dataset.csv',
    'csv_company': 'SAP_{name}_{bukrs}_Complete_Dataset.csv',
    'csv_fi': 'SAP_{name}_{bukrs}_DocTypes_{types}.csv',
    'pptx_full': 'SAP_SpendCube_Maverick_DeepDive.pptx',
    'pptx_company': 'SAP_{name}_{bukrs}_Presentation.pptx',
    'pptx_fi': 'SAP_{name}_{bukrs}_DocTypes_Presentation.pptx',
    'docx_full': 'SAP_SpendCube_Full_Analysis.docx',
    'docx_company': 'SAP_{name}_{bukrs}_Analysis.docx',
    'docx_fi': 'SAP_{name}_{bukrs}_DocTypes_Analysis.docx',
}


# ============================================================================
# 19. HELPER FUNCTIONS
# ============================================================================

def safe_vendor_name(s, max_len=28):
    """Encode vendor name to ASCII-safe string for printing/PPTX."""
    return str(s).encode('ascii', errors='replace').decode('ascii')[:max_len]

def fmt_eur(amount, unit='M'):
    """Format EUR amount with unit."""
    if unit == 'M':
        return f"EUR {amount/1e6:.1f}M"
    elif unit == 'K':
        return f"EUR {amount/1e3:.0f}K"
    else:
        return f"EUR {amount:,.0f}"

def fmt_pct(value, total, decimals=1):
    """Format as percentage."""
    if total == 0:
        return "0%"
    return f"{value/total*100:.{decimals}f}%"

def fmt_count(n):
    """Format integer with commas."""
    return f"{int(n):,}"

def get_analysis_date():
    """Return formatted date for footers."""
    return datetime.datetime.now().strftime('%b %Y')

def get_gl_description(gl_account):
    """Look up GL account description."""
    try:
        gl_int = int(float(gl_account))
        return GL_ACCOUNT_DESCRIPTIONS.get(gl_int, '')
    except (ValueError, TypeError):
        return ''

def get_country_name(bukrs):
    """Map BUKRS to country name."""
    try:
        return BUKRS_NAME_MAP.get(int(bukrs), 'Other')
    except (ValueError, TypeError):
        return 'Other'
