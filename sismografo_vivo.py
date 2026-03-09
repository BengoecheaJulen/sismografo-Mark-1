"""
╔══════════════════════════════════════════════════════════════════════════╗
║            SISMÓGRAFO — MARK 1 — SISTEMA EN VIVO               ║
║                                                                          ║
║  Ejecuta diariamente. Descarga datos, integra, genera           ║
║  dashboard HTML público y actualiza el registro histórico.               ║
║                                                                          ║
║  USO LOCAL:     python sismografo_vivo.py                                ║
║  USO SERVIDOR:  se ejecuta solo via GitHub Actions (ver README)          ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Para servidores sin pantalla
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import os, sys, json, io, warnings, traceback
import requests
warnings.filterwarnings('ignore')

# ══════════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ══════════════════════════════════════════════════════════════════

FRED_API_KEY = "c89819cd8848c4d51e71a4dafda037b9"

# Directorio base = donde está este script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "docs")  # GitHub Pages sirve desde /docs

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ══════════════════════════════════════════════════════════════════
# PARÁMETROS CALIBRADOS v6-A (CONGELADOS — NO TOCAR NUNCA)
# ══════════════════════════════════════════════════════════════════

PARAMS = {
    'k_bur':   0.0948,   # Sensibilidad HHI (burbuja)
    'k_cat':   0.8523,   # Sensibilidad GPR (catástrofe)
    'k_sent':  5.8146,   # Sensibilidad Put/Call (sentimiento)
    'k_mac':   8.5780,   # Sensibilidad CESI/PMI (macro)
    'k_liq':   0.0919,   # Sensibilidad HY OAS (liquidez)
    'gamma_0': 1.3659,   # Decoherencia base
    'n_exp':   2.6958,   # Exponente correlación
    'K':       0.00547,  # Escala volatilidad
    'L1':      8.3470,   # Peso activación Λ
    'L2':      3.5262,   # Peso coherencia C_q
    'alpha':   2.0723,   # Exponente potencia
}

SECTORES = ['XLK','XLF','XLV','XLY','XLP','XLE','XLI','XLB','XLRE','XLU','XLC']

# ══════════════════════════════════════════════════════════════════
# MOTOR DE LINDBLAD
# ══════════════════════════════════════════════════════════════════

def generadores_SU3():
    """5 generadores de SU(3) para el hamiltoniano."""
    G_NE = np.array([[0,0,0],[0,0,1],[0,1,0]], dtype=complex)
    G_NP = np.array([[0,0,1],[0,0,0],[1,0,0]], dtype=complex)
    G_PE = np.array([[0,1,0],[1,0,0],[0,0,0]], dtype=complex)
    G_ph1 = np.diag([1.0, -1.0, 0.0]).astype(complex)
    G_ph2 = np.diag([1.0, 1.0, -2.0]).astype(complex) / np.sqrt(3)
    return G_NE, G_NP, G_PE, G_ph1, G_ph2

def operadores_salto():
    """3 operadores de salto de Lindblad."""
    L1 = np.zeros((3,3), dtype=complex); L1[2,0] = 1  # |N><P|
    L2 = np.zeros((3,3), dtype=complex); L2[2,1] = 1  # |N><E|
    L3 = np.zeros((3,3), dtype=complex); L3[0,1] = 1  # |P><E|
    return [L1, L2, L3]

def lindblad_rhs(rho, H, gamma, Ls):
    """Lado derecho de dρ/dt = -i[H,ρ] + D[ρ]."""
    drho = -1j * (H @ rho - rho @ H)
    for L in Ls:
        Ld = L.conj().T
        LdL = Ld @ L
        drho += gamma * (L @ rho @ Ld - 0.5 * (LdL @ rho + rho @ LdL))
    return drho

def paso_rk4(rho, H, gamma, Ls, dt=1.0):
    """Un paso de Runge-Kutta 4 con correcciones de positividad."""
    H = np.nan_to_num(H, nan=0.0, posinf=1.0, neginf=-1.0)
    gamma = min(max(float(np.nan_to_num(gamma, nan=1.0)), 0.0), 100.0)
    
    k1 = lindblad_rhs(rho, H, gamma, Ls)
    k2 = lindblad_rhs(rho + 0.5*dt*k1, H, gamma, Ls)
    k3 = lindblad_rhs(rho + 0.5*dt*k2, H, gamma, Ls)
    k4 = lindblad_rhs(rho + dt*k3, H, gamma, Ls)
    rho_new = rho + (dt/6)*(k1 + 2*k2 + 2*k3 + k4)
    
    rho_new = np.nan_to_num(rho_new, nan=0.0, posinf=0.0, neginf=0.0)
    rho_new = 0.5 * (rho_new + rho_new.conj().T)
    tr = np.trace(rho_new).real
    if tr <= 0 or not np.isfinite(tr):
        return rho
    rho_new /= tr
    
    try:
        eigvals, eigvecs = np.linalg.eigh(rho_new)
        eigvals = np.maximum(eigvals.real, 0)
        rho_new = (eigvecs * eigvals) @ eigvecs.conj().T
        rho_new /= np.trace(rho_new).real
    except np.linalg.LinAlgError:
        return rho
    
    return rho_new

def calc_observables(rho):
    """Extrae Λ, C_q, Δ de la matriz densidad."""
    Lambda = rho[0,0].real + rho[1,1].real
    Cq = abs(rho[0,1]) + abs(rho[0,2]) + abs(rho[1,2])
    Delta = rho[0,0].real - rho[1,1].real
    return float(Lambda), float(Cq), float(Delta)

def calc_sigma_pred(Lambda, Cq):
    """σ_pred = K·(1 + L₁·Λ + L₂·C_q)^α"""
    return PARAMS['K'] * (1 + PARAMS['L1']*Lambda + PARAMS['L2']*Cq)**PARAMS['alpha']


# ══════════════════════════════════════════════════════════════════
# DESCARGA DE DATOS — FUENTES REALES (no se congela ningún factor)
# ══════════════════════════════════════════════════════════════════

GPR_DAILY_URL = 'https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls'

def descargar_yahoo(dias=120):
    """Descarga S&P500, VIX, PutCall y 11 sectores de Yahoo Finance."""
    import yfinance as yf
    end = datetime.now()
    start = end - timedelta(days=dias)
    
    print("  📥 S&P 500 + VIX...", end=" ", flush=True)
    market = yf.download(["^GSPC", "^VIX"], start=start, end=end, 
                         progress=False, auto_adjust=True)
    print("✓")
    
    print("  📥 11 sectores GICS...", end=" ", flush=True)
    sectors = yf.download(SECTORES, start=start, end=end, 
                          progress=False, auto_adjust=True)
    print("✓")
    
    # Put/Call Ratio real (CBOE) — FUENTE REAL
    putcall = None
    for ticker in ['^PCCE', '^PCALL']:
        try:
            print(f"  📥 Put/Call ({ticker})...", end=" ", flush=True)
            pc = yf.download(ticker, start=start, end=end,
                             progress=False, auto_adjust=True)
            if isinstance(pc.columns, pd.MultiIndex):
                pc.columns = pc.columns.get_level_values(0)
            if not pc.empty and 'Close' in pc.columns:
                putcall = pc['Close'].dropna()
                print("✓")
                break
        except Exception:
            pass
    if putcall is None:
        print("⚠ No disponible")
    
    return market, sectors, putcall

def descargar_fred(dias=120):
    """Descarga HY OAS y STLFSI4 (proxy CESI) de FRED."""
    hy_oas = None
    stlfsi = None
    
    try:
        from fredapi import Fred
        fred = Fred(api_key=FRED_API_KEY)
        end = datetime.now()
        start = end - timedelta(days=dias)
        
        # HY OAS (liquidez) — FUENTE REAL
        print("  📥 HY OAS (FRED)...", end=" ", flush=True)
        try:
            hy_oas = fred.get_series('BAMLH0A0HYM2', start, end).dropna()
            print(f"✓ ({len(hy_oas)} registros)")
        except Exception as e:
            print(f"⚠ ({e})")
        
        # STLFSI4 (proxy CESI/macro) — FUENTE REAL
        print("  📥 STLFSI4 (proxy macro/CESI, FRED)...", end=" ", flush=True)
        try:
            stlfsi = fred.get_series('STLFSI4', start, end).dropna()
            print(f"✓ ({len(stlfsi)} registros)")
        except Exception as e:
            # Fallback: NFCI
            try:
                stlfsi = fred.get_series('NFCI', start, end).dropna()
                print(f"✓ NFCI fallback ({len(stlfsi)} registros)")
            except:
                print(f"⚠ ({e})")
        
    except Exception as e:
        print(f"  ⚠ FRED no disponible: {e}")
    
    return hy_oas, stlfsi

def descargar_gpr():
    """
    Descarga el GPR Index diario de Caldara & Iacoviello.
    Fuente pública: https://www.matteoiacoviello.com/gpr.htm
    Actualizado mensualmente (~día 10 de cada mes).
    """
    print("  📥 GPR Index (Iacoviello)...", end=" ", flush=True)
    try:
        resp = requests.get(GPR_DAILY_URL, timeout=30)
        resp.raise_for_status()
        
        gpr_df = pd.read_excel(io.BytesIO(resp.content))
        
        # Identificar columnas
        date_col = None
        gpr_col = None
        for col in gpr_df.columns:
            cl = str(col).lower()
            if 'date' in cl or 'day' in cl:
                date_col = col
            elif cl in ('gpr', 'gprh', 'gpr_gpr'):
                gpr_col = col
            elif 'gpr' in cl and gpr_col is None:
                gpr_col = col
        
        if date_col is None:
            date_col = gpr_df.columns[0]
        if gpr_col is None:
            for col in gpr_df.columns:
                if col != date_col and pd.api.types.is_numeric_dtype(gpr_df[col]):
                    gpr_col = col
                    break
        
        gpr_df = gpr_df[[date_col, gpr_col]].copy()
        gpr_df.columns = ['Date', 'GPR']
        gpr_df['Date'] = pd.to_datetime(gpr_df['Date'])
        gpr_df = gpr_df.dropna(subset=['GPR']).set_index('Date').sort_index()
        
        print(f"✓ ({len(gpr_df)} registros, hasta {gpr_df.index.max().date()})")
        return gpr_df['GPR']
    except Exception as e:
        print(f"⚠ ({e})")
        return None

def procesar_datos_nuevos(market, sectors, putcall, hy_oas, stlfsi, gpr_series, df_hist):
    """
    Procesa datos descargados con FUENTES REALES para cada factor.
    NO congela ningún valor — cada serie se actualiza de su fuente.
    """
    filas = []
    
    # Extraer series de mercado
    try:
        sp_close = market['Close']['^GSPC'].dropna()
        vix = market['Close']['^VIX'].dropna()
    except (KeyError, TypeError):
        try:
            sp_close = market['Close'].iloc[:, 0].dropna()
            vix = market['Close'].iloc[:, 1].dropna() if market['Close'].shape[1] > 1 else None
        except:
            print("  ❌ Error parseando datos de Yahoo Finance")
            return pd.DataFrame()
    
    # Retornos y vol realizada
    returns = np.log(sp_close / sp_close.shift(1)).dropna()
    real_vol = returns.rolling(21).std() * np.sqrt(252)
    
    # Correlación sectorial (calculada en tiempo real desde ETFs)
    try:
        sec_close = sectors['Close'][SECTORES]
    except (KeyError, TypeError):
        sec_close = sectors['Close']
    
    sec_ret = np.log(sec_close / sec_close.shift(1)).dropna()
    
    mean_corrs = {}
    for i in range(20, len(sec_ret)):
        window = sec_ret.iloc[i-20:i]
        corr_mat = window.corr()
        mask = np.ones_like(corr_mat.values, dtype=bool)
        np.fill_diagonal(mask, False)
        vals = corr_mat.values[mask]
        vals = vals[np.isfinite(vals)]
        mean_corrs[sec_ret.index[i]] = np.mean(vals) if len(vals) > 0 else 0.3
    
    corr_series = pd.Series(mean_corrs)
    
    # HHI (concentración sectorial) — calculado en tiempo real desde ETFs
    hhi_series = pd.Series(dtype=float)
    try:
        sec_prices = sec_close
        for dt in sp_close.index:
            row = sec_prices.loc[:dt].tail(1)
            if not row.empty:
                p = row.values.flatten()
                p = p[~np.isnan(p)]
                if len(p) > 0:
                    w = p / p.sum()
                    hhi_series[dt] = np.sum(w ** 2)
    except Exception:
        pass
    
    # Últimos valores conocidos SOLO como fallback de último recurso
    last_vals = {
        'GPR': df_hist['GPR'].dropna().iloc[-1] if 'GPR' in df_hist.columns and df_hist['GPR'].notna().any() else 100,
        'CESI': df_hist['CESI'].dropna().iloc[-1] if 'CESI' in df_hist.columns and df_hist['CESI'].notna().any() else 0,
        'PMI_change': df_hist['PMI_change'].dropna().iloc[-1] if 'PMI_change' in df_hist.columns and df_hist['PMI_change'].notna().any() else 0,
        'PutCall': df_hist['PutCall'].dropna().iloc[-1] if 'PutCall' in df_hist.columns and df_hist['PutCall'].notna().any() else 0.85,
        'HHI': df_hist['HHI'].dropna().iloc[-1] if 'HHI' in df_hist.columns and df_hist['HHI'].notna().any() else 0.05,
        'HY_OAS': df_hist['HY_OAS'].dropna().iloc[-1] if 'HY_OAS' in df_hist.columns and df_hist['HY_OAS'].notna().any() else 4.0,
    }
    
    # Construir filas con DATOS REALES
    common_idx = sp_close.index.intersection(corr_series.index).intersection(real_vol.dropna().index)
    
    fallback_count = {'GPR': 0, 'CESI': 0, 'PutCall': 0, 'HY_OAS': 0, 'HHI': 0}
    
    for dt in common_idx:
        # ── HY_OAS: FRED real ──
        hy_val = last_vals['HY_OAS']
        if hy_oas is not None:
            mask_hy = hy_oas.index <= dt
            if mask_hy.any():
                hy_val = float(hy_oas[mask_hy].iloc[-1])
            else:
                fallback_count['HY_OAS'] += 1
        else:
            fallback_count['HY_OAS'] += 1
        
        # ── GPR: Iacoviello real ──
        gpr_val = last_vals['GPR']
        if gpr_series is not None:
            mask_gpr = gpr_series.index <= dt
            if mask_gpr.any():
                gpr_val = float(gpr_series[mask_gpr].iloc[-1])
            else:
                fallback_count['GPR'] += 1
        else:
            fallback_count['GPR'] += 1
        
        # ── CESI: STLFSI4 proxy real ──
        cesi_val = last_vals['CESI']
        if stlfsi is not None:
            mask_st = stlfsi.index <= dt
            if mask_st.any():
                # STLFSI4: media~0, >0=estrés. CESI: >0=sorpresa positiva. Invertir.
                cesi_val = float(-stlfsi[mask_st].iloc[-1] * 42.55)
            else:
                fallback_count['CESI'] += 1
        else:
            fallback_count['CESI'] += 1
        
        # ── PutCall: CBOE real ──
        pc_val = last_vals['PutCall']
        if putcall is not None:
            mask_pc = putcall.index <= dt
            if mask_pc.any():
                pc_val = float(putcall[mask_pc].iloc[-1])
            else:
                fallback_count['PutCall'] += 1
        else:
            fallback_count['PutCall'] += 1
        
        # ── HHI: calculado en tiempo real ──
        hhi_val = last_vals['HHI']
        if dt in hhi_series.index:
            hhi_val = float(hhi_series[dt])
        else:
            fallback_count['HHI'] += 1
        
        filas.append({
            'Date': dt,
            'Close': float(sp_close[dt]),
            'Return': float(returns[dt]) if dt in returns.index else 0,
            'RealizedVol': float(real_vol[dt]),
            'VIX': float(vix[dt]) if vix is not None and dt in vix.index else 20,
            'HY_OAS': hy_val,
            'GPR': gpr_val,
            'CESI': cesi_val,
            'PMI_change': float(last_vals['PMI_change']),  # PMI solo se publica mensual
            'PutCall': pc_val,
            'HHI': hhi_val,
            'MeanCorr': float(corr_series[dt]),
        })
    
    # Reportar cobertura
    n_total = len(common_idx)
    if n_total > 0:
        for name, count in fallback_count.items():
            real = n_total - count
            pct = 100 * real / n_total
            src = {'GPR': 'Iacoviello XLS', 'CESI': 'FRED/STLFSI4', 'PutCall': 'Yahoo/CBOE',
                   'HY_OAS': 'FRED', 'HHI': 'ETFs sector'}
            status = "✅" if pct > 80 else "⚠"
            print(f"    {status} {name:10s}: {real}/{n_total} reales ({pct:.0f}%) — {src.get(name)}")
    
    return pd.DataFrame(filas) if filas else pd.DataFrame()


# ══════════════════════════════════════════════════════════════════
# CÁLCULO DE FACTORES (normalización expansiva)
# ══════════════════════════════════════════════════════════════════

def calcular_factores(df):
    """Calcula los 5 factores f_i y C_norm con normalización expansiva."""
    proxy_k = {
        'f_bur': ('HHI', PARAMS['k_bur']),
        'f_cat': ('GPR', PARAMS['k_cat']),
        'f_sent': ('PutCall', PARAMS['k_sent']),
        'f_liq': ('HY_OAS', PARAMS['k_liq']),
    }
    
    for fname, (col, k) in proxy_k.items():
        if col in df.columns:
            emean = df[col].expanding(min_periods=50).mean()
            estd = df[col].expanding(min_periods=50).std().replace(0, 1)
            X = (df[col] - emean) / estd
            df[fname] = np.tanh(k * X)
        else:
            df[fname] = 0.0
    
    # f_mac: CESI (post 2003) o PMI_change (pre 2003)
    if 'CESI' in df.columns:
        mac = df['CESI'].copy()
        if 'PMI_change' in df.columns and 'Date' in df.columns:
            pre2003 = df['Date'] < '2003-01-01'
            mac[pre2003] = df.loc[pre2003, 'PMI_change']
        emean = mac.expanding(min_periods=50).mean()
        estd = mac.expanding(min_periods=50).std().replace(0, 1)
        X = (mac - emean) / estd
        df['f_mac'] = np.tanh(PARAMS['k_mac'] * X)
    else:
        df['f_mac'] = 0.0
    
    # C_norm
    if 'MeanCorr' in df.columns:
        mc = df['MeanCorr']
        cmin = mc.expanding(min_periods=50).min()
        cmax = mc.expanding(min_periods=50).max()
        df['C_norm'] = ((mc - cmin) / (cmax - cmin).replace(0, 1)).clip(0, 1)
    else:
        df['C_norm'] = 0.3
    
    return df


# ══════════════════════════════════════════════════════════════════
# INTEGRACIÓN LINDBLAD
# ══════════════════════════════════════════════════════════════════

def integrar_completo(df):
    """Integra Lindblad sobre todo el dataframe desde ρ(0) = |N><N|."""
    Gs = generadores_SU3()
    Ls = operadores_salto()
    rho = np.zeros((3,3), dtype=complex)
    rho[2,2] = 1.0
    
    resultados = []
    
    for i in range(len(df)):
        row = df.iloc[i]
        
        fb = float(np.nan_to_num(row.get('f_bur', 0), nan=0.0))
        fc = float(np.nan_to_num(row.get('f_cat', 0), nan=0.0))
        fs = float(np.nan_to_num(row.get('f_sent', 0), nan=0.0))
        fm = float(np.nan_to_num(row.get('f_mac', 0), nan=0.0))
        fl = float(np.nan_to_num(row.get('f_liq', 0), nan=0.0))
        
        H = fb*Gs[0] + fc*Gs[1] + fs*Gs[2] + fm*Gs[3] + fl*Gs[4]
        
        C = float(np.nan_to_num(row.get('C_norm', 0.3), nan=0.3))
        C = max(0.0, min(1.0, C))
        gamma = PARAMS['gamma_0'] * (1 - C)**PARAMS['n_exp']
        
        rho = paso_rk4(rho, H, gamma, Ls, dt=1.0)
        Lam, Cq, Delta = calc_observables(rho)
        sp = calc_sigma_pred(Lam, Cq)
        
        resultados.append({
            'Date': row['Date'],
            'sigma_real': row.get('RealizedVol', np.nan),
            'sigma_pred': sp,
            'Lambda': Lam,
            'Cq': Cq,
            'Delta': Delta,
            'gamma_t': gamma,
        })
    
    return pd.DataFrame(resultados), rho


# ══════════════════════════════════════════════════════════════════
# NIVEL DE ALERTA
# ══════════════════════════════════════════════════════════════════

def calcular_alerta(Cq, sigma_pred, Cq_hist):
    """Determina nivel de alerta basado en C_q, sigma_pred y percentiles."""
    pct = 100 * np.mean(Cq_hist < Cq) if len(Cq_hist) > 100 else 50
    p70 = np.percentile(Cq_hist, 70) if len(Cq_hist) > 100 else 0.40
    p85 = np.percentile(Cq_hist, 85) if len(Cq_hist) > 100 else 0.48
    p95 = np.percentile(Cq_hist, 95) if len(Cq_hist) > 100 else 0.55
    
    if Cq > p95 or sigma_pred > 0.40:
        return "ALERTA MÁXIMA", "#DC2626", "🔴", int(pct)
    elif Cq > p85 or sigma_pred > 0.25:
        return "ALERTA ELEVADA", "#EA580C", "🟠", int(pct)
    elif Cq > p70:
        return "VIGILANCIA", "#CA8A04", "🟡", int(pct)
    else:
        return "CALMA", "#16A34A", "🟢", int(pct)


# ══════════════════════════════════════════════════════════════════
# GENERACIÓN DE GRÁFICOS
# ══════════════════════════════════════════════════════════════════

def generar_graficos(obs_df, n_dias=120):
    """Genera gráfico PNG del dashboard."""
    recent = obs_df.tail(n_dias).copy()
    recent['Date'] = pd.to_datetime(recent['Date'])
    
    fig, axes = plt.subplots(3, 1, figsize=(14, 9),
                              gridspec_kw={'height_ratios': [2, 1, 1]})
    
    ultimo = obs_df.iloc[-1]
    _, _, emoji, pct = calcular_alerta(
        ultimo['Cq'], ultimo['sigma_pred'], obs_df['Cq'].values[:-1]
    )
    
    fig.suptitle(
        f'Sismógrafo MARK 1 — {pd.to_datetime(ultimo["Date"]).strftime("%d %b %Y")}',
        fontsize=15, fontweight='bold'
    )
    
    # Panel 1: Volatilidad
    ax = axes[0]
    ax.plot(recent.Date, recent.sigma_real, 'b-', lw=1, alpha=0.6, label='σ realizada')
    ax.plot(recent.Date, recent.sigma_pred, 'r-', lw=1.5, label='σ predicha')
    ax.axhline(0.25, color='orange', ls='--', lw=0.7, alpha=0.5)
    ax.set_ylabel('Volatilidad')
    ax.legend(loc='upper left', fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.set_title('Predicción de Volatilidad', fontsize=11)
    
    # Panel 2: C_q
    ax = axes[1]
    cq_smooth = recent.Cq.rolling(5, min_periods=1).mean()
    ax.fill_between(recent.Date, cq_smooth, alpha=0.25, color='purple')
    ax.plot(recent.Date, cq_smooth, 'purple', lw=1.5)
    cq_all = obs_df['Cq'].values
    ax.axhline(np.percentile(cq_all, 80), color='red', ls='--', lw=0.7, alpha=0.5, label='P80')
    ax.axhline(np.median(cq_all), color='gray', ls='--', lw=0.7, alpha=0.5, label='Mediana')
    ax.set_ylabel('C_q')
    ax.legend(loc='upper left', fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.set_title('CQ (indicador líder, horizonte 15-20 días)', fontsize=11)
    
    # Panel 3: Λ y Δ
    ax = axes[2]
    ax.plot(recent.Date, recent.Lambda, 'b-', lw=1, label='Λ (activación)')
    ax.plot(recent.Date, recent.Delta, 'g-', lw=0.8, alpha=0.7, label='Δ (sesgo)')
    ax.axhline(0, color='black', lw=0.5)
    ax.set_ylabel('Observable')
    ax.legend(loc='upper left', fontsize=9)
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, "dashboard.png")
    plt.savefig(path, dpi=150, bbox_inches='tight')
    plt.close()
    return path


# ══════════════════════════════════════════════════════════════════
# GENERACIÓN HTML (para GitHub Pages)
# ══════════════════════════════════════════════════════════════════

def generar_html(obs_df, alerta_nombre, alerta_color, alerta_emoji, pct):
    """Genera index.html con el dashboard público."""
    u = obs_df.iloc[-1]
    fecha = pd.to_datetime(u['Date']).strftime('%d %B %Y')
    
    # Últimos 30 días para la tabla
    ultimos_30 = obs_df.tail(30).iloc[::-1]
    
    tabla_rows = ""
    for _, r in ultimos_30.iterrows():
        d = pd.to_datetime(r['Date']).strftime('%Y-%m-%d')
        _, c, e, _ = calcular_alerta(r['Cq'], r['sigma_pred'], obs_df['Cq'].values)
        tabla_rows += f"""
        <tr>
            <td>{d}</td>
            <td>{e}</td>
            <td>{r['Cq']:.4f}</td>
            <td>{r['Lambda']:.4f}</td>
            <td>{r['Delta']:+.4f}</td>
            <td>{r['sigma_pred']:.4f}</td>
            <td>{r['sigma_real']:.4f}</td>
            <td>{r['gamma_t']:.4f}</td>
        </tr>"""
    
    # Tendencia
    if len(obs_df) >= 30:
        cq_5d = obs_df.tail(5)['Cq'].mean()
        cq_30d = obs_df.tail(30)['Cq'].mean()
        if cq_5d > cq_30d * 1.05:
            tendencia = "↑ Subiendo"
            tend_color = "#DC2626"
        elif cq_5d < cq_30d * 0.95:
            tendencia = "↓ Bajando"
            tend_color = "#16A34A"
        else:
            tendencia = "→ Estable"
            tend_color = "#6B7280"
    else:
        tendencia = "→ Sin datos suficientes"
        tend_color = "#6B7280"
    
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title> Sismógrafo MARK 1</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; background: #0F172A; color: #E2E8F0; }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        header {{ text-align: center; padding: 30px 0 20px; }}
        header h1 {{ font-size: 2em; letter-spacing: 2px; color: #F8FAFC; }}
        header p {{ color: #94A3B8; margin-top: 5px; }}
        .status-card {{
            background: #1E293B; border-radius: 16px; padding: 30px;
            margin: 20px 0; border-left: 6px solid {alerta_color};
            display: flex; flex-wrap: wrap; gap: 30px; align-items: center;
        }}
        .status-main {{ flex: 1; min-width: 250px; }}
        .status-emoji {{ font-size: 3em; }}
        .status-label {{ font-size: 1.5em; font-weight: bold; color: {alerta_color}; }}
        .status-date {{ color: #94A3B8; font-size: 0.9em; margin-top: 4px; }}
        .metrics {{ display: flex; flex-wrap: wrap; gap: 15px; flex: 2; }}
        .metric {{
            background: #334155; border-radius: 10px; padding: 15px 20px;
            min-width: 140px; flex: 1;
        }}
        .metric-label {{ color: #94A3B8; font-size: 0.8em; text-transform: uppercase; letter-spacing: 1px; }}
        .metric-value {{ font-size: 1.6em; font-weight: bold; margin-top: 4px; color: #F8FAFC; }}
        .metric-sub {{ font-size: 0.75em; color: #64748B; margin-top: 2px; }}
        .chart-container {{
            background: #1E293B; border-radius: 16px; padding: 20px;
            margin: 20px 0; text-align: center;
        }}
        .chart-container img {{ max-width: 100%; border-radius: 8px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
        th {{ background: #334155; padding: 10px; text-align: left; font-size: 0.85em;
             color: #94A3B8; text-transform: uppercase; letter-spacing: 1px; }}
        td {{ padding: 8px 10px; border-bottom: 1px solid #334155; font-size: 0.9em;
             font-family: 'Courier New', monospace; }}
        tr:hover {{ background: #334155; }}
        .footer {{
            text-align: center; padding: 30px; color: #475569; font-size: 0.8em;
        }}
        .footer a {{ color: #64748B; }}
        .disclaimer {{
            background: #1E293B; border-radius: 10px; padding: 15px; margin: 20px 0;
            font-size: 0.8em; color: #64748B; border-left: 3px solid #475569;
        }}
        .tendencia {{ color: {tend_color}; font-weight: bold; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>{alerta_emoji} Sismógrafo MARK 1</h1>
            <p>MARK 1</p>
        </header>

        <div class="status-card">
            <div class="status-main">
                <div class="status-emoji">{alerta_emoji}</div>
                <div class="status-label">{alerta_nombre}</div>
                <div class="status-date">Actualizado: {fecha}</div>
            </div>
            <div class="metrics">
                <div class="metric">
                    <div class="metric-label"> C<sub>q</sub></div>
                    <div class="metric-value">{u['Cq']:.4f}</div>
                    <div class="metric-sub">Percentil {pct}% · <span class="tendencia">{tendencia}</span></div>
                </div>
                <div class="metric">
                    <div class="metric-label">Activación Λ</div>
                    <div class="metric-value">{u['Lambda']:.4f}</div>
                    <div class="metric-sub">Probabilidad estados extremos</div>
                </div>
                <div class="metric">
                    <div class="metric-label">σ predicha</div>
                    <div class="metric-value">{u['sigma_pred']:.2%}</div>
                    <div class="metric-sub">σ real: {u['sigma_real']:.2%}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Sesgo Δ</div>
                    <div class="metric-value">{u['Delta']:+.4f}</div>
                    <div class="metric-sub">{'Pánico' if u['Delta'] > 0.01 else 'Euforia' if u['Delta'] < -0.01 else 'Neutro'}</div>
                </div>
            </div>
        </div>

        <div class="chart-container">
            <h3 style="margin-bottom: 15px; color: #F8FAFC;">Dashboard — Últimos 120 días</h3>
            <img src="dashboard.png" alt="Dashboard Sismógrafo MARK 1">
        </div>

        <div class="chart-container">
            <h3 style="margin-bottom: 15px; color: #F8FAFC;">Registro histórico (últimos 30 días)</h3>
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr>
                            <th>Fecha</th>
                            <th>Estado</th>
                            <th>C<sub>q</sub></th>
                            <th>Λ</th>
                            <th>Δ</th>
                            <th>σ pred</th>
                            <th>σ real</th>
                            <th>γ(t)</th>
                        </tr>
                    </thead>
                    <tbody>
                        {tabla_rows}
                    </tbody>
                </table>
            </div>
        </div>

        <div class="disclaimer">
            <strong>Aviso legal:</strong> El MARK1 es un modelo experimental de investigación 
            . Las señales generadas no constituyen 
            asesoramiento financiero. Rendimientos pasados no garantizan resultados futuros.
        </div>

        <div class="footer">
            <p>· Datos: Yahoo Finance, FRED</p>
            <p>Código fuente: <a href="https://github.com/BengoecheaJulen/sismografo-cuantico">GitHub</a></p>
            <p>© 2026 Julen Bengoechea · Proyecto de investigación</p>
        </div>
    </div>
</body>
</html>"""
    
    path = os.path.join(OUTPUT_DIR, "index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


# ══════════════════════════════════════════════════════════════════
# PROGRAMA PRINCIPAL
# ══════════════════════════════════════════════════════════════════

def main():
    print()
    print("═" * 60)
    print("  Sismógrafo MARK 1 — ACTUALIZACIÓN DIARIA")
    print("═" * 60)
    print()
    
    # 1. Cargar dataset histórico
    hist_path = os.path.join(DATA_DIR, "dataset_definitivo.csv")
    if not os.path.exists(hist_path):
        # Intentar en el directorio base también
        hist_path = os.path.join(BASE_DIR, "dataset_definitivo.csv")
    if not os.path.exists(hist_path):
        print(f"❌ No encuentro dataset_definitivo.csv")
        print(f"   Búsqueda en: {DATA_DIR} y {BASE_DIR}")
        sys.exit(1)
    
    print("[1/6] Cargando dataset histórico...")
    try:
        df_hist = pd.read_csv(hist_path)
    except Exception:
        # Fallback: usar engine python si el engine C falla (pandas 3.x en Windows)
        print("  ⚠ Reintentando con engine='python'...")
        df_hist = pd.read_csv(hist_path, engine='python', on_bad_lines='skip')
    df_hist['Date'] = pd.to_datetime(df_hist['Date'])
    last_hist_date = df_hist['Date'].max()
    print(f"  ✓ {len(df_hist)} días ({df_hist['Date'].min().strftime('%Y-%m-%d')} → {last_hist_date.strftime('%Y-%m-%d')})")
    
    # 2. Descargar datos nuevos de TODAS las fuentes reales
    print("\n[2/6] Descargando datos nuevos...")
    try:
        market, sectors, putcall = descargar_yahoo(dias=120)
        hy_oas, stlfsi = descargar_fred(dias=120)
        gpr_series = descargar_gpr()
    except Exception as e:
        print(f"  ❌ Error de descarga: {e}")
        traceback.print_exc()
        sys.exit(1)
    
    # 3. Procesar
    print("\n[3/6] Procesando datos nuevos...")
    df_new = procesar_datos_nuevos(market, sectors, putcall, hy_oas, stlfsi, gpr_series, df_hist)
    
    if len(df_new) == 0:
        print("  ⚠ No hay datos nuevos (¿fin de semana / festivo?)")
        # Aun así generar el dashboard con los datos que tenemos
    else:
        df_new = df_new[df_new['Date'] > last_hist_date].copy()
        print(f"  ✓ {len(df_new)} días nuevos")
    
    # 4. Concatenar con histórico
    print("\n[4/6] Construyendo serie completa...")
    cols_needed = ['Date','Close','Return','RealizedVol','VIX','HY_OAS','GPR',
                   'CESI','PMI_change','PutCall','HHI','MeanCorr']
    cols_present = [c for c in cols_needed if c in df_hist.columns]
    
    if len(df_new) > 0:
        cols_new = [c for c in cols_present if c in df_new.columns]
        df_full = pd.concat([df_hist[cols_present], df_new[cols_new]], ignore_index=True)
    else:
        df_full = df_hist[cols_present].copy()
    
    df_full['Date'] = pd.to_datetime(df_full['Date'])
    df_full = df_full.sort_values('Date').drop_duplicates(subset='Date').reset_index(drop=True)
    
    # Calcular factores
    df_full = calcular_factores(df_full)
    
    # Filtrar desde 2000
    mask = df_full['Date'] >= '2000-01-01'
    df_model = df_full[mask].reset_index(drop=True)
    print(f"  ✓ Serie completa: {len(df_model)} días")
    
    # 5. Integrar Lindblad
    print("\n[5/6] Integrando ecuación de Lindblad...")
    import time
    t0 = time.time()
    obs_df, rho_final = integrar_completo(df_model)
    elapsed = time.time() - t0
    obs_df['Date'] = pd.to_datetime(obs_df['Date'])
    print(f"  ✓ {len(obs_df)} días en {elapsed:.1f}s")
    
    # Guardar rho y observables
    np.save(os.path.join(DATA_DIR, "rho_ultimo.npy"), rho_final)
    obs_df.to_csv(os.path.join(DATA_DIR, "historico_observables.csv"), index=False)
    
    # 6. Generar outputs
    print("\n[6/6] Generando dashboard...")
    ultimo = obs_df.iloc[-1]
    alerta_nombre, alerta_color, alerta_emoji, pct = calcular_alerta(
        ultimo['Cq'], ultimo['sigma_pred'], obs_df['Cq'].values[:-1]
    )
    
    png_path = generar_graficos(obs_df)
    html_path = generar_html(obs_df, alerta_nombre, alerta_color, alerta_emoji, pct)
    
    # Resultado
    fecha = pd.to_datetime(ultimo['Date']).strftime('%d %b %Y')
    print()
    print("╔" + "═" * 58 + "╗")
    print("║" + f"  Sismógrafo MARK 1 — {fecha}".ljust(58) + "║")
    print("╠" + "═" * 58 + "╣")
    print("║" + f"  Estado:     {alerta_emoji} {alerta_nombre}".ljust(58) + "║")
    print("║" + f"  C_q:        {ultimo['Cq']:.4f}  (percentil {pct}%)".ljust(58) + "║")
    print("║" + f"  Λ:          {ultimo['Lambda']:.4f}".ljust(58) + "║")
    print("║" + f"  Δ:          {ultimo['Delta']:+.4f}  ({'pánico' if ultimo['Delta']>0.01 else 'euforia' if ultimo['Delta']<-0.01 else 'neutro'})".ljust(58) + "║")
    print("║" + f"  σ_pred:     {ultimo['sigma_pred']:.4f}".ljust(58) + "║")
    print("║" + f"  σ_real:     {ultimo['sigma_real']:.4f}".ljust(58) + "║")
    print("║" + f"  γ(t):       {ultimo['gamma_t']:.4f}".ljust(58) + "║")
    print("╠" + "═" * 58 + "╣")
    print("║" + f"  📊 Dashboard: {os.path.relpath(html_path, BASE_DIR)}".ljust(58) + "║")
    print("║" + f"  📈 Gráfico:   {os.path.relpath(png_path, BASE_DIR)}".ljust(58) + "║")
    print("╚" + "═" * 58 + "╝")
    print()
    
    # Guardar lectura del día como JSON (para el track record)
    lectura = {
        'date': pd.to_datetime(ultimo['Date']).strftime('%Y-%m-%d'),
        'timestamp': datetime.now().isoformat(),
        'Cq': round(float(ultimo['Cq']), 6),
        'Lambda': round(float(ultimo['Lambda']), 6),
        'Delta': round(float(ultimo['Delta']), 6),
        'sigma_pred': round(float(ultimo['sigma_pred']), 6),
        'sigma_real': round(float(ultimo['sigma_real']), 6),
        'gamma_t': round(float(ultimo['gamma_t']), 6),
        'alerta': alerta_nombre,
        'percentil_Cq': pct,
    }
    
    # Append al registro diario
    registro_path = os.path.join(DATA_DIR, "registro_diario.jsonl")
    with open(registro_path, "a") as f:
        f.write(json.dumps(lectura) + "\n")
    
    print(f"✓ Lectura guardada en registro_diario.jsonl")
    print(f"✓ Abre docs/index.html en tu navegador para ver el dashboard")
    print()


if __name__ == "__main__":
    main()
