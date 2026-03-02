"""
SAP Procurement Spend Cube - Metrics Computation Engine
========================================================
Compute all KPIs, breakdowns, and analytical metrics.
Supports full-dataset (multi-company) and single-company modes.
Uses named aggregation to avoid duplicate column key issues.
"""

import pandas as pd
import numpy as np
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import BUKRS_NAME_MAP, GL_ACCOUNT_DESCRIPTIONS, safe_vendor_name


# ============================================================================
# BASIC METRICS
# ============================================================================

def compute_basic_metrics(df):
    """Compute fundamental spend metrics."""
    m = {}
    m['total_records'] = len(df)
    m['total_gross'] = float(df['Gross_Amount'].sum())
    m['total_net'] = float(df['Net_Amount'].sum())
    m['total_credit'] = float(df['Credit_Amount'].sum())
    m['total_dmbtr'] = float(df['DMBTR'].sum()) if 'DMBTR' in df.columns else m['total_gross'] + m['total_credit']
    m['unique_invoices'] = int(df['BELNR'].nunique())
    m['unique_pos'] = int(df['EBELN'].nunique()) if 'EBELN' in df.columns else 0
    m['debit_count'] = int(df['Is_Debit'].sum())
    m['credit_count'] = m['total_records'] - m['debit_count']
    if 'DMBTR' in df.columns:
        m['debit_spend'] = float(df[df['Is_Debit']]['DMBTR'].sum())
    else:
        m['debit_spend'] = float(df[df['Is_Debit']]['Gross_Amount'].sum())
    return m


# ============================================================================
# DIRECT / INDIRECT BREAKDOWN
# ============================================================================

def compute_direct_indirect(df):
    """Compute Direct/Indirect breakdown with reason analysis."""
    direct = df[df['Spend_Type'] == 'DIRECT']
    indirect = df[df['Spend_Type'] == 'INDIRECT']
    total_gross = df['Gross_Amount'].sum()

    m = {}
    m['direct_spend'] = float(direct['Gross_Amount'].sum())
    m['indirect_spend'] = float(indirect['Gross_Amount'].sum())
    m['direct_lines'] = len(direct)
    m['indirect_lines'] = len(indirect)
    m['direct_pct'] = m['direct_spend'] / total_gross * 100 if total_gross > 0 else 0
    m['indirect_pct'] = m['indirect_spend'] / total_gross * 100 if total_gross > 0 else 0

    # Indirect by reason
    m['indirect_reasons'] = indirect.groupby('Spend_Type_Reason').agg(
        Lines=('BELNR', 'count'),
        EUR_Amount=('Gross_Amount', 'sum'),
    ).reset_index()
    m['indirect_reasons'].columns = ['Reason', 'Lines', 'EUR_Amount']
    m['indirect_reasons'] = m['indirect_reasons'].sort_values('EUR_Amount', ascending=False)

    return m


# ============================================================================
# MATERIAL METRICS
# ============================================================================

def compute_material_metrics(df):
    """Compute material classification breakdown."""
    m = {}
    no_mat = df[~df['Has_Material_Number']]
    m['no_material_lines'] = len(no_mat)
    m['no_material_spend'] = float(no_mat['Gross_Amount'].sum())

    if 'Material_Digit_Count' in df.columns:
        six = df[df['Material_Digit_Count'] == 6]
        seven = df[df['Material_Digit_Count'] >= 7]
        m['six_digit_lines'] = len(six)
        m['six_digit_spend'] = float(six['Gross_Amount'].sum())
        m['seven_plus_lines'] = len(seven)
        m['seven_plus_spend'] = float(seven['Gross_Amount'].sum())
        m['digit_distribution'] = df['Material_Digit_Count'].value_counts().sort_index().to_dict()
    else:
        m['six_digit_lines'] = 0
        m['six_digit_spend'] = 0
        m['seven_plus_lines'] = 0
        m['seven_plus_spend'] = 0
        m['digit_distribution'] = {}

    return m


