"""
SAP Procurement Spend Cube - Classification Engine
====================================================
Direct/Indirect classification, Maverick spend tiers, Three-way match,
Debit/Credit computation, and all derived flag logic.
"""

import pandas as pd
import numpy as np
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import KOART_MAPPINGS


# ============================================================================
# DIRECT / INDIRECT CLASSIFICATION
# ============================================================================

def classify_spend_rseg(row):
    """
    Classify row as DIRECT/INDIRECT using the standard flowchart.
    For RSEG-based (MM Invoice Verification) records.
    """
    if not row.get('Has_PR_PO_GR', False):
        return 'INDIRECT', 'No PR/PO/GR document reference'
    if not row.get('Has_Material_Number', False):
        return 'INDIRECT', 'No material number'
    digits = row.get('Material_Digit_Count', 0)
    if digits == 6:
        return 'DIRECT', 'Material number has 6 digits (6 = Direct)'
    elif digits >= 7:
        return 'INDIRECT', f'Material number has {digits} digits (7+ = Indirect)'
    else:
        return 'INDIRECT', f'Material number has {digits} digits (less than 6)'


def classify_spend_fi(row):
    """
    Classify row as DIRECT/INDIRECT for FI-direct documents.
    FI docs typically lack PR/GR so first check is Has_PO only.
    """
    if not row.get('Has_PO', False):
        return 'INDIRECT', 'No PO reference (FI document)'
    if not row.get('Has_Material_Number', False):
        return 'INDIRECT', 'No material number'
    digits = row.get('Material_Digit_Count', 0)
    if digits == 6:
        return 'DIRECT', 'Material number has 6 digits (6 = Direct)'
    elif digits >= 7:
        return 'INDIRECT', f'Material number has {digits} digits (7+ = Indirect)'
    else:
        return 'INDIRECT', f'Material number has {digits} digits (less than 6)'


def apply_classification(df, mode='rseg'):
    """Apply spend classification to entire DataFrame. Returns df with Spend_Type and Spend_Type_Reason columns."""
    if 'Spend_Type' in df.columns and 'Spend_Type_Reason' in df.columns:
        # Already classified (pre-built dataset)
        print("  Classification already present in data")
        return df

    classify_fn = classify_spend_rseg if mode == 'rseg' else classify_spend_fi
    print(f"  Classifying spend ({mode} mode)...")
    results = df.apply(classify_fn, axis=1)
    df['Spend_Type'] = [r[0] for r in results]
    df['Spend_Type_Reason'] = [r[1] for r in results]
    return df


# ============================================================================
# DEBIT / CREDIT COMPUTATION
# ============================================================================

def compute_debit_credit(df):
    """Compute debit/credit fields from SHKZG indicator."""
    if 'Is_Debit' in df.columns and 'Gross_Amount' in df.columns:
        print("  Debit/Credit already computed")
        return df

    df['Is_Debit'] = df['SHKZG'] == 'S'
    df['Debit_Credit'] = df['SHKZG'].map({
        'S': 'Debit (Expense)',
        'H': 'Credit (Reversal)'
    }).fillna('Unknown')

    # Determine amount column
    dmbtr_col = 'DMBTR' if 'DMBTR' in df.columns else 'WRBTR'
    df[dmbtr_col] = pd.to_numeric(df[dmbtr_col], errors='coerce').fillna(0)

    df['Amount_Signed'] = np.where(df['SHKZG'] == 'H', -df[dmbtr_col], df[dmbtr_col])
    df['Gross_Amount'] = np.where(df['Is_Debit'], df[dmbtr_col], 0)
    df['Credit_Amount'] = np.where(~df['Is_Debit'], df[dmbtr_col], 0)
    df['Net_Amount'] = df['Amount_Signed']

    return df


# ============================================================================
# MATERIAL FLAGS
# ============================================================================

def compute_material_flags(df):
    """Compute material digit count and Has_Material_Number flag."""
    if 'Material_Digit_Count' in df.columns and 'Has_Material_Number' in df.columns:
        print("  Material flags already computed")
        return df

    matnr_col = 'MATNR'
    if 'MATNR_ENRICHED' in df.columns:
        matnr_col = 'MATNR_ENRICHED'

    df[matnr_col] = df[matnr_col].astype(str).replace('nan', '')
    df['Material_Digit_Count'] = df[matnr_col].apply(
        lambda x: len(''.join(c for c in str(x) if c.isdigit()))
        if pd.notna(x) and str(x).strip() not in ['', 'nan', 'None'] else 0
    )
    df['Has_Material_Number'] = df['Material_Digit_Count'] > 0
    return df


# ============================================================================
# PO / PR / GR FLAGS
# ============================================================================

def compute_po_flags_rseg(df):
    """Compute PO/PR/GR flags for RSEG-based (pre-built) data."""
    if 'Has_PO' not in df.columns:
        df['EBELN'] = df['EBELN'].astype(str).replace('nan', '')
        df['Has_PO'] = (df['EBELN'].str.strip() != '') & (df['EBELN'] != 'nan')
    if 'Has_PR' not in df.columns:
        df['Has_PR'] = False
    if 'Has_GR' not in df.columns:
        df['Has_GR'] = False
    if 'Has_PR_PO_GR' not in df.columns:
        df['Has_PR_PO_GR'] = df['Has_PO'] & df['Has_PR'] & df['Has_GR']
    return df


