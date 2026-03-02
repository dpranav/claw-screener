"""
SAP Procurement Spend Cube - Data Loaders
==========================================
Load and prepare data from pre-built CSVs or raw SAP table exports.
Handles BSEG split files, memory optimization, and vendor enrichment.
"""

import pandas as pd
import numpy as np
import os
import glob
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (BSEG_LOAD_COLS, BKPF_LOAD_COLS, LFA1_LOAD_COLS,
                    BUKRS_NAME_MAP, COMPANY_CODES)


# ============================================================================
# PRE-BUILT DATASET LOADERS (for full and company modes)
# ============================================================================

def load_comprehensive_dataset(base_path, filename='SAP_Final_Comprehensive_With_BSEG_Vendor.csv'):
    """
    Load the pre-built comprehensive RSEG+BSEG+Vendor dataset.
    This is used for full-dataset and single-company analyses.
    """
    # Try multiple possible locations
    paths_to_try = [
        os.path.join(base_path, 'final-output-v3', filename),
        os.path.join(base_path, 'final-output', filename),
        os.path.join(base_path, filename),
    ]

    for path in paths_to_try:
        if os.path.exists(path):
            print(f"  Loading: {path}")
            df = pd.read_csv(path, low_memory=False)
            print(f"  Loaded {len(df):,} records with {len(df.columns)} columns")
            return df

    raise FileNotFoundError(
        f"Could not find {filename} in any of:\n" +
        '\n'.join(f'  - {p}' for p in paths_to_try)
    )


def load_normalized_dataset(base_path, filename='SAP_Final_Normalized_Data.csv'):
    """Load normalized data for UNSPSC and packaging classification."""
    paths_to_try = [
        os.path.join(base_path, 'final-output', filename),
        os.path.join(base_path, filename),
    ]

    for path in paths_to_try:
        if os.path.exists(path):
            print(f"  Loading normalized: {path}")
            df = pd.read_csv(path, low_memory=False)
            print(f"  Loaded {len(df):,} normalized records")
            return df

    print(f"  WARNING: Normalized data not found, skipping UNSPSC/packaging")
    return None


def filter_by_company(df, bukrs):
    """
    Filter dataset by company code.
    Handles BUKRS stored as int or string (e.g., 113 or '0113').
    """
    bukrs_int = int(str(bukrs).lstrip('0')) if str(bukrs).startswith('0') else int(bukrs)

    # Try integer comparison first
    if df['BUKRS'].dtype in ['int64', 'float64']:
        filtered = df[df['BUKRS'] == bukrs_int].copy()
    else:
        # String comparison - try both padded and unpadded
        bukrs_str = str(bukrs_int)
        bukrs_padded = str(bukrs).zfill(4)
        filtered = df[(df['BUKRS'].astype(str) == bukrs_str) |
                       (df['BUKRS'].astype(str) == bukrs_padded)].copy()

    print(f"  Filtered BUKRS={bukrs_int}: {len(filtered):,} of {len(df):,} records")
    return filtered


def add_country_column(df):
    """Add Country column from BUKRS mapping."""
    df['Country'] = df['BUKRS'].map(BUKRS_NAME_MAP).fillna('Other')
    return df


# ============================================================================
# RAW SAP TABLE LOADERS (for FI mode)
# ============================================================================

def load_bkpf(base_path, bukrs=None, doc_types=None, filename='HRP_BKPF.csv'):
    """
    Load BKPF (Accounting Document Headers) with reduced columns for memory.
    Optionally filter by company code and document types.
    """
    filepath = os.path.join(base_path, filename)
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"BKPF file not found: {filepath}")

    print(f"  Loading BKPF: {filepath}")
    bkpf = pd.read_csv(filepath, sep=';', low_memory=False, usecols=BKPF_LOAD_COLS,
                        on_bad_lines='skip', quotechar='"')
    print(f"  Raw BKPF: {len(bkpf):,} rows")

    if bukrs is not None:
        bukrs_int = int(str(bukrs).lstrip('0')) if str(bukrs).startswith('0') else int(bukrs)
        bkpf['BUKRS'] = pd.to_numeric(bkpf['BUKRS'], errors='coerce')
        bkpf = bkpf[bkpf['BUKRS'] == bukrs_int]
        print(f"  After BUKRS={bukrs_int}: {len(bkpf):,}")

    if doc_types is not None:
        bkpf = bkpf[bkpf['BLART'].isin(doc_types)]
        print(f"  After doc types {doc_types}: {len(bkpf):,}")

    return bkpf