# ============================================================================
# BSEG COVERAGE
# ============================================================================

def compute_bseg_coverage(df):
    """Compute BSEG field coverage metrics."""
    total = len(df)
    m = {}

    gl_col = 'BSEG_GL_Account' if 'BSEG_GL_Account' in df.columns else 'HKONT'
    m['gl_coverage'] = int(df[gl_col].notna().sum()) if gl_col in df.columns else 0

    pc_col = 'BSEG_Profit_Center' if 'BSEG_Profit_Center' in df.columns else 'PRCTR'
    m['prctr_coverage'] = int(df[pc_col].notna().sum()) if pc_col in df.columns else 0

    cc_col = 'BSEG_Cost_Center' if 'BSEG_Cost_Center' in df.columns else 'KOSTL'
    if cc_col in df.columns:
        m['kostl_coverage'] = int((df[cc_col].notna() &
                                    (df[cc_col].astype(str) != '') &
                                    (df[cc_col].astype(str) != 'nan') &
                                    (df[cc_col].astype(str) != 'None')).sum())
    else:
        m['kostl_coverage'] = 0

    m['gl_pct'] = m['gl_coverage'] / total * 100 if total > 0 else 0
    m['prctr_pct'] = m['prctr_coverage'] / total * 100 if total > 0 else 0
    m['kostl_pct'] = m['kostl_coverage'] / total * 100 if total > 0 else 0

    return m


# ============================================================================
# GL ACCOUNT ANALYSIS
# ============================================================================

def compute_gl_analysis(df, top_n=15):
    """Top GL accounts by spend."""
    gl_col = 'BSEG_GL_Account' if 'BSEG_GL_Account' in df.columns else 'HKONT'
    if gl_col not in df.columns:
        return pd.DataFrame()

    has_dmbtr = 'DMBTR' in df.columns
    filtered = df[df[gl_col].notna()]

    if has_dmbtr:
        analysis = filtered.groupby(gl_col).agg(
            Gross_EUR=('Gross_Amount', 'sum'),
            Lines=('BELNR', 'count'),
            Total_EUR=('DMBTR', 'sum'),
        ).reset_index().sort_values('Total_EUR', ascending=False).head(top_n)
        analysis.columns = ['GL_Account', 'Gross_EUR', 'Lines', 'Total_EUR']
    else:
        analysis = filtered.groupby(gl_col).agg(
            Gross_EUR=('Gross_Amount', 'sum'),
            Lines=('BELNR', 'count'),
        ).reset_index().sort_values('Gross_EUR', ascending=False).head(top_n)
        analysis.columns = ['GL_Account', 'Gross_EUR', 'Lines']
        analysis['Total_EUR'] = analysis['Gross_EUR']

    return analysis


# ============================================================================
# PROFIT CENTER ANALYSIS
# ============================================================================

def compute_prctr_analysis(df, top_n=10):
    """Top profit centers by spend."""
    pc_col = 'BSEG_Profit_Center' if 'BSEG_Profit_Center' in df.columns else 'PRCTR'
    if pc_col not in df.columns:
        return pd.DataFrame()

    amt_col = 'DMBTR' if 'DMBTR' in df.columns else 'Gross_Amount'
    analysis = df[df[pc_col].notna()].groupby(pc_col).agg(
        Total_EUR=(amt_col, 'sum'), Lines=('BELNR', 'count')
    ).reset_index().sort_values('Total_EUR', ascending=False).head(top_n)
    analysis.columns = ['Profit_Center', 'Total_EUR', 'Lines']
    return analysis


# ============================================================================
# COST CENTER ANALYSIS
# ============================================================================

