# SEISMIC MARK I — Quantum Systemic Risk Monitor

**Live daily S&P 500 risk classification powered by a Lindblad master equation.**

[![Status](https://img.shields.io/badge/status-operational-brightgreen)]()
[![Model](https://img.shields.io/badge/model-v6--A-blue)]()
[![Data](https://img.shields.io/badge/data-2000--2026-orange)]()
[![License](https://img.shields.io/badge/license-MIT-lightgrey)]()

---

## What Is This?

SEISMIC MARK I applies the **Lindblad master equation** — the fundamental equation of open quantum systems — to model systemic risk in the S&P 500. The market is treated as a 3-state density matrix (neutral / pessimistic / euphoric) driven by 5 macrofinancial forcings. Every trading day, the system evolves the density matrix and extracts **5 observables** that are combined into a single risk state.

The dashboard shows you, at a glance, whether the market is in a calm, stressed, or crisis regime — with full transparency on what drives the classification.

> **This is NOT a trading signal.** It is a regime detection system. Use for risk management (position sizing, hedging decisions), not market timing.

---

## Live Dashboard

**[→ Open Dashboard](https://bengoecheajulen.github.io/sismografo-Mark-1/)**

Updated automatically every trading day at ~22:30 CET. No login, no dependencies — opens in any browser.

---

## Dashboard States

| State | Emoji | Rule | Historical Mean σ |
|-------|-------|------|-------------------|
| **CALM** | 🟢 | Λ < P30 AND γ > P75 | 0.095 |
| **STABLE** | 🟩 | Λ < P50 AND γ ≥ P50 | 0.123 |
| **ELEVATED** | 🟡 | Λ > P50 OR γ < P50 | 0.147 |
| **HIGH** | 🟠 | Λ > P70 OR (Λ > P50 AND γ < P25) | 0.202 |
| **CRITICAL** | 🔴 | Λ > P85 AND γ < P50 | 0.274 |
| **VOID** | 🌑 | 5+ consecutive days CRITICAL | 0.350+ |
| **SYNC** | 🔵 | Cq > P90 AND Λ < P70 AND γ > P50 | 0.126 |

All σ values are historical means of realized S&P 500 volatility (annualized) for each state, computed from the full 2000–2026 dataset (N = 6,317 trading days). The monotonic progression from CALM to CRITICAL confirms the system discriminates regimes correctly.

---

## The 5 Observables

| Code | Public Name | What It Measures | Key Stat |
|------|-------------|-----------------|----------|
| **Cq** | NEXUS INDEX | Quantum coherence — collective opinion synchronization | Leading indicator, 12–25 day horizon |
| **Λ** | APEX SIGNAL | Tail-event probability from density matrix evolution | Spearman +0.59 with realized vol |
| **γ(t)** | CORE STABILITY | Decoherence rate — diversity of market opinions (INVERTED: low = crisis) | Spearman −0.57 with realized vol |
| **σ_pred** | PULSE FORECAST | Model-predicted volatility | Spearman +0.52 with realized vol |
| **Δ** | VECTOR BIAS | Panic/euphoria directional bias from density matrix | Extreme negatives flag panic regimes |

### Design Principle: Why Lambda + Gamma, Not Cq Alone

High coherence (Cq > P95) has only **28% precision** for detecting high-volatility days — most such days are calm markets with synchronized-but-relaxed opinions. However, **Cq > P95 combined with Λ > P90 reaches ~80% precision**. 

The classification system therefore uses:
- **Lambda (Λ)** as the primary risk axis — highest direct correlation with realized volatility
- **Gamma (γ)** as the confirming axis — low gamma alongside high Lambda = confirmed systemic stress
- **Cq** as a regime modifier and early warning indicator, never as the sole driver of state

---

## Model Architecture

```
5 Macrofinancial Forcings           Lindblad Equation              5 Observables
┌─────────────────────┐     ┌────────────────────────────┐    ┌──────────────┐
│ f_bur  (bubble)     │     │  dρ/dt = -i[H(t),ρ]       │    │ Cq  (NEXUS)  │
│ f_cat  (catastrophe)│ ──▶ │         + Σ L_k ρ L_k†    │──▶ │ Λ   (APEX)   │
│ f_sent (sentiment)  │     │         - ½{L†L, ρ}       │    │ γ   (CORE)   │
│ f_mac  (macro)      │     │                            │    │ σ   (PULSE)  │
│ f_liq  (liquidity)  │     │  11 free parameters        │    │ Δ   (VECTOR) │
└─────────────────────┘     └────────────────────────────┘    └──────────────┘
                                      │
                              ┌───────┴───────┐
                              │  Rule Engine   │
                              │  (Λ + γ axes)  │
                              └───────┬───────┘
                                      │
                               System State
                          (calm → void, 7 levels)
```

**Parameters:** 11 (5 forcing weights + γ₀, n, K, L₁, L₂, α)  
**Calibrated:** 2000–2021 via differential evolution (train: 2000–2017, val: 2018–2021)  
**Tested:** 2022–2026 fully frozen — model parameters unchanged since calibration  
**Val/Train RMSE ratio: 0.84** — model performs 16% better on unseen data than training data  
**Data efficiency:** 480:1 observations-to-parameters ratio

---

## Performance

| Metric | Lindblad v6-A | GARCH(1,1)-X | Neural Net |
|--------|---------------|--------------|------------|
| RMSE (test) | 0.100 | **0.064** | 0.107 |
| Pearson (test) | 0.413 | **0.873** | 0.200 |
| Parameters | **11** | 9 | 177 |
| Provides Cq, γ observables | ✅ | ❌ | ❌ |
| Crisis RMSE improvement with Cq | **+31.4%** | N/A | N/A |

GARCH wins on raw RMSE — it is purpose-built for volatility forecasting. The Lindblad model's value is the **unique observables** (Cq, γ) that no classical model produces. When those observables are included in crisis periods, RMSE improves by 31.4%. The model extracts information from market structure that volatility alone cannot capture.

---

## Crisis Detection Track Record

| Event | Λ mean | γ mean | σ_real mean | Detected? |
|-------|--------|--------|-------------|-----------|
| GFC 2008–09 | 0.642 | 0.019 | 0.520 | ✅ CRITICAL/VOID |
| COVID Mar 2020 | 0.601 | 0.014 | 0.615 | ✅ CRITICAL/VOID |
| EU Debt Crisis 2011 | 0.580 | 0.040 | 0.310 | ✅ HIGH/CRITICAL |
| China Selloff 2015 | moderate | low | 0.250+ | ✅ HIGH |
| Tariffs 2025 | 0.481 | 0.117 | 0.250 | ✅ HIGH |
| Calm 2017 | 0.200 | 0.495 | 0.067 | ✅ CALM |
| **Iran War Feb–Mar 2026** | **0.631** | **0.599** | **0.136** | ✅ **ELEVATED → HIGH** |

### First Live Validation: Iran War (Feb–Mar 2026)

On 28 February 2026, the United States launched military operations against Iran. Oil crossed $100/barrel, the S&P 500 fell 3.42% from its all-time high, and the Dow Jones lost 900 points intraday on 9 March before recovering.

SEISMIC MARK I's response, with timestamps verifiable via GitHub commit history:

| Date | State | Λ | γ | Market |
|------|-------|---|---|--------|
| 2026-02-23 | STABLE | 0.226 | 0.732 | Normal. No visible catalyst. |
| 2026-02-24 | STABLE→ELEVATED | 0.389 | 0.742 | Normal. Lambda begins rising with no news. |
| 2026-02-27 | **ELEVATED** | 0.544 | 0.762 | S&P -0.4%. **First alert — 1 day before attack.** |
| 2026-03-02 | **HIGH** | 0.587 | 0.750 | War confirmed. Airlines -3%. |
| 2026-03-06 | **HIGH** | 0.645 | 0.494 | Oil $95. Dow biggest weekly drop in months. |
| 2026-03-09 | **HIGH** | 0.675 | 0.499 | Oil $100+. S&P annual low. Cq at **P99** (top 1% of 26 years). |

The system reached ELEVATED **before** the attack and HIGH **the day operations began**. It never falsely returned to CALM or STABLE during the escalation. The HIGH classification (not CRITICAL) was proportional to the actual drawdown: -3.4% is consistent with HIGH's historical mean σ of 0.202, not a GFC-level collapse (which required γ < 0.040).

The March 2026 episode is also historically anomalous: **Cq at P99 combined with Λ at P92 and γ at P90 simultaneously** has no clear precedent in the 2000–2026 dataset. Previous P99 Cq episodes (Dotcom 2001–03, GFC 2008–09) were accompanied by collapsing γ. The current regime — extreme synchronization with sustained opinion diversity — is a novel quantum state the model had not previously observed at this intensity.

---

## File Structure (Public Repository)

```
sismografo-Mark-1/
├── index.html          # Dashboard — single file, no build step, no dependencies
├── README.md           # This file
└── data/
    └── registro_diario.jsonl   # Live data feed — appended every trading day ~22:30 CET
```

The model code, calibration engine, and parameters are maintained separately in a private repository.

---

## Data Format

Each line in `registro_diario.jsonl` is a JSON object:

```json
{
  "date": "2026-03-09",
  "Cq": 0.6241,
  "Lambda": 0.6746,
  "Delta": -0.1347,
  "sigma_pred": 0.4994,
  "sigma_real": 0.1356,
  "gamma_t": 0.4986
}
```

The dashboard fetches this file directly from GitHub raw and classifies each entry in the browser. No server, no API, no authentication required.

---

## Acknowledgments

Based on original research applying the Lindblad master equation to financial markets. The quantum formalism provides observables — coherence (Cq) and decoherence rate (γ) — that have no classical equivalent, offering a genuinely new lens on systemic risk dynamics.

---

## License

MIT
