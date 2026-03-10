# SEISMIC · MARK I
### Systemic Risk Intelligence — S&P 500

> Real-time detection of systemic risk regimes using a proprietary quantitative model. Auto-updates daily at 22:30 CET.

---

## Live Dashboard

**[→ Open SEISMIC MARK I](https://bengoecheajulen.github.io/sismografo-Mark-1/)**

---

## What is SEISMIC?

SEISMIC is a quantitative early-warning system that monitors the internal structure of financial markets to detect elevated systemic risk **before** it becomes visible in prices or media coverage.

The model tracks five core observables derived from market microstructure dynamics. These are combined into a 7-state classification system that signals the current risk regime in real time.

---

## Core Observables

| ID | Name | Description |
|----|------|-------------|
| SYS-01 | **NEXUS INDEX** | Degree of collective synchronization across market participants. High values indicate the system is behaving as a single correlated unit — a precursor to instability. Acts as a **15–20 day leading indicator** of volatility spikes. |
| SYS-02 | **APEX SIGNAL** | Probability of the system transitioning into an extreme tail state. Rising values signal increased likelihood of non-linear market moves. |
| SYS-03 | **PULSE FORECAST** | Model-predicted forward volatility (annualized). Compared against realized volatility to assess model accuracy in real time. |
| SYS-04 | **VECTOR BIAS** | Directional bias of market dynamics. Negative values indicate suppressed fear with underlying fragility (bubble conditions). Positive values indicate active panic or stress. |
| SYS-05 | **CORE STABILITY** | Internal diversity of market states. High values indicate healthy dispersion of opinions; low values indicate dangerous consensus. |

---

## 7-State Alert Classification

| Color | State | Trigger Conditions |
|-------|-------|--------------------|
| 🔴 `#FF3D00` | **EXTREME TAIL** | 5+ consecutive CRITICAL sessions. Systemic cascade risk. |
| 🔴 `#FF1744` | **CRITICAL** | NEXUS > 0.50 AND APEX > 0.30 |
| 🟠 `#FF6D00` | **HIGH RISK** | NEXUS > 0.35 sustained, APEX rising |
| 🟡 `#FFB300` | **ELEVATED** | NEXUS between 0.25 and 0.35, monitoring mode |
| 🟢 `#00E676` | **STABLE** | Normal market regime, no anomalies detected |
| 🟢 `#00BFA5` | **SILENT BUBBLE** | NEXUS > 0.40 AND APEX < 0.15 AND VECTOR < −0.15 (3+ days) |
| 🟢 `#1DE9B6` | **EXTREME BUBBLE** | NEXUS > 0.45 AND APEX < 0.10 AND VECTOR < −0.20 (3+ days) |

**Reading the states:**
- **CRITICAL / EXTREME TAIL** — Elevated probability of a sharp market dislocation. Systemic coherence is dangerously high.
- **HIGH RISK / ELEVATED** — The system is entering a stress zone. Not yet critical, but conditions are deteriorating.
- **STABLE** — Market dynamics are within historical norms. No significant systemic signal.
- **SILENT / EXTREME BUBBLE** — The market is highly synchronized but in a euphoric rather than fearful direction. These states often precede sharp corrections. The VECTOR is suppressing perceived risk while NEXUS coherence is high — a fragile equilibrium.

---

## Data & Methodology

- **Universe:** S&P 500
- **Data sources:** Yahoo Finance (price), FRED (macro)
- **Update frequency:** Daily, automated at ~22:30 CET
- **Historical record:** GitHub-timestamped, cryptographically immutable
- **Model validation period:** 2022–2025 (out-of-sample)
- **NEXUS lead time:** 15–20 trading days ahead of volatility spikes (validated across 8 historical crises)

---

## Repository Structure

```
sismografo-Mark-1/
├── index.html              # Live dashboard (GitHub Pages)
├── data/
│   └── registro_diario.jsonl   # Daily signal log (JSONL, auto-updated)
└── dashboard.png           # Static snapshot (legacy)
```

### JSONL Data Format

Each line in `registro_diario.jsonl` follows this schema:

```json
{
  "date": "2026-03-09",
  "timestamp": "2026-03-09T22:03:02.410282",
  "Cq": 0.624139,
  "Lambda": 0.674614,
  "Delta": -0.134665,
  "sigma_pred": 0.499447,
  "sigma_real": 0.135631,
  "gamma_t": 0.498558,
  "alerta": "ALERTA MÁXIMA",
  "percentil_Cq": 97
}
```

| Field | Observable | Range |
|-------|------------|-------|
| `Cq` | NEXUS INDEX | [0, 1] |
| `Lambda` | APEX SIGNAL | [0, 1] |
| `Delta` | VECTOR BIAS | [−1, +1] |
| `sigma_pred` | PULSE FORECAST | [0, ∞) annualized |
| `sigma_real` | Realized volatility | [0, ∞) annualized |
| `gamma_t` | CORE STABILITY | [0, 1] |
| `percentil_Cq` | NEXUS historical percentile | [0, 100] |

---

## Notable Events Detected

| Date | NEXUS | State | Event |
|------|-------|-------|-------|
| 2026-02-24 | 0.5474 | CRITICAL | Initial escalation signal, 13 days before media coverage |
| 2026-03-03 | 0.4591 | HIGH RISK | Sustained stress, 5-day streak begins |
| 2026-03-05 | 0.5630 | CRITICAL | Coherence breach above P88 |
| 2026-03-09 | 0.6241 | CRITICAL (P97) | Peak signal, ALERTA MÁXIMA |

---

## Intelligence Network — Upcoming

| System | Focus | Status |
|--------|-------|--------|
| MARK II | Sector rotation · Cross-asset intelligence | In development |
| MARK III | Credit stress · Sovereign risk detection | In development |
| MARK IV | Contagion mapping · Network topology | In development |

---

## Legal Notice

SEISMIC MARK I is an experimental research intelligence system. Signals do not constitute financial advice or investment recommendations. Past performance does not guarantee future results. For institutional research purposes only.

---

*Data: Yahoo Finance · FRED · Auto-update 22:30 CET*