def compute_kostl_analysis(df, top_n=10):
    """Top cost centers by spend."""
    cc_col = 'BSEG_Cost_Center' if 'BSEG_Cost_Center' in df.columns else 'KOSTL'
    if cc_col not in df.columns:
        return pd.DataFrame()

    amt_col = 'DMBTR' if 'DMBTR' in df.columns else 'Gross_Amount'
    valid = df[(df[cc_col].notna()) &
               (df[cc_col].astype(str) != '') &
               (df[cc_col].astype(str) != 'nan')]

    if len(valid) == 0:
        return pd.DataFrame()

    analysis = valid.groupby(cc_col).agg(
        Total_EUR=(amt_col, 'sum'), Lines=('BELNR', 'count')
    ).reset_index().sort_values('Total_EUR', ascending=False).head(top_n)
    analysis.columns = ['Cost_Center', 'Total_EUR', 'Lines']
    return analysis


# ============================================================================
# VENDOR METRICS
# ============================================================================

def compute_vendor_metrics(df, total_spend=None):
    """Compute vendor concentration metrics."""
    vendor_col = 'NAME1'
    if vendor_col not in df.columns:
        return {}, pd.DataFrame()

    vendor_df = df[df[vendor_col].notna()].copy()
    has_dmbtr = 'DMBTR' in df.columns

    if has_dmbtr:
        vendor_spend = vendor_df.groupby(vendor_col).agg(
            Total_EUR=('DMBTR', 'sum'),
            Gross_EUR=('Gross_Amount', 'sum'),
            Net_EUR=('Net_Amount', 'sum'),
            Lines=('BELNR', 'count'),
        ).reset_index().sort_values('Total_EUR', ascending=False)
    else:
        vendor_spend = vendor_df.groupby(vendor_col).agg(
            Gross_EUR=('Gross_Amount', 'sum'),
            Net_EUR=('Net_Amount', 'sum'),
            Lines=('BELNR', 'count'),
        ).reset_index().sort_values('Gross_EUR', ascending=False)
        vendor_spend['Total_EUR'] = vendor_spend['Gross_EUR']

    if 'EBELN' in vendor_df.columns:
        po_counts = vendor_df[vendor_df['EBELN'].astype(str).str.strip() != ''].groupby(vendor_col)['EBELN'].nunique().reset_index()
        po_counts.columns = [vendor_col, 'Unique_POs']
        vendor_spend = vendor_spend.merge(po_counts, on=vendor_col, how='left')
        vendor_spend['Unique_POs'] = vendor_spend['Unique_POs'].fillna(0).astype(int)
    else:
        vendor_spend['Unique_POs'] = 0

    vendor_spend = vendor_spend.rename(columns={vendor_col: 'Vendor'})

    if total_spend is None:
        total_spend = vendor_spend['Total_EUR'].sum()

    total_vendors = len(vendor_spend)
    top10 = vendor_spend.head(10)['Total_EUR'].sum()
    top20 = vendor_spend.head(20)['Total_EUR'].sum()
    top10_pct = top10 / total_spend * 100 if total_spend > 0 else 0
    top20_pct = top20 / total_spend * 100 if total_spend > 0 else 0

    cumsum = vendor_spend['Total_EUR'].cumsum()
    pareto_80 = int((cumsum <= total_spend * 0.8).sum() + 1)

    vendor_coverage = len(vendor_df) / len(df) * 100 if len(df) > 0 else 0

    m = {
        'total_vendors': total_vendors,
        'vendor_coverage': vendor_coverage,
        'top10_pct': top10_pct,
        'top20_pct': top20_pct,
        'pareto_80': pareto_80,
    }

    return m, vendor_spend


# ============================================================================
# SPEND BY COUNTRY
# ============================================================================

def compute_country_breakdown(df):
    """Spend breakdown by country/company code."""
    if 'Country' not in df.columns:
        df['Country'] = df['BUKRS'].map(BUKRS_NAME_MAP).fillna('Other')

    by_country = df.groupby('Country').agg(
        Gross_EUR=('Gross_Amount', 'sum'),
        Net_EUR=('Net_Amount', 'sum'),
        Lines=('BELNR', 'count'),
    ).reset_index().sort_values('Gross_EUR', ascending=False)

    return by_country