def compute_po_flags_fi(df):
    """Compute PO flags for FI-direct documents. PR and GR are always False."""
    df['EBELN'] = df['EBELN'].astype(str).replace('nan', '')
    df['Has_PO'] = (df['EBELN'].str.strip() != '') & (df['EBELN'] != 'nan') & (df['EBELN'] != '')
    df['Has_PR'] = False
    df['Has_GR'] = False
    df['Has_PR_PO_GR'] = df['Has_PO']
    return df


# ============================================================================
# ACCOUNT TYPE MAPPING
# ============================================================================

def compute_account_type(df):
    """Map KOART to descriptive account type names."""
    if 'KOART' in df.columns:
        df['Account_Type'] = df['KOART'].map(KOART_MAPPINGS).fillna('Other')
    return df


# ============================================================================
# MAVERICK SPEND COMPUTATION
# ============================================================================

def compute_maverick_rseg(df):
    """
    Compute all maverick spend tiers for RSEG-based data.
    Returns dict of metrics with masks, line counts, and spend amounts.
    """
    total_gross = df['Gross_Amount'].sum()

    no_pr = ~df['Has_PR']
    no_gr = ~df['Has_GR']
    no_mat = ~df['Has_Material_Number']
    has_po = df['Has_PO']
    has_pr = df['Has_PR']
    has_gr = df['Has_GR']

    # Tiers
    primary = no_pr & no_gr                # HIGH: No PR + No GR
    critical = no_pr & no_gr & no_mat      # CRITICAL: No PR + No GR + No Material
    medium_no_pr = no_pr & has_gr          # MEDIUM: No PR only
    medium_no_gr = has_pr & no_gr          # MEDIUM: No GR only
    low = has_pr & has_gr & no_mat         # LOW: No Material only

    # Three-way match
    three_way = has_po & has_pr & has_gr
    po_gr = has_po & ~has_pr & has_gr
    po_pr = has_po & has_pr & ~has_gr
    po_only = has_po & ~has_pr & ~has_gr

    metrics = {
        'primary': {'mask': primary, 'lines': int(primary.sum()), 'spend': float(df.loc[primary, 'Gross_Amount'].sum())},
        'critical': {'mask': critical, 'lines': int(critical.sum()), 'spend': float(df.loc[critical, 'Gross_Amount'].sum())},
        'medium_no_pr': {'mask': medium_no_pr, 'lines': int(medium_no_pr.sum()), 'spend': float(df.loc[medium_no_pr, 'Gross_Amount'].sum())},
        'medium_no_gr': {'mask': medium_no_gr, 'lines': int(medium_no_gr.sum()), 'spend': float(df.loc[medium_no_gr, 'Gross_Amount'].sum())},
        'low': {'mask': low, 'lines': int(low.sum()), 'spend': float(df.loc[low, 'Gross_Amount'].sum())},
        'three_way_match': {'mask': three_way, 'lines': int(three_way.sum()), 'spend': float(df.loc[three_way, 'Gross_Amount'].sum())},
        'po_gr': {'mask': po_gr, 'lines': int(po_gr.sum()), 'spend': float(df.loc[po_gr, 'Gross_Amount'].sum())},
        'po_pr': {'mask': po_pr, 'lines': int(po_pr.sum()), 'spend': float(df.loc[po_pr, 'Gross_Amount'].sum())},
        'po_only': {'mask': po_only, 'lines': int(po_only.sum()), 'spend': float(df.loc[po_only, 'Gross_Amount'].sum())},
        'three_way_rate': float(three_way.sum() / len(df) * 100) if len(df) > 0 else 0,
        'total_gross': float(total_gross),
        'total_records': len(df),
    }
    return metrics


def compute_maverick_fi(df):
    """Compute maverick spend for FI-direct documents."""
    total_gross = df['Gross_Amount'].sum()

    no_po = ~df['Has_PO']
    no_mat = ~df['Has_Material_Number']

    primary = no_po
    critical = no_po & no_mat

    metrics = {
        'primary': {'mask': primary, 'lines': int(primary.sum()), 'spend': float(df.loc[primary, 'Gross_Amount'].sum())},
        'critical': {'mask': critical, 'lines': int(critical.sum()), 'spend': float(df.loc[critical, 'Gross_Amount'].sum())},
        'total_gross': float(total_gross),
        'total_records': len(df),
    }
    return metrics


# ============================================================================
# CREDIT-HEAVY VENDORS
# ============================================================================

