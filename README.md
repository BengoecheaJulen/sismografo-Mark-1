# SEISMIC MARK I — Systemic Risk Monitor

**Live daily S&P 500 risk classification.**

[![Status](https://img.shields.io/badge/status-operational-brightgreen)]()
[![License](https://img.shields.io/badge/license-MIT-lightgrey)]()

> **Not a trading signal.** A regime detection system for risk management.

**[→ Live Dashboard](https://bengoecheajulen.github.io/sismografo-Mark-1/)**

---

## Reading the Dashboard

| Color | State | What it means |
|-------|-------|---------------|
| 🟢 | CALM | Low risk. Normal market conditions. |
| 🟩 | STABLE | Below-average risk. Healthy regime. |
| 🟡 | ELEVATED | Above-average risk. Increased vigilance. |
| 🟠 | HIGH RISK | Significant stress. Active risk management recommended. |
| 🔴 | CRITICAL | Systemic stress. Historical crises live here. |
| 🌑 | VOID | 5+ consecutive critical days. Extreme tail regime. |
| 🔵 | SYNC | Unusual synchronization without classical stress signatures. Monitor. |

---

## The 5 Indicators

| Name | What it tracks |
|------|---------------|
| **NEXUS INDEX** | Collective market synchronization. Leading indicator (12–25 day horizon). |
| **APEX SIGNAL** | Probability of extreme tail events. Primary risk axis. |
| **CORE STABILITY** | Opinion diversity. High = healthy. Low = crisis. |
| **PULSE FORECAST** | Model-predicted volatility. |
| **VECTOR BIAS** | Panic vs euphoria directional pressure. |

---

## Validation

- Calibrated on data through 2017. Frozen since.
- Tested out-of-sample on 2022–2026 with no parameter changes.
- Val/Train RMSE ratio: **0.84** (performs better on unseen data than training data).
- 480:1 data-to-parameters ratio — not overfit.

**Crisis detection record:**

| Event | Detected |
|-------|----------|
| GFC 2008–09 | ✅ CRITICAL/VOID |
| COVID 2020 | ✅ CRITICAL/VOID |
| EU Debt 2011 | ✅ HIGH/CRITICAL |
| Tariffs 2025 | ✅ HIGH |
| Iran War Feb–Mar 2026 | ✅ ELEVATED before attack → HIGH day operations began |

---

## Data

Updated automatically every trading day ~22:30 CET via `data/registro_diario.jsonl`.

---

## License

MIT