# ============================================================================
# PLANT ANALYSIS
# ============================================================================

def compute_plant_analysis(df, top_n=10):
    """Top plants/locations by spend."""
    if 'WERKS' not in df.columns:
        return pd.DataFrame()

    amt_col = 'DMBTR' if 'DMBTR' in df.columns else 'Gross_Amount'
    valid = df[df['WERKS'].notna() & (df['WERKS'].astype(str) != '') & (df['WERKS'].astype(str) != 'nan')]

    if len(valid) == 0:
        return pd.DataFrame()

    analysis = valid.groupby('WERKS').agg(
        Total_EUR=(amt_col, 'sum'), Lines=('BELNR', 'count')
    ).reset_index().sort_values('Total_EUR', ascending=False).head(top_n)
    analysis.columns = ['Plant', 'Total_EUR', 'Lines']
    return analysis


# ============================================================================
# DOCUMENT TYPE / POSTING KEY / ACCOUNT TYPE ANALYSIS
# ============================================================================

def compute_doc_type_stats(df):
    """Breakdown by document type (BLART)."""
    if 'BLART' not in df.columns:
        return pd.DataFrame()

    amt_col = 'DMBTR' if 'DMBTR' in df.columns else 'Gross_Amount'
    stats = df.groupby('BLART').agg(
        Total_Amount=(amt_col, 'sum'),
        Lines=('BELNR', 'count'),
        Gross=('Gross_Amount', 'sum'),
        Credits=('Credit_Amount', 'sum'),
    ).reset_index()
    stats.columns = ['Doc_Type', 'Total_Amount', 'Lines', 'Gross', 'Credits']
    return stats.sort_values('Total_Amount', ascending=False)


def compute_posting_key_analysis(df, top_n=10):
    """Posting key (BSCHL) analysis."""
    if 'BSCHL' not in df.columns:
        return pd.DataFrame()

    amt_col = 'DMBTR' if 'DMBTR' in df.columns else 'Gross_Amount'
    analysis = df.groupby('BSCHL').agg(
        Total_EUR=(amt_col, 'sum'), Lines=('BELNR', 'count')
    ).reset_index().sort_values('Total_EUR', ascending=False).head(top_n)
    analysis.columns = ['Posting_Key', 'Total_EUR', 'Lines']
    return analysis


def compute_account_type_analysis(df):
    """Account type (KOART) analysis."""
    if 'Account_Type' not in df.columns:
        return pd.DataFrame()

    amt_col = 'DMBTR' if 'DMBTR' in df.columns else 'Gross_Amount'
    analysis = df.groupby('Account_Type').agg(
        Total_EUR=(amt_col, 'sum'), Lines=('BELNR', 'count')
    ).reset_index().sort_values('Total_EUR', ascending=False)
    analysis.columns = ['Account_Type', 'Total_EUR', 'Lines']
    return analysis


# ============================================================================
# MAVERICK DIMENSION ANALYSES (for full-dataset spend cube)
# ============================================================================

def compute_maverick_by_country(df, mav_mask, by_country_df):
    """Maverick spend breakdown by country."""
    mav_df = df[mav_mask].copy()
    if 'Country' not in mav_df.columns:
        mav_df['Country'] = mav_df['BUKRS'].map(BUKRS_NAME_MAP).fillna('Other')

    mav_country = mav_df.groupby('Country').agg(
        Mav_Gross=('Gross_Amount', 'sum'),
        Mav_Lines=('BELNR', 'count'),
    ).reset_index().sort_values('Mav_Gross', ascending=False)

    # Merge with total by country
    mav_country = mav_country.merge(by_country_df[['Country', 'Gross_EUR', 'Lines']], on='Country', how='left')
    mav_country['Mav_Pct'] = mav_country['Mav_Gross'] / mav_country['Gross_EUR'] * 100

    return mav_country