def compute_credit_heavy_vendors(df, ratio_threshold=0.20, min_debit=1000):
    """Find vendors with high credit-to-debit ratios."""
    vendor_col = 'NAME1' if 'NAME1' in df.columns else 'Vendor'
    if vendor_col not in df.columns:
        return pd.DataFrame(columns=['Vendor', 'Debit_Total', 'Credit_Total', 'Credit_Ratio'])

    vendor_dc = df[df[vendor_col].notna()].groupby(vendor_col).agg({
        'Gross_Amount': 'sum',
        'Credit_Amount': 'sum',
    }).reset_index()
    vendor_dc.columns = ['Vendor', 'Debit_Total', 'Credit_Total']
    vendor_dc['Credit_Ratio'] = vendor_dc['Credit_Total'] / vendor_dc['Debit_Total'].replace(0, np.nan)

    high_credit = vendor_dc[
        (vendor_dc['Credit_Ratio'] > ratio_threshold) &
        (vendor_dc['Debit_Total'] > min_debit)
    ].sort_values('Credit_Ratio', ascending=False)

    return high_credit


def compute_credit_heavy_pct_based(df, min_debit=50000):
    """
    Credit-heavy analysis using percentage-based ratio (for full dataset).
    Returns vendors with Credit_Ratio as percentage (e.g., 25 = 25%).
    """
    vendor_col = 'NAME1' if 'NAME1' in df.columns else 'Vendor'
    if vendor_col not in df.columns:
        return pd.DataFrame(columns=['Vendor', 'Debit_EUR', 'Credit_EUR', 'Credit_Ratio'])

    # Separate debit and credit by vendor
    vendor_dc = df[df[vendor_col].notna()].groupby([vendor_col, 'Debit_Credit']).agg({
        'Gross_Amount': 'sum', 'Credit_Amount': 'sum', 'BELNR': 'count'
    }).reset_index()

    vd = vendor_dc[vendor_dc['Debit_Credit'].str.contains('Debit', na=False)].groupby(vendor_col)['Gross_Amount'].sum().reset_index()
    vd.columns = ['Vendor', 'Debit_EUR']
    vc = vendor_dc[vendor_dc['Debit_Credit'].str.contains('Credit', na=False)].groupby(vendor_col)['Credit_Amount'].sum().reset_index()
    vc.columns = ['Vendor', 'Credit_EUR']

    vcomb = vd.merge(vc, on='Vendor', how='left')
    vcomb['Credit_EUR'] = vcomb['Credit_EUR'].fillna(0)
    vcomb['Credit_Ratio'] = vcomb['Credit_EUR'] / vcomb['Debit_EUR'] * 100
    vcomb = vcomb[vcomb['Credit_EUR'] > 0].sort_values('Credit_Ratio', ascending=False)

    high_credit = vcomb[(vcomb['Credit_Ratio'] > 20) & (vcomb['Debit_EUR'] > min_debit)]
    return high_credit


# ============================================================================
# SINGLE-SOURCE RISK
# ============================================================================

def compute_single_source(df):
    """
    Find materials sourced from only 1 vendor.
    Returns: (single_source_df, single_count, single_pct, multi_count, ss_spend, ms_spend)
    """
    mat_col = 'MATNR_ENRICHED' if 'MATNR_ENRICHED' in df.columns else 'MATNR'
    vendor_col = 'NAME1' if 'NAME1' in df.columns else 'LIFNR'

    if mat_col not in df.columns or vendor_col not in df.columns:
        return pd.DataFrame(), 0, 0, 0, 0, 0

    mat_vendor = df[(df[mat_col].notna()) & (df[mat_col].astype(str) != '') &
                     (df[mat_col].astype(str) != 'nan') & (df[vendor_col].notna())]

    if len(mat_vendor) == 0:
        return pd.DataFrame(), 0, 0, 0, 0, 0

    mat_count = mat_vendor.groupby(mat_col).agg({
        vendor_col: 'nunique',
        'Gross_Amount': 'sum',
    }).reset_index()
    mat_count.columns = ['Material', 'Vendor_Count', 'Gross_EUR']

    single = mat_count[mat_count['Vendor_Count'] == 1]
    multi = mat_count[mat_count['Vendor_Count'] > 1]
    total = len(mat_count)
    ss_count = len(single)
    ms_count = len(multi)
    ss_pct = ss_count / total * 100 if total > 0 else 0
    ss_spend = single['Gross_EUR'].sum()
    ms_spend = multi['Gross_EUR'].sum()

    return single, ss_count, ss_pct, ms_count, ss_spend, ms_spend


# ============================================================================
# FULL PIPELINE: PREPARE DATA
# ============================================================================

def prepare_rseg_data(df):
    """Full preparation pipeline for RSEG-based data (pre-built CSV)."""
    print("  Preparing RSEG data...")
    df = compute_material_flags(df)
    df = compute_po_flags_rseg(df)
    df = compute_debit_credit(df)
    df = apply_classification(df, mode='rseg')
    return df


def prepare_fi_data(df):
    """Full preparation pipeline for FI-direct documents (BKPF/BSEG)."""
    print("  Preparing FI data...")
    df = compute_debit_credit(df)
    df = compute_material_flags(df)
    df = compute_po_flags_fi(df)
    df = compute_account_type(df)
    df = apply_classification(df, mode='fi')
    return df