def load_bseg_for_docs(base_path, target_keys, bukrs=None, file_pattern='hrp--BSEG.csv_part*.csv'):
    """
    Load BSEG lines matching specific document keys from split files.
    target_keys: set of (BELNR, GJAHR) tuples
    """
    pattern = os.path.join(base_path, file_pattern)
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No BSEG files found matching: {pattern}")

    print(f"  Loading BSEG from {len(files)} part files...")
    parts = []

    for i, f in enumerate(files, 1):
        try:
            chunk = pd.read_csv(f, sep=';', low_memory=False, usecols=BSEG_LOAD_COLS,
                                on_bad_lines='skip')

            if bukrs is not None:
                bukrs_int = int(str(bukrs).lstrip('0')) if str(bukrs).startswith('0') else int(bukrs)
                chunk['BUKRS'] = pd.to_numeric(chunk['BUKRS'], errors='coerce')
                chunk = chunk[chunk['BUKRS'] == bukrs_int]

            if len(chunk) > 0:
                # Match to target document keys
                chunk['_key'] = chunk['BELNR'].astype(str) + '_' + chunk['GJAHR'].astype(str)
                target_key_strs = {f"{b}_{g}" for b, g in target_keys}
                chunk = chunk[chunk['_key'].isin(target_key_strs)]
                chunk = chunk.drop(columns=['_key'])

            if len(chunk) > 0:
                parts.append(chunk)
                print(f"    Part {i:02d}: {len(chunk):,} matched lines")
        except Exception as e:
            print(f"    Part {i:02d}: ERROR - {e}")

    if parts:
        result = pd.concat(parts, ignore_index=True)
        print(f"  Total BSEG lines: {len(result):,}")
        return result
    else:
        print("  WARNING: No BSEG lines matched")
        return pd.DataFrame()


def load_lfa1(base_path, filename='HRP_LFA1.csv'):
    """Load LFA1 (Vendor Master) with reduced columns."""
    filepath = os.path.join(base_path, filename)
    if not os.path.exists(filepath):
        print(f"  WARNING: LFA1 not found at {filepath}")
        return pd.DataFrame()

    # Try loading with limited columns
    try:
        lfa1 = pd.read_csv(filepath, sep=';', low_memory=False, usecols=LFA1_LOAD_COLS,
                            on_bad_lines='skip', quotechar='"')
    except (ValueError, KeyError):
        # Some columns might not exist, try just the essentials
        lfa1 = pd.read_csv(filepath, sep=';', low_memory=False,
                            usecols=['LIFNR', 'NAME1', 'LAND1'],
                            on_bad_lines='skip', quotechar='"')

    print(f"  LFA1: {len(lfa1):,} vendors loaded")
    return lfa1


# ============================================================================
# DATA ENRICHMENT
# ============================================================================

def enrich_with_vendors(df, lfa1):
    """
    Enrich DataFrame with vendor names from LFA1.
    Also fills missing vendor info within documents (vendor propagation).
    """
    if len(lfa1) == 0 or 'LIFNR' not in df.columns:
        return df

    # Merge vendor info
    lfa1_slim = lfa1[['LIFNR', 'NAME1', 'LAND1']].drop_duplicates(subset='LIFNR')
    df = df.merge(lfa1_slim, on='LIFNR', how='left', suffixes=('', '_lfa1'))

    # Handle column name conflicts
    if 'NAME1_lfa1' in df.columns:
        df['NAME1'] = df['NAME1'].fillna(df['NAME1_lfa1'])
        df['LAND1'] = df['LAND1'].fillna(df['LAND1_lfa1'])
        df = df.drop(columns=[c for c in df.columns if c.endswith('_lfa1')])

    # Propagate vendor within documents (for FI docs where some lines lack LIFNR)
    vendor_map = df[df['NAME1'].notna()].groupby(['BELNR', 'GJAHR']).agg({
        'NAME1': 'first', 'LAND1': 'first', 'LIFNR': 'first'
    }).reset_index()
    vendor_map.columns = ['BELNR', 'GJAHR', 'NAME1_fill', 'LAND1_fill', 'LIFNR_fill']

    df = df.merge(vendor_map, on=['BELNR', 'GJAHR'], how='left')
    df['NAME1'] = df['NAME1'].fillna(df['NAME1_fill'])
    df['LAND1'] = df['LAND1'].fillna(df['LAND1_fill'])
    df['LIFNR'] = df['LIFNR'].fillna(df['LIFNR_fill'])
    df = df.drop(columns=['NAME1_fill', 'LAND1_fill', 'LIFNR_fill'])

    return df


def merge_bkpf_into_bseg(bseg_df, bkpf_df):
    """Merge BKPF header fields into BSEG line items."""
    bkpf_info = bkpf_df[['BELNR', 'GJAHR', 'BLART', 'WAERS', 'BUDAT', 'BLDAT', 'TCODE']].copy()

    merged = bseg_df.merge(bkpf_info, on=['BELNR', 'GJAHR'], how='left',
                           suffixes=('', '_bkpf'))

    # Handle conflicts
    for col in ['BLART', 'WAERS', 'BUDAT', 'BLDAT', 'TCODE']:
        if f'{col}_bkpf' in merged.columns:
            merged[col] = merged[col].fillna(merged[f'{col}_bkpf'])
            merged = merged.drop(columns=[f'{col}_bkpf'])

    return merged