def compute_maverick_vendors(df, mav_mask):
    """Top vendors within maverick spend."""
    mav_df = df[mav_mask & df['NAME1'].notna()].copy()
    if len(mav_df) == 0:
        return pd.DataFrame(columns=['Vendor', 'Gross_EUR', 'Lines', 'POs'])

    mav_vendors = mav_df.groupby('NAME1').agg(
        Gross_EUR=('Gross_Amount', 'sum'),
        Lines=('BELNR', 'count'),
    ).reset_index().sort_values('Gross_EUR', ascending=False)

    if 'EBELN' in mav_df.columns:
        po_c = mav_df[mav_df['EBELN'].astype(str).str.strip() != ''].groupby('NAME1')['EBELN'].nunique().reset_index()
        po_c.columns = ['NAME1', 'POs']
        mav_vendors = mav_vendors.merge(po_c, on='NAME1', how='left')
        mav_vendors['POs'] = mav_vendors['POs'].fillna(0).astype(int)
    else:
        mav_vendors['POs'] = 0

    mav_vendors.columns = ['Vendor', 'Gross_EUR', 'Lines', 'POs']
    return mav_vendors


def compute_maverick_gl(df, mav_mask, top_n=10):
    """GL account breakdown within maverick spend."""
    gl_col = 'BSEG_GL_Account' if 'BSEG_GL_Account' in df.columns else 'HKONT'
    if gl_col not in df.columns:
        return pd.DataFrame()

    mav_df = df[mav_mask & df[gl_col].notna()]
    if len(mav_df) == 0:
        return pd.DataFrame()

    analysis = mav_df.groupby(gl_col).agg(
        Gross_EUR=('Gross_Amount', 'sum'),
        Lines=('BELNR', 'count'),
    ).reset_index().sort_values('Gross_EUR', ascending=False).head(top_n)
    analysis.columns = ['GL_Account', 'Gross_EUR', 'Lines']
    return analysis


def compute_maverick_prctr(df, mav_mask, top_n=10):
    """Profit center breakdown within maverick spend."""
    pc_col = 'BSEG_Profit_Center' if 'BSEG_Profit_Center' in df.columns else 'PRCTR'
    if pc_col not in df.columns:
        return pd.DataFrame()

    mav_df = df[mav_mask & df[pc_col].notna()]
    if len(mav_df) == 0:
        return pd.DataFrame()

    analysis = mav_df.groupby(pc_col).agg(
        Gross_EUR=('Gross_Amount', 'sum'),
        Lines=('BELNR', 'count'),
    ).reset_index().sort_values('Gross_EUR', ascending=False).head(top_n)
    analysis.columns = ['Profit_Center', 'Gross_EUR', 'Lines']
    return analysis


def compute_maverick_kostl(df, mav_mask, top_n=10):
    """Cost center breakdown within maverick spend."""
    cc_col = 'BSEG_Cost_Center' if 'BSEG_Cost_Center' in df.columns else 'KOSTL'
    if cc_col not in df.columns:
        return pd.DataFrame()

    mav_df = df[mav_mask]
    valid = mav_df[(mav_df[cc_col].notna()) & (mav_df[cc_col].astype(str) != '') & (mav_df[cc_col].astype(str) != 'None')]
    if len(valid) == 0:
        return pd.DataFrame()

    analysis = valid.groupby(cc_col).agg(
        Gross_EUR=('Gross_Amount', 'sum'),
        Lines=('BELNR', 'count'),
    ).reset_index().sort_values('Gross_EUR', ascending=False).head(top_n)
    analysis.columns = ['Cost_Center', 'Gross_EUR', 'Lines']
    return analysis


def compute_maverick_by_spend_type(df, mav_mask):
    """Direct vs Indirect breakdown within maverick."""
    mav_df = df[mav_mask]
    mav_direct = mav_df[mav_df['Spend_Type'] == 'DIRECT']
    mav_indirect = mav_df[mav_df['Spend_Type'] == 'INDIRECT']

    result = {
        'mav_direct_spend': float(mav_direct['Gross_Amount'].sum()),
        'mav_indirect_spend': float(mav_indirect['Gross_Amount'].sum()),
        'mav_direct_lines': len(mav_direct),
        'mav_indirect_lines': len(mav_indirect),
    }

    # Indirect reasons within maverick
    if len(mav_indirect) > 0:
        result['mav_indirect_reasons'] = mav_indirect.groupby('Spend_Type_Reason').agg(
            Gross_EUR=('Gross_Amount', 'sum'),
            Lines=('BELNR', 'count'),
        ).reset_index().sort_values('Gross_EUR', ascending=False)
    else:
        result['mav_indirect_reasons'] = pd.DataFrame(columns=['Spend_Type_Reason', 'Gross_EUR', 'Lines'])

    return result


def compute_compliance_by_country(df):
    """Three-way match compliance rate by country."""
    if 'Country' not in df.columns:
        df['Country'] = df['BUKRS'].map(BUKRS_NAME_MAP).fillna('Other')

    results = []
    for country in df['Country'].unique():
        c_df = df[df['Country'] == country]
        has_pr = c_df['Has_PR'] == True if 'Has_PR' in c_df.columns else pd.Series(False, index=c_df.index)
        has_gr = c_df['Has_GR'] == True if 'Has_GR' in c_df.columns else pd.Series(False, index=c_df.index)
        no_pr = ~has_pr
        no_gr = ~has_gr

        full_match = (has_pr & has_gr).sum()
        mav = (no_pr & no_gr).sum()

        results.append({
            'Country': country,
            'Total_Lines': len(c_df),
            'Three_Way_Match': full_match,
            'Match_Pct': full_match / len(c_df) * 100 if len(c_df) > 0 else 0,
            'Maverick': mav,
            'Mav_Pct': mav / len(c_df) * 100 if len(c_df) > 0 else 0,
        })

    return pd.DataFrame(results).sort_values('Total_Lines', ascending=False)


# ============================================================================
# COMPREHENSIVE METRICS ORCHESTRATOR
# ============================================================================

def compute_all_metrics(df, mode='full'):
    """Compute ALL metrics in a single call. Returns comprehensive dict."""
    print("  Computing basic metrics...")
    basic = compute_basic_metrics(df)

    print("  Computing Direct/Indirect...")
    di = compute_direct_indirect(df)

    print("  Computing material metrics...")
    material = compute_material_metrics(df)

    print("  Computing BSEG coverage...")
    bseg = compute_bseg_coverage(df)

    print("  Computing GL analysis...")
    gl = compute_gl_analysis(df)

    print("  Computing Profit Center analysis...")
    prctr = compute_prctr_analysis(df)

    print("  Computing Cost Center analysis...")
    kostl = compute_kostl_analysis(df)

    print("  Computing vendor metrics...")
    vendor_m, vendor_spend = compute_vendor_metrics(df)

    print("  Computing plant analysis...")
    plant = compute_plant_analysis(df)

    print("  Computing country breakdown...")
    by_country = compute_country_breakdown(df)

    all_metrics = {
        **basic,
        **di,
        **material,
        **bseg,
        **vendor_m,
        'gl_analysis': gl,
        'prctr_analysis': prctr,
        'kostl_analysis': kostl,
        'vendor_spend': vendor_spend,
        'plant_analysis': plant,
        'by_country': by_country,
    }

    # Doc type stats (if BLART column present)
    if 'BLART' in df.columns:
        all_metrics['doc_type_stats'] = compute_doc_type_stats(df)

    # Posting key (if BSCHL present)
    if 'BSCHL' in df.columns:
        all_metrics['bschl_analysis'] = compute_posting_key_analysis(df)
        all_metrics['acct_type_analysis'] = compute_account_type_analysis(df)

    return all_metrics
