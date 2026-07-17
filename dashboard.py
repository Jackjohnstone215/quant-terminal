
import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta, timezone
from pathlib import Path
import math
import time
import os
import io
import json
import urllib.request
import urllib.error
import plotly.graph_objects as go
import plotly.express as px

st.set_page_config(
    page_title="Mastermind Quant Investing Terminal",
    page_icon="📈",
    layout="wide",
)


def apply_custom_style():
    """Inject CSS to make the app look like a polished product rather than default Streamlit."""
    st.markdown(
        """
        <style>
        /* Tighten the top padding so content sits higher */
        .block-container { padding-top: 2rem; max-width: 1500px; }
        /* Metric cards: give st.metric a carded look */
        div[data-testid="stMetric"] {
            background: linear-gradient(180deg, #151A23 0%, #10141c 100%);
            border: 1px solid #232a36;
            border-radius: 12px;
            padding: 14px 16px;
        }
        div[data-testid="stMetricLabel"] p { color: #8a94a6; font-size: 0.8rem; }
        /* News/article link color -> accent teal instead of default blue */
        a { color: #00C39A !important; }
        /* Headings a touch tighter */
        h1, h2, h3 { letter-spacing: -0.01em; }
        /* Dataframe rounded corners */
        div[data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def app_header():
    """Branded gradient header shown at the top of every page."""
    st.markdown(
        """
        <div style="
            background: linear-gradient(90deg, #00C39A 0%, #0a7d67 55%, #0B0E14 100%);
            border-radius: 14px; padding: 18px 24px; margin-bottom: 18px;
            border: 1px solid #10241f;">
            <div style="font-size: 1.55rem; font-weight: 800; color: #04150f; letter-spacing:-0.02em;">
                📈 Mastermind Quant Terminal
            </div>
            <div style="color: #043027; font-size: 0.9rem; font-weight: 600; margin-top: 2px;">
                Data-driven stock research — quality · value · growth · momentum · risk
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def score_color(value):
    """Green/amber/red for a 0-100 score."""
    v = safe_float(value, 0)
    if v >= 70:
        return "#00C39A"
    if v >= 50:
        return "#E0B34D"
    if v >= 35:
        return "#E08A4D"
    return "#E0574D"


def render_score_bars(scores, title=None):
    """Render a dict of {label: 0-100 value} as colored horizontal bars (HTML)."""
    if title:
        st.markdown(f"**{title}**")
    rows = []
    for label, value in scores.items():
        v = max(0, min(100, safe_float(value, 0)))
        color = score_color(v)
        rows.append(
            f"""
            <div style="display:flex; align-items:center; margin:6px 0; gap:10px;">
                <div style="width:190px; color:#c3cad6; font-size:0.86rem;">{label}</div>
                <div style="flex:1; background:#1b2130; border-radius:6px; height:16px; overflow:hidden;">
                    <div style="width:{v}%; background:{color}; height:100%;"></div>
                </div>
                <div style="width:44px; text-align:right; color:{color}; font-weight:700; font-size:0.86rem;">{v:.0f}</div>
            </div>
            """
        )
    st.markdown("".join(rows), unsafe_allow_html=True)


# ---- Plotly charts (dark-theme styled) ----
CHART_BG = "#0B0E14"
CHART_GRID = "#232a36"
ACCENT = "#00C39A"


def _style_fig(fig, height=380):
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#E6EAF1",
        height=height,
        margin=dict(l=10, r=10, t=40, b=10),
    )
    return fig


def factor_radar(row):
    """Radar/spider chart of a stock's six core factor scores (0-100)."""
    axes = ["Quality", "Valuation", "Growth", "Financial Health", "Momentum", "Risk Control"]
    keys = ["Quality Score", "Valuation Score", "Growth Score",
            "Financial Strength Score", "Momentum Score", "Risk Score"]
    vals = [max(0, min(100, safe_float(row.get(k), 0))) for k in keys]
    # close the loop
    axes_c, vals_c = axes + [axes[0]], vals + [vals[0]]
    fig = go.Figure(go.Scatterpolar(
        r=vals_c, theta=axes_c, fill="toself",
        line=dict(color=ACCENT, width=2), fillcolor="rgba(0,195,154,0.25)",
        hovertemplate="%{theta}: %{r:.0f}/100<extra></extra>",
    ))
    fig.update_layout(
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            radialaxis=dict(range=[0, 100], gridcolor=CHART_GRID, tickfont=dict(size=9)),
            angularaxis=dict(gridcolor=CHART_GRID),
        ),
        showlegend=False,
    )
    return _style_fig(fig, height=360)


def factor_radar_multi(df):
    """Overlay several stocks' factor shapes on one radar for side-by-side comparison."""
    axes = ["Quality", "Valuation", "Growth", "Financial Health", "Momentum", "Risk Control"]
    keys = ["Quality Score", "Valuation Score", "Growth Score",
            "Financial Strength Score", "Momentum Score", "Risk Score"]
    palette = ["#00C39A", "#E0B34D", "#6aa9ff", "#E0574D", "#b98cff"]
    fig = go.Figure()
    for i, (_, row) in enumerate(df.iterrows()):
        vals = [max(0, min(100, safe_float(row.get(k), 0))) for k in keys]
        color = palette[i % len(palette)]
        fig.add_trace(go.Scatterpolar(
            r=vals + [vals[0]], theta=axes + [axes[0]], fill="toself", name=str(row.get("Ticker", "")),
            line=dict(color=color, width=2), opacity=0.7,
            hovertemplate="%{theta}: %{r:.0f}<extra>" + str(row.get("Ticker", "")) + "</extra>",
        ))
    fig.update_layout(
        polar=dict(bgcolor="rgba(0,0,0,0)",
                   radialaxis=dict(range=[0, 100], gridcolor=CHART_GRID, tickfont=dict(size=9)),
                   angularaxis=dict(gridcolor=CHART_GRID)),
        legend=dict(orientation="h", yanchor="bottom", y=1.05),
    )
    return _style_fig(fig, height=420)


def valuation_quality_scatter(df):
    """Scatter of Valuation vs Quality for the whole scan — the cheap-and-good corner
    is the top-right. Colored by sector, hover shows the ticker."""
    d2 = df.copy()
    for c in ["Valuation Score", "Quality Score", "Overall Quant Score"]:
        d2[c] = pd.to_numeric(d2[c], errors="coerce")
    d2 = d2.dropna(subset=["Valuation Score", "Quality Score"])
    fig = px.scatter(
        d2, x="Valuation Score", y="Quality Score",
        color="Sector", hover_name="Ticker",
        hover_data={"Overall Quant Score": True, "Valuation Score": ":.0f", "Quality Score": ":.0f"},
        size=d2["Overall Quant Score"].clip(lower=1),
    )
    # quadrant guides at the midpoint
    fig.add_hline(y=50, line_dash="dot", line_color=CHART_GRID)
    fig.add_vline(x=50, line_dash="dot", line_color=CHART_GRID)
    fig.add_annotation(x=88, y=95, text="cheap & high-quality", showarrow=False,
                       font=dict(color=ACCENT, size=11))
    fig.update_xaxes(range=[0, 100], gridcolor=CHART_GRID, title="Valuation (higher = cheaper)")
    fig.update_yaxes(range=[0, 100], gridcolor=CHART_GRID, title="Quality (higher = better)")
    return _style_fig(fig, height=520)


def etf_sector_chart(weights):
    """Horizontal bar chart of an ETF's sector weightings (dict of name->fraction)."""
    if not weights:
        return None
    items = sorted(((k.replace("_", " ").title(), v * 100) for k, v in weights.items() if v),
                   key=lambda x: x[1])
    fig = go.Figure(go.Bar(
        x=[v for _, v in items], y=[k for k, _ in items], orientation="h",
        marker_color=ACCENT, hovertemplate="%{y}: %{x:.1f}%<extra></extra>",
    ))
    fig.update_xaxes(gridcolor=CHART_GRID, title="Weight %")
    fig.update_yaxes(gridcolor=CHART_GRID)
    return _style_fig(fig, height=360)


def price_with_fair_value(hist, fv_low, fv_high, fv_central):
    """Price history line with the fair-value range shaded across it — so you can see at a
    glance whether the stock is trading below, inside, or above its estimated fair value."""
    fig = go.Figure()
    x = list(hist.index)
    fig.add_trace(go.Scatter(
        x=x, y=hist["Close"], mode="lines", name="Price",
        line=dict(color=ACCENT, width=2),
        hovertemplate="%{x|%b %Y}: $%{y:.2f}<extra></extra>",
    ))
    lo, hi, mid = safe_float(fv_low), safe_float(fv_high), safe_float(fv_central)
    if lo and hi and x:
        # shaded fair-value band spanning the whole time axis
        fig.add_trace(go.Scatter(x=[x[0], x[-1]], y=[hi, hi], mode="lines",
                                 line=dict(width=0), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=[x[0], x[-1]], y=[lo, lo], mode="lines", fill="tonexty",
                                 fillcolor="rgba(224,179,77,0.15)", line=dict(width=0),
                                 name="Fair-value range", hoverinfo="skip"))
        if mid:
            fig.add_hline(y=mid, line_dash="dash", line_color="#E0B34D",
                          annotation_text="fair value", annotation_font_color="#E0B34D")
    fig.update_yaxes(gridcolor=CHART_GRID, title="Price ($)")
    fig.update_xaxes(gridcolor=CHART_GRID)
    fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0))
    return _style_fig(fig, height=380)


APP_DIR = Path(__file__).parent
SP500_CACHE = APP_DIR / "sp500_quant_scores.csv"
SP500_HISTORY = APP_DIR / "sp500_quant_score_history.csv"
PORTFOLIO_FILE = APP_DIR / "portfolio_manager_ai.csv"
WATCHLIST_FILE = APP_DIR / "watchlist.csv"
JOURNAL_FILE = APP_DIR / "research_journal.csv"
TRADES_FILE = APP_DIR / "paper_trades.json"

# Load a local .env (for OPENAI_API_KEY etc.) if present. Safe no-op if the file/lib is missing.
try:
    from dotenv import load_dotenv
    load_dotenv(APP_DIR / ".env")
except Exception:
    pass

MARKET_ASSETS = {
    "SPY": "S&P 500",
    "QQQ": "Nasdaq 100",
    "IWM": "Small Caps",
    "DIA": "Dow",
    "^VIX": "VIX",
    "TLT": "Long Bonds",
    "DX-Y.NYB": "Dollar Index",
    "GLD": "Gold",
    "USO": "Oil",
    "BTC-USD": "Bitcoin",
}

NEWS_WATCHLIST = list(MARKET_ASSETS.keys()) + ["NVDA", "MSFT", "META", "AAPL", "GOOGL", "AMZN"]

QUALITY_COMPOUNDERS = [
    "MSFT", "AAPL", "NVDA", "META", "GOOGL", "AMZN", "COST", "AVGO", "V", "MA",
    "LLY", "UNH", "HD", "PG", "ADBE", "CRM", "NFLX", "NOW", "AMD", "QCOM"
]

RECOVERY_WATCHLIST = [
    "PYPL", "DIS", "NKE", "SBUX", "INTC", "TGT", "CVS", "WBD", "BA", "PFE",
    "F", "GM", "SHOP", "SQ", "ROKU", "ZM", "PARA", "BABA"
]

CATEGORIES = {
    "Macro": ["fed", "federal reserve", "powell", "inflation", "cpi", "ppi", "jobs", "payrolls", "unemployment", "recession", "rates"],
    "AI / Tech": ["ai", "artificial intelligence", "chip", "semiconductor", "nvidia", "microsoft", "meta"],
    "Earnings": ["earnings", "revenue", "profit", "guidance", "margin", "forecast", "eps"],
    "Analyst": ["upgrade", "downgrade", "price target", "analyst", "rating"],
    "Bonds / Rates": ["treasury", "yield", "bond", "tlt", "interest rate"],
    "Oil / Energy": ["oil", "energy", "crude", "uso", "opec"],
    "Gold / Dollar": ["gold", "gld", "dollar", "dxy"],
    "Legal / Regulation": ["lawsuit", "sec", "doj", "regulation", "antitrust", "fine"],
}

BULLISH_WORDS = ["beats", "surges", "rallies", "jumps", "rises", "record", "strong", "upgrade", "raises", "growth", "optimism", "buy"]
BEARISH_WORDS = ["falls", "drops", "slumps", "misses", "cuts", "downgrade", "weak", "risk", "lawsuit", "recession", "warning", "sell"]


def safe_float(value, default=None):
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def clamp(value, low=0, high=100):
    value = safe_float(value, 50)
    return max(low, min(high, value))


def safe_score(value, good_low, good_high, reverse=False):
    value = safe_float(value)
    if value is None:
        return 50.0
    if reverse:
        if value <= good_low:
            return 100.0
        if value >= good_high:
            return 0.0
        return round(100 - ((value - good_low) / (good_high - good_low)) * 100, 1)
    if value <= good_low:
        return 0.0
    if value >= good_high:
        return 100.0
    return round(((value - good_low) / (good_high - good_low)) * 100, 1)


def grade(score):
    score = safe_float(score, 0)
    if score >= 97: return "A+"
    if score >= 93: return "A"
    if score >= 90: return "A-"
    if score >= 87: return "B+"
    if score >= 83: return "B"
    if score >= 80: return "B-"
    if score >= 77: return "C+"
    if score >= 73: return "C"
    if score >= 70: return "C-"
    if score >= 67: return "D+"
    if score >= 63: return "D"
    if score >= 60: return "D-"
    return "F"


def tier(score):
    score = safe_float(score, 0)
    if score >= 85:
        return "Tier 1 — Strong Research Candidate"
    if score >= 75:
        return "Tier 2 — Worth Researching"
    if score >= 60:
        return "Tier 3 — Watchlist Only"
    return "Tier 4 — Low Priority / Avoid"


def pct(value):
    value = safe_float(value)
    if value is None:
        return None
    return round(value * 100, 2)


def money(value):
    value = safe_float(value)
    if value is None:
        return "N/A"
    return f"${value:,.2f}"


def today_string():
    return datetime.now().strftime("%Y-%m-%d")


def clean_ticker(ticker):
    return MARKET_ASSETS.get(ticker, ticker)


def build_labels(row):
    labels = []
    if row.get("Investment Score", 0) >= 80:
        labels.append("Long-Term Compounder")
    if row.get("Opportunity Score", 0) >= 75:
        labels.append("Undervalued Opportunity")
    if row.get("Position Trade Score", 0) >= 75:
        labels.append("Position Trade Candidate")
    if row.get("Valuation Score", 0) >= 70 and row.get("Momentum Score", 0) < 55:
        labels.append("Recovery Candidate")
    if row.get("Health Score", 0) >= 80:
        labels.append("Healthy Business")
    if row.get("Expected Return Score", 0) >= 80:
        labels.append("High Expected Return Candidate")
    return ", ".join(labels) if labels else "General Watchlist"



def signal_strength_label(score):
    score = safe_float(score, 0)
    if score >= 80:
        return "Strong"
    if score >= 65:
        return "Positive"
    if score >= 50:
        return "Neutral"
    if score >= 35:
        return "Weak"
    return "Negative"


def calculate_evidence_score(row):
    """
    Evidence Score asks: how many independent factors agree that this stock deserves research?
    It rewards agreement across quality, value, cash flow, growth, momentum, health, and news.
    """
    checks = [
        safe_float(row.get("Quality Score"), 0) >= 70,
        safe_float(row.get("Valuation Score"), 0) >= 65,
        safe_float(row.get("Cash Flow Score"), 0) >= 65,
        safe_float(row.get("Growth Score"), 0) >= 60,
        safe_float(row.get("Financial Strength Score"), 0) >= 60,
        safe_float(row.get("Momentum Score"), 0) >= 60,
        safe_float(row.get("Relative Strength Score"), 0) >= 60,
        safe_float(row.get("News Sentiment Score"), 50) >= 55,
    ]

    positive = sum(checks)
    evidence = (positive / len(checks)) * 100

    # Strong red flags reduce evidence because factor agreement becomes less trustworthy.
    if safe_float(row.get("Risk Score"), 50) < 40:
        evidence -= 10
    if safe_float(row.get("Financial Strength Score"), 50) < 40:
        evidence -= 10
    if safe_float(row.get("Cash Flow Score"), 50) < 35:
        evidence -= 10

    return round(clamp(evidence), 1)


def calculate_conviction_score(row):
    """
    Conviction Score asks: how confident should I be that this stock deserves research today?
    It favors opportunity + quality + health, but still cares about news and risk.
    """
    opportunity = safe_float(row.get("Opportunity Score"), 0)
    investment = safe_float(row.get("Investment Score"), 0)
    health = safe_float(row.get("Health Score"), 0)
    cash_flow = safe_float(row.get("Cash Flow Score"), 0)
    financial = safe_float(row.get("Financial Strength Score"), 0)
    relative = safe_float(row.get("Relative Strength Score"), 0)
    news = safe_float(row.get("News Sentiment Score"), 50)
    risk = safe_float(row.get("Risk Score"), 50)
    evidence = safe_float(row.get("Evidence Score"), calculate_evidence_score(row))

    conviction = (
        opportunity * 0.24 +
        investment * 0.21 +
        health * 0.17 +
        cash_flow * 0.12 +
        financial * 0.10 +
        relative * 0.06 +
        news * 0.05 +
        evidence * 0.05
    )

    # Penalize major risk because we want good research candidates, not traps.
    if risk < 40:
        conviction -= 8
    if financial < 35:
        conviction -= 8
    if cash_flow < 30:
        conviction -= 6
    if safe_float(row.get("Valuation Score"), 50) < 30:
        conviction -= 5

    return round(clamp(conviction), 1)


def detect_biggest_risk(row):
    risks = []

    risk_map = [
        ("Valuation Risk", 100 - safe_float(row.get("Valuation Score"), 50)),
        ("Growth Risk", 100 - safe_float(row.get("Growth Score"), 50)),
        ("Cash Flow Risk", 100 - safe_float(row.get("Cash Flow Score"), 50)),
        ("Debt / Balance Sheet Risk", 100 - safe_float(row.get("Financial Strength Score"), 50)),
        ("Momentum Risk", 100 - safe_float(row.get("Momentum Score"), 50)),
        ("Business Quality Risk", 100 - safe_float(row.get("Quality Score"), 50)),
        ("Volatility / Drawdown Risk", 100 - safe_float(row.get("Risk Score"), 50)),
        ("News / Sentiment Risk", 100 - safe_float(row.get("News Sentiment Score"), 50)),
    ]

    sorted_risks = sorted(risk_map, key=lambda x: x[1], reverse=True)
    biggest = sorted_risks[0][0]
    severity = sorted_risks[0][1]

    if severity < 35:
        return "No major obvious risk"
    return biggest


def generate_rank_reasons(row, max_reasons=5):
    reasons = []

    checks = [
        ("Strong investment score", row.get("Investment Score"), 80),
        ("Strong conviction score", row.get("Conviction Score"), 80),
        ("Strong evidence score", row.get("Evidence Score"), 80),
        ("Attractive opportunity/valuation setup", row.get("Opportunity Score"), 75),
        ("High business health", row.get("Health Score"), 75),
        ("Strong cash-flow profile", row.get("Cash Flow Score"), 75),
        ("Strong quality profile", row.get("Quality Score"), 75),
        ("Strong growth profile", row.get("Growth Score"), 75),
        ("Strong relative strength vs SPY", row.get("Relative Strength Score"), 75),
        ("Strong 3-6 month position-trade setup", row.get("Position Trade Score"), 75),
        ("Positive news sentiment", row.get("News Sentiment Score"), 65),
    ]

    for label, value, threshold in checks:
        if safe_float(value, 0) >= threshold:
            reasons.append(f"{label} ({safe_float(value, 0):.1f}/100)")

    if safe_float(row.get("FCF Yield %"), 0) and safe_float(row.get("FCF Yield %"), 0) >= 5:
        reasons.append(f"FCF yield looks attractive ({row.get('FCF Yield %')}%)")
    if safe_float(row.get("ROIC Proxy %"), 0) and safe_float(row.get("ROIC Proxy %"), 0) >= 10:
        reasons.append(f"ROIC proxy is strong ({row.get('ROIC Proxy %')}%)")
    if safe_float(row.get("Upside %"), 0) >= 10:
        reasons.append(f"Fair value upside is positive ({row.get('Upside %')}%)")

    if not reasons:
        reasons.append("No single dominant strength; needs manual research.")

    return " | ".join(reasons[:max_reasons])


def generate_concerns(row, max_concerns=4):
    concerns = []

    checks = [
        ("Valuation may be stretched", row.get("Valuation Score"), 40),
        ("Cash-flow profile looks weak", row.get("Cash Flow Score"), 40),
        ("Growth profile looks weak", row.get("Growth Score"), 40),
        ("Financial strength looks weak", row.get("Financial Strength Score"), 40),
        ("Momentum is weak", row.get("Momentum Score"), 40),
        ("Relative strength is weak", row.get("Relative Strength Score"), 40),
        ("Risk profile is elevated", row.get("Risk Score"), 40),
        ("Recent news sentiment is weak", row.get("News Sentiment Score"), 40),
    ]

    for label, value, threshold in checks:
        if safe_float(value, 50) < threshold:
            concerns.append(f"{label} ({safe_float(value, 0):.1f}/100)")

    if safe_float(row.get("Debt/Equity"), 0) and safe_float(row.get("Debt/Equity"), 0) > 200:
        concerns.append("Debt/equity is high")
    if safe_float(row.get("FCF Yield %"), 1) is not None and safe_float(row.get("FCF Yield %"), 1) < 0:
        concerns.append("Free cash flow yield is negative")

    if not concerns:
        concerns.append("No major quant red flag detected.")

    return " | ".join(concerns[:max_concerns])


def estimate_research_time(row):
    """
    More conflict + more risk = more time required.
    """
    scores = [
        safe_float(row.get("Investment Score"), 50),
        safe_float(row.get("Opportunity Score"), 50),
        safe_float(row.get("Position Trade Score"), 50),
        safe_float(row.get("Health Score"), 50),
        safe_float(row.get("Risk Score"), 50),
        safe_float(row.get("Evidence Score"), 50),
    ]

    conflict = max(scores) - min(scores)
    risk = 100 - safe_float(row.get("Risk Score"), 50)
    evidence = safe_float(row.get("Evidence Score"), 50)

    minutes = 15
    if conflict > 45:
        minutes += 20
    elif conflict > 30:
        minutes += 10

    if risk > 65:
        minutes += 20
    elif risk > 50:
        minutes += 10

    if evidence < 50:
        minutes += 15
    elif evidence < 65:
        minutes += 5

    if "Recovery Candidate" in str(row.get("Labels", "")):
        minutes += 10
    if "High Risk" in str(row.get("Research Action", "")):
        minutes += 10

    if minutes <= 15:
        return "15 minutes"
    if minutes <= 30:
        return "30 minutes"
    if minutes <= 45:
        return "45 minutes"
    return "60+ minutes"


def enhance_research_columns(df):
    if df is None or df.empty:
        return df

    df = normalize_scores_df(df).copy()

    if "Evidence Score" not in df.columns:
        df["Evidence Score"] = df.apply(calculate_evidence_score, axis=1)
    else:
        df["Evidence Score"] = df.apply(lambda r: safe_float(r.get("Evidence Score"), calculate_evidence_score(r)), axis=1)

    if "Conviction Score" not in df.columns:
        df["Conviction Score"] = df.apply(calculate_conviction_score, axis=1)
    else:
        df["Conviction Score"] = df.apply(lambda r: safe_float(r.get("Conviction Score"), calculate_conviction_score(r)), axis=1)

    df["Biggest Risk"] = df.apply(detect_biggest_risk, axis=1)
    df["Why Ranked High"] = df.apply(generate_rank_reasons, axis=1)
    df["Main Concerns"] = df.apply(generate_concerns, axis=1)
    df["Research Time"] = df.apply(estimate_research_time, axis=1)

    # Research priority is the homepage ranking score.
    df["Research Priority"] = (
        df["Conviction Score"] * 0.35 +
        df["Evidence Score"] * 0.25 +
        df["Expected Return Score"] * 0.15 +
        df["Opportunity Score"] * 0.15 +
        df["Investment Score"] * 0.10
    ).round(1)

    # Sector-relative fair value: what each stock would be worth at its SECTOR's median P/E
    # (relative valuation done properly — a bank vs banks, software vs software). Needs >=3
    # peers with valid P/E in the sector, else left blank.
    if "P/E" in df.columns and "Sector" in df.columns and "Price" in df.columns:
        pe_num = pd.to_numeric(df["P/E"], errors="coerce")
        price_num = pd.to_numeric(df["Price"], errors="coerce")
        eps = price_num / pe_num.where(pe_num > 0)
        sec_med = pe_num.where(pe_num > 0).groupby(df["Sector"]).transform("median")
        sec_cnt = pe_num.where(pe_num > 0).groupby(df["Sector"]).transform("count")
        sfv = (sec_med * eps).where(sec_cnt >= 3)
        df["Sector Fair Value"] = sfv.round(2)
        df["Sector Median P/E"] = sec_med.where(sec_cnt >= 3).round(1)

    return df


# Which absolute factors get a "within-sector" companion score.
SECTOR_RELATIVE_FACTORS = {
    "Overall Quant Score": "Overall vs Sector",
    "Valuation Score": "Valuation vs Sector",
    "Quality Score": "Quality vs Sector",
    "Growth Score": "Growth vs Sector",
    "Health Score": "Health vs Sector",
    "Momentum Score": "Momentum vs Sector",
}


def add_sector_relative_scores(df):
    """Add 0-100 percentile ranks computed WITHIN each stock's sector.

    Comparing a bank's raw valuation to a software company's is misleading — banks
    structurally trade cheap, software structurally trades rich. A percentile *among
    sector peers* answers the more useful question: is this the cheapest/best-quality
    name relative to companies it actually competes with? Sectors with fewer than 3
    scanned names are left blank, since a percentile among 1-2 peers isn't meaningful.
    (This gets more powerful the more of the S&P 500 you scan.)"""
    if df is None or df.empty or "Sector" not in df.columns:
        return df
    df = df.copy()
    peer_counts = df.groupby("Sector")["Ticker"].transform("count")
    df["Sector Peers"] = peer_counts.astype("Int64")
    for src, dest in SECTOR_RELATIVE_FACTORS.items():
        if src in df.columns:
            ranks = (df.groupby("Sector")[src].rank(pct=True) * 100).round(0)
            ranks = ranks.where(peer_counts >= 3, other=pd.NA)
            df[dest] = ranks.astype("Int64")
    return df



def normalize_scores_df(df):
    if df is None or df.empty:
        return pd.DataFrame()

    defaults = {
        "Ticker": "",
        "Company": "",
        "Sector": "Unknown",
        "Industry": "Unknown",
        "Price": None,
        "Fair Value": None,
        "Upside %": None,
        "Margin of Safety %": None,
        "Sell Target": None,
        "Suggested Hold": "Research only",
        "Investment Score": 0.0,
        "Opportunity Score": 0.0,
        "Position Trade Score": 0.0,
        "Health Score": 0.0,
        "Expected Return Score": 0.0,
        "Conviction Score": 0.0,
        "Evidence Score": 0.0,
        "Research Priority": 0.0,
        "Overall Quant Score": 0.0,
        "Quality Score": 0.0,
        "Valuation Score": 0.0,
        "Growth Score": 0.0,
        "Cash Flow Score": 0.0,
        "Financial Strength Score": 0.0,
        "Momentum Score": 0.0,
        "Risk Score": 0.0,
        "Earnings Quality Score": 0.0,
        "Relative Strength Score": 0.0,
        "Labels": "General Watchlist",
        "Verdict": "Watchlist only",
        "Research Action": "Research only",
        "Biggest Risk": "",
        "Why Ranked High": "",
        "Main Concerns": "",
        "Research Time": "",
        "Alerts": "No major signal",
        "Scan Date": today_string(),
    }
    for col, default in defaults.items():
        if col not in df.columns:
            df[col] = default

    numeric_cols = [
        "Investment Score", "Opportunity Score", "Position Trade Score", "Health Score",
        "Expected Return Score", "Overall Quant Score", "Quality Score", "Valuation Score",
        "Growth Score", "Cash Flow Score", "Financial Strength Score", "Momentum Score",
        "Risk Score", "Earnings Quality Score", "Relative Strength Score", "Conviction Score", "Evidence Score", "Research Priority"
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df["Overall Grade"] = df["Overall Quant Score"].apply(grade)
    df["Tier"] = df["Overall Quant Score"].apply(tier)
    missing = df["Labels"].isna() | (df["Labels"].astype(str).str.strip() == "")
    df.loc[missing, "Labels"] = df[missing].apply(build_labels, axis=1)
    return df


@st.cache_data(ttl=900, show_spinner=False)
def get_market_snapshot():
    """Snapshot of the market assets. Uses a SINGLE batched download (fast) instead of one
    slow sequential call per ticker — the old approach hung the home page on Streamlit Cloud
    where Yahoo is rate-limited. Falls back to per-ticker only if the batch fails."""
    tickers = list(MARKET_ASSETS.keys())

    def _row(name, tk, closes):
        closes = closes.dropna()
        if len(closes) < 2:
            return None
        cur, prev = safe_float(closes.iloc[-1]), safe_float(closes.iloc[-2])
        if not cur or not prev:
            return None
        r3 = ((cur / safe_float(closes.iloc[-63], cur)) - 1) * 100 if len(closes) > 63 else 0
        return {"Asset": name, "Ticker": clean_ticker(tk), "Price": round(cur, 2),
                "Change %": round((cur - prev) / prev * 100, 2), "3M Return %": round(r3, 2)}

    rows = []
    try:
        data = yf.download(tickers, period="6mo", progress=False, group_by="ticker", threads=True)
        for tk, name in MARKET_ASSETS.items():
            try:
                closes = data[tk]["Close"] if tk in data.columns.get_level_values(0) else None
                if closes is not None:
                    r = _row(name, tk, closes)
                    if r:
                        rows.append(r)
            except Exception:
                pass
    except Exception:
        pass

    if not rows:   # fallback: per-ticker (short period so it can't hang for long)
        for tk, name in MARKET_ASSETS.items():
            try:
                h = yf.Ticker(tk).history(period="5d")
                if len(h) >= 2:
                    r = _row(name, tk, h["Close"])
                    if r:
                        rows.append(r)
            except Exception:
                pass
    return rows


def get_market_health(snapshot):
    if not snapshot:
        return 50, "Unknown"
    df = pd.DataFrame(snapshot)
    changes = {row["Asset"]: row["Change %"] for _, row in df.iterrows()}
    score = 50
    if changes.get("S&P 500", 0) > 0: score += 8
    if changes.get("Nasdaq 100", 0) > 0: score += 8
    if changes.get("Small Caps", 0) > 0: score += 5
    if changes.get("VIX", 0) < 0: score += 8
    if changes.get("Long Bonds", 0) > 0: score += 5
    if changes.get("Dollar Index", 0) < 0: score += 4
    if changes.get("Oil", 0) > 2: score -= 5
    if changes.get("VIX", 0) > 3: score -= 10
    score = max(0, min(100, score))
    if score >= 75:
        regime = "Risk-On / Bullish"
    elif score >= 60:
        regime = "Neutral-Bullish"
    elif score >= 45:
        regime = "Mixed / Neutral"
    elif score >= 30:
        regime = "Cautious / Bearish"
    else:
        regime = "Risk-Off"
    return score, regime


def categorize_news(title, summary):
    text = f"{title} {summary}".lower()
    matched = []
    for category, words in CATEGORIES.items():
        if any(word in text for word in words):
            matched.append(category)
    return matched if matched else ["General Market"]


def score_news(title, summary):
    text = f"{title} {summary}".lower()
    score = 1
    for words in CATEGORIES.values():
        for word in words:
            if word in text:
                score += 1
    if any(w in text for w in ["fed", "inflation", "cpi", "rates", "earnings", "guidance", "upgrade", "downgrade"]):
        score += 3
    return min(score, 10)


def news_sentiment(title, summary):
    text = f"{title} {summary}".lower()
    bullish = sum(word in text for word in BULLISH_WORDS)
    bearish = sum(word in text for word in BEARISH_WORDS)
    if bullish > bearish:
        return "Bullish"
    if bearish > bullish:
        return "Bearish"
    return "Neutral"


@st.cache_data(ttl=900, show_spinner=False)
def get_ticker_news(ticker, hours_back=24):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    articles = []
    seen = set()
    try:
        stock = yf.Ticker(ticker)
        for item in stock.news:
            content = item.get("content", {})
            title = content.get("title", "")
            summary = content.get("summary", "")
            provider = content.get("provider", {}).get("displayName", "Yahoo Finance")
            url = content.get("canonicalUrl", {}).get("url", "")
            pub_date = content.get("pubDate")
            if not title or not pub_date:
                continue
            published = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
            if published < cutoff:
                continue
            key = title.lower().strip()
            if key in seen:
                continue
            seen.add(key)
            articles.append({
                "Ticker": clean_ticker(ticker),
                "Title": title,
                "Summary": summary,
                "Provider": provider,
                "URL": url,
                "Published": published,
                "Importance": score_news(title, summary),
                "Signal": news_sentiment(title, summary),
                "Category": ", ".join(categorize_news(title, summary)),
            })
    except Exception:
        pass
    return sorted(articles, key=lambda x: (x["Importance"], x["Published"]), reverse=True)


@st.cache_data(ttl=900, show_spinner=False)
def get_market_news(hours_back=10):
    articles = []
    for ticker in NEWS_WATCHLIST:
        articles.extend(get_ticker_news(ticker, hours_back))
    seen = set()
    unique = []
    for a in articles:
        k = a["Title"].lower().strip()
        if k not in seen:
            seen.add(k)
            unique.append(a)
    return sorted(unique, key=lambda x: (x["Importance"], x["Published"]), reverse=True)


RISK_FREE_RATE = 0.043     # ~10-yr Treasury
EQUITY_RISK_PREMIUM = 0.05  # long-run equity premium over risk-free


def capm_rate(beta):
    """Discount rate from CAPM: risk_free + beta × equity-risk-premium, clamped to a sane
    band. A high-beta stock is discounted harder (worth less), a defensive one less so —
    far more principled than a fixed rate."""
    b = safe_float(beta, 1.0)
    if b is None:
        b = 1.0
    b = max(0.5, min(2.2, b))
    return max(0.075, min(0.14, RISK_FREE_RATE + b * EQUITY_RISK_PREMIUM))


def dcf_from_params(fcf_ps, g1, r, g_term=0.025, years=5):
    """Simple 2-stage DCF (used by the interactive Valuation Lab)."""
    fcf_ps = safe_float(fcf_ps)
    if fcf_ps is None or fcf_ps <= 0 or r is None or g_term is None or r <= g_term:
        return None
    pv, cf = 0.0, fcf_ps
    for yr in range(1, years + 1):
        cf *= (1 + g1)
        pv += cf / ((1 + r) ** yr)
    terminal = cf * (1 + g_term) / (r - g_term)
    pv += terminal / ((1 + r) ** years)
    return pv


def dcf_3stage(fcf_ps, g_high, r, g_term=0.025, high_years=5, fade_years=5):
    """3-stage DCF: `high_years` at g_high, then a linear fade to g_term over `fade_years`,
    then a Gordon-growth terminal — the realistic shape (few firms grow fast forever)."""
    fcf_ps = safe_float(fcf_ps)
    if fcf_ps is None or fcf_ps <= 0 or r is None or r <= g_term:
        return None
    pv, cf, yr = 0.0, fcf_ps, 0
    for _ in range(high_years):
        yr += 1
        cf *= (1 + g_high)
        pv += cf / ((1 + r) ** yr)
    for i in range(1, fade_years + 1):
        g = g_high + (g_term - g_high) * (i / fade_years)
        yr += 1
        cf *= (1 + g)
        pv += cf / ((1 + r) ** yr)
    terminal = cf * (1 + g_term) / (r - g_term)
    pv += terminal / ((1 + r) ** yr)
    return pv


def sustainable_growth(roe, payout):
    """Fundamental (self-funded) growth = retention × ROE = (1 − payout) × ROE. Damodaran's
    core discipline: a firm can't grow faster than its reinvestment and returns allow.
    roe/payout are fractions. Returns None if ROE unavailable."""
    roe = safe_float(roe)
    if roe is None:
        return None
    payout = safe_float(payout, 0.0)
    payout = min(max(payout if payout is not None else 0.0, 0.0), 1.0)
    return roe * (1 - payout)


def _dcf_fair_value(fcf_ps, growth_rate, risk_score, beta=None, roe=None, payout=None):
    """Engine DCF: CAPM discount rate + 3-stage growth, with stage-1 growth ANCHORED to
    sustainable growth (retention × ROE) so we never assume more growth than the business
    can fund. Terminal growth capped at the risk-free rate. None if no positive FCF."""
    observed = max(safe_float(growth_rate, 0.05) or 0.05, 0.0)
    sg = sustainable_growth(roe, payout)
    if sg is not None:
        # take the more conservative of observed vs fundable (allow a small near-term buffer)
        g1 = min(observed, max(sg, 0.0) + 0.03)
    else:
        g1 = observed
    g1 = min(max(g1, 0.0), 0.16)
    g_term = min(0.025, RISK_FREE_RATE)   # can't outgrow the economy forever
    return dcf_3stage(fcf_ps, g1, capm_rate(beta), g_term=g_term)


def reverse_dcf_growth(price, fcf_ps, beta):
    """Solve for the stage-1 FCF growth rate the CURRENT PRICE implies (3-stage DCF, CAPM
    rate). Answers 'what does the market expect?' — compare it to reality to judge the price."""
    price, fcf_ps = safe_float(price), safe_float(fcf_ps)
    if not price or not fcf_ps or fcf_ps <= 0:
        return None
    r = capm_rate(beta)
    lo, hi = -0.10, 0.50
    if dcf_3stage(fcf_ps, hi, r) < price:   # even 50% growth can't justify it
        return None
    for _ in range(60):
        mid = (lo + hi) / 2
        v = dcf_3stage(fcf_ps, mid, r)
        if v is None:
            return None
        if v < price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _cost_of_debt(net_debt_to_ebitda):
    """Pre-tax cost of debt ≈ risk-free + a credit spread that widens with leverage."""
    spread = min(max(0.010 + (safe_float(net_debt_to_ebitda, 1.0) or 1.0) * 0.006, 0.010), 0.06)
    return RISK_FREE_RATE + spread


def wacc(beta, market_cap, total_debt, net_debt_to_ebitda, tax=0.21):
    """Weighted-average cost of capital: blends cost of equity (CAPM) and after-tax cost of
    debt by capital-structure weights. Lower than cost of equity for levered firms — which
    correctly raises their intrinsic value (the debt tax shield)."""
    E = safe_float(market_cap)
    if not E or E <= 0:
        return None
    D = max(safe_float(total_debt, 0.0) or 0.0, 0.0)
    V = E + D
    re, rd = capm_rate(beta), _cost_of_debt(net_debt_to_ebitda)
    return (E / V) * re + (D / V) * rd * (1 - tax)


def fcff_wacc_value(fcf_ps, price, market_cap, total_debt, total_cash, beta,
                    net_debt_to_ebitda, growth_rate, roe=None, payout=None, tax=0.21):
    """Enterprise DCF: value FCFF (free cash flow to the FIRM) at WACC → enterprise value →
    subtract net debt → equity value per share. The right approach for heavily-levered
    non-financials, where cost-of-equity FCFE DCF understates the value of cheap debt."""
    fcf_ps, price, mc = safe_float(fcf_ps), safe_float(price), safe_float(market_cap)
    if not fcf_ps or fcf_ps <= 0 or not price or not mc or mc <= 0:
        return None
    shares = mc / price
    td = max(safe_float(total_debt, 0.0) or 0.0, 0.0)
    tc = max(safe_float(total_cash, 0.0) or 0.0, 0.0)
    # FCFF ≈ FCFE + after-tax interest (add back cash paid to debt holders)
    fcfe_total = fcf_ps * shares
    fcff_total = fcfe_total + td * _cost_of_debt(net_debt_to_ebitda) * (1 - tax)
    w = wacc(beta, mc, td, net_debt_to_ebitda, tax)
    if w is None or w <= 0.025:
        return None
    observed = max(safe_float(growth_rate, 0.05) or 0.05, 0.0)
    sg = sustainable_growth(roe, payout)
    g1 = min(observed, max(sg, 0.0) + 0.03) if sg is not None else observed
    g1 = min(max(g1, 0.0), 0.16)
    ev_ps = dcf_3stage(fcff_total / shares, g1, w, g_term=min(0.025, RISK_FREE_RATE))
    if ev_ps is None:
        return None
    equity_value = ev_ps * shares - (td - tc)   # EV − net debt = equity value
    return equity_value / shares if shares else None


def monte_carlo_dcf(fcf_ps, base_growth, beta, n=3000, seed=0):
    """Run N DCF simulations with randomized assumptions (growth, discount rate, terminal
    rate, starting FCF) to get a DISTRIBUTION of fair value instead of a point estimate.
    Returns the array of simulated per-share values (deterministic per seed)."""
    import numpy as np
    fcf_ps = safe_float(fcf_ps)
    if not fcf_ps or fcf_ps <= 0:
        return None
    rng = np.random.default_rng(seed)
    base_r = capm_rate(beta)
    g = np.clip(rng.normal(base_growth, 0.045, n), -0.05, 0.30)      # growth uncertainty
    r = np.clip(rng.normal(base_r, 0.015, n), 0.06, 0.16)           # discount-rate uncertainty
    gt = np.clip(rng.normal(0.023, 0.005, n), 0.005, RISK_FREE_RATE)  # terminal-growth uncertainty
    fmult = np.clip(rng.normal(1.0, 0.10, n), 0.7, 1.35)            # starting-FCF uncertainty
    vals = []
    for i in range(n):
        v = dcf_3stage(fcf_ps * fmult[i], float(g[i]), float(r[i]), g_term=float(gt[i]))
        if v is not None and v > 0:
            vals.append(v)
    return np.array(vals) if len(vals) > 100 else None


def estimate_fair_value(price, pe, fcf_ps, ev_to_fcf, peg, quality_score, growth_score,
                        cash_flow_score, risk_score, growth_rate, high_52, low_52,
                        beta=None, dividend_yield=None, roe=None, payout=None,
                        sector=None, price_to_book=None, market_cap=None, total_debt=None,
                        total_cash=None, net_debt_to_ebitda=None):
    """Blend several valuation methods into an honest fair-value range.

    Sector-aware: banks/insurers can't be valued on free cash flow, so for financials we
    skip DCF/EV-FCF and add a justified P/B (from ROE) instead — the right tool per business.
    Each method is capped to a sane band around price; central value is the median."""
    price = safe_float(price)
    if not price or price <= 0:
        return {"central": None, "low": None, "high": None, "methods": []}
    is_financial = bool(sector) and any(k in str(sector).lower() for k in ["financ", "bank", "insur"])
    methods = []

    pe = safe_float(pe)
    if pe and pe > 0:
        eps = price / pe
        fair_pe = 18
        if quality_score >= 80 and growth_score >= 75:
            fair_pe = 30
        elif quality_score >= 70 and growth_score >= 60:
            fair_pe = 24
        elif quality_score < 45:
            fair_pe = 14
        methods.append(("P/E", eps * fair_pe))

    if not is_financial:
        ev_to_fcf = safe_float(ev_to_fcf)
        if ev_to_fcf and ev_to_fcf > 0:
            fair_ev_fcf = 20
            if quality_score >= 80 and cash_flow_score >= 75:
                fair_ev_fcf = 28
            elif quality_score < 50:
                fair_ev_fcf = 14
            methods.append(("EV/FCF", price * (fair_ev_fcf / ev_to_fcf)))

        # Heavily-levered non-financials → FCFF discounted at WACC (captures the debt tax
        # shield). Lightly-levered → the simpler FCFE / cost-of-equity DCF.
        ndte = safe_float(net_debt_to_ebitda)
        if ndte is not None and ndte > 1.5:
            dcf = fcff_wacc_value(fcf_ps, price, market_cap, total_debt, total_cash, beta,
                                  ndte, growth_rate, roe, payout)
            if dcf:
                methods.append(("DCF (FCFF/WACC)", dcf))
        else:
            dcf = _dcf_fair_value(fcf_ps, growth_rate, risk_score, beta, roe, payout)
            if dcf:
                methods.append(("DCF (3-stage, CAPM)", dcf))
    else:
        # Financials: justified P/B = (ROE − g)/(r − g), applied to book value per share.
        ptb = safe_float(price_to_book)
        roe_f = safe_float(roe)
        if ptb and ptb > 0 and roe_f is not None:
            book_ps = price / ptb
            r = capm_rate(beta)
            g = min(max(sustainable_growth(roe, payout) or 0.02, 0.0), r - 0.005)
            fair_pb = (roe_f - g) / (r - g) if (r > g and roe_f > g) else (roe_f / r if r else 1.0)
            fair_pb = min(max(fair_pb, 0.3), 5.0)
            methods.append(("P/B (justified)", fair_pb * book_ps))

    # Dividend Discount Model (Gordon growth) — for dividend payers
    dy = safe_float(dividend_yield)
    if dy and dy > 0.001:
        r = capm_rate(beta)
        g = min(max(safe_float(growth_rate, 0.02) or 0.02, 0.0), r - 0.005, 0.08)
        if r > g:
            d1 = (dy * price) * (1 + g)
            methods.append(("Dividend (DDM)", d1 / (r - g)))

    peg = safe_float(peg)
    if peg and peg > 0:
        fair_peg = 1.4
        if quality_score >= 80:
            fair_peg = 2.0
        elif quality_score >= 70:
            fair_peg = 1.7
        if growth_score < 45:
            fair_peg = 1.1
        methods.append(("PEG", price * (fair_peg / peg)))

    high_52, low_52 = safe_float(high_52), safe_float(low_52)
    if high_52 and low_52:
        midpoint = (high_52 + low_52) / 2
        methods.append(("52-week midpoint", midpoint * (1 + (quality_score - 50) / 250)))

    if not methods:
        return {"central": price, "low": price, "high": price, "methods": []}

    lo_cap, hi_cap = 0.4 * price, 2.5 * price
    capped = [(n, min(max(v, lo_cap), hi_cap)) for n, v in methods]
    vals = sorted(v for _, v in capped)
    m = len(vals)
    central = vals[m // 2] if m % 2 else (vals[m // 2 - 1] + vals[m // 2]) / 2
    return {"central": central, "low": min(vals), "high": max(vals), "methods": capped}


class DataUnavailable(Exception):
    """Raised when a ticker has no usable market data (delisted, renamed, or invalid)."""
    pass


def _norm_pct(v):
    """yfinance mixes fractions (0.25) and percents (20.3) for returns/yields. Normalize
    to percent: treat |v|<3 as a fraction and scale up, otherwise assume it's already %."""
    v = safe_float(v)
    if v is None:
        return None
    return round(v * 100, 2) if abs(v) < 3 else round(v, 2)


@st.cache_data(ttl=3600, show_spinner=False)
def analyze_etf(ticker):
    """Fetch ETF characteristics from Yahoo (free): cost, size, yield, returns, risk,
    sector mix, and top holdings. Works for any fund/ETF ticker."""
    t = yf.Ticker(ticker)
    info = t.info or {}
    hist = _yf_history(ticker, period="2y")   # 2y so the 1-year return is always available

    price = safe_float(info.get("navPrice"))
    if price is None and len(hist):
        price = safe_float(hist["Close"].iloc[-1])

    def ret(days):
        if len(hist) > days:
            base = safe_float(hist["Close"].iloc[-days])
            cur = safe_float(hist["Close"].iloc[-1])
            if base and cur:
                return round((cur / base - 1) * 100, 1)
        return None

    vol = mdd = None
    if len(hist) > 30:
        window = hist["Close"].tail(252)   # risk over the last year
        dr = window.pct_change().dropna()
        vol = round(safe_float(dr.std() * math.sqrt(252), 0) * 100, 1)
        rh = window.cummax()
        mdd = round(safe_float((window / rh - 1).min(), 0) * 100, 1)

    sectors, holdings, family = {}, None, None
    category = info.get("category")
    try:
        fd = t.funds_data
        sectors = fd.sector_weightings or {}
        holdings = fd.top_holdings
        ov = fd.fund_overview or {}
        family = ov.get("family")
        category = ov.get("categoryName") or category
    except Exception:
        pass

    expense = safe_float(info.get("annualReportExpenseRatio")) or safe_float(info.get("netExpenseRatio"))
    # yfinance returns expense either as a fraction (0.000945) or already as a percent
    # (0.0945). Values below ~0.02 are fractions and need scaling; larger ones are already %.
    if expense is not None:
        expense_pct = round(expense * 100 if expense < 0.02 else expense, 3)
    else:
        expense_pct = None
    return {
        "Ticker": ticker.upper(),
        "Name": info.get("longName", ticker),
        "Is ETF": info.get("quoteType") == "ETF",
        "Category": category,
        "Family": family,
        "Price": round(price, 2) if price else None,
        "AUM": safe_float(info.get("totalAssets")),
        "Yield %": _norm_pct(info.get("yield")),
        "Expense Ratio %": expense_pct,
        "Beta (3y)": safe_float(info.get("beta3Year")),
        "YTD %": _norm_pct(info.get("ytdReturn")),
        "1M %": ret(21), "3M %": ret(63), "6M %": ret(126), "1Y %": ret(252),
        "3Y Ann %": _norm_pct(info.get("threeYearAverageReturn")),
        "5Y Ann %": _norm_pct(info.get("fiveYearAverageReturn")),
        "Volatility %": vol,
        "Max Drawdown %": mdd,
        "Sector Weightings": sectors,
        "Top Holdings": holdings,
    }


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def get_analyst_data(ticker):
    """Forward-looking analyst data from Yahoo (free): consensus price target, rating,
    forward P/E / EPS, and next-year EPS growth estimate. Complements the engine's
    trailing-data valuation with a future-facing view."""
    out = {k: None for k in ["forward_pe", "forward_eps", "trailing_eps", "target_mean",
                             "target_high", "target_low", "target_median", "n_analysts",
                             "rating", "rec_mean", "eps_growth_next_y", "current"]}
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        out.update({
            "forward_pe": safe_float(info.get("forwardPE")),
            "forward_eps": safe_float(info.get("forwardEps")),
            "trailing_eps": safe_float(info.get("trailingEps")),
            "target_mean": safe_float(info.get("targetMeanPrice")),
            "target_high": safe_float(info.get("targetHighPrice")),
            "target_low": safe_float(info.get("targetLowPrice")),
            "target_median": safe_float(info.get("targetMedianPrice")),
            "n_analysts": safe_float(info.get("numberOfAnalystOpinions")),
            "rating": info.get("recommendationKey"),
            "rec_mean": safe_float(info.get("recommendationMean")),
            "current": safe_float(info.get("currentPrice")) or safe_float(info.get("regularMarketPrice")),
        })
        try:
            ee = t.earnings_estimate
            if ee is not None and hasattr(ee, "index") and "+1y" in ee.index:
                out["eps_growth_next_y"] = safe_float(ee.loc["+1y", "growth"])
        except Exception:
            pass
    except Exception:
        pass
    return out


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def get_fundamental_trends(ticker):
    """Multi-year (usually 4) annual fundamentals from Yahoo (free): revenue, margins, FCF,
    EPS — so you can see whether the business is improving or decaying, not just a snapshot."""
    try:
        t = yf.Ticker(ticker)
        inc = t.income_stmt
        cf = t.cashflow
        if inc is None or getattr(inc, "empty", True):
            return None
        years = [c.year for c in inc.columns]

        def rowvals(df, name):
            return df.loc[name].values if (df is not None and not getattr(df, "empty", True) and name in df.index) else [None] * len(years)

        rev, gp = rowvals(inc, "Total Revenue"), rowvals(inc, "Gross Profit")
        oi, ni = rowvals(inc, "Operating Income"), rowvals(inc, "Net Income")
        eps, fcf = rowvals(inc, "Diluted EPS"), rowvals(cf, "Free Cash Flow")

        data = []
        for i, y in enumerate(years):
            r = safe_float(rev[i])
            def margin(v):
                v = safe_float(v)
                return round(v / r * 100, 1) if (r and v is not None) else None
            data.append({
                "Year": y,
                "Revenue ($B)": round(r / 1e9, 1) if r else None,
                "Gross Margin %": margin(gp[i]),
                "Operating Margin %": margin(oi[i]),
                "Net Margin %": margin(ni[i]),
                "FCF ($B)": round(safe_float(fcf[i]) / 1e9, 1) if safe_float(fcf[i]) is not None else None,
                "EPS": round(safe_float(eps[i]), 2) if safe_float(eps[i]) is not None else None,
            })
        df = pd.DataFrame(data).sort_values("Year").reset_index(drop=True)
        return df if len(df) >= 2 else None
    except Exception:
        return None


def revenue_margin_chart(tdf):
    """Revenue bars + net-margin line (dual axis) — growth and profitability together."""
    fig = go.Figure()
    fig.add_trace(go.Bar(x=tdf["Year"], y=tdf["Revenue ($B)"], name="Revenue ($B)",
                         marker_color="#2b6f63", yaxis="y"))
    fig.add_trace(go.Scatter(x=tdf["Year"], y=tdf["Net Margin %"], name="Net Margin %",
                             mode="lines+markers", line=dict(color=ACCENT, width=3), yaxis="y2"))
    fig.update_layout(
        yaxis=dict(title="Revenue ($B)", gridcolor=CHART_GRID),
        yaxis2=dict(title="Net Margin %", overlaying="y", side="right", showgrid=False),
        xaxis=dict(title=None, gridcolor=CHART_GRID, tickmode="array", tickvals=tdf["Year"]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return _style_fig(fig, height=340)


def margins_trend_chart(tdf):
    fig = go.Figure()
    for col, color in [("Gross Margin %", "#6aa9ff"), ("Operating Margin %", "#E0B34D"), ("Net Margin %", ACCENT)]:
        fig.add_trace(go.Scatter(x=tdf["Year"], y=tdf[col], name=col, mode="lines+markers",
                                 line=dict(color=color, width=2)))
    fig.update_yaxes(title="Margin %", gridcolor=CHART_GRID)
    fig.update_xaxes(gridcolor=CHART_GRID, tickmode="array", tickvals=tdf["Year"])
    fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02))
    return _style_fig(fig, height=340)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def get_forward_signals(ticker):
    """Forward-looking factors with real documented edge (Yahoo, free):
    - estimate revisions momentum (analysts raising vs cutting next-year EPS)
    - earnings-surprise track record (beat rate, avg & latest surprise -> drift)."""
    out = {"rev_up": None, "rev_down": None, "rev_net": None, "rev_label": None,
           "beat_rate": None, "avg_surprise": None, "last_surprise": None, "quarters": 0}
    try:
        t = yf.Ticker(ticker)
        try:
            er = t.eps_revisions
            if er is not None and hasattr(er, "index"):
                row = er.loc["+1y"] if "+1y" in er.index else er.iloc[-1]
                up = safe_float(row.get("upLast30days"), 0) or 0
                dn = safe_float(row.get("downLast30days"), 0) or 0
                out["rev_up"], out["rev_down"], out["rev_net"] = up, dn, up - dn
                out["rev_label"] = "Rising ⬆️" if up > dn else ("Falling ⬇️" if dn > up else "Flat →")
        except Exception:
            pass
        try:
            eh = t.earnings_history
            if eh is not None and "surprisePercent" in eh.columns:
                s = eh["surprisePercent"].dropna()
                if len(s):
                    # Cap each quarter to +/-100%: a near-zero estimate makes the raw
                    # surprise % explode (e.g. est $0.01, actual $0.20 = 1900%), which is
                    # mathematically real but meaningless. Beat rate uses the sign, so it's fine.
                    sc = s.clip(-1.0, 1.0)
                    out["quarters"] = int(len(s))
                    out["beat_rate"] = round((s > 0).mean() * 100)
                    out["avg_surprise"] = round(sc.mean() * 100, 1)
                    out["last_surprise"] = round(max(-1.0, min(1.0, float(s.iloc[-1]))) * 100, 1)
        except Exception:
            pass
    except Exception:
        pass
    return out


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def get_next_earnings(ticker):
    """Next earnings date (ISO string) for a ticker via Yahoo (free). None if unknown."""
    try:
        cal = yf.Ticker(ticker).calendar
        ed = cal.get("Earnings Date") if isinstance(cal, dict) else None
        if ed:
            dt = ed[0] if isinstance(ed, (list, tuple)) else ed
            return pd.to_datetime(dt).date().isoformat()
    except Exception:
        pass
    return None


@st.cache_data(ttl=3600, show_spinner=False)
def get_spy_history():
    """Fetch SPY history ONCE per hour and reuse it for every stock's relative-strength
    calc. Previously this was re-downloaded for every ticker in a scan — hundreds of
    redundant calls that slowed scans and triggered Yahoo rate limits."""
    for attempt in range(3):
        try:
            hist = yf.Ticker("SPY").history(period="2y")
            if hist is not None and not hist.empty:
                return hist
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    return pd.DataFrame()


# ----- Lightweight on-disk cache (persists fetched data across sessions/re-scans) -----
CACHE_DIR = APP_DIR / ".data_cache"
FMP_CACHE_TTL = 20 * 3600      # fundamentals don't change intraday
HIST_CACHE_TTL = 12 * 3600     # daily prices


def _cache_file(key, ext="json"):
    safe = "".join(c if c.isalnum() else "_" for c in key)[:120]
    return CACHE_DIR / f"{safe}.{ext}"


def _disk_get_json(key, ttl):
    try:
        p = _cache_file(key)
        if p.exists() and (time.time() - p.stat().st_mtime) < ttl:
            return json.loads(p.read_text())
    except Exception:
        pass
    return None


def _disk_set_json(key, value):
    try:
        CACHE_DIR.mkdir(exist_ok=True)
        _cache_file(key).write_text(json.dumps(value))
    except Exception:
        pass


def clear_data_cache():
    n = 0
    try:
        if CACHE_DIR.exists():
            for f in CACHE_DIR.iterdir():
                f.unlink()
                n += 1
    except Exception:
        pass
    return n


def _yf_history(ticker, period="2y"):
    """Fetch price history from Yahoo (reliable, free) with retries + a short disk cache
    so repeated scans/deep-dives don't re-download the same daily prices."""
    ck = f"hist::{ticker}::{period}"
    cached = _disk_get_json(ck, HIST_CACHE_TTL)
    if cached is not None:
        try:
            return pd.read_json(io.StringIO(cached), orient="split")
        except Exception:
            pass
    for attempt in range(3):
        try:
            hist = yf.Ticker(ticker).history(period=period)
            if hist is not None and not hist.empty:
                try:
                    _disk_set_json(ck, hist.to_json(orient="split"))
                except Exception:
                    pass
                return hist
        except Exception:
            time.sleep(1.0 * (attempt + 1))
    return pd.DataFrame()


# ----- Financial Modeling Prep (optional upgrade over Yahoo for fundamentals) -----
FMP_BASE = "https://financialmodelingprep.com/stable"


def fmp_available():
    return bool(_get_secret("FMP_API_KEY"))


def _fmp_get(path):
    """Call one FMP 'stable' endpoint, return the first record (dict) or None. Successful
    responses are disk-cached for ~20h so re-scans are instant and don't burn API quota."""
    key = _get_secret("FMP_API_KEY")
    if not key:
        return None
    ck = f"fmp::{path}"
    cached = _disk_get_json(ck, FMP_CACHE_TTL)
    if cached is not None:
        return cached
    sep = "&" if "?" in path else "?"
    url = f"{FMP_BASE}/{path}{sep}apikey={key}"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                data = json.loads(r.read().decode())
            if isinstance(data, dict) and (data.get("Error Message") or data.get("error")):
                return None
            result = data[0] if isinstance(data, list) and data else (data if isinstance(data, dict) else None)
            if result is not None:
                _disk_set_json(ck, result)   # only cache real successes, so failures retry
            return result
        except Exception:
            time.sleep(1.0 * (attempt + 1))
    return None


def _fmp_get_list(path):
    """Like _fmp_get but returns the full list (for multi-row endpoints like annual ratios).
    Disk-cached ~20h."""
    key = _get_secret("FMP_API_KEY")
    if not key:
        return None
    ck = f"fmplist::{path}"
    cached = _disk_get_json(ck, FMP_CACHE_TTL)
    if cached is not None:
        return cached
    sep = "&" if "?" in path else "?"
    url = f"{FMP_BASE}/{path}{sep}apikey={key}"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                data = json.loads(r.read().decode())
            if isinstance(data, list) and data:
                _disk_set_json(ck, data)
                return data
            return None
        except Exception:
            time.sleep(1.0 * (attempt + 1))
    return None


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def get_valuation_history(ticker):
    """5-year P/E history from FMP annual ratios → is the stock cheap vs its OWN history?"""
    data = _fmp_get_list(f"ratios?symbol={ticker}&period=annual&limit=6")
    if not data:
        return None
    pts = []
    for x in data:
        yr = x.get("fiscalYear") or str(x.get("date", ""))[:4]
        pe = safe_float(x.get("priceToEarningsRatio"))
        if yr and pe and pe > 0:
            pts.append((str(yr), round(pe, 1)))
    if len(pts) < 3:
        return None
    pts = sorted(pts)
    pes = [p for _, p in pts]
    return {"points": pts, "avg_pe": round(sum(pes) / len(pes), 1),
            "min_pe": round(min(pes), 1), "max_pe": round(max(pes), 1)}


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def get_ownership_activity(ticker):
    """Institutional/insider ownership + recent insider buying vs selling (Yahoo, free)."""
    out = {"inst_pct": None, "insider_pct": None, "inst_count": None,
           "insider_buys": 0, "insider_sells": 0, "insider_net_shares": 0}
    try:
        t = yf.Ticker(ticker)
        try:
            mh = t.major_holders
            if mh is not None and "Value" in mh.columns:
                def g(k):
                    return safe_float(mh.loc[k, "Value"]) if k in mh.index else None
                out["inst_pct"] = g("institutionsPercentHeld")
                out["insider_pct"] = g("insidersPercentHeld")
                out["inst_count"] = g("institutionsCount")
        except Exception:
            pass
        try:
            it = t.insider_transactions
            if it is not None and not it.empty and "Transaction" in it.columns:
                cutoff = datetime.now() - timedelta(days=180)
                recent = it
                if "Start Date" in it.columns:
                    recent = it[pd.to_datetime(it["Start Date"], errors="coerce") >= cutoff]
                for _, r in recent.iterrows():
                    txt = str(r.get("Transaction", "")).lower()
                    sh = safe_float(r.get("Shares"), 0) or 0
                    if "purchase" in txt or "buy" in txt:
                        out["insider_buys"] += 1
                        out["insider_net_shares"] += sh
                    elif "sale" in txt or "sold" in txt or "sell" in txt:
                        out["insider_sells"] += 1
                        out["insider_net_shares"] -= sh
        except Exception:
            pass
    except Exception:
        pass
    return out


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def get_dividend_growth(ticker):
    """Dividend growth streak (consecutive up years) from Yahoo dividend history (free)."""
    out = {"streak": 0, "years": 0, "last_annual": None, "cut": False}
    try:
        divs = yf.Ticker(ticker).dividends
        if divs is None or len(divs) == 0:
            return out
        ann = divs.groupby(divs.index.year).sum()
        # Drop the current calendar year — it's only partially paid, so its sum would look
        # like a "cut" vs the prior full year and wreck the streak/cut logic.
        this_year = datetime.now().year
        ann = ann[ann.index < this_year]
        vals = [float(v) for v in ann.values]
        out["years"] = len(vals)
        out["last_annual"] = round(vals[-1], 2) if vals else None
        streak = 0
        for i in range(len(vals) - 1, 0, -1):
            if vals[i] > vals[i - 1] * 1.001:
                streak += 1
            else:
                break
        out["streak"] = streak
        # Only flag a cut in the last ~10 full years — older yfinance data has split/coverage
        # artifacts that create false "cuts" for decades-long payers.
        recent = vals[-11:]
        out["cut"] = any(recent[i] < recent[i - 1] * 0.9 for i in range(1, len(recent)))
    except Exception:
        pass
    return out


def dividend_safety(row, growth):
    """Standard dividend-safety read: can the company comfortably keep paying?
    Blends payout coverage, cash-flow support, balance-sheet strength, and growth history.
    Returns None for non-payers. (Standard public methodology — not any firm's proprietary model.)"""
    yld = safe_float(row.get("Dividend Yield %"), 0)
    if not yld or yld <= 0:
        return None
    payout = safe_float(row.get("Payout Ratio %"))
    ndte = safe_float(row.get("Net Debt/EBITDA"))
    cf_score = safe_float(row.get("Cash Flow Score"), 50)

    # Payout coverage (lower payout = safer). Negative/над-100% payout is a red flag.
    if payout is None:
        payout_pts = 50
    elif payout < 0:
        payout_pts = 5
    else:
        payout_pts = clamp(105 - payout)          # 40%→65, 60%→45, 80%→25, 100%→5
    # Balance sheet (lower net debt/EBITDA = safer)
    debt_pts = clamp(100 - (ndte * 20)) if ndte is not None else 50   # 0→100, 2.5→50, 5→0
    # Cash-flow support
    cf_pts = clamp(cf_score)
    # Growth history
    streak = growth.get("streak", 0)
    growth_pts = clamp(45 + streak * 9)
    if growth.get("cut"):
        growth_pts = min(growth_pts, 30)          # a past cut is a serious mark

    score = round(payout_pts * 0.35 + cf_pts * 0.30 + debt_pts * 0.20 + growth_pts * 0.15, 0)
    if score >= 75:
        verdict = "🟢 Very Safe"
    elif score >= 60:
        verdict = "🟢 Safe"
    elif score >= 45:
        verdict = "🟡 Moderate"
    else:
        verdict = "🔴 At Risk"
    return {"score": score, "verdict": verdict, "yield": yld, "payout": payout,
            "ndte": ndte, "cf_score": cf_score, "streak": streak, "cut": growth.get("cut"),
            "components": {"Payout coverage": round(payout_pts), "Cash-flow support": round(cf_pts),
                           "Balance sheet": round(debt_pts), "Growth history": round(growth_pts)}}


def fetch_fmp_fundamentals(ticker):
    """Build a yfinance-style `info` dict from FMP (SEC-sourced ratios). Raises
    DataUnavailable if FMP has no profile for the ticker. Prices/news still come from
    Yahoo; FMP is used only for the fundamentals it does better."""
    profile = _fmp_get(f"profile?symbol={ticker}")
    if not profile or not profile.get("price"):
        raise DataUnavailable(f"FMP has no data for '{ticker}' (delisted/renamed/invalid).")
    ratios = _fmp_get(f"ratios-ttm?symbol={ticker}") or {}
    km = _fmp_get(f"key-metrics-ttm?symbol={ticker}") or {}
    growth = _fmp_get(f"financial-growth?symbol={ticker}&period=annual&limit=1") or {}

    price = safe_float(profile.get("price"))
    mktcap = safe_float(profile.get("marketCap"))
    shares = (mktcap / price) if (mktcap and price) else None

    def per_share_to_total(field):
        v = safe_float(ratios.get(field))
        return (v * shares) if (v is not None and shares) else None

    total_revenue = per_share_to_total("revenuePerShareTTM")
    ebitda_margin = safe_float(ratios.get("ebitdaMarginTTM"))
    dte = safe_float(ratios.get("debtToEquityRatioTTM"))

    info = {
        "shortName": profile.get("companyName") or ticker,
        "sector": profile.get("sector") or "Unknown",
        "industry": profile.get("industry") or "Unknown",
        "currentPrice": price,
        "regularMarketPrice": price,
        "marketCap": mktcap,
        "enterpriseValue": safe_float(ratios.get("enterpriseValueTTM")) or safe_float(km.get("enterpriseValueTTM")),
        "trailingPE": safe_float(ratios.get("priceToEarningsRatioTTM")),
        "forwardPE": None,  # not on FMP free; scoring degrades gracefully
        "trailingPegRatio": safe_float(ratios.get("priceToEarningsGrowthRatioTTM")),
        "priceToSalesTrailing12Months": safe_float(ratios.get("priceToSalesRatioTTM")),
        "enterpriseToEbitda": safe_float(ratios.get("enterpriseValueMultipleTTM")) or safe_float(km.get("evToEBITDATTM")),
        "priceToBook": safe_float(ratios.get("priceToBookRatioTTM")),
        "profitMargins": safe_float(ratios.get("netProfitMarginTTM")),
        "operatingMargins": safe_float(ratios.get("operatingProfitMarginTTM")),
        "grossMargins": safe_float(ratios.get("grossProfitMarginTTM")),
        "ebitdaMargins": ebitda_margin,
        "returnOnEquity": safe_float(km.get("returnOnEquityTTM")),
        "returnOnAssets": safe_float(km.get("returnOnAssetsTTM")),
        "beta": safe_float(profile.get("beta")),
        # FMP gives a plain ratio (0.14); yfinance-based scoring expects a percent (14).
        "debtToEquity": (dte * 100) if dte is not None else None,
        "currentRatio": safe_float(ratios.get("currentRatioTTM")),
        "quickRatio": safe_float(ratios.get("quickRatioTTM")),
        "dividendYield": safe_float(ratios.get("dividendYieldTTM")),
        "payoutRatio": safe_float(ratios.get("dividendPayoutRatioTTM")),
        "totalRevenue": total_revenue,
        "freeCashflow": per_share_to_total("freeCashFlowPerShareTTM"),
        "operatingCashflow": per_share_to_total("operatingCashFlowPerShareTTM"),
        "totalCash": per_share_to_total("cashPerShareTTM"),
        "totalDebt": per_share_to_total("interestDebtPerShareTTM"),
        "ebitda": (ebitda_margin * total_revenue) if (ebitda_margin is not None and total_revenue) else None,
        "revenueGrowth": safe_float(growth.get("revenueGrowth")),
        "earningsGrowth": safe_float(growth.get("netIncomeGrowth")),
        # Authoritative values we prefer over our derived proxies (avoids synthesis error):
        "_source": "FMP (SEC filings)",
        "_fmp_roic": safe_float(km.get("returnOnInvestedCapitalTTM")),
        "_fmp_fcf_yield": safe_float(km.get("freeCashFlowYieldTTM")),
        "_fmp_ev_to_fcf": safe_float(km.get("evToFreeCashFlowTTM")),
        "_fmp_net_debt_to_ebitda": safe_float(km.get("netDebtToEBITDATTM")),
        "_fmp_ocf_margin": safe_float(ratios.get("operatingCashFlowSalesRatioTTM")),
        "_fmp_fcf_conversion": safe_float(ratios.get("freeCashFlowOperatingCashFlowRatioTTM")),
        "_fmp_fcf_margin": (
            safe_float(ratios.get("freeCashFlowPerShareTTM")) / safe_float(ratios.get("revenuePerShareTTM"))
            if safe_float(ratios.get("revenuePerShareTTM")) else None
        ),
    }
    return info


def fetch_ticker_bundle(ticker):
    """Fetch (info, history) for a ticker, honestly failing on dead tickers.

    Uses FMP for fundamentals when a key is configured (SEC-sourced, more accurate),
    otherwise Yahoo. Price history always comes from Yahoo (its reliable, free part).
    If neither price nor fundamentals can be had, raises DataUnavailable so the caller
    SKIPS the ticker instead of inventing neutral 50-scores."""
    if fmp_available():
        try:
            info = fetch_fmp_fundamentals(ticker)   # raises DataUnavailable if not found
            # If FMP is rate-limited mid-request (free tier = 250 calls/day), the profile
            # can arrive but ratios/metrics come back empty. Rather than score on a sparse
            # record, fall through to Yahoo so we still produce an honest number.
            core = [info.get("trailingPE"), info.get("returnOnEquity"),
                    info.get("profitMargins"), info.get("debtToEquity")]
            if any(v is not None for v in core):
                return info, _yf_history(ticker)
        except DataUnavailable:
            pass  # FMP has nothing usable — try Yahoo before giving up

    # ---- Yahoo path (fallback, or when no FMP key) ----
    last_err = None
    info, hist = {}, pd.DataFrame()
    for attempt in range(3):
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2y")
            try:
                info = stock.info or {}
            except Exception as e:
                info, last_err = {}, e
            info["_source"] = "Yahoo Finance"
            has_price = bool(info.get("currentPrice") or info.get("regularMarketPrice"))
            has_hist = hist is not None and not hist.empty
            has_fundamentals = bool(info.get("marketCap") or info.get("totalRevenue"))
            if has_price or has_hist or has_fundamentals:
                return info, hist
        except Exception as e:
            last_err = e
        time.sleep(1.2 * (attempt + 1))
    raise DataUnavailable(
        f"No usable market data for '{ticker}' (likely delisted, renamed, or invalid)."
    )


# Fields that must be present for a score to be trustworthy. We track how many of these
# Yahoo actually returned so we can show a data-coverage % and flag low-confidence scores.
COVERAGE_FIELDS = [
    "trailingPE", "forwardPE", "priceToSalesTrailing12Months", "enterpriseToEbitda",
    "profitMargins", "operatingMargins", "grossMargins", "returnOnEquity",
    "revenueGrowth", "earningsGrowth", "debtToEquity", "currentRatio",
    "freeCashflow", "totalRevenue", "marketCap", "beta",
]


@st.cache_data(ttl=3600, show_spinner=False)
def get_quant_score(ticker):
    info, hist = fetch_ticker_bundle(ticker)
    spy_hist = get_spy_history()

    name = info.get("shortName", ticker)
    sector = info.get("sector", "Unknown")
    industry = info.get("industry", "Unknown")

    price = safe_float(info.get("currentPrice"))
    if price is None and len(hist) > 0:
        price = safe_float(hist["Close"].iloc[-1])

    market_cap = safe_float(info.get("marketCap"))
    enterprise_value = safe_float(info.get("enterpriseValue"))
    total_revenue = safe_float(info.get("totalRevenue"))
    ebitda = safe_float(info.get("ebitda"))
    total_cash = safe_float(info.get("totalCash"))
    total_debt = safe_float(info.get("totalDebt"))
    operating_cashflow = safe_float(info.get("operatingCashflow"))
    free_cashflow = safe_float(info.get("freeCashflow"))

    # Data coverage: how many key inputs Yahoo actually returned (0-1). Low coverage
    # means the score leans heavily on neutral fallbacks and should be trusted less.
    data_coverage = sum(1 for f in COVERAGE_FIELDS if safe_float(info.get(f)) is not None) / len(COVERAGE_FIELDS)

    pe = safe_float(info.get("trailingPE"))
    forward_pe = safe_float(info.get("forwardPE"))
    # Yahoo renamed the PEG field to "trailingPegRatio"; keep the old key as a fallback.
    peg = safe_float(info.get("trailingPegRatio")) or safe_float(info.get("pegRatio"))
    ps = safe_float(info.get("priceToSalesTrailing12Months"))
    ev_ebitda = safe_float(info.get("enterpriseToEbitda"))
    price_to_book = safe_float(info.get("priceToBook"))

    profit_margin = safe_float(info.get("profitMargins"))
    operating_margin = safe_float(info.get("operatingMargins"))
    gross_margin = safe_float(info.get("grossMargins"))
    ebitda_margin = safe_float(info.get("ebitdaMargins"))
    roe = safe_float(info.get("returnOnEquity"))
    roa = safe_float(info.get("returnOnAssets"))
    revenue_growth = safe_float(info.get("revenueGrowth"))
    earnings_growth = safe_float(info.get("earningsGrowth"))
    beta = safe_float(info.get("beta"))
    debt_to_equity = safe_float(info.get("debtToEquity"))
    current_ratio = safe_float(info.get("currentRatio"))
    quick_ratio = safe_float(info.get("quickRatio"))
    dividend_yield = safe_float(info.get("dividendYield"))
    payout_ratio = safe_float(info.get("payoutRatio"))

    fcf_yield = (free_cashflow / market_cap) if free_cashflow and market_cap else None
    earnings_yield = (1 / pe) if pe and pe > 0 else None
    ev_to_fcf = (enterprise_value / free_cashflow) if enterprise_value and free_cashflow and free_cashflow > 0 else None
    fcf_margin = (free_cashflow / total_revenue) if free_cashflow and total_revenue else None
    ocf_margin = (operating_cashflow / total_revenue) if operating_cashflow and total_revenue else None
    fcf_conversion = (free_cashflow / operating_cashflow) if free_cashflow and operating_cashflow and operating_cashflow > 0 else None
    cash_to_debt = (total_cash / total_debt) if total_cash and total_debt and total_debt > 0 else None
    net_debt = (total_debt - total_cash) if total_debt is not None and total_cash is not None else None
    net_debt_to_ebitda = (net_debt / ebitda) if net_debt is not None and ebitda and ebitda > 0 else None

    invested_capital_proxy = None
    if market_cap is not None and total_debt is not None and total_cash is not None:
        invested_capital_proxy = market_cap + total_debt - total_cash
    roic_proxy = None
    if operating_margin is not None and invested_capital_proxy and invested_capital_proxy > 0 and total_revenue:
        estimated_operating_income = total_revenue * operating_margin
        roic_proxy = estimated_operating_income / invested_capital_proxy

    # When FMP provides authoritative figures, prefer them over our derived proxies.
    # (These come straight from filings, so they avoid the per-share x shares synthesis
    # error — e.g. net-debt/EBITDA was flipping sign because per-share debt undercounts
    # leases/other debt. Using the direct value fixes the Financial Strength score.)
    if info.get("_fmp_roic") is not None:
        roic_proxy = safe_float(info.get("_fmp_roic"))
    if info.get("_fmp_fcf_yield") is not None:
        fcf_yield = safe_float(info.get("_fmp_fcf_yield"))
    if info.get("_fmp_ev_to_fcf") is not None:
        ev_to_fcf = safe_float(info.get("_fmp_ev_to_fcf"))
    if info.get("_fmp_net_debt_to_ebitda") is not None:
        net_debt_to_ebitda = safe_float(info.get("_fmp_net_debt_to_ebitda"))
    if info.get("_fmp_ocf_margin") is not None:
        ocf_margin = safe_float(info.get("_fmp_ocf_margin"))
    if info.get("_fmp_fcf_conversion") is not None:
        fcf_conversion = safe_float(info.get("_fmp_fcf_conversion"))
    if info.get("_fmp_fcf_margin") is not None:
        fcf_margin = safe_float(info.get("_fmp_fcf_margin"))

    if len(hist) > 252:
        current_price = safe_float(hist["Close"].iloc[-1], price)
        high_52 = safe_float(hist["Close"].tail(252).max())
        low_52 = safe_float(hist["Close"].tail(252).min())
        return_1m = current_price / safe_float(hist["Close"].iloc[-21], current_price) - 1 if len(hist) > 21 else 0
        return_3m = current_price / safe_float(hist["Close"].iloc[-63], current_price) - 1 if len(hist) > 63 else 0
        return_6m = current_price / safe_float(hist["Close"].iloc[-126], current_price) - 1 if len(hist) > 126 else 0
        return_12m = current_price / safe_float(hist["Close"].iloc[-252], current_price) - 1 if len(hist) > 252 else 0
        price_position = (current_price - low_52) / (high_52 - low_52) if high_52 and low_52 and high_52 != low_52 else 0.5
        rolling_high = hist["Close"].cummax()
        drawdowns = hist["Close"] / rolling_high - 1
        max_drawdown = safe_float(drawdowns.min(), -0.25)
        daily_returns = hist["Close"].pct_change().dropna()
        volatility = safe_float(daily_returns.std() * math.sqrt(252), 0.30)
        relative_strength_6m = 0
        relative_strength_12m = 0
        if len(spy_hist) > 252:
            spy_current = safe_float(spy_hist["Close"].iloc[-1])
            spy_6m = spy_current / safe_float(spy_hist["Close"].iloc[-126], spy_current) - 1
            spy_12m = spy_current / safe_float(spy_hist["Close"].iloc[-252], spy_current) - 1
            relative_strength_6m = return_6m - spy_6m
            relative_strength_12m = return_12m - spy_12m
        volume_today = safe_float(hist["Volume"].iloc[-1], 0)
        avg_volume = safe_float(hist["Volume"].tail(30).mean(), 0)
        volume_ratio = volume_today / avg_volume if avg_volume else 1
    else:
        current_price = price
        return_1m = return_3m = return_6m = return_12m = 0
        price_position = 0.5
        max_drawdown = -0.25
        volatility = 0.30
        relative_strength_6m = 0
        relative_strength_12m = 0
        volume_ratio = 1
        high_52 = low_52 = None

    quality_score = (
        safe_score(roic_proxy, 0.02, 0.18) * 0.28 +
        safe_score(roe, 0.05, 0.30) * 0.22 +
        safe_score(gross_margin, 0.20, 0.70) * 0.15 +
        safe_score(operating_margin, 0.05, 0.35) * 0.18 +
        safe_score(profit_margin, 0.03, 0.25) * 0.17
    )

    cash_flow_score = (
        safe_score(fcf_yield, 0.00, 0.08) * 0.30 +
        safe_score(fcf_margin, 0.00, 0.25) * 0.25 +
        safe_score(ocf_margin, 0.00, 0.30) * 0.20 +
        safe_score(fcf_conversion, 0.30, 1.00) * 0.15 +
        safe_score(ev_to_fcf, 8, 40, reverse=True) * 0.10
    )

    valuation_score = (
        safe_score(forward_pe, 8, 40, reverse=True) * 0.22 +
        safe_score(pe, 8, 45, reverse=True) * 0.18 +
        safe_score(peg, 0.5, 3.0, reverse=True) * 0.20 +
        safe_score(ev_ebitda, 6, 30, reverse=True) * 0.15 +
        safe_score(ev_to_fcf, 8, 40, reverse=True) * 0.15 +
        safe_score(fcf_yield, 0.00, 0.08) * 0.10
    )

    growth_score = (
        safe_score(revenue_growth, -0.03, 0.25) * 0.35 +
        safe_score(earnings_growth, -0.05, 0.30) * 0.35 +
        safe_score(return_12m, -0.25, 0.50) * 0.10 +
        safe_score(operating_margin, 0.03, 0.30) * 0.10 +
        safe_score(fcf_margin, 0.00, 0.25) * 0.10
    )

    financial_strength_score = (
        safe_score(debt_to_equity, 20, 220, reverse=True) * 0.25 +
        safe_score(net_debt_to_ebitda, 0, 5, reverse=True) * 0.25 +
        safe_score(cash_to_debt, 0.10, 1.50) * 0.20 +
        safe_score(current_ratio, 0.80, 2.50) * 0.15 +
        safe_score(quick_ratio, 0.60, 1.80) * 0.15
    )

    momentum_score = (
        safe_score(return_1m, -0.10, 0.15) * 0.20 +
        safe_score(return_3m, -0.15, 0.25) * 0.25 +
        safe_score(return_6m, -0.20, 0.35) * 0.25 +
        safe_score(return_12m, -0.30, 0.55) * 0.20 +
        safe_score(volume_ratio, 0.70, 1.80) * 0.10
    )

    relative_strength_score = (
        safe_score(relative_strength_6m, -0.15, 0.20) * 0.55 +
        safe_score(relative_strength_12m, -0.20, 0.30) * 0.45
    )

    risk_score = (
        safe_score(beta, 0.70, 2.00, reverse=True) * 0.30 +
        safe_score(volatility, 0.15, 0.60, reverse=True) * 0.25 +
        safe_score(abs(max_drawdown), 0.10, 0.55, reverse=True) * 0.25 +
        safe_score(debt_to_equity, 20, 220, reverse=True) * 0.20
    )

    earnings_quality_score = (
        safe_score(earnings_growth, -0.05, 0.30) * 0.25 +
        safe_score(fcf_conversion, 0.30, 1.00) * 0.25 +
        safe_score(profit_margin, 0.03, 0.25) * 0.20 +
        safe_score(operating_margin, 0.05, 0.35) * 0.20 +
        safe_score(revenue_growth, -0.03, 0.25) * 0.10
    )

    # Fair value from a capped, median-based blend of P/E, EV/FCF, DCF, PEG and 52-week
    # methods (see estimate_fair_value). fcf_per_share = fcf_yield * price.
    fcf_per_share = (fcf_yield * price) if (fcf_yield is not None and price) else None
    fv = estimate_fair_value(
        price, pe, fcf_per_share, ev_to_fcf, peg,
        quality_score, growth_score, cash_flow_score, risk_score,
        revenue_growth, high_52, low_52,
        beta=beta, dividend_yield=dividend_yield, roe=roe, payout=payout_ratio,
        sector=sector, price_to_book=price_to_book,
        market_cap=market_cap, total_debt=total_debt, total_cash=total_cash,
        net_debt_to_ebitda=net_debt_to_ebitda,
    )
    fair_value = fv["central"] if fv["central"] else price
    fair_value_low = fv["low"]
    fair_value_high = fv["high"]
    fair_value_methods = " | ".join(f"{n}: {money(v)}" for n, v in fv["methods"]) if fv["methods"] else "None"
    margin_of_safety = ((fair_value - price) / fair_value) if fair_value and price else None
    upside_to_fair_value = ((fair_value - price) / price) if fair_value and price else None

    if upside_to_fair_value is not None and price:
        sell_target = price * (1 + min(max(upside_to_fair_value * 0.75, 0.06), 0.28))
    else:
        sell_target = None

    news = get_ticker_news(ticker, 48)
    if news:
        bullish = sum(1 for n in news if n["Signal"] == "Bullish")
        bearish = sum(1 for n in news if n["Signal"] == "Bearish")
        importance = sum(n["Importance"] for n in news[:5]) / max(len(news[:5]), 1)
        news_sentiment_score = clamp(50 + (bullish - bearish) * 8 + (importance - 5) * 3)
    else:
        news_sentiment_score = 50

    health_score = (
        quality_score * 0.35 +
        cash_flow_score * 0.25 +
        financial_strength_score * 0.20 +
        earnings_quality_score * 0.20
    )

    investment_score = (
        quality_score * 0.28 +
        cash_flow_score * 0.22 +
        growth_score * 0.18 +
        financial_strength_score * 0.17 +
        earnings_quality_score * 0.10 +
        risk_score * 0.05
    )

    opportunity_score = (
        valuation_score * 0.30 +
        cash_flow_score * 0.20 +
        quality_score * 0.18 +
        growth_score * 0.12 +
        financial_strength_score * 0.10 +
        safe_score(upside_to_fair_value, -0.10, 0.35) * 0.10
    )

    position_trade_score = (
        momentum_score * 0.30 +
        relative_strength_score * 0.25 +
        earnings_quality_score * 0.15 +
        news_sentiment_score * 0.15 +
        risk_score * 0.15
    )

    expected_return_score = (
        opportunity_score * 0.35 +
        investment_score * 0.25 +
        position_trade_score * 0.20 +
        health_score * 0.15 +
        risk_score * 0.05
    )

    overall_quant_score = (
        investment_score * 0.30 +
        opportunity_score * 0.25 +
        position_trade_score * 0.20 +
        health_score * 0.15 +
        expected_return_score * 0.10
    )

    if overall_quant_score >= 85 and opportunity_score >= 70:
        research_action = "Research Now"
    elif investment_score >= 85 and valuation_score < 55:
        research_action = "Great Business — Watch for Pullback"
    elif opportunity_score >= 80 and momentum_score < 50:
        research_action = "Undervalued — Wait for Confirmation"
    elif position_trade_score >= 80:
        research_action = "Position Trade Candidate"
    elif risk_score < 40 or financial_strength_score < 40:
        research_action = "High Risk — Needs Confirmation"
    elif overall_quant_score < 55:
        research_action = "Avoid for Now"
    else:
        research_action = "Watchlist / Research Later"

    if position_trade_score >= 80:
        hold_period = "3-6 months"
    elif investment_score >= 85:
        hold_period = "1-5 years / long-term watch"
    elif opportunity_score >= 80:
        hold_period = "6-18 months / value thesis"
    else:
        hold_period = "Research only"

    alerts = []
    if investment_score >= 85:
        alerts.append("Long-term investment quality is strong.")
    if opportunity_score >= 80:
        alerts.append("Potential undervaluation detected.")
    if position_trade_score >= 80:
        alerts.append("3-6 month position-trade setup detected.")
    if health_score >= 85:
        alerts.append("Stock health is strong.")
    if fcf_yield and fcf_yield >= 0.06:
        alerts.append("Strong free cash flow yield.")
    if roic_proxy and roic_proxy >= 0.12:
        alerts.append("Strong ROIC proxy.")
    if relative_strength_score >= 75:
        alerts.append("Outperforming SPY on relative strength.")
    if valuation_score < 35:
        alerts.append("Valuation risk: stock may be expensive.")
    if financial_strength_score < 40:
        alerts.append("Financial risk: balance sheet metrics look weak.")
    if risk_score < 40:
        alerts.append("Risk warning: volatility/drawdown risk is elevated.")
    if news_sentiment_score < 40:
        alerts.append("Recent news sentiment is negative.")
    if data_coverage < 0.5:
        alerts.append(f"Low-confidence score: only {round(data_coverage * 100)}% of key data was available.")

    row_for_labels = {
        "Investment Score": investment_score,
        "Opportunity Score": opportunity_score,
        "Position Trade Score": position_trade_score,
        "Health Score": health_score,
        "Expected Return Score": expected_return_score,
        "Valuation Score": valuation_score,
        "Momentum Score": momentum_score,
        "Quality Score": quality_score,
        "Cash Flow Score": cash_flow_score,
        "Growth Score": growth_score,
        "Financial Strength Score": financial_strength_score,
        "Relative Strength Score": relative_strength_score,
        "Risk Score": risk_score,
        "News Sentiment Score": news_sentiment_score,
        "FCF Yield %": pct(fcf_yield),
        "ROIC Proxy %": pct(roic_proxy),
        "Upside %": round(upside_to_fair_value * 100, 1) if upside_to_fair_value is not None else None,
    }

    evidence_score = calculate_evidence_score(row_for_labels)
    row_for_labels["Evidence Score"] = evidence_score
    conviction_score = calculate_conviction_score(row_for_labels)
    row_for_labels["Conviction Score"] = conviction_score
    labels = build_labels(row_for_labels)

    biggest_risk = detect_biggest_risk(row_for_labels)
    why_ranked_high = generate_rank_reasons(row_for_labels)
    main_concerns = generate_concerns(row_for_labels)
    research_time = estimate_research_time({**row_for_labels, "Labels": labels, "Research Action": research_action})

    research_priority = round(
        conviction_score * 0.35 +
        evidence_score * 0.25 +
        expected_return_score * 0.15 +
        opportunity_score * 0.15 +
        investment_score * 0.10,
        1
    )

    if overall_quant_score >= 85:
        verdict = "Strong Quant Research Candidate"
    elif overall_quant_score >= 75:
        verdict = "Worth Researching"
    elif overall_quant_score >= 60:
        verdict = "Watchlist Only"
    else:
        verdict = "Low Priority / Avoid"

    return {
        "Ticker": ticker,
        "Company": name,
        "Sector": sector,
        "Industry": industry,
        "Price": round(price, 2) if price else None,
        "Fair Value": round(fair_value, 2) if fair_value else None,
        "Fair Value Low": round(fair_value_low, 2) if fair_value_low else None,
        "Fair Value High": round(fair_value_high, 2) if fair_value_high else None,
        "Valuation Methods": fair_value_methods,
        "Upside %": round(upside_to_fair_value * 100, 1) if upside_to_fair_value is not None else None,
        "Margin of Safety %": round(margin_of_safety * 100, 1) if margin_of_safety is not None else None,
        "Sell Target": round(sell_target, 2) if sell_target else None,
        "Suggested Hold": hold_period,
        "Overall Quant Score": round(overall_quant_score, 1),
        "Overall Grade": grade(overall_quant_score),
        "Tier": tier(overall_quant_score),
        "Investment Score": round(investment_score, 1),
        "Opportunity Score": round(opportunity_score, 1),
        "Position Trade Score": round(position_trade_score, 1),
        "Health Score": round(health_score, 1),
        "Expected Return Score": round(expected_return_score, 1),
        "Conviction Score": round(conviction_score, 1),
        "Evidence Score": round(evidence_score, 1),
        "Research Priority": research_priority,
        "Quality Score": round(quality_score, 1),
        "Cash Flow Score": round(cash_flow_score, 1),
        "Valuation Score": round(valuation_score, 1),
        "Growth Score": round(growth_score, 1),
        "Financial Strength Score": round(financial_strength_score, 1),
        "Momentum Score": round(momentum_score, 1),
        "Relative Strength Score": round(relative_strength_score, 1),
        "Risk Score": round(risk_score, 1),
        "Earnings Quality Score": round(earnings_quality_score, 1),
        "News Sentiment Score": round(news_sentiment_score, 1),
        "P/E": pe,
        "Forward P/E": forward_pe,
        "PEG": peg,
        "P/S": ps,
        "EV/EBITDA": ev_ebitda,
        "EV/FCF": round(ev_to_fcf, 2) if ev_to_fcf else None,
        "FCF Yield %": pct(fcf_yield),
        "Earnings Yield %": pct(earnings_yield),
        "Profit Margin %": pct(profit_margin),
        "Gross Margin %": pct(gross_margin),
        "Operating Margin %": pct(operating_margin),
        "EBITDA Margin %": pct(ebitda_margin),
        "FCF Margin %": pct(fcf_margin),
        "OCF Margin %": pct(ocf_margin),
        "FCF Conversion %": pct(fcf_conversion),
        "ROE %": pct(roe),
        "ROA %": pct(roa),
        "ROIC Proxy %": pct(roic_proxy),
        "Revenue Growth %": pct(revenue_growth),
        "Earnings Growth %": pct(earnings_growth),
        "Debt/Equity": debt_to_equity,
        "Current Ratio": current_ratio,
        "Quick Ratio": quick_ratio,
        "Cash/Debt": round(cash_to_debt, 2) if cash_to_debt else None,
        "Net Debt/EBITDA": round(net_debt_to_ebitda, 2) if net_debt_to_ebitda else None,
        "Beta": beta,
        "Volatility %": round(volatility * 100, 1),
        "Max Drawdown %": round(max_drawdown * 100, 1),
        "Dividend Yield %": pct(dividend_yield),
        "Payout Ratio %": pct(payout_ratio),
        "1M Return %": round(return_1m * 100, 1),
        "3M Return %": round(return_3m * 100, 1),
        "6M Return %": round(return_6m * 100, 1),
        "12M Return %": round(return_12m * 100, 1),
        "Relative Strength 6M %": round(relative_strength_6m * 100, 1) if relative_strength_6m is not None else None,
        "Relative Strength 12M %": round(relative_strength_12m * 100, 1) if relative_strength_12m is not None else None,
        "Volume Ratio": round(volume_ratio, 2),
        "52W Position": round(price_position, 2),
        "Labels": labels,
        "Verdict": verdict,
        "Research Action": research_action,
        "Biggest Risk": biggest_risk,
        "Why Ranked High": why_ranked_high,
        "Main Concerns": main_concerns,
        "Research Time": research_time,
        "Alerts": " | ".join(alerts) if alerts else "No major signal",
        "Data Coverage %": round(data_coverage * 100),
        "Data Source": info.get("_source", "Yahoo Finance"),
        "Scan Date": today_string(),
        "Last Updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def score_many(tickers):
    """Score a list of tickers, skipping (not fabricating) any with no reliable data.
    Returns (scored_dataframe, failures_list) so the caller can report what was skipped."""
    rows = []
    failures = []
    progress = st.progress(0)
    for i, ticker in enumerate(tickers):
        try:
            rows.append(get_quant_score(ticker))
        except DataUnavailable:
            failures.append({"Ticker": ticker, "Reason": "No reliable data — skipped (likely delisted/renamed/invalid)"})
        except Exception as e:
            failures.append({"Ticker": ticker, "Reason": str(e)[:140]})
        progress.progress((i + 1) / max(len(tickers), 1))
    progress.empty()
    return pd.DataFrame(rows), failures


@st.cache_data(ttl=86400)
def get_sp500_table():
    """Full S&P 500 list with GICS sector (free, from Wikipedia). Returns a DataFrame with
    Symbol + Sector. Wikipedia 403s requests without a browser User-Agent, so we fetch the
    HTML ourselves with one set before parsing — otherwise the whole universe silently
    collapses to the small fallback list."""
    import io
    try:
        req = urllib.request.Request(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        with urllib.request.urlopen(req, timeout=25) as r:
            html = r.read().decode("utf-8", errors="ignore")
        tables = pd.read_html(io.StringIO(html))
        df = tables[0].rename(columns={"GICS Sector": "Sector"})
        df["Symbol"] = df["Symbol"].astype(str).str.replace(".", "-", regex=False)
        out = df[["Symbol", "Sector"]].dropna()
        if len(out) >= 100:      # sanity: a real S&P 500 pull has ~500 rows
            return out
    except Exception:
        pass
    fallback = QUALITY_COMPOUNDERS + RECOVERY_WATCHLIST
    return pd.DataFrame({"Symbol": fallback, "Sector": ["Unknown"] * len(fallback)})


def get_sp500_tickers():
    return get_sp500_table()["Symbol"].tolist()


def sp500_sectors():
    return sorted(get_sp500_table()["Sector"].dropna().unique().tolist())


def tickers_for_sectors(sectors):
    """Symbols in the chosen GICS sectors (all if none/empty selected)."""
    table = get_sp500_table()
    if not sectors:
        return table["Symbol"].tolist()
    return table[table["Sector"].isin(sectors)]["Symbol"].tolist()


def save_sp500_scores(df, merge=True):
    df = enhance_research_columns(df)
    # Merge into the existing cache by ticker (new scores replace old for the same names,
    # everything else is kept) so scanning one sector at a time ACCUMULATES coverage
    # instead of wiping the rest.
    if merge and SP500_CACHE.exists():
        try:
            old = pd.read_csv(SP500_CACHE)
            keep = old[~old["Ticker"].astype(str).isin(df["Ticker"].astype(str))]
            combined = pd.concat([keep, df], ignore_index=True)
        except Exception:
            combined = df
    else:
        combined = df
    combined.to_csv(SP500_CACHE, index=False)
    history_cols = [
        "Scan Date", "Ticker", "Company", "Sector", "Overall Quant Score", "Investment Score",
        "Opportunity Score", "Position Trade Score", "Health Score", "Expected Return Score", "Conviction Score", "Evidence Score", "Research Priority",
        "Price", "Fair Value", "Upside %", "Tier", "Labels"
    ]
    history_df = df[[c for c in history_cols if c in df.columns]].copy()
    if SP500_HISTORY.exists():
        old = pd.read_csv(SP500_HISTORY)
        combined = pd.concat([old, history_df], ignore_index=True)
        combined = combined.drop_duplicates(subset=["Scan Date", "Ticker"], keep="last")
    else:
        combined = history_df
    combined.to_csv(SP500_HISTORY, index=False)


def load_sp500_scores():
    if SP500_CACHE.exists():
        return enhance_research_columns(pd.read_csv(SP500_CACHE))
    return pd.DataFrame()


def load_history():
    if SP500_HISTORY.exists():
        return enhance_research_columns(pd.read_csv(SP500_HISTORY))
    return pd.DataFrame()


def cache_age_text():
    if not SP500_CACHE.exists():
        return "No saved quant scan yet."
    modified = datetime.fromtimestamp(SP500_CACHE.stat().st_mtime)
    return f"Last quant scan saved: {modified.strftime('%Y-%m-%d %I:%M %p')}"


def add_score_change(df):
    history = load_history()
    if df.empty or history.empty or "Ticker" not in history.columns:
        df["Score Change"] = 0.0
        return df
    latest_date = history["Scan Date"].max()
    old_dates = sorted([d for d in history["Scan Date"].dropna().unique() if d != latest_date])
    if not old_dates:
        df["Score Change"] = 0.0
        return df
    previous_date = old_dates[-1]
    previous_cols = ["Ticker", "Overall Quant Score"]
    if "Conviction Score" in history.columns:
        previous_cols.append("Conviction Score")
    previous = history[history["Scan Date"] == previous_date][previous_cols].rename(columns={
        "Overall Quant Score": "Previous Overall",
        "Conviction Score": "Previous Conviction"
    })
    merged = df.merge(previous, on="Ticker", how="left")
    merged["Score Change"] = merged["Overall Quant Score"] - merged["Previous Overall"].fillna(merged["Overall Quant Score"])
    if "Previous Conviction" in merged.columns:
        merged["Conviction Change"] = merged["Conviction Score"] - merged["Previous Conviction"].fillna(merged["Conviction Score"])
    else:
        merged["Conviction Change"] = 0.0
    return merged


def explain_price_move(ticker):
    stock = yf.Ticker(ticker)
    hist = stock.history(period="1mo")
    score = get_quant_score(ticker)
    news = get_ticker_news(ticker, 48)
    if len(hist) < 2:
        return None, score, news
    current = safe_float(hist["Close"].iloc[-1])
    previous = safe_float(hist["Close"].iloc[-2])
    one_day = ((current - previous) / previous) * 100 if previous else 0
    five_day = 0
    if len(hist) >= 6:
        five_day = ((current - safe_float(hist["Close"].iloc[-6])) / safe_float(hist["Close"].iloc[-6])) * 100
    volume_today = safe_float(hist["Volume"].iloc[-1], 0)
    avg_volume = safe_float(hist["Volume"].tail(20).mean(), 0)
    volume_ratio = volume_today / avg_volume if avg_volume else 1
    news_text = " ".join([f"{n['Title']} {n['Summary']}" for n in news]).lower()
    reasons = []
    if "earnings" in news_text or "revenue" in news_text or "guidance" in news_text:
        reasons.append("Earnings, revenue, or guidance news may be influencing the stock.")
    if "upgrade" in news_text or "price target" in news_text or "analyst" in news_text:
        reasons.append("Analyst rating or price-target news may be contributing.")
    if "downgrade" in news_text or "cuts" in news_text:
        reasons.append("Negative analyst commentary or estimate cuts may be pressuring the stock.")
    if "ai" in news_text or "chip" in news_text or "semiconductor" in news_text:
        reasons.append("AI, chip, or technology-sector news may be affecting sentiment.")
    if "lawsuit" in news_text or "sec" in news_text or "doj" in news_text or "regulation" in news_text:
        reasons.append("Legal or regulatory news may be affecting risk perception.")
    if "fed" in news_text or "inflation" in news_text or "rates" in news_text or "treasury" in news_text:
        reasons.append("Macro news around rates, inflation, or bonds may be moving the stock.")
    if volume_ratio >= 1.5:
        reasons.append("Trading volume is above normal, suggesting stronger-than-usual investor attention.")
    if abs(one_day) >= 3 and not reasons:
        reasons.append("Meaningful price move, but no obvious single Yahoo Finance catalyst found.")
    if not reasons:
        reasons.append("No obvious catalyst found. Move may be broad market/sector action or normal volatility.")
    if one_day > 2:
        tone = "Strong upward move"
    elif one_day > 0.5:
        tone = "Moderate upward move"
    elif one_day < -2:
        tone = "Strong downward move"
    elif one_day < -0.5:
        tone = "Moderate downward move"
    else:
        tone = "Small / normal move"
    return {
        "Ticker": ticker,
        "Current Price": current,
        "1-Day Move %": round(one_day, 2),
        "5-Day Move %": round(five_day, 2),
        "Volume Ratio": round(volume_ratio, 2),
        "Move Tone": tone,
        "Possible Reasons": reasons,
    }, score, news


# ============================================================
# AI RESEARCH SUMMARIES (optional — needs an OpenAI API key)
# ============================================================

# Model can be overridden via env var or Streamlit secrets (e.g. "gpt-5.5", "gpt-4o").
# Defaults to a widely-available, low-cost model so it works out of the box.
def _get_secret(name, default=None):
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.getenv(name, default)


AI_MODEL = _get_secret("OPENAI_MODEL", "gpt-4o-mini")


def get_openai_client():
    """Return an OpenAI client if a key is configured, else None (feature stays optional)."""
    key = _get_secret("OPENAI_API_KEY")
    if not key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=key)
    except Exception:
        return None


def ai_available():
    return get_openai_client() is not None


@st.cache_data(ttl=3600, show_spinner=False)
def generate_ai_research_summary(signature, payload):
    """Turn quant scores + headlines into a plain-English research memo.

    `signature` is a compact cache key (ticker + rounded scores) so we don't re-bill the
    API for identical inputs. `payload` is the full context dict sent to the model.
    Returns a memo string, or an error/notice string. Never raises."""
    client = get_openai_client()
    if client is None:
        return None
    system = (
        "You are a disciplined equity research assistant for a self-directed investor. "
        "You are given quantitative factor scores (0-100) and recent headlines for one stock. "
        "Write a concise, plain-English research memo. Be balanced and specific, cite the "
        "numbers you're reasoning from, and never give a buy/sell recommendation or price "
        "prediction. This is research to guide further study, not financial advice. "
        "Use these sections with markdown headers: '### One-line take', '### Bull case', "
        "'### Bear case', '### What to verify next'. Keep it under 250 words."
    )
    user = "Here is the data for the stock:\n" + json.dumps(payload, indent=2, default=str)
    try:
        resp = client.chat.completions.create(
            model=AI_MODEL,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.4,
            max_tokens=650,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"⚠️ AI summary unavailable: {str(e)[:200]}"


def build_ai_payload(row, news_list):
    """Compact, model-friendly context from a quant row + recent headlines."""
    keys = [
        "Ticker", "Company", "Sector", "Industry", "Price", "Fair Value", "Upside %",
        "Overall Quant Score", "Investment Score", "Opportunity Score", "Position Trade Score",
        "Health Score", "Conviction Score", "Evidence Score", "Quality Score", "Valuation Score",
        "Growth Score", "Cash Flow Score", "Financial Strength Score", "Momentum Score",
        "Relative Strength Score", "Risk Score", "P/E", "Forward P/E", "PEG", "FCF Yield %",
        "ROIC Proxy %", "Revenue Growth %", "Earnings Growth %", "Debt/Equity",
        "Biggest Risk", "Data Coverage %",
    ]
    payload = {k: row.get(k) for k in keys if k in row}
    payload["Recent Headlines"] = [
        {"title": n.get("Title"), "signal": n.get("Signal")} for n in (news_list or [])[:6]
    ]
    return payload


def ai_signature(row):
    """Stable cache key: ticker + key scores rounded, so identical inputs reuse the memo."""
    parts = [str(row.get("Ticker"))]
    for k in ["Overall Quant Score", "Conviction Score", "Valuation Score", "Health Score", "Momentum Score"]:
        parts.append(f"{k}={round(safe_float(row.get(k), 0))}")
    return "|".join(parts)


def generate_quant_memo(row):
    bull = []
    bear = []
    if row["Investment Score"] >= 80:
        bull.append("Strong long-term investment profile.")
    if row["Health Score"] >= 80:
        bull.append("Business health is strong.")
    if row["Cash Flow Score"] >= 75:
        bull.append("Cash-flow profile is strong.")
    if row["Opportunity Score"] >= 75:
        bull.append("Valuation/opportunity setup looks attractive.")
    if row["Position Trade Score"] >= 75:
        bull.append("Momentum and relative strength support a 3-6 month setup.")
    if row["ROIC Proxy %"] is not None and row["ROIC Proxy %"] >= 12:
        bull.append("ROIC proxy suggests strong capital efficiency.")
    if row["Valuation Score"] < 40:
        bear.append("Valuation looks stretched.")
    if row["Financial Strength Score"] < 45:
        bear.append("Financial strength is weak or uncertain.")
    if row["Risk Score"] < 45:
        bear.append("Risk profile is elevated.")
    if row["Growth Score"] < 45:
        bear.append("Growth profile is weak or slowing.")
    if row["Cash Flow Score"] < 45:
        bear.append("Cash-flow profile is weak.")
    return row["Research Action"], bull or ["No strong bull-case signal detected from current data."], bear or ["No major bear-case signal detected from current data."]



# ============================================================
# BACKTESTING
# ============================================================

@st.cache_data(ttl=3600, show_spinner=False)
def get_price_history(tickers, period="1y"):
    data = {}
    for ticker in tickers:
        try:
            hist = yf.Ticker(ticker).history(period=period)
            if hist is not None and not hist.empty and "Close" in hist.columns:
                data[ticker] = hist["Close"]
        except Exception:
            pass
    return data


def calculate_total_return(price_series):
    if price_series is None or len(price_series) < 2:
        return None
    start = safe_float(price_series.iloc[0])
    end = safe_float(price_series.iloc[-1])
    if not start or start <= 0:
        return None
    return (end / start) - 1


def calculate_max_drawdown(price_series):
    if price_series is None or len(price_series) < 2:
        return None
    running_max = price_series.cummax()
    drawdown = price_series / running_max - 1
    return safe_float(drawdown.min())


@st.cache_data(ttl=3600, show_spinner=False)
def get_forward_return(ticker, start_date, end_date):
    """Actual price return for a ticker between two calendar dates (out-of-sample)."""
    try:
        hist = yf.Ticker(ticker).history(start=start_date, end=end_date)
        if hist is None or hist.empty or "Close" not in hist.columns:
            return None
        return calculate_total_return(hist["Close"])
    except Exception:
        return None


def run_pointintime_backtest(rank_by, top_n, start_date, end_date):
    """A METHODOLOGICALLY HONEST backtest.

    It ranks stocks using ONLY the scores that existed on `start_date` (pulled from the
    saved score history), then measures the ACTUAL price return that happened AFTERWARD,
    from start_date to end_date. Because the ranking uses no future information, this is a
    real out-of-sample test — unlike the illustrative version, which ranks by today's
    scores and looks backward (lookahead bias)."""
    history = load_history()
    if history.empty or "Scan Date" not in history.columns:
        return pd.DataFrame(), {}, "no_history"
    snap = history[history["Scan Date"] == start_date].copy()
    if snap.empty or rank_by not in snap.columns:
        return pd.DataFrame(), {}, "no_snapshot"

    snap[rank_by] = pd.to_numeric(snap[rank_by], errors="coerce")
    ranked = snap.dropna(subset=[rank_by]).sort_values(rank_by, ascending=False).head(top_n)

    rows, returns = [], []
    for _, r in ranked.iterrows():
        ticker = str(r.get("Ticker", "")).upper().strip()
        if not ticker:
            continue
        fwd = get_forward_return(ticker, start_date, end_date)
        if fwd is None:
            continue
        rows.append({
            "Ticker": ticker,
            "Company": r.get("Company", ""),
            "Sector": r.get("Sector", ""),
            f"{rank_by} (as of {start_date})": round(safe_float(r.get(rank_by), 0), 1),
            "Forward Return %": round(fwd * 100, 2),
        })
        returns.append(fwd)

    spy_fwd = get_forward_return("SPY", start_date, end_date)
    avg = sum(returns) / len(returns) if returns else None
    win = len([x for x in returns if x > 0]) / len(returns) if returns else None
    beat = len([x for x in returns if spy_fwd is not None and x > spy_fwd]) / len(returns) if returns else None
    summary = {
        "Portfolio Return %": round(avg * 100, 2) if avg is not None else None,
        "SPY Return %": round(spy_fwd * 100, 2) if spy_fwd is not None else None,
        "Excess vs SPY %": round((avg - spy_fwd) * 100, 2) if avg is not None and spy_fwd is not None else None,
        "Win Rate %": round(win * 100, 2) if win is not None else None,
        "Beat SPY Rate %": round(beat * 100, 2) if beat is not None else None,
        "Stocks Tested": len(returns),
    }
    result_df = pd.DataFrame(rows)
    if not result_df.empty:
        result_df = result_df.sort_values("Forward Return %", ascending=False)
    return result_df, summary, "ok"


EFFICACY_FACTORS = [
    "Overall Quant Score", "Conviction Score", "Investment Score", "Opportunity Score",
    "Position Trade Score", "Health Score", "Expected Return Score", "Evidence Score",
    "Research Priority",
]


def run_factor_efficacy(end_date):
    """Does the scoring actually predict returns? For every past snapshot in the score
    history, measure each stock's ACTUAL forward return (to end_date), then for each factor
    compute:
      - Information Coefficient (Spearman rank correlation of score vs forward return)
      - the return spread between the top third and bottom third by that factor.
    Positive IC / spread = the factor ranked winners above losers. Honest, out-of-sample."""
    history = load_history()
    if history.empty or "Scan Date" not in history.columns:
        return None
    dates = sorted(str(d) for d in history["Scan Date"].dropna().unique())
    past_dates = [d for d in dates if d < str(end_date)]
    if not past_dates:
        return None
    factors = [f for f in EFFICACY_FACTORS if f in history.columns]

    recs = []
    for d in past_dates:
        snap = history[history["Scan Date"].astype(str) == d]
        for _, r in snap.iterrows():
            tk = str(r.get("Ticker", "")).upper().strip()
            if not tk:
                continue
            fwd = get_forward_return(tk, d, str(end_date))
            if fwd is None:
                continue
            rec = {"ret": fwd * 100}
            for f in factors:
                rec[f] = safe_float(r.get(f))
            recs.append(rec)
    if not recs:
        return None
    data = pd.DataFrame(recs)

    results = []
    for f in factors:
        sub = data[[f, "ret"]].dropna()
        if len(sub) < 6:
            continue
        ic = sub[f].rank().corr(sub["ret"].rank())          # Spearman IC
        sub = sub.sort_values(f)
        third = max(1, len(sub) // 3)
        bottom = sub.head(third)["ret"].mean()
        top = sub.tail(third)["ret"].mean()
        results.append({
            "Factor": f,
            "Predictive power (IC)": round(ic, 2) if ic == ic else None,
            "Top ⅓ return %": round(top, 1),
            "Bottom ⅓ return %": round(bottom, 1),
            "Top − Bottom %": round(top - bottom, 1),
            "Samples": len(sub),
        })
    if not results:
        return None
    res_df = pd.DataFrame(results).sort_values("Predictive power (IC)", ascending=False, na_position="last")
    return res_df, len(past_dates), len(data)


def run_simple_backtest(df, rank_by, top_n, period):
    if df.empty:
        return pd.DataFrame(), {}

    ranked = df.sort_values(rank_by, ascending=False).head(top_n)
    tickers = ranked["Ticker"].dropna().astype(str).tolist()

    price_data = get_price_history(tickers + ["SPY"], period=period)

    rows = []
    returns = []

    for ticker in tickers:
        prices = price_data.get(ticker)
        total_return = calculate_total_return(prices)
        max_dd = calculate_max_drawdown(prices)

        if total_return is None:
            continue

        score_row = ranked[ranked["Ticker"] == ticker].iloc[0]

        rows.append({
            "Ticker": ticker,
            "Company": score_row.get("Company", ""),
            "Sector": score_row.get("Sector", ""),
            "Rank Score": score_row.get(rank_by, None),
            "Return %": round(total_return * 100, 2),
            "Max Drawdown %": round(max_dd * 100, 2) if max_dd is not None else None,
            "Research Action": score_row.get("Research Action", ""),
            "Labels": score_row.get("Labels", "")
        })
        returns.append(total_return)

    result_df = pd.DataFrame(rows)

    spy_return = calculate_total_return(price_data.get("SPY"))
    spy_dd = calculate_max_drawdown(price_data.get("SPY"))

    avg_return = sum(returns) / len(returns) if returns else None
    win_rate = len([r for r in returns if r > 0]) / len(returns) if returns else None
    beat_spy_rate = len([r for r in returns if spy_return is not None and r > spy_return]) / len(returns) if returns else None

    summary = {
        "Average Return %": round(avg_return * 100, 2) if avg_return is not None else None,
        "SPY Return %": round(spy_return * 100, 2) if spy_return is not None else None,
        "Excess Return vs SPY %": round((avg_return - spy_return) * 100, 2) if avg_return is not None and spy_return is not None else None,
        "Win Rate %": round(win_rate * 100, 2) if win_rate is not None else None,
        "Beat SPY Rate %": round(beat_spy_rate * 100, 2) if beat_spy_rate is not None else None,
        "SPY Max Drawdown %": round(spy_dd * 100, 2) if spy_dd is not None else None,
        "Stocks Tested": len(returns)
    }

    return result_df.sort_values("Return %", ascending=False) if not result_df.empty else result_df, summary



def market_command_center():
    st.title("Market Command Center")
    st.caption("Market health, important news, winners, losers, and macro read.")
    if st.button("Refresh Market Command Center", type="primary"):
        st.cache_data.clear()
    snapshot = get_market_snapshot()
    health, regime = get_market_health(snapshot)
    news = get_market_news(10)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Market Health", f"{health}/100", regime)
    c2.metric("Important Headlines", len([n for n in news if n["Importance"] >= 7]))
    c3.metric("Bullish Headlines", len([n for n in news if n["Signal"] == "Bullish"]))
    c4.metric("Bearish Headlines", len([n for n in news if n["Signal"] == "Bearish"]))
    st.divider()
    col1, col2 = st.columns([1.2, 1])
    with col1:
        st.subheader("Market Snapshot")
        if snapshot:
            df = pd.DataFrame(snapshot)
            st.dataframe(df.sort_values("Change %", ascending=False), width="stretch")
            st.write("**Winners:**")
            for _, row in df.sort_values("Change %", ascending=False).head(3).iterrows():
                st.write(f"- **{row['Asset']}**: {row['Change %']}%")
            st.write("**Losers:**")
            for _, row in df.sort_values("Change %").head(3).iterrows():
                st.write(f"- **{row['Asset']}**: {row['Change %']}%")
    with col2:
        st.subheader("Macro Read")
        st.write(f"**Regime:** {regime}")
        st.write("- **Risk-on:** SPY/QQQ up, VIX down, TLT stable or up.")
        st.write("- **Risk-off:** VIX up, SPY/QQQ down, dollar rising.")
        st.write("- **Growth-friendly:** yields falling, inflation pressure easing.")
        st.write("- **Caution:** oil/yields/VIX rising together.")
    st.divider()
    st.subheader("Most Important Market News")
    category = st.selectbox("Filter news", ["All"] + list(CATEGORIES.keys()))
    filtered = news
    if category != "All":
        filtered = [n for n in filtered if category in n["Category"]]
    for article in filtered[:12]:
        with st.container(border=True):
            st.markdown(f"### [{article['Title']}]({article['URL']})")
            st.write(f"**Importance:** {article['Importance']}/10 | **Signal:** {article['Signal']} | **Category:** {article['Category']}")
            st.write(f"**Source:** {article['Provider']} | **Published:** {article['Published'].strftime('%Y-%m-%d %I:%M %p UTC')}")
            if article["Summary"]:
                st.write(article["Summary"])




# ============================================================
# SUPABASE AUTH + CLOUD STORAGE (optional; falls back to local files)
# ============================================================

def supabase_configured():
    return bool(_get_secret("SUPABASE_URL") and _get_secret("SUPABASE_ANON_KEY"))


def get_sb():
    """The signed-in Supabase client (held in session), or None."""
    return st.session_state.get("sb_client")


def sb_user():
    return st.session_state.get("sb_user")


def signed_in():
    return supabase_configured() and get_sb() is not None and sb_user() is not None


def _clean_secret(v):
    """Strip whitespace and any non-printable-ASCII characters. Supabase URLs/keys are pure
    ASCII, so this only removes paste artifacts (smart quotes, zero-width chars, newlines)
    that otherwise crash header encoding with an 'ascii codec' error."""
    return "".join(ch for ch in str(v or "").strip() if 32 <= ord(ch) < 127)


def _new_sb_client():
    from supabase import create_client
    return create_client(_clean_secret(_get_secret("SUPABASE_URL")),
                         _clean_secret(_get_secret("SUPABASE_ANON_KEY")))


def sb_sign_in(email, password, sign_up=False):
    """Sign in or sign up. Returns (ok, message). Supabase handles password security."""
    try:
        client = _new_sb_client()
        if sign_up:
            res = client.auth.sign_up({"email": email, "password": password})
            if res.user is None:
                return False, "Sign-up failed — check the email/password."
            # If email confirmation is on, there may be no session yet.
            if res.session is None:
                return False, "Account created — check your email to confirm, then sign in."
        else:
            res = client.auth.sign_in_with_password({"email": email, "password": password})
        if res.session is None or res.user is None:
            return False, "Could not sign in — check your credentials."
        st.session_state["sb_client"] = client
        st.session_state["sb_user"] = {"id": res.user.id, "email": res.user.email}
        st.session_state.pop("_user_state", None)   # clear any cached state
        return True, "Signed in."
    except Exception as e:
        return False, f"Auth error: {str(e)[:160]}"


def sb_sign_out():
    try:
        c = get_sb()
        if c:
            c.auth.sign_out()
    except Exception:
        pass
    for k in ("sb_client", "sb_user", "_user_state"):
        st.session_state.pop(k, None)


def _sb_load_state():
    """Read this user's stored blob (watchlist/journal/portfolio), cached per session."""
    if "_user_state" in st.session_state:
        return st.session_state["_user_state"]
    default = {"watchlist": [], "journal": [], "portfolio": [], "trades": []}
    try:
        c, u = get_sb(), sb_user()
        res = c.table("user_state").select("*").eq("user_id", u["id"]).execute()
        if res.data:
            row = res.data[0]
            default = {"watchlist": row.get("watchlist") or [],
                       "journal": row.get("journal") or [],
                       "portfolio": row.get("portfolio") or [],
                       "trades": row.get("trades") or []}
    except Exception:
        pass
    st.session_state["_user_state"] = default
    return default


def _sb_save_field(field, value):
    stt = _sb_load_state()
    stt[field] = value
    try:
        c, u = get_sb(), sb_user()
        c.table("user_state").upsert({"user_id": u["id"], field: value}).execute()
    except Exception as e:
        st.warning(f"Couldn't sync to your account: {str(e)[:120]}")


def auth_sidebar():
    """Login / signup box in the sidebar. No-op if Supabase isn't configured."""
    if not supabase_configured():
        st.sidebar.caption("💾 Sign-in not configured — data saves locally only.")
        return
    if signed_in():
        st.sidebar.success(f"✅ Signed in: {sb_user()['email']}")
        if st.sidebar.button("Sign out"):
            sb_sign_out()
            st.rerun()
        return
    with st.sidebar.expander("🔐 Sign in to save your data", expanded=True):
        email = st.text_input("Email", key="auth_email")
        pw = st.text_input("Password", type="password", key="auth_pw")
        c1, c2 = st.columns(2)
        if c1.button("Sign in", width="stretch"):
            ok, msg = sb_sign_in(email, pw, sign_up=False)
            (st.success if ok else st.error)(msg)
            if ok:
                st.rerun()
        if c2.button("Sign up", width="stretch"):
            ok, msg = sb_sign_in(email, pw, sign_up=True)
            (st.success if ok else st.warning)(msg)
            if ok:
                st.rerun()
        st.caption("Your watchlist, notes & portfolio save to your account and follow you across devices.")


# ============================================================
# PORTFOLIO MANAGER AI HELPERS
# ============================================================

def load_portfolio():
    if signed_in():
        recs = _sb_load_state().get("portfolio") or []
        return pd.DataFrame(recs) if recs else pd.DataFrame(columns=["Ticker", "Shares", "Average Cost"])
    if PORTFOLIO_FILE.exists():
        return pd.read_csv(PORTFOLIO_FILE)
    return pd.DataFrame(columns=["Ticker", "Shares", "Average Cost"])


def save_portfolio(df):
    if signed_in():
        _sb_save_field("portfolio", df.fillna("").to_dict("records"))
        return
    df.to_csv(PORTFOLIO_FILE, index=False)


# ============================================================
# WATCHLIST + ALERTS
# ============================================================

def load_watchlist():
    # Signed in → your account (persists everywhere)
    if signed_in():
        return [str(t).upper().strip() for t in (_sb_load_state().get("watchlist") or []) if str(t).strip()]
    # Otherwise: local file, then URL query param (bookmark) fallback
    if WATCHLIST_FILE.exists():
        try:
            df = pd.read_csv(WATCHLIST_FILE)
            fl = [str(t).upper().strip() for t in df["Ticker"].dropna().tolist() if str(t).strip()]
            if fl:
                return fl
        except Exception:
            pass
    try:
        wl = st.query_params.get("wl")
        if wl:
            return [t.strip().upper() for t in wl.split(",") if t.strip()]
    except Exception:
        pass
    return []


def save_watchlist(tickers):
    clean = []
    for t in tickers:
        t = str(t).upper().strip()
        if t and t not in clean:
            clean.append(t)
    if signed_in():
        _sb_save_field("watchlist", clean)
        return clean
    try:
        pd.DataFrame({"Ticker": clean}).to_csv(WATCHLIST_FILE, index=False)
    except Exception:
        pass
    try:
        st.query_params["wl"] = ",".join(clean)
    except Exception:
        pass
    return clean


JOURNAL_COLS = ["Ticker", "My Rating", "My Target", "Thesis", "Notes", "Updated"]


def load_journal():
    if signed_in():
        recs = _sb_load_state().get("journal") or []
        df = pd.DataFrame(recs)
        for c in JOURNAL_COLS:
            if c not in df.columns:
                df[c] = ""
        return df[JOURNAL_COLS].fillna("") if not df.empty else pd.DataFrame(columns=JOURNAL_COLS)
    if JOURNAL_FILE.exists():
        try:
            df = pd.read_csv(JOURNAL_FILE)
            for c in JOURNAL_COLS:
                if c not in df.columns:
                    df[c] = ""
            return df[JOURNAL_COLS].fillna("")
        except Exception:
            pass
    return pd.DataFrame(columns=JOURNAL_COLS)


def _persist_journal(df):
    if signed_in():
        _sb_save_field("journal", df[JOURNAL_COLS].fillna("").to_dict("records"))
    else:
        try:
            df.to_csv(JOURNAL_FILE, index=False)
        except Exception:
            pass


def save_journal_entry(ticker, rating, target, thesis, notes):
    ticker = str(ticker).upper().strip()
    if not ticker:
        return
    df = load_journal()
    df = df[df["Ticker"] != ticker]   # replace any existing entry for this ticker
    new = pd.DataFrame([{
        "Ticker": ticker, "My Rating": rating, "My Target": target,
        "Thesis": thesis, "Notes": notes, "Updated": today_string(),
    }])
    df = pd.concat([new, df], ignore_index=True)
    _persist_journal(df)


def delete_journal_entry(ticker):
    df = load_journal()
    df = df[df["Ticker"] != str(ticker).upper().strip()]
    _persist_journal(df)


def load_trades():
    if signed_in():
        return _sb_load_state().get("trades") or []
    if TRADES_FILE.exists():
        try:
            return json.loads(TRADES_FILE.read_text())
        except Exception:
            return []
    return []


def save_trades(trades):
    if signed_in():
        _sb_save_field("trades", trades)
        return
    try:
        TRADES_FILE.write_text(json.dumps(trades))
    except Exception:
        pass


def get_last_price(ticker):
    """Latest close for a ticker (disk-cached history). None if unavailable."""
    h = _yf_history(ticker, period="5d")
    if h is not None and not h.empty and "Close" in h.columns:
        return safe_float(h["Close"].iloc[-1])
    return None


def compute_alerts(row):
    """Return a list of (emoji, message) alerts currently triggered for a scored stock.
    These are evaluated whenever you view the watchlist — 'what needs my attention now'."""
    alerts = []
    conv = safe_float(row.get("Conviction Score"), 0)
    upside = safe_float(row.get("Upside %"), 0)
    health = safe_float(row.get("Health Score"), 0)
    ptrade = safe_float(row.get("Position Trade Score"), 0)
    risk = safe_float(row.get("Risk Score"), 100)
    fin = safe_float(row.get("Financial Strength Score"), 100)
    tier = str(row.get("Tier", ""))
    change = safe_float(row.get("Conviction Change"), 0)

    if conv >= 75:
        alerts.append(("🟢", f"High conviction ({conv:.0f})"))
    if upside >= 20 and health >= 60:
        alerts.append(("💰", f"Undervalued: {upside:.0f}% upside to fair value"))
    if ptrade >= 75:
        alerts.append(("📈", f"Momentum setup (Position Trade {ptrade:.0f})"))
    if "Tier 1" in tier or "Tier 2" in tier:
        alerts.append(("⭐", tier.split("—")[0].strip()))
    if upside is not None and upside <= 0:
        alerts.append(("🔻", "Trading at/above fair value"))
    if risk < 40:
        alerts.append(("⚠️", "Elevated volatility/drawdown risk"))
    if fin < 40:
        alerts.append(("⚠️", "Weak balance sheet"))
    if change >= 8:
        alerts.append(("⬆️", f"Conviction rose +{change:.0f} since last scan"))
    if change <= -8:
        alerts.append(("⬇️", f"Conviction fell {change:.0f} since last scan"))
    return alerts


def build_watchlist_analysis(tickers):
    """Score the watchlist tickers, preferring the saved scan (free) and only scoring
    live (uses an FMP/Yahoo call) the ones not already in it. Returns (df, live_scored)."""
    saved = load_sp500_scores()
    saved_map = {}
    if not saved.empty and "Ticker" in saved.columns:
        saved = enhance_research_columns(saved)
        saved = add_score_change(saved)
        saved_map = {str(r["Ticker"]).upper(): r for _, r in saved.iterrows()}

    rows, live = [], []
    for t in tickers:
        if t in saved_map:
            rows.append(saved_map[t].to_dict())
        else:
            try:
                rows.append(get_quant_score(t))
                live.append(t)
            except DataUnavailable:
                live.append(f"{t} (no data)")
            except Exception:
                live.append(f"{t} (error)")
    df = pd.DataFrame(rows)
    return df, live


def get_deploy_percent(market_health):
    market_health = safe_float(market_health, 50)
    if market_health >= 75:
        return 0.95, "Very favorable", "Deploy 90–95% now. Keep a small cash reserve."
    if market_health >= 60:
        return 0.85, "Favorable", "Deploy around 80–90% now. Dollar-cost average the rest."
    if market_health >= 45:
        return 0.70, "Mixed", "Deploy around 60–75% now. Spread the rest over time."
    if market_health >= 30:
        return 0.55, "Cautious", "Deploy around 40–60% now. Use slower dollar-cost averaging."
    return 0.40, "Weak / Risk-Off", "Deploy around 30–45% now. Keep more dry powder."


def recommend_holding_action(row, weight, market_health):
    conviction = safe_float(row.get("Conviction Score"), 50)
    investment = safe_float(row.get("Investment Score"), 50)
    opportunity = safe_float(row.get("Opportunity Score"), 50)
    health = safe_float(row.get("Health Score"), 50)
    valuation = safe_float(row.get("Valuation Score"), 50)
    risk = safe_float(row.get("Risk Score"), 50)
    market_health = safe_float(market_health, 50)

    reasons = []
    if conviction >= 80:
        reasons.append("Conviction remains high.")
    if investment >= 80:
        reasons.append("Long-term investment quality is strong.")
    if opportunity >= 75:
        reasons.append("Opportunity score suggests attractive upside/valuation.")
    if health >= 75:
        reasons.append("Business health is strong.")
    if valuation < 40:
        reasons.append("Valuation looks stretched.")
    if risk < 40:
        reasons.append("Risk score is weak.")
    if weight > 20:
        reasons.append("Position exceeds your 20% max-position rule.")
    if market_health < 45:
        reasons.append("Market health is weak, so adding aggressively is not ideal.")

    if conviction < 45 and health < 50:
        action = "SELL / Exit Candidate"
        reasons.append("Conviction and business health are both weak.")
    elif weight > 20 and valuation < 55:
        action = "TRIM"
        reasons.append("Position is oversized and valuation is not especially attractive.")
    elif conviction >= 80 and opportunity >= 70 and market_health >= 55 and weight < 20:
        action = "ADD / Buy More"
        reasons.append("High conviction plus attractive opportunity in a supportive market.")
    elif conviction >= 70 and investment >= 70:
        action = "HOLD"
        reasons.append("Still looks like a strong enough holding.")
    elif conviction >= 55:
        action = "WATCH / Hold Small"
        reasons.append("Data is mixed; not enough evidence to add.")
    else:
        action = "REDUCE / Review Thesis"
        reasons.append("Conviction is not strong enough to justify a large position.")

    tax_note = "Tax note: consider capital gains/losses before trimming or selling, but taxes are not calculated here."
    return action, " | ".join(dict.fromkeys(reasons)), tax_note


def build_portfolio_analysis(portfolio_df):
    rows = []
    for _, holding in portfolio_df.iterrows():
        ticker = str(holding.get("Ticker", "")).upper().strip()
        shares = safe_float(holding.get("Shares"), 0)
        avg_cost = safe_float(holding.get("Average Cost"), 0)

        if not ticker or shares <= 0:
            continue

        try:
            score = get_quant_score(ticker)
            price = safe_float(score.get("Price"), 0)
            current_value = shares * price
            cost_basis = shares * avg_cost
            gain_loss = current_value - cost_basis
            gain_loss_pct = gain_loss / cost_basis * 100 if cost_basis else 0
            score.update({
                "Shares": shares,
                "Average Cost": avg_cost,
                "Current Value": round(current_value, 2),
                "Cost Basis": round(cost_basis, 2),
                "Gain/Loss $": round(gain_loss, 2),
                "Gain/Loss %": round(gain_loss_pct, 2),
            })
            rows.append(score)
        except Exception as e:
            st.warning(f"Could not analyze {ticker}: {e}")

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    total_value = df["Current Value"].sum()
    df["Portfolio Weight %"] = (df["Current Value"] / total_value * 100).round(2)
    return df


def portfolio_risk_analytics(analysis):
    """Diversification & risk view of the holdings: weighted beta, concentration
    (Herfindahl / effective number of positions), and the correlation between holdings —
    the 'am I really diversified, or do I own six versions of the same bet?' check."""
    if analysis is None or analysis.empty:
        return {}
    tickers = [str(t).upper() for t in analysis["Ticker"].tolist()]
    weights = (analysis.set_index("Ticker")["Portfolio Weight %"].astype(float) / 100)

    betas = analysis.set_index("Ticker").get("Beta")
    weighted_beta = None
    if betas is not None:
        wb = [weights.get(t, 0) * safe_float(betas.get(t), 1.0) for t in tickers]
        weighted_beta = round(sum(wb), 2)

    w = weights.reindex(tickers).fillna(0).values
    hhi = float((w ** 2).sum()) if len(w) else 0.0
    eff_n = round(1 / hhi, 1) if hhi > 0 else len(tickers)

    corr, avg_corr = None, None
    if len(tickers) >= 2:
        price_data = get_price_history(tickers, period="1y")
        rets = {}
        for t in tickers:
            s = price_data.get(t)
            if s is not None and len(s) > 30:
                rets[t] = s.pct_change().dropna()
        if len(rets) >= 2:
            rdf = pd.DataFrame(rets).dropna()
            if len(rdf) > 20:
                corr = rdf.corr().round(2)
                import numpy as np
                m = corr.values
                mask = ~np.eye(len(m), dtype=bool)
                avg_corr = round(float(m[mask].mean()), 2)

    return {
        "weighted_beta": weighted_beta,
        "effective_positions": eff_n,
        "n_positions": len(tickers),
        "avg_correlation": avg_corr,
        "corr": corr,
    }


def portfolio_corr_heatmap(corr):
    if corr is None or getattr(corr, "empty", True):
        return None
    fig = go.Figure(go.Heatmap(
        z=corr.values, x=list(corr.columns), y=list(corr.index),
        zmin=-1, zmax=1, colorscale="RdYlGn_r",
        text=corr.values, texttemplate="%{text:.2f}", textfont={"size": 9},
        colorbar=dict(title="corr"),
    ))
    return _style_fig(fig, height=max(320, 60 + 34 * len(corr)))


def calculate_portfolio_health(portfolio_analysis):
    if portfolio_analysis is None or portfolio_analysis.empty:
        return {}

    weights = portfolio_analysis["Portfolio Weight %"] / 100
    weighted_conviction = (portfolio_analysis["Conviction Score"] * weights).sum()
    weighted_health = (portfolio_analysis["Health Score"] * weights).sum()
    weighted_risk = (portfolio_analysis["Risk Score"] * weights).sum()
    weighted_valuation = (portfolio_analysis["Valuation Score"] * weights).sum()
    weighted_investment = (portfolio_analysis["Investment Score"] * weights).sum()

    top_weight = portfolio_analysis["Portfolio Weight %"].max()
    sector_weights = portfolio_analysis.groupby("Sector")["Portfolio Weight %"].sum()
    top_sector_weight = sector_weights.max() if not sector_weights.empty else 0

    diversification_score = 100
    if top_weight > 20:
        diversification_score -= (top_weight - 20) * 2
    if top_sector_weight > 40:
        diversification_score -= (top_sector_weight - 40) * 1.5
    diversification_score = clamp(diversification_score)

    overall = (
        weighted_conviction * 0.25 +
        weighted_health * 0.25 +
        weighted_risk * 0.20 +
        weighted_valuation * 0.10 +
        weighted_investment * 0.10 +
        diversification_score * 0.10
    )

    return {
        "Portfolio Health": round(overall, 1),
        "Weighted Conviction": round(weighted_conviction, 1),
        "Weighted Health": round(weighted_health, 1),
        "Weighted Risk": round(weighted_risk, 1),
        "Weighted Valuation": round(weighted_valuation, 1),
        "Diversification Score": round(diversification_score, 1),
        "Largest Position %": round(top_weight, 1),
        "Largest Sector %": round(top_sector_weight, 1),
    }


def build_sector_allocation(invest_amount, market_health, scan_df, portfolio_df=None):
    deploy_pct, timing_label, timing_text = get_deploy_percent(market_health)
    deploy_amount = invest_amount * deploy_pct
    reserve_amount = invest_amount - deploy_amount

    if scan_df is None or scan_df.empty:
        return pd.DataFrame(), pd.DataFrame(), deploy_pct, timing_label, timing_text

    df = enhance_research_columns(scan_df).copy()
    df = df[~df["Ticker"].astype(str).str.contains("BTC|ETH|USD", case=False, na=False)]
    df = df[df["Sector"].astype(str).str.lower() != "unknown"]

    sector_scores = df.groupby("Sector").agg(
        Avg_Conviction=("Conviction Score", "mean"),
        Avg_Investment=("Investment Score", "mean"),
        Avg_Opportunity=("Opportunity Score", "mean"),
        Avg_Health=("Health Score", "mean"),
        Avg_Risk=("Risk Score", "mean"),
        Count=("Ticker", "count")
    ).reset_index()

    if sector_scores.empty:
        return pd.DataFrame(), pd.DataFrame(), deploy_pct, timing_label, timing_text

    sector_scores["Sector Score"] = (
        sector_scores["Avg_Conviction"] * 0.30 +
        sector_scores["Avg_Investment"] * 0.25 +
        sector_scores["Avg_Opportunity"] * 0.20 +
        sector_scores["Avg_Health"] * 0.15 +
        sector_scores["Avg_Risk"] * 0.10
    )

    sector_scores = sector_scores.sort_values("Sector Score", ascending=False).head(6)
    total_sector_score = sector_scores["Sector Score"].sum()
    sector_scores["Raw Weight"] = sector_scores["Sector Score"] / total_sector_score
    sector_scores["Target Weight"] = sector_scores["Raw Weight"].clip(lower=0.07, upper=0.35)
    sector_scores["Target Weight"] = sector_scores["Target Weight"] / sector_scores["Target Weight"].sum()
    sector_scores["Dollar Allocation"] = (sector_scores["Target Weight"] * deploy_amount).round(2)
    sector_scores["Target Weight %"] = (sector_scores["Target Weight"] * 100).round(1)

    cash_row = pd.DataFrame([{
        "Sector": "Cash / Wait",
        "Avg_Conviction": None,
        "Avg_Investment": None,
        "Avg_Opportunity": None,
        "Avg_Health": None,
        "Avg_Risk": None,
        "Count": None,
        "Sector Score": None,
        "Raw Weight": None,
        "Target Weight": reserve_amount / invest_amount if invest_amount else 0,
        "Target Weight %": round((reserve_amount / invest_amount * 100), 1) if invest_amount else 0,
        "Dollar Allocation": round(reserve_amount, 2)
    }])
    sector_allocation = pd.concat([sector_scores, cash_row], ignore_index=True)

    existing_weights = {}
    if portfolio_df is not None and not portfolio_df.empty and "Ticker" in portfolio_df.columns:
        for _, r in portfolio_df.iterrows():
            existing_weights[str(r.get("Ticker", "")).upper()] = safe_float(r.get("Portfolio Weight %"), 0)

    stock_rows = []
    for _, sector_row in sector_scores.iterrows():
        sector = sector_row["Sector"]
        sector_amount = safe_float(sector_row["Dollar Allocation"], 0)
        candidates = df[df["Sector"] == sector].copy()
        candidates = candidates.sort_values(
            ["Research Priority", "Conviction Score", "Evidence Score", "Investment Score"],
            ascending=False
        ).head(3)

        if candidates.empty:
            continue

        weights = [0.50, 0.30, 0.20][:len(candidates)]
        weight_sum = sum(weights)
        weights = [w / weight_sum for w in weights]

        for idx, (_, stock_row) in enumerate(candidates.iterrows()):
            ticker = str(stock_row["Ticker"]).upper()
            suggested_amount = sector_amount * weights[idx]
            current_weight = existing_weights.get(ticker, 0)
            note = ""

            if current_weight >= 20:
                suggested_amount = 0
                note = "Already at/above 20% max-position rule."

            stock_rows.append({
                "Sector": sector,
                "Ticker": ticker,
                "Company": stock_row.get("Company", ""),
                "Suggested $": round(suggested_amount, 2),
                "Conviction Score": stock_row.get("Conviction Score"),
                "Evidence Score": stock_row.get("Evidence Score"),
                "Investment Score": stock_row.get("Investment Score"),
                "Opportunity Score": stock_row.get("Opportunity Score"),
                "Biggest Risk": stock_row.get("Biggest Risk"),
                "Why": stock_row.get("Why Ranked High"),
                "Note": note
            })

    stock_allocation = pd.DataFrame(stock_rows)
    return sector_allocation, stock_allocation, deploy_pct, timing_label, timing_text




def portfolio_manager_page():
    st.title("Portfolio Manager AI")
    st.caption("Track holdings, get hold/add/trim/sell guidance, and allocate new money by sector + specific stocks.")

    st.info("Research assistant only. Not financial advice. Taxes are mentioned but not calculated.")

    snapshot = get_market_snapshot()
    market_health, regime = get_market_health(snapshot)
    deploy_pct_preview, timing_label, timing_text = get_deploy_percent(market_health)

    c1, c2, c3 = st.columns(3)
    c1.metric("Market Health", f"{market_health}/100", regime)
    c2.metric("Timing Assessment", timing_label)
    c3.metric("Suggested Deploy %", f"{round(deploy_pct_preview * 100)}%")
    st.write(f"**Timing guidance:** {timing_text}")

    tab1, tab2, tab3 = st.tabs(["Current Portfolio", "New Money Allocator", "Combined Summary"])

    with tab1:
        st.subheader("Current Portfolio")
        portfolio = load_portfolio()

        edited = st.data_editor(
            portfolio,
            num_rows="dynamic",
            width="stretch",
            column_config={
                "Ticker": st.column_config.TextColumn("Ticker"),
                "Shares": st.column_config.NumberColumn("Shares", min_value=0.0),
                "Average Cost": st.column_config.NumberColumn("Average Cost", min_value=0.0),
            }
        )

        if st.button("Save Portfolio"):
            save_portfolio(edited)
            st.success("Portfolio saved.")

        if st.button("Analyze Portfolio", type="primary"):
            with st.spinner("Analyzing portfolio..."):
                analysis = build_portfolio_analysis(edited)

            if analysis.empty:
                st.warning("Add at least one valid holding.")
                return

            health = calculate_portfolio_health(analysis)
            total_value = analysis["Current Value"].sum()
            total_cost = analysis["Cost Basis"].sum()
            total_gain = total_value - total_cost
            total_gain_pct = total_gain / total_cost * 100 if total_cost else 0

            a, b, c, d = st.columns(4)
            a.metric("Portfolio Value", money(total_value))
            b.metric("Gain/Loss", money(total_gain), f"{round(total_gain_pct, 2)}%")
            c.metric("Portfolio Health", f"{health.get('Portfolio Health')} / 100")
            d.metric("Largest Position", f"{health.get('Largest Position %')}%")

            st.subheader("Holding Recommendations")
            recommendation_rows = []
            for _, row in analysis.iterrows():
                action, reason, tax_note = recommend_holding_action(row, row["Portfolio Weight %"], market_health)
                recommendation_rows.append({
                    "Ticker": row["Ticker"],
                    "Company": row["Company"],
                    "Sector": row["Sector"],
                    "Current Value": row["Current Value"],
                    "Weight %": row["Portfolio Weight %"],
                    "Gain/Loss %": row["Gain/Loss %"],
                    "Action": action,
                    "Conviction": row["Conviction Score"],
                    "Evidence": row["Evidence Score"],
                    "Health": row["Health Score"],
                    "Biggest Risk": row["Biggest Risk"],
                    "Reason": reason,
                    "Tax Note": tax_note
                })

            rec_df = pd.DataFrame(recommendation_rows)
            st.dataframe(rec_df, width="stretch")

            st.subheader("Sector Exposure")
            sector_exposure = analysis.groupby("Sector")["Portfolio Weight %"].sum().reset_index().sort_values("Portfolio Weight %", ascending=False)
            st.dataframe(sector_exposure, width="stretch")

            st.subheader("Portfolio Health Breakdown")
            st.json(health)

            st.divider()
            st.subheader("🛡️ Risk & Diversification")
            with st.spinner("Analyzing diversification..."):
                risk = portfolio_risk_analytics(analysis)
            r1, r2, r3 = st.columns(3)
            wb = risk.get("weighted_beta")
            r1.metric("Portfolio Beta", wb if wb is not None else "N/A",
                      help="Weighted market sensitivity. >1 = swings more than the market, <1 = less.")
            eff, npos = risk.get("effective_positions"), risk.get("n_positions")
            r2.metric("Effective Positions", f"{eff} of {npos}",
                      help="Diversification-adjusted count. Much lower than your holding count means a few positions dominate.")
            ac = risk.get("avg_correlation")
            r3.metric("Avg Correlation", ac if ac is not None else "N/A",
                      help="How similarly your holdings move. Lower = better diversified.")

            if wb is not None:
                st.caption(f"Beta {wb}: your portfolio {'amplifies' if wb > 1.05 else 'dampens' if wb < 0.95 else 'tracks'} market moves.")
            if ac is not None:
                if ac >= 0.7:
                    st.warning(f"⚠️ High average correlation ({ac}) — your holdings tend to move together, so you're less diversified than the number of names suggests.")
                elif ac <= 0.4:
                    st.success(f"🟢 Low average correlation ({ac}) — holdings move fairly independently. Good diversification.")
                else:
                    st.info(f"Moderate average correlation ({ac}).")
            if eff and npos and eff < npos * 0.6:
                st.warning(f"⚠️ Concentration: your {npos} holdings behave like ~{eff} equal positions — a few names dominate the risk.")

            heat = portfolio_corr_heatmap(risk.get("corr"))
            if heat is not None:
                st.markdown("**How your holdings move together** (green = independent, red = move in lockstep)")
                st.plotly_chart(heat, width="stretch")

            st.divider()
            st.subheader("🌩️ Stress Test")
            st.caption("How would your portfolio move if the market did? Estimated via your portfolio beta (sensitivity to market moves) — standard scenario analysis.")
            beta = risk.get("weighted_beta")
            if beta is None:
                st.caption("Need holding betas to run scenarios.")
            else:
                scenarios = [("Severe crash", -30), ("Bear market", -20), ("Correction", -10),
                             ("Pullback", -5), ("Rally", 10), ("Strong rally", 20)]
                srows = []
                for name, mkt in scenarios:
                    port = beta * mkt                      # CAPM-style: portfolio move ≈ beta × market move
                    srows.append({
                        "Scenario": f"{name} ({mkt:+d}%)",
                        "Est. Portfolio Move %": round(port, 1),
                        "Est. Value Change": money(total_value * port / 100),
                        "Portfolio Value After": money(total_value * (1 + port / 100)),
                    })
                st.dataframe(pd.DataFrame(srows), width="stretch")
                worst = total_value * (beta * -30) / 100
                st.warning(f"In a severe (−30%) market, this portfolio (beta {beta}) could fall ~{money(abs(worst))} ({beta*-30:.0f}%). Make sure that's a loss you could stomach and hold through.")
                st.caption("⚠️ Simplified: assumes moves scale with beta and ignores stock-specific news, correlations breaking down in crises, and that high-beta names often fall *more* than beta predicts in real crashes. A planning aid, not a forecast.")

    with tab2:
        st.subheader("New Money Allocator")
        invest_amount = st.number_input("Amount you want to invest", min_value=0.0, value=1000.0, step=100.0)

        col_a, col_b = st.columns(2)
        with col_a:
            st.write("**Risk profile:** True Medium")
            st.write("**Goal:** Long-term wealth growth")
            st.write("**Crypto:** Excluded")
        with col_b:
            st.write("**Max position size:** 20%")
            st.write("**Buying style:** System decides based on market health")
            st.write("**Output:** Sectors + specific stocks")

        scan_df = load_sp500_scores()
        if scan_df.empty:
            st.warning("No quant scan saved yet. Run a scan in Quant Opportunity Engine before using the allocator.")
        else:
            current_portfolio = load_portfolio()
            portfolio_analysis = build_portfolio_analysis(current_portfolio) if not current_portfolio.empty else pd.DataFrame()

            if st.button("Create Allocation Plan", type="primary"):
                with st.spinner("Building allocation plan..."):
                    sector_alloc, stock_alloc, deploy_pct, timing_label, timing_text = build_sector_allocation(
                        invest_amount,
                        market_health,
                        scan_df,
                        portfolio_analysis
                    )

                st.subheader("Should You Invest Now?")
                x, y, z = st.columns(3)
                x.metric("Market Health", f"{market_health}/100")
                y.metric("Timing", timing_label)
                z.metric("Deploy Now", money(invest_amount * deploy_pct))

                st.write(f"**Recommendation:** {timing_text}")
                st.write(f"**Reserve / DCA later:** {money(invest_amount * (1 - deploy_pct))}")

                st.subheader("Sector Allocation")
                st.dataframe(sector_alloc, width="stretch")

                st.subheader("Specific Stock Allocation")
                if stock_alloc.empty:
                    st.warning("Could not build stock allocation. Try running a broader quant scan first.")
                else:
                    st.dataframe(stock_alloc, width="stretch")

                st.subheader("Evidence Logic")
                st.write("""
                The allocator favors sectors and stocks with stronger:
                - Conviction Score
                - Investment Score
                - Opportunity Score
                - Health Score
                - Risk Score

                It avoids crypto and reduces allocations to holdings already at or above your 20% position-size rule.
                """)

    with tab3:
        st.subheader("Combined Portfolio + New Capital View")
        st.write("""
        This page is designed to answer:

        - What should I hold?
        - What should I add to?
        - What should I trim or sell?
        - Where should new money go?
        - Is this a good or bad time to deploy capital?
        """)

        st.write("Use **Current Portfolio** first, then **New Money Allocator**.")

def research_queue_page():
    st.title("Research Queue")
    st.caption("What to research today, why it matters, what changed, and what the biggest risk is.")

    df = load_sp500_scores()

    if df.empty:
        st.warning("No saved quant scan yet. Go to Quant Opportunity Engine and run a scan first.")
        return

    df = enhance_research_columns(df)
    df = add_score_change(df)

    st.subheader("Today's Research Queue")
    st.write("Built to avoid one giant mega-cap list. It separates high conviction, undervalued, recovery, momentum, and biggest improvements.")

    tabs = st.tabs([
        "High Conviction",
        "Most Undervalued",
        "Recovery Candidates",
        "Momentum Leaders",
        "Biggest Improvements"
    ])

    display_cols = [
        "Ticker", "Company", "Sector", "Research Priority", "Conviction Score", "Evidence Score",
        "Investment Score", "Opportunity Score", "Position Trade Score", "Health Score",
        "Biggest Risk", "Research Time", "Research Action", "Why Ranked High", "Main Concerns"
    ]

    with tabs[0]:
        st.subheader("Top 5 High Conviction")
        q = df.sort_values(["Conviction Score", "Evidence Score"], ascending=False).head(5)
        st.dataframe(q[[c for c in display_cols if c in q.columns]], width="stretch")
        for _, row in q.iterrows():
            with st.container(border=True):
                st.markdown(f"### {row['Ticker']} — {row.get('Company','')}")
                st.write(f"**Why research:** {row.get('Why Ranked High','')}")
                st.write(f"**Biggest risk:** {row.get('Biggest Risk','')}")
                st.write(f"**Research time:** {row.get('Research Time','')}")
                st.write(f"**Action:** {row.get('Research Action','')}")

    with tabs[1]:
        st.subheader("Top 5 Most Undervalued")
        q = df.sort_values(["Opportunity Score", "Valuation Score", "Evidence Score"], ascending=False).head(5)
        st.dataframe(q[[c for c in display_cols if c in q.columns]], width="stretch")

    with tabs[2]:
        st.subheader("Top 5 Recovery Candidates")
        recovery = df[df["Labels"].astype(str).str.contains("Recovery Candidate|Undervalued Opportunity", na=False)]
        if recovery.empty:
            recovery = df.sort_values(["Opportunity Score", "Momentum Score"], ascending=[False, True])
        q = recovery.sort_values(["Opportunity Score", "Health Score"], ascending=False).head(5)
        st.dataframe(q[[c for c in display_cols if c in q.columns]], width="stretch")

    with tabs[3]:
        st.subheader("Top 5 Momentum Leaders")
        q = df.sort_values(["Position Trade Score", "Relative Strength Score", "Momentum Score"], ascending=False).head(5)
        st.dataframe(q[[c for c in display_cols if c in q.columns]], width="stretch")

    with tabs[4]:
        st.subheader("Top 5 Biggest Improvements")
        if "Conviction Change" not in df.columns:
            df["Conviction Change"] = 0.0
        q = df.sort_values(["Conviction Change", "Score Change"], ascending=False).head(5)
        improvement_cols = ["Ticker", "Company", "Sector", "Conviction Score", "Conviction Change", "Overall Quant Score", "Score Change", "Biggest Risk", "Why Ranked High"]
        st.dataframe(q[[c for c in improvement_cols if c in q.columns]], width="stretch")

    st.divider()
    st.subheader("Full Research Priority Table")
    sector = st.selectbox("Filter by sector", ["All"] + sorted(df["Sector"].dropna().unique().tolist()))
    min_conviction = st.slider("Minimum conviction", 0, 100, 60)
    filtered = df[df["Conviction Score"] >= min_conviction]
    if sector != "All":
        filtered = filtered[filtered["Sector"] == sector]
    st.dataframe(filtered.sort_values("Research Priority", ascending=False)[[c for c in display_cols if c in filtered.columns]], width="stretch")



def opportunity_engine():
    st.title("Quant Opportunity Engine")
    st.caption("Ranks stocks using Investment, Opportunity, Position Trade, Health, and Expected Return scores.")
    st.write(cache_age_text())
    df = load_sp500_scores()
    tab_saved, tab_scan = st.tabs(["Saved Quant Scan", "Run / Update Quant Scan"])
    with tab_scan:
        st.write("Scan the **full S&P 500** — target a sector to keep each scan fast and within the FMP daily quota. Scans **merge** into your saved data, so you can build full coverage a sector at a time.")
        chosen_sectors = st.multiselect(
            "Sectors to scan (leave empty for all 500)", sp500_sectors(),
            help="Scanning one or two sectors at a time is the best way to build full coverage on the free data tier.",
        )
        tickers = tickers_for_sectors(chosen_sectors)
        max_n = max(10, len(tickers))
        scan_size = st.slider("How many stocks to scan", 10, min(500, max_n), min(50, max_n))
        st.caption(f"{len(tickers)} names available in the selected universe. Scanning the first {scan_size}.")
        st.warning("A large scan takes time and burns FMP quota (free tier = 250 calls/day, ~4 per stock). Start with one sector.")
        st.caption("⚡ Fetched data is cached on disk (~20h) — re-scanning the same names is fast and free. Clear the cache to force fresh data.")
        if st.button("🧹 Clear data cache"):
            st.success(f"Cleared {clear_data_cache()} cached files. Next scan pulls fresh data.")
        if st.button("Run Quant Scan and Save", type="primary"):
            with st.spinner("Running deeper quant scan..."):
                new_df, failures = score_many(tickers[:scan_size])
            if not new_df.empty:
                save_sp500_scores(new_df)
                st.success(f"Saved {len(new_df)} quant scores.")
                df = new_df
            else:
                st.error("No stocks could be scored — Yahoo Finance may be rate-limiting. Try again in a few minutes with a smaller scan size.")
            if failures:
                low_cov = 0
                if not new_df.empty and "Data Coverage %" in new_df.columns:
                    low_cov = int((new_df["Data Coverage %"] < 50).sum())
                with st.expander(f"⚠️ {len(failures)} ticker(s) skipped — no reliable data" + (f"  •  {low_cov} scored with limited data" if low_cov else "")):
                    st.caption("These were left OUT of your rankings instead of being given fake neutral scores.")
                    st.dataframe(pd.DataFrame(failures), width="stretch")
    with tab_saved:
        if df.empty:
            st.warning("No saved quant scan yet. Use the Run / Update Quant Scan tab first.")
            return
        df = enhance_research_columns(df)
        df = add_score_change(df)
        df = add_sector_relative_scores(df)
        st.subheader("Best Overall Research Priorities")
        st.dataframe(df.sort_values("Research Priority", ascending=False).head(25), width="stretch")

        st.subheader("Opportunity Map")
        st.caption("Each dot is a stock. **Top-right = cheap *and* high-quality** (the sweet spot). Bubble size = overall score; hover for the ticker.")
        try:
            st.plotly_chart(valuation_quality_scatter(df), width="stretch")
        except Exception:
            st.info("Not enough scored data to draw the map yet — run a scan first.")

        st.subheader("Highest Conviction")
        st.dataframe(df.sort_values(["Conviction Score", "Evidence Score"], ascending=False).head(15), width="stretch")
        st.divider()
        a, b = st.columns(2)
        with a:
            st.subheader("Best Long-Term Investments")
            st.dataframe(df.sort_values("Investment Score", ascending=False).head(15), width="stretch")
            st.subheader("Most Undervalued / Best Opportunity")
            st.dataframe(df.sort_values("Opportunity Score", ascending=False).head(15), width="stretch")
            st.subheader("Strongest Business Health")
            st.dataframe(df.sort_values("Health Score", ascending=False).head(15), width="stretch")
        with b:
            st.subheader("Best 3-6 Month Position Trades")
            st.dataframe(df.sort_values("Position Trade Score", ascending=False).head(15), width="stretch")
            st.subheader("Best Expected Return Profile")
            st.dataframe(df.sort_values("Expected Return Score", ascending=False).head(15), width="stretch")
            st.subheader("Best Relative Strength")
            st.dataframe(df.sort_values("Relative Strength Score", ascending=False).head(15), width="stretch")
        st.divider()
        st.subheader("Sector-Relative Leaders")
        st.caption(
            "These rank each stock **against its own sector**, not the whole market. A bank "
            "with a mediocre absolute valuation score can still be the cheapest bank — that's "
            "what these percentiles surface. Higher = better vs peers. Sectors with fewer than "
            "3 scanned names are blank, so this gets sharper the more of the S&P 500 you scan."
        )
        rel_options = [d for d in SECTOR_RELATIVE_FACTORS.values() if d in df.columns]
        if not rel_options:
            st.info("Scan more names (aim for a broad scan) to unlock sector-relative rankings.")
        else:
            rel_choice = st.selectbox("Rank within sector by", rel_options)
            rel_cols = ["Ticker", "Company", "Sector", "Sector Peers", rel_choice]
            # show the matching absolute score next to the relative one for context
            abs_for_rel = {v: k for k, v in SECTOR_RELATIVE_FACTORS.items()}
            abs_col = abs_for_rel.get(rel_choice)
            if abs_col and abs_col in df.columns:
                rel_cols.append(abs_col)
            rel_df = df.dropna(subset=[rel_choice]).sort_values(rel_choice, ascending=False)
            st.dataframe(rel_df[[c for c in rel_cols if c in rel_df.columns]].head(20), width="stretch")

        st.divider()
        st.subheader("Filter Quant Database")
        score_type = st.selectbox("Rank by", [
            "Overall Quant Score", "Investment Score", "Opportunity Score", "Position Trade Score",
            "Health Score", "Expected Return Score", "Quality Score", "Cash Flow Score",
            "Valuation Score", "Growth Score", "Relative Strength Score", "Risk Score"
        ])
        sector = st.selectbox("Sector", ["All"] + sorted(df["Sector"].dropna().unique().tolist()))
        min_score = st.slider("Minimum selected score", 0, 100, 60)
        filtered = df[df[score_type] >= min_score]
        if sector != "All":
            filtered = filtered[filtered["Sector"] == sector]
        st.dataframe(filtered.sort_values(score_type, ascending=False), width="stretch")


def stock_deep_dive():
    st.title("Quant Stock Deep Dive")
    st.caption("Deep statistical research page: master scores, valuation, cash flow, ROIC proxy, relative strength, news, and risks.")
    ticker = st.text_input("Enter ticker", "MSFT").upper().strip()
    if st.button("Analyze Stock", type="primary"):
        try:
            with st.spinner("Building full quant research view..."):
                row = get_quant_score(ticker)
                verdict, bull, bear = generate_quant_memo(row)
                move, _, ticker_news = explain_price_move(ticker)
                stock = yf.Ticker(ticker)
                hist = stock.history(period="2y")
        except DataUnavailable:
            st.error(f"No reliable market data for **{ticker}**. Check the symbol — it may be delisted, renamed, or mistyped.")
            return
        except Exception as e:
            st.error(f"Could not analyze **{ticker}**: {e}")
            return
        if row.get("Data Coverage %", 100) < 50:
            st.warning(f"⚠️ Limited data for {ticker}: only {row.get('Data Coverage %')}% of key metrics were available, so scores are low-confidence.")
        st.subheader(f"{row['Ticker']} — {row['Company']}")
        st.write(f"**Sector:** {row['Sector']} | **Industry:** {row['Industry']}")
        st.caption(
            f"📊 Fundamentals: **{row.get('Data Source', 'Yahoo Finance')}** · "
            f"Data coverage: **{row.get('Data Coverage %', 'N/A')}%** · "
            f"Prices/news: Yahoo Finance · As of {row.get('Scan Date', today_string())}"
        )
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Research Action", verdict)
        c2.metric("Conviction", f"{row['Conviction Score']}/100")
        c3.metric("Evidence", f"{row['Evidence Score']}/100")
        c4.metric("Overall Quant", f"{row['Overall Quant Score']}/100 — {row['Overall Grade']}")
        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Fair Value", money(row["Fair Value"]))
        c6.metric("Upside", f"{row['Upside %']}%" if row["Upside %"] is not None else "N/A")
        c7.metric("Research Time", row["Research Time"])
        c8.metric("Biggest Risk", row["Biggest Risk"])
        try:
            pdf_bytes = build_stock_pdf(row, verdict, bull, bear)
            st.download_button(
                "📄 Download 1-page PDF report", data=pdf_bytes,
                file_name=f"{row['Ticker']}_research_{row.get('Scan Date','')}.pdf",
                mime="application/pdf",
            )
        except Exception as e:
            st.caption(f"(PDF export unavailable: {str(e)[:80]})")
        if len(hist):
            st.plotly_chart(
                price_with_fair_value(hist, row.get("Fair Value Low"), row.get("Fair Value High"), row.get("Fair Value")),
                width="stretch",
            )
        tab1, tab2, tab3, tab8, tab4, tab5, tab6, tab7 = st.tabs([
            "Master Scores", "Valuation + Cash Flow", "Quality + Health",
            "📊 Analyst View", "Momentum + News", "Bull vs Bear", "🤖 AI Analyst", "Metric Guide"
        ])
        with tab1:
            st.subheader("Master Quant Scores")
            score_df = pd.DataFrame([
                {"Score": "Investment Score", "Value": row["Investment Score"], "Purpose": "Best for 3-5+ year wealth building."},
                {"Score": "Opportunity Score", "Value": row["Opportunity Score"], "Purpose": "Best for undervaluation and margin of safety."},
                {"Score": "Position Trade Score", "Value": row["Position Trade Score"], "Purpose": "Best for 3-6 month setups."},
                {"Score": "Health Score", "Value": row["Health Score"], "Purpose": "Business and financial health."},
                {"Score": "Expected Return Score", "Value": row["Expected Return Score"], "Purpose": "Blended future return profile."},
                {"Score": "Conviction Score", "Value": row["Conviction Score"], "Purpose": "Confidence that this deserves research today."},
                {"Score": "Evidence Score", "Value": row["Evidence Score"], "Purpose": "How many independent factors agree."},
                {"Score": "Research Priority", "Value": row["Research Priority"], "Purpose": "Final research queue ranking."},
                {"Score": "Overall Quant Score", "Value": row["Overall Quant Score"], "Purpose": "Combined ranking score."},
            ])
            rc1, rc2 = st.columns([1, 1])
            with rc1:
                st.markdown("**Factor shape**")
                st.plotly_chart(factor_radar(row), width="stretch")
            with rc2:
                st.markdown("**Master scores**")
                render_score_bars({
                    "Investment": row["Investment Score"],
                    "Opportunity": row["Opportunity Score"],
                    "Position Trade": row["Position Trade Score"],
                    "Health": row["Health Score"],
                    "Expected Return": row["Expected Return Score"],
                    "Conviction": row["Conviction Score"],
                    "Evidence": row["Evidence Score"],
                    "Overall Quant": row["Overall Quant Score"],
                })
            with st.expander("Score details & what each one is for"):
                st.dataframe(score_df, width="stretch")
            st.write(f"**Labels:** {row['Labels']}")
            st.write(f"**Why ranked high:** {row['Why Ranked High']}")
            st.write(f"**Main concerns:** {row['Main Concerns']}")
            st.write(f"**Biggest risk:** {row['Biggest Risk']}")
            st.write(f"**Alerts:** {row['Alerts']}")

            st.divider()
            st.markdown("### How it compares to sector peers")
            scan_peers = load_sp500_scores()
            if scan_peers.empty:
                st.caption("Run a scan to compare against sector peers.")
            else:
                scan_peers = enhance_research_columns(scan_peers)
                sector = row.get("Sector")
                peers = scan_peers[scan_peers["Sector"] == sector].copy()
                peers = peers[peers["Ticker"].astype(str).str.upper() != str(row["Ticker"]).upper()]
                combined = pd.concat([peers, pd.DataFrame([row])], ignore_index=True)
                if len(combined) < 3:
                    st.caption(f"Not enough scanned **{sector}** names yet to compare — scan that sector to unlock peer comparison.")
                else:
                    combined = combined.sort_values("Overall Quant Score", ascending=False).reset_index(drop=True)
                    rank = combined.index[combined["Ticker"].astype(str).str.upper() == str(row["Ticker"]).upper()][0] + 1
                    n = len(combined)
                    # valuation rank (higher Valuation Score = cheaper)
                    val_sorted = combined.sort_values("Valuation Score", ascending=False).reset_index(drop=True)
                    val_rank = val_sorted.index[val_sorted["Ticker"].astype(str).str.upper() == str(row["Ticker"]).upper()][0] + 1
                    st.write(f"**{row['Ticker']}** ranks **#{rank} of {n}** in {sector} by Overall Quant Score, and **#{val_rank} of {n}** on valuation (cheapness).")
                    # Sector-relative fair value: value this stock at its sector's median P/E
                    cur_pe2 = safe_float(row.get("P/E"))
                    px2 = safe_float(row.get("Price"))
                    peer_pes = pd.to_numeric(peers["P/E"], errors="coerce")
                    peer_pes = peer_pes[peer_pes > 0]
                    if cur_pe2 and cur_pe2 > 0 and px2 and len(peer_pes) >= 2:
                        med_pe = float(peer_pes.median())
                        sec_fv = med_pe * (px2 / cur_pe2)
                        updown = (sec_fv - px2) / px2 * 100
                        st.write(f"At the **sector median P/E ({med_pe:.1f})**, {row['Ticker']} would be worth ~**{money(sec_fv)}** ({updown:+.0f}% vs today) — its own P/E is {cur_pe2:.1f}.")
                    pcols = ["Ticker", "Company", "Overall Quant Score", "Conviction Score",
                             "Valuation Score", "Quality Score", "Growth Score", "P/E", "Upside %"]
                    peer_view = combined[[c for c in pcols if c in combined.columns]].head(10)
                    st.dataframe(peer_view, width="stretch")
                    st.caption("Same-sector comparison from your latest scan (this stock included). Higher Valuation Score = cheaper vs peers.")
        with tab2:
            st.subheader("Valuation + Cash Flow")
            val_df = pd.DataFrame([
                {"Metric": "P/E", "Value": row["P/E"], "Why It Matters": "Price relative to earnings."},
                {"Metric": "Forward P/E", "Value": row["Forward P/E"], "Why It Matters": "Price relative to expected earnings."},
                {"Metric": "PEG", "Value": row["PEG"], "Why It Matters": "Valuation adjusted for growth."},
                {"Metric": "EV/EBITDA", "Value": row["EV/EBITDA"], "Why It Matters": "Enterprise value relative to operating cash-like earnings."},
                {"Metric": "EV/FCF", "Value": row["EV/FCF"], "Why It Matters": "Enterprise value relative to free cash flow."},
                {"Metric": "FCF Yield %", "Value": row["FCF Yield %"], "Why It Matters": "Free cash flow return relative to market cap."},
                {"Metric": "FCF Margin %", "Value": row["FCF Margin %"], "Why It Matters": "How much free cash the company keeps from revenue."},
                {"Metric": "FCF Conversion %", "Value": row["FCF Conversion %"], "Why It Matters": "How well operating cash becomes free cash."},
            ])
            st.dataframe(val_df, width="stretch")
            lo, hi = row.get("Fair Value Low"), row.get("Fair Value High")
            central = safe_float(row.get("Fair Value"))
            if lo and hi and central:
                spread = (hi - lo) / central if central else 0
                if spread <= 0.35:
                    conf = "🟢 High agreement — the methods broadly concur, so this fair-value zone is fairly reliable."
                elif spread <= 0.7:
                    conf = "🟡 Moderate disagreement — treat fair value as a wide zone, not a target."
                else:
                    conf = "🔴 Low confidence — the methods disagree sharply, so the fair-value estimate is unreliable for this stock. Lean on the individual factor scores instead."
                st.info(
                    f"**Fair value range: {money(lo)} – {money(hi)}**  (central estimate {money(central)}).  "
                    f"Current price: {money(row['Price'])} · Margin of safety: {row['Margin of Safety %']}%."
                )
                st.caption(f"{conf}")
                st.caption(f"How each method votes → {row.get('Valuation Methods', 'N/A')}")
            else:
                st.info(f"Fair value estimate: {money(row['Fair Value'])}. Margin of safety: {row['Margin of Safety %']}%.")

            st.divider()
            st.markdown("### Valuation vs. its own history")
            st.caption("Is the stock cheap relative to *itself*? Comparing today's P/E to its own multi-year average is a classic mean-reversion check.")
            vh = get_valuation_history(ticker)
            cur_pe = safe_float(row.get("P/E"))
            if not vh or not cur_pe:
                st.info("Not enough P/E history available for this ticker.")
            else:
                avg = vh["avg_pe"]
                vc1, vc2, vc3 = st.columns(3)
                vc1.metric("Current P/E", f"{cur_pe:.1f}")
                vc2.metric("5-yr avg P/E", f"{avg:.1f}")
                disc = (cur_pe - avg) / avg * 100 if avg else 0
                vc3.metric("vs. own history", f"{disc:+.0f}%", delta=f"{-disc:+.0f}%")
                if cur_pe < avg * 0.85:
                    st.success(f"🟢 Trading **below** its own 5-yr average P/E ({cur_pe:.1f} vs {avg:.1f}) — cheaper than its own norm (range {vh['min_pe']}–{vh['max_pe']}).")
                elif cur_pe > avg * 1.15:
                    st.warning(f"🔴 Trading **above** its own 5-yr average P/E ({cur_pe:.1f} vs {avg:.1f}) — richer than its own norm.")
                else:
                    st.info(f"Roughly in line with its own 5-yr average P/E ({cur_pe:.1f} vs {avg:.1f}).")
                hist_fig = go.Figure(go.Bar(x=[y for y, _ in vh["points"]], y=[p for _, p in vh["points"]],
                                            marker_color="#2b6f63", name="Annual P/E"))
                hist_fig.add_hline(y=cur_pe, line_dash="dash", line_color=ACCENT,
                                   annotation_text="current", annotation_font_color=ACCENT)
                hist_fig.update_yaxes(title="P/E", gridcolor=CHART_GRID)
                hist_fig.update_xaxes(gridcolor=CHART_GRID)
                st.plotly_chart(_style_fig(hist_fig, height=300), width="stretch")
                st.caption("⚠️ 'Cheap vs its own history' only helps if the business hasn't deteriorated — a falling multiple can be justified. Cross-check with the 5-year trends tab.")

            st.divider()
            st.markdown("### Reverse DCF — what growth is priced in?")
            st.caption("Instead of guessing fair value, this solves for the FCF growth rate the *current price* already assumes. If that's higher than the company can realistically deliver, the stock is expensive.")
            fcf_ps_dd = (safe_float(row.get("FCF Yield %"), 0) / 100) * safe_float(row.get("Price"), 0)
            implied = reverse_dcf_growth(row.get("Price"), fcf_ps_dd, row.get("Beta"))
            if implied is None:
                st.caption("Reverse DCF needs positive free cash flow — not meaningful for this stock.")
            else:
                hist_g = safe_float(row.get("Revenue Growth %"))
                rr = capm_rate(row.get("Beta"))
                st.write(f"At today's price, the market is pricing in **~{implied*100:.0f}%/yr** free-cash-flow growth for the next 5 years (discounting at a {rr*100:.1f}% CAPM rate).")
                if hist_g is not None:
                    if implied * 100 > hist_g + 8:
                        st.warning(f"🔴 That's **well above** its recent revenue growth (~{hist_g:.0f}%). The price assumes acceleration — a high bar to clear.")
                    elif implied * 100 < hist_g - 5:
                        st.success(f"🟢 That's **below** its recent revenue growth (~{hist_g:.0f}%). The market is pricing in a slowdown — potential value if growth holds.")
                    else:
                        st.info(f"That's roughly in line with its recent revenue growth (~{hist_g:.0f}%) — the price looks reasonable on growth expectations.")

                # Sustainable-growth reality check (Damodaran): can the business FUND this growth?
                roe_f = safe_float(row.get("ROE %"))
                payout_f = safe_float(row.get("Payout Ratio %"))
                if roe_f is not None:
                    sg = sustainable_growth(roe_f / 100, (payout_f / 100) if payout_f is not None else 0.0)
                    if sg is not None:
                        st.caption(
                            f"**Fundable (sustainable) growth ≈ {sg*100:.0f}%/yr** — that's what the business can self-fund "
                            f"(ROE {roe_f:.0f}% × retention). "
                            + ("🔴 The price implies *more* growth than the company can fund from its own returns — it must either raise capital or exceed its historical efficiency."
                               if implied * 100 > sg * 100 + 3
                               else "🟢 The implied growth is within what the business can fund internally — a realistic, self-financing path.")
                        )

            # ---- Normalized (cyclically-adjusted) earnings ----
            price_now = safe_float(row.get("Price"))
            st.divider()
            st.markdown("### Normalized earnings check")
            st.caption("A single boom/bust year distorts P/E. Normalizing to the company's *average* margin shows whether current earnings (and today's P/E) are unusually high or low.")
            tnorm = get_fundamental_trends(ticker)
            cur_pe3 = safe_float(row.get("P/E"))
            if tnorm is None or "Net Margin %" not in tnorm.columns or not cur_pe3:
                st.caption("Not enough margin history to normalize for this stock.")
            else:
                nm = tnorm["Net Margin %"].dropna()
                if len(nm) >= 3:
                    avg_m, cur_m = float(nm.mean()), float(nm.iloc[-1])
                    if cur_m and cur_m != 0:
                        norm_eps = (price_now / cur_pe3) * (avg_m / cur_m)  # scale EPS by margin normalcy
                        norm_pe = price_now / norm_eps if norm_eps else None
                        n1, n2, n3 = st.columns(3)
                        n1.metric("Current P/E", f"{cur_pe3:.1f}")
                        n2.metric("Normalized P/E", f"{norm_pe:.1f}" if norm_pe else "N/A",
                                  help="P/E if earnings were at the company's average margin.")
                        n3.metric("Margin now vs avg", f"{cur_m:.0f}% vs {avg_m:.0f}%")
                        if cur_m > avg_m * 1.15:
                            st.warning(f"🔴 Current margin ({cur_m:.0f}%) is **above** its average ({avg_m:.0f}%) — earnings may be peaking, so the real (normalized) P/E is higher (~{norm_pe:.0f}). The stock may be more expensive than it looks.")
                        elif cur_m < avg_m * 0.85:
                            st.success(f"🟢 Current margin ({cur_m:.0f}%) is **below** its average ({avg_m:.0f}%) — earnings may be depressed, so normalized P/E is lower (~{norm_pe:.0f}). Could be cheaper than it looks if margins recover.")
                        else:
                            st.info("Current margin is near its historical average — reported earnings look representative.")

            # ---- Bull / base / bear scenario valuation ----
            st.divider()
            st.markdown("### Scenario valuation (bull / base / bear)")
            st.caption("Fair value isn't one number. Here's the DCF under three growth scenarios so you see the plausible range.")
            fcf_ps_s = (safe_float(row.get("FCF Yield %"), 0) / 100) * price_now
            base_g = min(max(safe_float(row.get("Revenue Growth %"), 6) / 100, 0.0), 0.16)
            rr_s = capm_rate(row.get("Beta"))
            if fcf_ps_s and fcf_ps_s > 0:
                scenarios = [("🐻 Bear", max(base_g - 0.05, -0.02)), ("● Base", base_g), ("🐂 Bull", base_g + 0.05)]
                sc = st.columns(3)
                for i, (label, g) in enumerate(scenarios):
                    v = dcf_3stage(fcf_ps_s, g, rr_s)
                    up = (v - price_now) / price_now * 100 if (v and price_now) else None
                    sc[i].metric(f"{label} ({g*100:.0f}% gr)", money(v) if v else "N/A",
                                 f"{up:+.0f}%" if up is not None else None)
                st.caption(f"Discounted at a {rr_s*100:.1f}% CAPM rate. The spread between bear and bull is your uncertainty — a wide gap means the valuation hinges heavily on growth assumptions.")

                # ---- Monte Carlo: full distribution of fair value ----
                st.divider()
                st.markdown("### Monte Carlo valuation (3,000 simulations)")
                st.caption("Runs thousands of DCFs with randomized growth, discount rate, terminal rate & starting FCF — turning fair value into a *probability distribution* and estimating the odds the stock is undervalued.")
                seed = sum(ord(c) for c in ticker) if ticker else 0
                mc = monte_carlo_dcf(fcf_ps_s, base_g, row.get("Beta"), seed=seed)
                if mc is None:
                    st.caption("Not enough valid simulations (needs positive free cash flow).")
                else:
                    import numpy as np
                    p10, p50, p90 = np.percentile(mc, [10, 50, 90])
                    prob_under = float((mc > price_now).mean() * 100) if price_now else 0
                    q1, q2, q3 = st.columns(3)
                    q1.metric("Median fair value", money(p50))
                    q2.metric("80% range", f"{money(p10)} – {money(p90)}")
                    q3.metric("Odds undervalued", f"{prob_under:.0f}%",
                              help="Share of simulations where fair value exceeds today's price.")
                    if prob_under >= 70:
                        st.success(f"🟢 In **{prob_under:.0f}%** of simulations the stock is worth more than today's price — the odds favor undervaluation.")
                    elif prob_under <= 30:
                        st.warning(f"🔴 Only **{prob_under:.0f}%** of simulations put fair value above the price — the odds lean overvalued.")
                    else:
                        st.info(f"About **{prob_under:.0f}%** of simulations show it undervalued — genuinely a coin-flip; the price is roughly fair given the uncertainty.")
                    clipped = mc[(mc >= np.percentile(mc, 1)) & (mc <= np.percentile(mc, 99))]
                    fig_mc = go.Figure(go.Histogram(x=clipped, nbinsx=40, marker_color="#2b6f63"))
                    if price_now:
                        fig_mc.add_vline(x=price_now, line_dash="dash", line_color=ACCENT,
                                         annotation_text="price", annotation_font_color=ACCENT)
                    fig_mc.update_xaxes(title="Simulated fair value / share ($)", gridcolor=CHART_GRID)
                    fig_mc.update_yaxes(title="Simulations", gridcolor=CHART_GRID)
                    st.plotly_chart(_style_fig(fig_mc, height=320), width="stretch")
                    st.caption("The width of the distribution is the honest uncertainty. A tall, narrow peak far above the price = a confident buy signal; a wide smear straddling the price = genuinely uncertain.")
            else:
                st.caption("Scenario DCF needs positive free cash flow — not applicable here.")
        with tab3:
            st.subheader("Quality + Health")
            health_df = pd.DataFrame([
                {"Metric": "Quality Score", "Value": row["Quality Score"], "Meaning": "Margins, ROE, ROIC proxy, profitability."},
                {"Metric": "Cash Flow Score", "Value": row["Cash Flow Score"], "Meaning": "FCF yield, margins, conversion."},
                {"Metric": "Financial Strength Score", "Value": row["Financial Strength Score"], "Meaning": "Debt, liquidity, cash/debt."},
                {"Metric": "Earnings Quality Score", "Value": row["Earnings Quality Score"], "Meaning": "Growth plus cash conversion and profitability."},
                {"Metric": "ROIC Proxy %", "Value": row["ROIC Proxy %"], "Meaning": "Approximate capital efficiency."},
                {"Metric": "ROE %", "Value": row["ROE %"], "Meaning": "Return on shareholder equity."},
                {"Metric": "Debt/Equity", "Value": row["Debt/Equity"], "Meaning": "Debt burden."},
                {"Metric": "Net Debt/EBITDA", "Value": row["Net Debt/EBITDA"], "Meaning": "Debt compared to earnings power."},
            ])
            st.dataframe(health_df, width="stretch")

            st.divider()
            st.markdown("### 5-Year Fundamental Trends")
            st.caption("Is the business actually improving, or just cheap? Trajectory matters as much as the snapshot.")
            tdf = get_fundamental_trends(ticker)
            if tdf is None or len(tdf) < 2:
                st.info("Multi-year financials aren't available for this ticker.")
            else:
                # summary read
                rev = tdf["Revenue ($B)"].dropna()
                nm = tdf["Net Margin %"].dropna()
                fcf = tdf["FCF ($B)"].dropna()
                bits = []
                if len(rev) >= 2 and rev.iloc[0] > 0:
                    yrs = len(rev) - 1
                    cagr = ((rev.iloc[-1] / rev.iloc[0]) ** (1 / yrs) - 1) * 100 if yrs else 0
                    bits.append(f"Revenue { 'growing' if cagr>1 else 'flat/declining'} (~{cagr:.0f}%/yr over {yrs}y)")
                if len(nm) >= 2:
                    d = nm.iloc[-1] - nm.iloc[0]
                    bits.append(f"net margin {'expanding' if d>0.5 else 'contracting' if d<-0.5 else 'stable'} ({nm.iloc[0]:.0f}%→{nm.iloc[-1]:.0f}%)")
                if len(fcf) >= 2:
                    bits.append(f"FCF {'rising' if fcf.iloc[-1]>fcf.iloc[0] else 'falling/flat'}")
                if bits:
                    st.write("**Trajectory:** " + " · ".join(bits) + ".")
                g1, g2 = st.columns(2)
                with g1:
                    st.plotly_chart(revenue_margin_chart(tdf), width="stretch")
                with g2:
                    st.plotly_chart(margins_trend_chart(tdf), width="stretch")
                with st.expander("Year-by-year detail"):
                    st.dataframe(tdf.set_index("Year"), width="stretch")

            st.divider()
            st.markdown("### Dividend Safety")
            ds = dividend_safety(row, get_dividend_growth(ticker))
            if ds is None:
                st.caption(f"{ticker} doesn't pay a meaningful dividend — nothing to assess here.")
            else:
                d1, d2, d3 = st.columns(3)
                d1.metric("Dividend Safety", f"{ds['score']:.0f}/100", ds["verdict"])
                d2.metric("Yield", f"{ds['yield']:.2f}%")
                d3.metric("Payout ratio", f"{ds['payout']:.0f}%" if ds["payout"] is not None else "N/A",
                          help="Share of earnings paid as dividends. Under ~60% is comfortable.")
                render_score_bars(ds["components"])
                bits = []
                if ds["streak"]:
                    bits.append(f"{ds['streak']} straight years of dividend growth")
                if ds.get("cut"):
                    bits.append("⚠️ has cut its dividend before")
                if ds["ndte"] is not None:
                    bits.append(f"net debt/EBITDA {ds['ndte']:.1f}")
                if bits:
                    st.caption(" · ".join(bits) + ".")
                st.caption("Standard payout/cash-flow/balance-sheet methodology — the higher the score, the more comfortably the company can keep (and grow) the dividend.")
        with tab8:
            st.subheader("Analyst & Forward View")
            st.caption("Forward-looking Wall Street consensus (Yahoo Finance). Complements the engine's trailing-data valuation with what analysts expect ahead.")
            a = get_analyst_data(ticker)
            price_now = safe_float(row.get("Price")) or a.get("current")
            if not a.get("target_mean") and not a.get("forward_pe"):
                st.info("No analyst coverage data available for this ticker.")
            else:
                rating_map = {
                    "strong_buy": "🟢 Strong Buy", "buy": "🟢 Buy", "hold": "🟡 Hold",
                    "underperform": "🔴 Underperform", "sell": "🔴 Sell",
                }
                rating = rating_map.get(str(a.get("rating")), str(a.get("rating") or "N/A").replace("_", " ").title())
                x1, x2, x3 = st.columns(3)
                x1.metric("Consensus Rating", rating,
                          f"{a['n_analysts']:.0f} analysts" if a.get("n_analysts") else None)
                tgt = a.get("target_mean")
                if tgt and price_now:
                    tgt_upside = (tgt - price_now) / price_now * 100
                    x2.metric("Avg Price Target", money(tgt), f"{tgt_upside:+.0f}% vs price")
                else:
                    x2.metric("Avg Price Target", money(tgt) if tgt else "N/A")
                x3.metric("Target Range", f"{money(a.get('target_low'))} – {money(a.get('target_high'))}")

                y1, y2, y3 = st.columns(3)
                y1.metric("Forward P/E", f"{a['forward_pe']:.1f}" if a.get("forward_pe") else "N/A")
                y2.metric("Forward EPS", money(a.get("forward_eps")))
                if a.get("eps_growth_next_y") is not None:
                    y3.metric("Est. EPS growth (next yr)", f"{a['eps_growth_next_y'] * 100:+.0f}%")
                else:
                    y3.metric("Est. EPS growth (next yr)", "N/A")

                # Two independent views side by side
                st.markdown("**Two independent views of value:**")
                dcf_fv = safe_float(row.get("Fair Value"))
                st.write(
                    f"- 🧮 **Engine fair value (DCF/multiples, trailing):** {money(dcf_fv)}"
                    + (f"  → {((dcf_fv-price_now)/price_now*100):+.0f}%" if dcf_fv and price_now else "")
                )
                st.write(
                    f"- 👔 **Analyst avg target (~12-mo, forward):** {money(tgt)}"
                    + (f"  → {((tgt-price_now)/price_now*100):+.0f}%" if tgt and price_now else "")
                )
                if a.get("forward_pe") and row.get("P/E"):
                    fpe, tpe = a["forward_pe"], safe_float(row.get("P/E"))
                    if tpe:
                        cheaper = "cheaper" if fpe < tpe else "richer"
                        st.caption(f"Forward P/E ({fpe:.1f}) is {cheaper} than trailing P/E ({tpe:.1f}) — analysts expect earnings to {'grow' if fpe < tpe else 'fall'}.")
                st.caption("⚠️ Analyst targets are ~12-month price targets, tend to run optimistic, and reflect sentiment — treat as one input, not truth. When the engine and analysts disagree sharply, that's a flag to dig deeper.")

            st.divider()
            st.markdown("### Forward signals")
            fs = get_forward_signals(ticker)
            nxt = get_next_earnings(ticker)
            f1, f2, f3 = st.columns(3)
            # Estimate revisions momentum
            if fs.get("rev_label"):
                f1.metric("Estimate Revisions (30d)", fs["rev_label"],
                          f"{int(fs['rev_up'])} up / {int(fs['rev_down'])} down")
            else:
                f1.metric("Estimate Revisions (30d)", "N/A")
            # Earnings surprise track record
            if fs.get("beat_rate") is not None:
                f2.metric("Earnings Beat Rate", f"{fs['beat_rate']}%",
                          f"avg surprise {fs['avg_surprise']:+.1f}% ({fs['quarters']}q)")
            else:
                f2.metric("Earnings Beat Rate", "N/A")
            f3.metric("Next Earnings", nxt or "N/A")

            # Plain-English reads (with honest caveats)
            if fs.get("rev_net") is not None:
                if fs["rev_net"] > 0:
                    st.caption("🟢 Analysts are **raising** next-year EPS estimates — 'revisions momentum' is one of the more reliable forward signals (estimates tend to move in trends).")
                elif fs["rev_net"] < 0:
                    st.caption("🔴 Analysts are **cutting** next-year EPS estimates — a caution sign; downward revisions often continue.")
            if fs.get("beat_rate") is not None and fs["beat_rate"] >= 75:
                st.caption(f"🟢 Strong track record: beat estimates in ~{fs['beat_rate']}% of the last {fs['quarters']} quarters. Consistent beats can drift the stock up post-earnings (PEAD).")

            # Forward-looking fair value (forward EPS x justified P/E)
            fwd_eps = a.get("forward_eps")
            if fwd_eps and fwd_eps > 0:
                q, g = safe_float(row.get("Quality Score"), 50), safe_float(row.get("Growth Score"), 50)
                fair_pe = 18
                if q >= 80 and g >= 75:
                    fair_pe = 30
                elif q >= 70 and g >= 60:
                    fair_pe = 24
                elif q < 45:
                    fair_pe = 14
                fwd_fv = fwd_eps * fair_pe
                fwd_up = (fwd_fv - price_now) / price_now * 100 if price_now else None
                st.markdown("**Forward-looking fair value** (next-year EPS × a quality/growth-justified P/E):")
                st.write(
                    f"- 🔮 Forward fair value: **{money(fwd_fv)}**"
                    + (f"  → {fwd_up:+.0f}% vs price" if fwd_up is not None else "")
                    + f"  (fwd EPS {money(fwd_eps)} × {fair_pe}x)"
                )
                st.caption("This uses analysts' *forward* EPS instead of trailing earnings — a future-facing complement to the engine's trailing DCF. Both are estimates; agreement between them is the encouraging case.")

            st.divider()
            st.markdown("### Smart-money activity")
            st.caption("Who owns it, and are insiders buying or selling? Insider *buying* is a mild positive signal (they know the business); selling is noisier (often just diversification).")
            own = get_ownership_activity(ticker)
            o1, o2, o3 = st.columns(3)
            o1.metric("Institutional ownership", f"{own['inst_pct']*100:.0f}%" if own.get("inst_pct") is not None else "N/A",
                      f"{int(own['inst_count'])} holders" if own.get("inst_count") else None)
            o2.metric("Insider ownership", f"{own['insider_pct']*100:.1f}%" if own.get("insider_pct") is not None else "N/A")
            buys, sells = own.get("insider_buys", 0), own.get("insider_sells", 0)
            o3.metric("Insider trades (6mo)", f"{buys} buys / {sells} sells")
            if buys or sells:
                if buys > sells:
                    st.success(f"🟢 Net insider **buying** over the last 6 months ({buys} buys vs {sells} sells) — insiders putting money in is a mild positive.")
                elif sells > buys * 2 and sells >= 3:
                    st.caption(f"Insiders net sellers ({sells} sells vs {buys} buys) — common and often just diversification/comp, but worth noting.")
        with tab4:
            st.subheader("Momentum + Why Moving")
            if move:
                a, b, c, d = st.columns(4)
                a.metric("1-Day Move", f"{move['1-Day Move %']}%")
                b.metric("5-Day Move", f"{move['5-Day Move %']}%")
                c.metric("Volume Ratio", f"{move['Volume Ratio']}x")
                d.metric("Move Tone", move["Move Tone"])
                st.write("**Possible Reasons:**")
                for reason in move["Possible Reasons"]:
                    st.write(f"- {reason}")
            momentum_df = pd.DataFrame([
                {"Metric": "1M Return %", "Value": row["1M Return %"]},
                {"Metric": "3M Return %", "Value": row["3M Return %"]},
                {"Metric": "6M Return %", "Value": row["6M Return %"]},
                {"Metric": "12M Return %", "Value": row["12M Return %"]},
                {"Metric": "Relative Strength 6M %", "Value": row["Relative Strength 6M %"]},
                {"Metric": "Relative Strength 12M %", "Value": row["Relative Strength 12M %"]},
                {"Metric": "Volatility %", "Value": row["Volatility %"]},
                {"Metric": "Max Drawdown %", "Value": row["Max Drawdown %"]},
            ])
            st.dataframe(momentum_df, width="stretch")
            st.subheader("Recent Yahoo Finance News")
            if not ticker_news:
                st.info("No recent Yahoo Finance headlines found for this ticker.")
            for article in ticker_news[:8]:
                with st.container(border=True):
                    st.markdown(f"### [{article['Title']}]({article['URL']})")
                    st.write(f"**Signal:** {article['Signal']} | **Importance:** {article['Importance']}/10 | **Category:** {article['Category']}")
                    st.write(f"**Source:** {article['Provider']} | **Published:** {article['Published'].strftime('%Y-%m-%d %I:%M %p UTC')}")
                    if article["Summary"]:
                        st.write(article["Summary"])
        with tab5:
            st.subheader("Bull Case")
            for item in bull:
                st.write(f"- {item}")
            st.subheader("Bear Case")
            for item in bear:
                st.write(f"- {item}")
            st.subheader("Research Decision")
            st.write(f"**Action:** {row['Research Action']}")
            st.write(f"**Suggested hold:** {row['Suggested Hold']}")
            st.write(f"**Suggested sell/trim target:** {money(row['Sell Target'])}")
        with tab6:
            st.subheader("🤖 AI Research Analyst")
            st.caption("An LLM turns the quant scores + headlines above into a plain-English memo. Research aid only — not financial advice.")
            if not ai_available():
                st.info(
                    "**AI summaries are turned off.** To enable, add your OpenAI API key:\n\n"
                    "- **Local:** create a file named `.env` in the app folder with a line "
                    "`OPENAI_API_KEY=sk-...` (optionally `OPENAI_MODEL=gpt-4o-mini`), then restart.\n"
                    "- **Deployed (Streamlit Cloud):** add `OPENAI_API_KEY` under the app's Secrets."
                )
            else:
                st.caption(f"Model: `{AI_MODEL}`")
                if st.button("Generate AI Research Summary", type="primary", key="ai_deepdive"):
                    with st.spinner("The AI analyst is reading the numbers..."):
                        payload = build_ai_payload(row, ticker_news)
                        memo = generate_ai_research_summary(ai_signature(row), payload)
                    if memo:
                        st.markdown(memo)
                    else:
                        st.warning("Could not generate a summary. Check your API key and model name.")
        with tab7:
            st.subheader("How to read the important metrics")
            guide = [
                ("Investment Score", "Long-term wealth-building quality. High means the business may be worth holding for years."),
                ("Opportunity Score", "Undervaluation and upside potential. High means the stock may be mispriced."),
                ("Position Trade Score", "3-6 month setup. High means momentum, news, and relative strength look supportive."),
                ("Health Score", "Business health. High means strong quality, cash flow, debt, and earnings quality."),
                ("FCF Yield", "Free cash flow divided by market cap. Higher means more cash generation for the price."),
                ("ROIC Proxy", "Approximate return on invested capital. Higher means better capital efficiency."),
                ("Relative Strength", "Stock performance compared to SPY. Positive means it is beating the market."),
                ("EV/FCF", "Enterprise value divided by free cash flow. Lower can mean cheaper."),
            ]
            for name, explanation in guide:
                with st.expander(name):
                    st.write(explanation)



def backtesting_page():
    st.title("Backtesting Lab")
    st.caption("Does the engine's ranking actually predict future returns? Test it honestly here.")

    score_choices = [
        "Overall Quant Score", "Investment Score", "Opportunity Score", "Position Trade Score",
        "Health Score", "Expected Return Score", "Quality Score", "Cash Flow Score",
        "Valuation Score", "Growth Score", "Relative Strength Score", "Risk Score",
    ]

    honest_tab, efficacy_tab, illustrative_tab = st.tabs([
        "✅ Point-in-Time (honest)",
        "🔬 Factor Efficacy",
        "⚠️ Illustrative (in-sample)",
    ])

    # ---------------- FACTOR EFFICACY: does the scoring predict returns? ----------------
    with efficacy_tab:
        st.success(
            "**Does the engine actually work?** This measures whether each score *predicted* "
            "the returns that followed. For every past snapshot in your history it computes the "
            "**Information Coefficient** (rank correlation of score vs. real forward return) and "
            "the **top-⅓ minus bottom-⅓** return spread. Positive = the factor ranked winners "
            "above losers."
        )
        st.caption(
            "How to read IC: 0 = no predictive power; 0.05–0.15 is respectable for a single "
            "factor; negative means it pointed the wrong way. This grows trustworthy as more "
            "weekly snapshots accumulate — with only a few so far, treat it as an early signal."
        )
        end_e = st.text_input("Measure forward returns up to (YYYY-MM-DD)", today_string(), key="eff_end")
        if st.button("Analyze Factor Efficacy", type="primary"):
            with st.spinner("Measuring which factors predicted returns..."):
                out = run_factor_efficacy(end_e)
            if not out:
                st.warning("Not enough history yet. Run scans on multiple days (the weekly job does this) so there are past snapshots to test.")
            else:
                res_df, n_snaps, n_obs = out
                st.caption(f"Based on {n_snaps} snapshot date(s) and {n_obs} stock-observations.")
                best = res_df.iloc[0]
                if safe_float(best["Predictive power (IC)"], 0) > 0.05:
                    st.success(f"Best predictor so far: **{best['Factor']}** (IC {best['Predictive power (IC)']}, top−bottom {best['Top − Bottom %']}%). Encouraging early sign.")
                elif safe_float(best["Predictive power (IC)"], 0) > 0:
                    st.info("Factors show weakly positive predictive power so far — promising but not yet conclusive.")
                else:
                    st.warning("No factor shows positive predictive power in this (small) window. That's honest feedback — let more snapshots accumulate before drawing conclusions.")
                st.dataframe(res_df, width="stretch")
                st.caption("Top − Bottom %: return of the highest-scored third minus the lowest-scored third. A consistently positive value across many snapshots is what 'the engine works' looks like.")

    # ---------------- HONEST, OUT-OF-SAMPLE BACKTEST ----------------
    with honest_tab:
        st.success(
            "**This is the trustworthy test.** It ranks stocks using only the scores you had "
            "on a past scan date, then measures the real return that happened *after* that date. "
            "No future information leaks in, so a positive result actually means something."
        )
        history = load_history()
        if history.empty or "Scan Date" not in history.columns:
            st.warning("No score history yet. Run scans in the Quant Opportunity Engine on different days — each saved scan becomes a point-in-time snapshot you can test.")
        else:
            dates = sorted(history["Scan Date"].dropna().astype(str).unique())
            if len(dates) == 0:
                st.warning("No dated snapshots found in the score history.")
            else:
                col1, col2 = st.columns(2)
                with col1:
                    start_date = st.selectbox("Rank using scores as of (past scan date)", dates, index=0)
                    rank_by = st.selectbox("Rank stocks by", score_choices, key="pit_rank")
                with col2:
                    end_date = st.text_input("Measure returns up to (YYYY-MM-DD)", today_string())
                    top_n = st.slider("Top stocks to test", 3, 30, 10, key="pit_topn")

                st.caption(f"Snapshots available: {', '.join(dates)}")

                if st.button("Run Honest Backtest", type="primary"):
                    if str(end_date) <= str(start_date):
                        st.error("The end date must be AFTER the snapshot date.")
                    else:
                        with st.spinner("Measuring real forward returns..."):
                            result_df, summary, status = run_pointintime_backtest(rank_by, top_n, start_date, end_date)
                        if status != "ok" or result_df.empty:
                            st.warning("Couldn't run this test — no matching snapshot or no forward price data available.")
                        else:
                            st.subheader(f"Forward Results: {start_date} → {end_date}")
                            c1, c2, c3 = st.columns(3)
                            c1.metric("Your Top Picks Return", f"{summary['Portfolio Return %']}%")
                            c2.metric("SPY Return", f"{summary['SPY Return %']}%")
                            c3.metric("Excess vs SPY", f"{summary['Excess vs SPY %']}%",
                                      delta=f"{summary['Excess vs SPY %']}%")
                            c4, c5, c6 = st.columns(3)
                            c4.metric("Win Rate", f"{summary['Win Rate %']}%")
                            c5.metric("Beat SPY Rate", f"{summary['Beat SPY Rate %']}%")
                            c6.metric("Stocks Tested", summary["Stocks Tested"])

                            excess = summary["Excess vs SPY %"]
                            if excess is not None and excess > 0:
                                st.success(f"Ranking by **{rank_by}** beat SPY by {excess}% over this window. Encouraging — but one window is not proof. Repeat as more snapshots accumulate.")
                            elif excess is not None:
                                st.warning(f"Ranking by **{rank_by}** trailed SPY by {abs(excess)}% over this window. That's useful, honest feedback.")
                            st.dataframe(result_df, width="stretch")
                            st.caption("Only ~1 snapshot exists so far, so windows are short. The more days you run scans, the more robust this becomes.")

    # ---------------- ILLUSTRATIVE (IN-SAMPLE) BACKTEST ----------------
    with illustrative_tab:
        st.error(
            "**Read this first — this test has lookahead bias.** It ranks stocks by their "
            "scores *today* and then measures how they did *in the past*. Because you already "
            "know how the past turned out, this will almost always look like it 'beats the "
            "market' — but it proves nothing about future performance. Use it only to eyeball "
            "the relationship between a factor and past returns, never as evidence the engine works."
        )
        df = load_sp500_scores()
        if df.empty:
            st.warning("No saved quant scan found. Go to Quant Opportunity Engine and run a scan first.")
        else:
            df = normalize_scores_df(df)
            col1, col2, col3 = st.columns(3)
            with col1:
                rank_by2 = st.selectbox("Rank stocks by", score_choices, key="insample_rank")
            with col2:
                top_n2 = st.slider("Top stocks to test", 5, min(50, len(df)), 10, key="insample_topn")
            with col3:
                period = st.selectbox("Lookback period", ["3mo", "6mo", "1y", "2y"], index=2)

            sector = st.selectbox("Sector filter", ["All"] + sorted(df["Sector"].dropna().unique().tolist()))
            if sector != "All":
                df = df[df["Sector"] == sector]

            if st.button("Run Illustrative Test", key="insample_btn"):
                with st.spinner("Running illustrative in-sample test..."):
                    result_df, summary = run_simple_backtest(df, rank_by2, top_n2, period)
                if result_df.empty:
                    st.warning("No valid price data found.")
                else:
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Avg Return", f"{summary['Average Return %']}%")
                    c2.metric("SPY Return", f"{summary['SPY Return %']}%")
                    c3.metric("Excess vs SPY", f"{summary['Excess Return vs SPY %']}%")
                    c4.metric("Win Rate", f"{summary['Win Rate %']}%")
                    st.dataframe(result_df, width="stretch")
                    st.caption("Reminder: this is in-sample and lookahead-biased. Treat the honest tab as the real scoreboard.")



def learning_center():
    st.title("Learning Center")
    st.caption("Clear explanations for the quant statistics used by the engine.")
    topics = {
        "Investment Score": ("A composite score measuring long-term business quality, cash flow, growth, financial strength, earnings quality, and risk.", "Use this to find stocks that may be strong long-term wealth builders.", "80+ is strong. Below 60 means the long-term setup is weaker.", "Best for finding compounders."),
        "Opportunity Score": ("A composite score focused on valuation, fair value upside, cash flow, quality, and growth.", "Use this to find stocks that may be undervalued.", "80+ means the stock deserves valuation research.", "Best for finding mispriced companies."),
        "Position Trade Score": ("A composite score focused on momentum, relative strength, earnings quality, news sentiment, and risk.", "Use this for 3-6 month setups.", "80+ means short-to-medium-term conditions look favorable.", "Best for timing and market confirmation."),
        "Health Score": ("A composite of quality, cash flow, financial strength, and earnings quality.", "Use this to avoid weak businesses and value traps.", "80+ means strong business health. Below 50 means caution.", "A high health score separates cheap stocks from good stocks."),
        "FCF Yield": ("Free cash flow divided by market capitalization.", "Shows how much cash the company generates compared to what investors pay.", "Higher is usually better. 5%+ can be attractive, but depends on growth.", "One of the best valuation metrics."),
        "ROIC Proxy": ("Approximate return on invested capital using available Yahoo Finance data.", "Shows how efficiently the company turns capital into profits.", "10%+ is solid. 15%+ is strong.", "Great businesses usually earn high returns on capital."),
        "EV/FCF": ("Enterprise value divided by free cash flow.", "Shows how expensive the business is compared to cash flow.", "Lower is cheaper. High EV/FCF needs strong growth to justify.", "Better than P/E for many companies because it includes debt and cash."),
        "Relative Strength": ("A stock’s return compared to SPY over a period.", "Shows whether the stock is beating or lagging the market.", "Positive is good. Negative means underperformance.", "Important for position trades and spotting early winners."),
        "Earnings Quality": ("A score blending earnings growth, cash conversion, margins, and revenue growth.", "Helps detect whether earnings are backed by real business performance.", "Higher is better. Low earnings quality can signal fragile profits.", "Useful for avoiding weak or low-quality earnings."),
        "Risk Score": ("Measures beta, volatility, drawdown, and debt risk.", "Higher means lower risk by this model.", "80+ is safer. Below 50 means elevated risk.", "Useful for position sizing and avoiding blowups."),
        "Conviction Score": ("Measures how confident the engine is that this stock deserves research.", "Use this as your first research-priority signal.", "80+ means high conviction. Below 60 means weaker conviction.", "Best for deciding what to research first."),
        "Evidence Score": ("Measures how many independent factors agree.", "High evidence means valuation, quality, cash flow, growth, and momentum are aligned.", "80+ means many factors agree. Below 50 means conflict.", "Best for avoiding confusing or low-quality signals."),
        "Research Priority": ("Final ranking score for the Research Queue.", "It blends conviction, evidence, expected return, opportunity, and investment strength.", "Higher means research first.", "Best for answering: what should I research today?"),
    }
    tab1, tab2, tab3 = st.tabs(["Search", "Course", "Playbooks"])
    with tab1:
        query = st.text_input("Search a concept", "")
        if query:
            found = False
            for topic, data in topics.items():
                if query.lower() in topic.lower() or query.lower() in str(data).lower():
                    found = True
                    with st.container(border=True):
                        st.subheader(topic)
                        st.write(f"**College explanation:** {data[0]}")
                        st.write(f"**Investor explanation:** {data[1]}")
                        st.write(f"**Good vs bad:** {data[2]}")
                        st.write(f"**How to use it:** {data[3]}")
            if not found:
                st.warning("No exact match. Try Investment Score, FCF Yield, ROIC, EV/FCF, Relative Strength, or Risk Score.")
    with tab2:
        for topic, data in topics.items():
            with st.expander(topic):
                st.write(f"**College:** {data[0]}")
                st.write(f"**Investor:** {data[1]}")
                st.write(f"**Good vs bad:** {data[2]}")
                st.write(f"**Use:** {data[3]}")
    with tab3:
        st.subheader("Compounder Playbook")
        st.write("- Investment Score 80+")
        st.write("- Health Score 80+")
        st.write("- Strong ROIC proxy")
        st.write("- Strong FCF margin")
        st.write("- Reasonable valuation")
        st.subheader("Undervalued Opportunity Playbook")
        st.write("- Opportunity Score 80+")
        st.write("- Valuation Score 70+")
        st.write("- Positive margin of safety")
        st.write("- Health Score not terrible")
        st.write("- Look for improving news or momentum")
        st.subheader("Position Trade Playbook")
        st.write("- Position Trade Score 80+")
        st.write("- Relative Strength 70+")
        st.write("- Momentum Score 70+")
        st.write("- News sentiment not negative")
        st.write("- Clear sell/trim target")
        st.subheader("Avoiding Value Traps")
        st.write("- Cheap valuation but weak Health Score")
        st.write("- Weak cash flow")
        st.write("- High debt")
        st.write("- Bad margins")
        st.write("- Weak or negative relative strength")


def watchlist_page():
    st.title("My Watchlist")
    st.caption("Your saved names, front and center — with alerts flagging what needs attention today.")

    tickers = load_watchlist()

    with st.expander("✏️ Edit watchlist", expanded=not tickers):
        col_a, col_b = st.columns([2, 1])
        with col_a:
            new_t = st.text_input("Add ticker(s) — comma-separated", "", placeholder="e.g. NVDA, COST, JPM")
        with col_b:
            st.write("")
            st.write("")
            if st.button("➕ Add", width="stretch"):
                add = [x.strip().upper() for x in new_t.replace(";", ",").split(",") if x.strip()]
                tickers = save_watchlist(tickers + add)
                st.rerun()
        if tickers:
            remove = st.multiselect("Remove tickers", tickers)
            if remove and st.button("🗑️ Remove selected"):
                tickers = save_watchlist([t for t in tickers if t not in remove])
                st.rerun()
        if tickers:
            st.caption("💾 Your list is saved to this page's URL — **bookmark this page** to keep it across reboots and devices. Backup code below:")
            st.code(",".join(tickers), language=None)
            restore = st.text_input("Restore from a backup code", "", key="wl_restore")
            if restore and st.button("Restore"):
                save_watchlist([x.strip().upper() for x in restore.replace(";", ",").split(",") if x.strip()])
                st.rerun()

    if not tickers:
        st.info("Your watchlist is empty. Add a few tickers above to start tracking them.")
        return

    st.write(f"**Tracking {len(tickers)}:** {', '.join(tickers)}")
    if not st.button("Analyze Watchlist", type="primary"):
        st.caption("Click **Analyze Watchlist** to pull the latest scores and alerts.")
        return

    with st.spinner("Scoring your watchlist..."):
        df, live = build_watchlist_analysis(tickers)

    if df.empty:
        st.warning("Couldn't score any of your watchlist tickers. Check the symbols.")
        return
    df = enhance_research_columns(df)
    if "Conviction Change" not in df.columns:
        df = add_score_change(df)

    # ----- Alerts summary -----
    st.subheader("🔔 Alerts")
    any_alert = False
    for _, row in df.sort_values("Conviction Score", ascending=False).iterrows():
        fired = compute_alerts(row)
        if fired:
            any_alert = True
            badges = "  ".join(f"{e} {m}" for e, m in fired)
            st.markdown(f"**{row['Ticker']}** — {row.get('Company','')}  \n{badges}")
    if not any_alert:
        st.caption("No alerts firing right now — nothing on your watchlist needs urgent attention.")

    st.divider()
    st.subheader("Watchlist Scores")
    cols = ["Ticker", "Company", "Sector", "Price", "Fair Value", "Upside %",
            "Overall Quant Score", "Conviction Score", "Health Score", "Valuation Score",
            "Momentum Score", "Data Source"]
    st.dataframe(
        df.sort_values("Conviction Score", ascending=False)[[c for c in cols if c in df.columns]],
        width="stretch",
    )
    if live:
        st.caption(f"Scored live (not in last saved scan): {', '.join(map(str, live))}")

    st.divider()
    st.subheader("📅 Upcoming Earnings")
    st.caption("When your watchlist names next report — earnings can move a stock sharply, so plan research/risk around these.")
    today = today_string()
    earn_rows = []
    with st.spinner("Checking earnings dates..."):
        for t in tickers:
            dt = get_next_earnings(t)
            if dt:
                days = (pd.to_datetime(dt) - pd.to_datetime(today)).days
                earn_rows.append({"Ticker": t, "Next Earnings": dt,
                                  "Days Away": days, "When": "past" if days < 0 else f"in {days}d"})
    if earn_rows:
        edf = pd.DataFrame(earn_rows)
        upcoming = edf[edf["Days Away"] >= 0].sort_values("Days Away")
        soon = upcoming[upcoming["Days Away"] <= 14]
        if not soon.empty:
            st.warning("⏰ Reporting within 2 weeks: " + ", ".join(f"{r['Ticker']} ({r['When']})" for _, r in soon.iterrows()))
        st.dataframe((upcoming if not upcoming.empty else edf)[["Ticker", "Next Earnings", "When"]], width="stretch")
    else:
        st.caption("No upcoming earnings dates available for these tickers right now.")


def etf_explorer_page():
    st.title("ETF Explorer")
    st.caption("Analyze funds the right way — cost, size, yield, returns, risk, sector mix, and holdings. Data: Yahoo Finance (free).")

    tab_one, tab_cmp = st.tabs(["Single ETF", "Compare ETFs"])

    with tab_one:
        ticker = st.text_input("ETF ticker", "SPY").upper().strip()
        if st.button("Analyze ETF", type="primary"):
            with st.spinner("Loading fund data..."):
                e = analyze_etf(ticker)
            if not e.get("Price"):
                st.error(f"Couldn't load data for {ticker}. Check the symbol.")
                return
            if not e.get("Is ETF"):
                st.warning(f"{ticker} doesn't look like an ETF/fund — the equity Deep Dive page is a better fit for it.")

            st.subheader(f"{e['Ticker']} — {e['Name']}")
            st.caption(f"{e.get('Category') or 'Fund'} · {e.get('Family') or ''}")
            aum = e.get("AUM")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("AUM", f"${aum/1e9:.1f}B" if aum else "N/A")
            c2.metric("Expense Ratio", f"{e['Expense Ratio %']}%" if e["Expense Ratio %"] is not None else "N/A")
            c3.metric("Yield", f"{e['Yield %']}%" if e["Yield %"] is not None else "N/A")
            c4.metric("Beta (3y)", e["Beta (3y)"] if e["Beta (3y)"] is not None else "N/A")

            c5, c6, c7, c8 = st.columns(4)
            c5.metric("YTD", f"{e['YTD %']}%" if e["YTD %"] is not None else "N/A")
            c6.metric("1Y", f"{e['1Y %']}%" if e["1Y %"] is not None else "N/A")
            c7.metric("3Y (ann.)", f"{e['3Y Ann %']}%" if e["3Y Ann %"] is not None else "N/A")
            c8.metric("5Y (ann.)", f"{e['5Y Ann %']}%" if e["5Y Ann %"] is not None else "N/A")

            c9, c10 = st.columns(2)
            c9.metric("Volatility (1y)", f"{e['Volatility %']}%" if e["Volatility %"] is not None else "N/A")
            c10.metric("Max Drawdown (1y)", f"{e['Max Drawdown %']}%" if e["Max Drawdown %"] is not None else "N/A")

            if e["Expense Ratio %"] is not None:
                er = e["Expense Ratio %"]
                note = ("🟢 Very low cost" if er <= 0.10 else "🟡 Moderate cost" if er <= 0.5 else "🔴 Expensive — costs compound over time")
                st.caption(f"Cost check: {note} ({er}%/yr).")

            col_a, col_b = st.columns([1, 1])
            with col_a:
                st.markdown("**Sector weightings**")
                fig = etf_sector_chart(e.get("Sector Weightings"))
                if fig:
                    st.plotly_chart(fig, width="stretch")
                else:
                    st.caption("Sector breakdown not available for this fund.")
            with col_b:
                st.markdown("**Top holdings**")
                th = e.get("Top Holdings")
                if th is not None and hasattr(th, "empty") and not th.empty:
                    disp = th.copy()
                    if "Holding Percent" in disp.columns:
                        disp["Weight %"] = (disp["Holding Percent"] * 100).round(2)
                        disp = disp.drop(columns=["Holding Percent"])
                    st.dataframe(disp, width="stretch")
                else:
                    st.caption("Holdings not available for this fund.")

    with tab_cmp:
        raw = st.text_input("Compare ETFs (comma-separated)", "SPY, QQQ, VTI, SCHD")
        etfs = [x.strip().upper() for x in raw.replace(";", ",").split(",") if x.strip()][:6]
        if st.button("Compare", type="primary", key="etf_cmp"):
            with st.spinner("Loading funds..."):
                rows = [analyze_etf(t) for t in etfs]
            rows = [r for r in rows if r.get("Price")]
            if not rows:
                st.warning("Couldn't load those ETFs.")
                return
            cmp_cols = ["Ticker", "Name", "Category", "Expense Ratio %", "Yield %",
                        "YTD %", "1Y %", "3Y Ann %", "5Y Ann %", "Beta (3y)", "Volatility %", "Max Drawdown %"]
            cdf = pd.DataFrame(rows)[[c for c in cmp_cols if c in rows[0]]]
            st.dataframe(cdf, width="stretch")
            st.caption("Lower expense ratio and drawdown are better; compare returns *alongside* volatility, not alone.")


STRATEGY_FACTORS = [
    ("Quality Score", "Quality"), ("Valuation Score", "Valuation"), ("Growth Score", "Growth"),
    ("Cash Flow Score", "Cash Flow"), ("Financial Strength Score", "Fin. Strength"),
    ("Momentum Score", "Momentum"), ("Relative Strength Score", "Rel. Strength"), ("Risk Score", "Risk Control"),
]
STRATEGY_PRESETS = {
    "Balanced": {"Quality Score": 6, "Valuation Score": 6, "Growth Score": 5, "Cash Flow Score": 5,
                 "Financial Strength Score": 5, "Momentum Score": 4, "Relative Strength Score": 4, "Risk Score": 5},
    "Value": {"Quality Score": 6, "Valuation Score": 10, "Growth Score": 3, "Cash Flow Score": 7,
              "Financial Strength Score": 6, "Momentum Score": 2, "Relative Strength Score": 2, "Risk Score": 5},
    "GARP (growth at a reasonable price)": {"Quality Score": 7, "Valuation Score": 6, "Growth Score": 8, "Cash Flow Score": 5,
              "Financial Strength Score": 4, "Momentum Score": 4, "Relative Strength Score": 4, "Risk Score": 4},
    "Quality Compounder": {"Quality Score": 10, "Valuation Score": 4, "Growth Score": 5, "Cash Flow Score": 8,
              "Financial Strength Score": 7, "Momentum Score": 3, "Relative Strength Score": 3, "Risk Score": 5},
    "Momentum": {"Quality Score": 4, "Valuation Score": 2, "Growth Score": 5, "Cash Flow Score": 3,
              "Financial Strength Score": 3, "Momentum Score": 10, "Relative Strength Score": 9, "Risk Score": 2},
}


def daily_briefing_page():
    st.title("🏠 Daily Briefing")
    st.caption("Your one-glance start: market mood, what's moving on your watchlist, earnings ahead, and fresh opportunities.")

    # Local data first — renders instantly (no network).
    scan = load_sp500_scores()
    scan = enhance_research_columns(scan) if not scan.empty else scan
    if not scan.empty:
        scan = add_score_change(scan)
    wl = load_watchlist()

    # Live market data is OPT-IN: Yahoo is slow/rate-limited on the cloud, so we never let it
    # block the page. Click to pull today's market mood + earnings; everything else is instant.
    if st.button("🔄 Load live market data", type="primary") or st.session_state.get("briefing_live"):
        st.session_state["briefing_live"] = True
        with st.spinner("Fetching live market data..."):
            try:
                snapshot = get_market_snapshot()
                health, regime = get_market_health(snapshot)
            except Exception:
                snapshot, health, regime = [], 50, "Unknown"
        m = st.columns(4)
        m[0].metric("Market Health", f"{health}/100", regime)
        if snapshot:
            sd = pd.DataFrame(snapshot).sort_values("Change %", ascending=False)
            for i, (_, r) in enumerate(sd.head(3).iterrows()):
                m[i + 1].metric(r["Asset"], money(r["Price"]), f"{r['Change %']}%")
    else:
        st.caption("📈 Click **Load live market data** for today's market mood & earnings dates. (Kept off auto-load so this page opens instantly — live quotes are slow on the free cloud host.)")

    st.divider()
    left, right = st.columns([1.1, 1])

    with left:
        st.subheader("📋 Your Watchlist")
        if not wl:
            st.info("No watchlist yet — add names on the **My Watchlist** page and they'll appear here.")
        elif scan.empty:
            st.info("Run a scan so your watchlist names have fresh scores.")
        else:
            wl_rows = scan[scan["Ticker"].astype(str).str.upper().isin(wl)]
            if wl_rows.empty:
                st.caption("Your watchlist names aren't in the latest scan yet — scan their sectors to see them here.")
            else:
                # Alerts firing
                any_alert = False
                for _, r in wl_rows.sort_values("Conviction Score", ascending=False).iterrows():
                    fired = compute_alerts(r)
                    if fired:
                        any_alert = True
                        st.markdown(f"**{r['Ticker']}** — " + "  ".join(f"{e} {msg}" for e, msg in fired[:3]))
                if not any_alert:
                    st.caption("No alerts firing on your watchlist right now.")
                # Biggest conviction moves
                if "Conviction Change" in wl_rows.columns:
                    movers = wl_rows.reindex(wl_rows["Conviction Change"].abs().sort_values(ascending=False).index).head(3)
                    movers = movers[movers["Conviction Change"].abs() >= 1]
                    if not movers.empty:
                        st.caption("**Biggest conviction moves since last scan:**")
                        for _, r in movers.iterrows():
                            st.caption(f"  {r['Ticker']}: {r['Conviction Change']:+.0f} → {r['Conviction Score']:.0f}/100")

        # Earnings this week — only after live data is loaded (avoids per-ticker network on open)
        if wl and st.session_state.get("briefing_live"):
            soon = []
            for t in wl:
                d0 = get_next_earnings(t)
                if d0:
                    days = (pd.to_datetime(d0) - pd.to_datetime(today_string())).days
                    if 0 <= days <= 7:
                        soon.append((t, d0, days))
            if soon:
                st.warning("📅 **Reporting this week:** " + ", ".join(f"{t} ({d0})" for t, d0, _ in sorted(soon, key=lambda x: x[2])))

    with right:
        st.subheader("🔎 Fresh Opportunities")
        if scan.empty:
            st.info("Run a scan in the Quant Opportunity Engine to populate this.")
        else:
            top = scan.sort_values("Research Priority", ascending=False).head(6)
            for _, r in top.iterrows():
                st.markdown(f"**{r['Ticker']}** — {r.get('Company','')}")
                st.caption(f"Priority {r.get('Research Priority','?')} · conviction {r.get('Conviction Score','?')}/100 · {r.get('Sector','')} · {r.get('Research Action','')}")

    st.divider()
    st.caption("Tip: this page reads your saved scan + watchlist. Keep the daily scans running (they do, automatically) and it stays current.")


def paper_trading_page():
    st.title("Paper Trading — Decision Log")
    st.caption("Log your calls with your reasoning, then watch how they actually perform vs. the market. This measures *your* judgment — the honest way to know if you're ready to risk real money.")
    st.info("Simulated only — no real money moves. It records your decisions so you can learn from them.")
    if signed_in():
        st.caption("💾 Saved to your account.")
    else:
        st.caption("⚠️ Sign in (sidebar) to save your trades permanently across devices.")

    trades = load_trades()

    with st.expander("➕ Log a new trade", expanded=not trades):
        c1, c2, c3 = st.columns(3)
        with c1:
            tkr = st.text_input("Ticker", "").upper().strip()
            action = st.selectbox("Action", ["Buy (long)", "Short (sell)"])
        with c2:
            default_px = get_last_price(tkr) if tkr else None
            price = st.number_input("Entry price ($)", min_value=0.0,
                                    value=float(default_px) if default_px else 0.0, step=1.0,
                                    help="Auto-filled with the latest price when you type a ticker.")
            shares = st.number_input("Shares", min_value=0.0, value=10.0, step=1.0)
        with c3:
            tdate = st.text_input("Date (YYYY-MM-DD)", today_string())
            conviction = st.slider("Conviction (1–10)", 1, 10, 6)
        thesis = st.text_area("Why? (your thesis in one line)", "", height=70)
        if st.button("Log trade", type="primary"):
            if not tkr or price <= 0:
                st.warning("Enter a ticker and a valid entry price.")
            else:
                trades.append({"ticker": tkr, "action": action, "price": price, "shares": shares,
                               "date": tdate, "conviction": conviction, "thesis": thesis})
                save_trades(trades)
                st.success(f"Logged {action} {tkr} @ {money(price)}.")
                st.rerun()

    if not trades:
        st.info("No trades logged yet — log your first call above.")
        return

    st.subheader("Your Track Record")
    rows, returns, excesses, beats, convs = [], [], [], 0, []
    with st.spinner("Scoring your calls vs. the market..."):
        for t in trades:
            tk, entry, d0 = t["ticker"], safe_float(t["price"]), t.get("date", today_string())
            fwd = get_forward_return(tk, d0, today_string())
            spy = get_forward_return("SPY", d0, today_string())
            short = "short" in str(t.get("action", "")).lower()
            if fwd is None:
                rows.append({"Ticker": tk, "Action": t.get("action"), "Date": d0,
                             "Entry": round(entry, 2), "Return %": None, "vs SPY %": None,
                             "Conviction": t.get("conviction")})
                continue
            r = fwd * 100 * (-1 if short else 1)
            returns.append(r)
            convs.append((t.get("conviction"), r))
            ex = None
            if spy is not None:
                ex = r - spy * 100
                excesses.append(ex)
                if r > spy * 100:
                    beats += 1
            rows.append({"Ticker": tk, "Action": t.get("action"), "Date": d0,
                         "Entry": round(entry, 2), "Current": round(entry * (1 + fwd), 2),
                         "Return %": round(r, 1), "vs SPY %": round(ex, 1) if ex is not None else None,
                         "Conviction": t.get("conviction")})

    m1, m2, m3, m4 = st.columns(4)
    avg = sum(returns) / len(returns) if returns else 0
    avg_ex = sum(excesses) / len(excesses) if excesses else 0
    win = len([r for r in returns if r > 0]) / len(returns) * 100 if returns else 0
    beat_rate = beats / len(excesses) * 100 if excesses else 0
    m1.metric("Avg Return", f"{avg:+.1f}%")
    m2.metric("Avg vs SPY", f"{avg_ex:+.1f}%", delta=f"{avg_ex:+.1f}%")
    m3.metric("Win Rate", f"{win:.0f}%")
    m4.metric("Beat SPY Rate", f"{beat_rate:.0f}%")
    st.dataframe(pd.DataFrame(rows), width="stretch")

    # Does your conviction actually predict your results?
    if len([c for c, _ in convs if c is not None]) >= 4:
        cdf = pd.DataFrame([(c, r) for c, r in convs if c is not None], columns=["conv", "ret"])
        ic = cdf["conv"].rank().corr(cdf["ret"].rank())
        if ic == ic:
            if ic > 0.2:
                st.success(f"🟢 Your conviction is predictive (rank corr {ic:.2f}) — your higher-conviction calls have done better. Good sign your judgment adds value.")
            elif ic < -0.2:
                st.warning(f"🔴 Your conviction is inversely related to returns ({ic:.2f}) — your most confident calls did worse. Worth reflecting on why.")
            else:
                st.info(f"Conviction–return correlation is ~flat ({ic:.2f}) so far — need more trades to tell.")

    with st.expander("Remove a trade"):
        labels = [f"{i}: {t['ticker']} {t.get('action','')} @ {money(t['price'])} ({t.get('date')})" for i, t in enumerate(trades)]
        to_del = st.selectbox("Select a trade to delete", ["(none)"] + labels)
        if to_del != "(none)" and st.button("Delete selected trade"):
            idx = int(to_del.split(":")[0])
            trades.pop(idx)
            save_trades(trades)
            st.rerun()

    st.caption("This is your personal edge-check: over many logged calls, do you beat SPY, and does your conviction actually track your results? That's what tells you whether to trust yourself with real capital.")


def research_journal_page():
    st.title("Research Journal")
    st.caption("Write down *why* you're interested before you buy — then revisit it later. Disciplined investors keep a thesis; it's how you learn whether your reasoning (not just luck) was right.")

    journal = load_journal()
    existing_tickers = journal["Ticker"].tolist() if not journal.empty else []

    with st.expander("✍️ Add / edit an entry", expanded=True):
        ticker = st.text_input("Ticker", "").upper().strip()
        prefill = {}
        if ticker and ticker in existing_tickers:
            prefill = journal[journal["Ticker"] == ticker].iloc[0].to_dict()
            st.caption(f"Editing existing entry (last updated {prefill.get('Updated','')}).")

        # light context from the saved scan (free — no API call)
        if ticker:
            scan = load_sp500_scores()
            if not scan.empty and ticker in scan["Ticker"].astype(str).str.upper().values:
                r = scan[scan["Ticker"].astype(str).str.upper() == ticker].iloc[0]
                st.caption(f"📊 Engine snapshot: {ticker} · price {money(r.get('Price'))} · fair value {money(r.get('Fair Value'))} · conviction {r.get('Conviction Score','?')}/100 · {r.get('Tier','')}")

        c1, c2 = st.columns(2)
        with c1:
            ratings = ["", "Buy", "Accumulate", "Watch", "Pass", "Sell"]
            cur_rating = prefill.get("My Rating", "")
            rating = st.selectbox("My rating", ratings, index=ratings.index(cur_rating) if cur_rating in ratings else 0)
        with c2:
            target = st.text_input("My price target (optional)", str(prefill.get("My Target", "") or ""))
        thesis = st.text_area("Thesis — why is this interesting? (bull case, catalysts, what has to go right)",
                              str(prefill.get("Thesis", "") or ""), height=120)
        notes = st.text_area("Ongoing notes — risks, updates, what would change your mind",
                             str(prefill.get("Notes", "") or ""), height=120)
        if st.button("💾 Save entry", type="primary"):
            if not ticker:
                st.warning("Enter a ticker first.")
            else:
                save_journal_entry(ticker, rating, target, thesis, notes)
                st.success(f"Saved journal entry for {ticker}.")
                st.rerun()

    st.divider()
    journal = load_journal()
    if journal.empty:
        st.info("No journal entries yet. Add your first thesis above.")
        return

    st.subheader(f"Your journal ({len(journal)} entries)")
    for _, e in journal.iterrows():
        header = f"**{e['Ticker']}**" + (f" — {e['My Rating']}" if e['My Rating'] else "") + (f" · target {e['My Target']}" if str(e['My Target']).strip() else "")
        with st.container(border=True):
            st.markdown(f"{header}  \n<span style='color:#8a94a6;font-size:0.85rem'>updated {e['Updated']}</span>", unsafe_allow_html=True)
            if str(e["Thesis"]).strip():
                st.markdown(f"**Thesis:** {e['Thesis']}")
            if str(e["Notes"]).strip():
                st.markdown(f"**Notes:** {e['Notes']}")
            if st.button("🗑️ Delete", key=f"del_{e['Ticker']}"):
                delete_journal_entry(e["Ticker"])
                st.rerun()

    st.divider()
    st.caption("💾 Journal is saved on this device. On the cloud it resets on reboot — use Export to back it up, Import to restore.")
    b1, b2 = st.columns(2)
    with b1:
        st.download_button("⬇️ Export journal (CSV)", data=journal.to_csv(index=False).encode(),
                           file_name="research_journal.csv", mime="text/csv")
    with b2:
        up = st.file_uploader("⬆️ Import journal (CSV)", type="csv", label_visibility="collapsed")
        if up is not None and st.button("Restore from file"):
            try:
                imp = pd.read_csv(up)
                imp.to_csv(JOURNAL_FILE, index=False)
                st.success("Journal restored.")
                st.rerun()
            except Exception as ex:
                st.error(f"Couldn't import: {ex}")


def position_sizer_page():
    st.title("Position Sizer")
    st.caption("The bridge from research to action: given your capital and risk rules, how much of a stock should you actually buy? Position sizing — not stock picking — is what keeps you in the game.")

    st.info("Research tool, not advice. Sizing controls risk; it doesn't make a bad idea good.")

    c1, c2 = st.columns(2)
    with c1:
        capital = st.number_input("Total investable capital ($)", min_value=100.0, value=10000.0, step=500.0)
        ticker = st.text_input("Ticker", "MSFT").upper().strip()
        max_pos = st.slider("Max position size (% of capital)", 1, 50, 20,
                            help="Your hard cap on any single name. 15–25% is common for a concentrated portfolio; 5–10% for a diversified one.")
    with c2:
        risk_per_trade = st.slider("Risk per trade (% of capital)", 0.5, 5.0, 1.0, 0.5,
                                   help="Max you're willing to lose if the stop is hit. Pros risk ~0.5–2% per position.")
        stop_pct = st.slider("Stop-loss distance (% below entry)", 5, 40, 15,
                             help="How far the stock can fall before you'd exit. Wider stops = smaller position.")

    if st.button("Calculate Position Size", type="primary"):
        try:
            with st.spinner("Loading stock data..."):
                row = get_quant_score(ticker)
        except Exception:
            st.error(f"Couldn't load {ticker}. Check the symbol.")
            return
        price = safe_float(row.get("Price"))
        if not price:
            st.error("No price available for this ticker.")
            return
        conviction = safe_float(row.get("Conviction Score"), 50)
        vol = safe_float(row.get("Volatility %"), 30)

        # 1) Conviction- & volatility-adjusted target weight (risk-parity flavour)
        conv_frac = clamp(conviction, 0, 100) / 100
        vol_adj = max(0.4, min(1.3, 25.0 / vol)) if vol else 1.0     # target ~25% vol; riskier -> smaller
        conv_pct = min(max_pos, max_pos * conv_frac * vol_adj)
        conv_dollars = capital * conv_pct / 100
        conv_shares = conv_dollars / price

        # 2) Fixed-fractional risk sizing (from stop distance)
        risk_dollars = capital * risk_per_trade / 100
        risk_shares = risk_dollars / (price * stop_pct / 100)
        risk_dollars_pos = risk_shares * price
        capped = risk_dollars_pos > capital * max_pos / 100
        if capped:
            risk_dollars_pos = capital * max_pos / 100
            risk_shares = risk_dollars_pos / price

        recommended = min(conv_dollars, risk_dollars_pos)
        rec_shares = recommended / price

        st.subheader(f"{ticker} @ {money(price)}")
        st.caption(f"Conviction {conviction:.0f}/100 · Volatility {vol:.0f}% · your max position {max_pos}% = {money(capital*max_pos/100)}")

        m1, m2, m3 = st.columns(3)
        m1.metric("Conviction/vol sizing", money(conv_dollars), f"{conv_pct:.1f}% of capital")
        m2.metric("Risk-based sizing", money(risk_dollars_pos), f"risk {money(risk_dollars)} at −{stop_pct}%")
        m3.metric("✅ Suggested", money(recommended), f"≈ {rec_shares:.2f} shares")

        st.success(f"**Suggested position: {money(recommended)}** (~{rec_shares:.2f} shares, {recommended/capital*100:.1f}% of capital). Taking the more conservative of the two methods.")

        st.markdown("**How the two methods work:**")
        st.write(f"- 🎯 **Conviction/volatility sizing** scales your max position by conviction ({conviction:.0f}/100) and shrinks it for volatility ({vol:.0f}%) → {conv_pct:.1f}% = {money(conv_dollars)}.")
        st.write(f"- 🛡️ **Risk-based sizing** limits your loss to {risk_per_trade}% ({money(risk_dollars)}) if the stock falls {stop_pct}% to your stop → {money(risk_dollars_pos)}" + (" *(capped at your max position)*" if capped else "") + ".")
        st.caption("Rule of thumb: size so that being wrong on any one name is survivable. The goal isn't to maximize a single bet — it's to stay in the game long enough for the process to work.")


def strategy_builder_page():
    st.title("Strategy Builder")
    st.caption("Tune the engine to *your* style — set how much each factor matters and re-rank the whole scan instantly. No rescan needed; it recomputes from your saved data.")

    df = load_sp500_scores()
    if df.empty:
        st.warning("No saved scan yet. Run a scan in the Quant Opportunity Engine first.")
        return
    df = enhance_research_columns(df)

    for col, _ in STRATEGY_FACTORS:
        st.session_state.setdefault(f"w_{col}", 5)

    preset = st.selectbox("Start from a preset (then fine-tune)", list(STRATEGY_PRESETS))
    if st.session_state.get("_last_preset") != preset:
        for k, v in STRATEGY_PRESETS[preset].items():
            st.session_state[f"w_{k}"] = v
        st.session_state["_last_preset"] = preset

    st.markdown("**Factor weights** (0 = ignore, 10 = maximum priority)")
    cols = st.columns(4)
    weights = {}
    for i, (col, label) in enumerate(STRATEGY_FACTORS):
        with cols[i % 4]:
            weights[col] = st.slider(label, 0, 10, key=f"w_{col}")   # reads/writes session_state

    total_w = sum(weights.values())
    if total_w == 0:
        st.info("Set at least one weight above zero.")
        return

    scored = df.copy()
    scored["My Score"] = 0.0
    for col, _ in STRATEGY_FACTORS:
        if col in scored.columns:
            scored["My Score"] += pd.to_numeric(scored[col], errors="coerce").fillna(50) * weights[col]
    scored["My Score"] = (scored["My Score"] / total_w).round(1)

    st.divider()
    st.subheader(f"Top names by *your* strategy ({preset if st.session_state.get('_last_preset')==preset else 'custom'})")
    show_cols = ["Ticker", "Company", "Sector", "My Score", "Overall Quant Score"] + [c for c, _ in STRATEGY_FACTORS]
    ranked = scored.sort_values("My Score", ascending=False)
    st.dataframe(ranked[[c for c in show_cols if c in ranked.columns]].head(25), width="stretch")

    # Show how your ranking differs from the default engine ranking
    ranked = ranked.reset_index(drop=True)
    ranked["My Rank"] = ranked.index + 1
    eng = scored.sort_values("Overall Quant Score", ascending=False).reset_index(drop=True)
    eng_rank = {t: i + 1 for i, t in enumerate(eng["Ticker"])}
    ranked["Engine Rank"] = ranked["Ticker"].map(eng_rank)
    ranked["Rank Δ"] = ranked["Engine Rank"] - ranked["My Rank"]
    movers = ranked.head(15).sort_values("Rank Δ", ascending=False)
    st.caption("Biggest risers under your weights vs. the default engine ranking (positive = your strategy likes it more):")
    st.dataframe(movers[["Ticker", "Company", "My Rank", "Engine Rank", "Rank Δ", "My Score"]].head(8), width="stretch")
    st.caption("💡 Your Factor Efficacy tab can later tell you whether your custom blend would actually have predicted returns better than the default.")


def valuation_lab_page():
    st.title("Valuation Lab")
    st.caption("See exactly how a discounted-cash-flow (DCF) valuation works — move the assumptions and watch fair value change. The best way to build intuition for what a stock is really worth.")

    with st.expander("What is a DCF? (30-second version)", expanded=False):
        st.write(
            "A DCF values a company as the sum of all its future free cash flow, discounted "
            "back to today (a dollar next year is worth less than a dollar now). You assume: "
            "(1) how fast cash flow grows for the next several years, (2) a long-run 'terminal' "
            "growth rate forever after, and (3) a discount rate = the annual return you require. "
            "Small changes in these move the answer a lot — which is exactly why fair value is a range."
        )

    t = st.text_input("Ticker", "MSFT").upper().strip()
    if st.button("Load", type="primary"):
        try:
            with st.spinner("Loading cash-flow data..."):
                r = get_quant_score(t)
            fcfy, price = safe_float(r.get("FCF Yield %")), safe_float(r.get("Price"))
            st.session_state["vlab"] = {
                "ticker": t, "company": r.get("Company", ""), "price": price,
                "fcf_ps": (fcfy / 100 * price) if (fcfy and price) else None,
                "def_g": min(max((safe_float(r.get("Revenue Growth %"), 6) or 6) / 100, 0.0), 0.20),
                "src": r.get("Data Source", ""),
            }
        except Exception as e:
            st.error(f"Couldn't load {t}: {e}")

    v = st.session_state.get("vlab")
    if not v:
        st.info("Enter a ticker and click **Load** to begin.")
        return
    if not v["fcf_ps"] or v["fcf_ps"] <= 0:
        st.warning(f"{v['ticker']} has no positive free cash flow, so a DCF isn't meaningful. Try a profitable, cash-generative company.")
        return

    st.subheader(f"{v['ticker']} — {v['company']}")
    st.caption(f"Current price {money(v['price'])} · starting FCF/share ≈ {money(v['fcf_ps'])} · data: {v['src']}")

    c1, c2 = st.columns(2)
    with c1:
        g1 = st.slider("Stage-1 FCF growth per year, %", 0, 30, int(round(v["def_g"] * 100)),
                       help="How fast free cash flow grows during the high-growth years.")
        r_rate = st.slider("Discount rate (your required return), %", 6, 15, 9,
                           help="Higher = you demand more return / see more risk = lower value.")
    with c2:
        g_term = st.slider("Terminal growth forever after, %", 0.0, 4.0, 2.5, 0.5,
                           help="Long-run growth in perpetuity — keep near GDP/inflation (2–3%).")
        years = st.slider("Number of high-growth years", 3, 10, 5)

    fv = dcf_from_params(v["fcf_ps"], g1 / 100, r_rate / 100, g_term / 100, years)
    if fv is None:
        st.warning("Invalid combination — the discount rate must be higher than terminal growth.")
        return
    upside = (fv - v["price"]) / v["price"] * 100 if v["price"] else 0
    m1, m2, m3 = st.columns(3)
    m1.metric("DCF fair value / share", money(fv))
    m2.metric("Current price", money(v["price"]))
    m3.metric("Upside / (downside)", f"{upside:.0f}%", delta=f"{upside:.0f}%")
    if upside > 15:
        st.success(f"Under these assumptions, {v['ticker']} looks **undervalued** by ~{upside:.0f}%.")
    elif upside < -15:
        st.error(f"Under these assumptions, {v['ticker']} looks **overvalued** by ~{abs(upside):.0f}%.")
    else:
        st.info(f"Under these assumptions, {v['ticker']} looks **roughly fairly valued**.")

    st.subheader("Sensitivity: fair value by growth × discount rate")
    growths = sorted({max(0, g1 - 8), max(0, g1 - 4), g1, g1 + 4, g1 + 8})
    rates = sorted({max(g_term + 1, r_rate - 2), r_rate - 1, r_rate, r_rate + 1, r_rate + 2})
    grid = {}
    for rr in rates:
        rowvals = {}
        for gg in growths:
            val = dcf_from_params(v["fcf_ps"], gg / 100, rr / 100, g_term / 100, years)
            rowvals[f"{gg:.0f}% growth"] = round(val) if val else None
        grid[f"{rr:.0f}% discount"] = rowvals
    st.dataframe(pd.DataFrame(grid).T, width="stretch")
    st.caption("Rows = discount rate, columns = growth. Notice how much the value swings with small changes — that uncertainty is why the engine shows fair value as a *range*, not a single number. Current price for reference: " + money(v["price"]) + ".")


def _latin1(s):
    """fpdf core fonts are latin-1 only; strip characters they can't encode."""
    return str(s).replace("—", "-").replace("–", "-").replace("’", "'").replace("“", '"').replace("”", '"').encode("latin-1", "replace").decode("latin-1")


def build_stock_pdf(row, verdict, bull, bear):
    """One-page research summary PDF (bytes). Pure-Python (fpdf2), works on the cloud."""
    from fpdf import FPDF

    pdf = FPDF(format="letter")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, _latin1(f"{row.get('Ticker','')} - {row.get('Company','')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(110)
    pdf.cell(0, 5, _latin1(f"{row.get('Sector','')} | {row.get('Industry','')} | Data: {row.get('Data Source','Yahoo Finance')} | As of {row.get('Scan Date','')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0)
    pdf.ln(3)

    def line(label, value, bold_val=False):
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(60, 6, _latin1(label))
        pdf.set_font("Helvetica", "B" if bold_val else "", 10)
        pdf.cell(0, 6, _latin1(value), new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, "Verdict", new_x="LMARGIN", new_y="NEXT")
    line("Research action:", verdict, True)
    line("Overall Quant Score:", f"{row.get('Overall Quant Score','')}/100 ({row.get('Overall Grade','')})")
    line("Tier:", str(row.get("Tier", "")))
    line("Price:", money(row.get("Price")))
    fv_l, fv_h = row.get("Fair Value Low"), row.get("Fair Value High")
    fv_txt = f"{money(row.get('Fair Value'))}  (range {money(fv_l)} - {money(fv_h)})" if fv_l and fv_h else money(row.get("Fair Value"))
    line("Fair value:", fv_txt)
    line("Upside to fair value:", f"{row.get('Upside %','')}%")
    line("Suggested hold:", str(row.get("Suggested Hold", "")))
    line("Biggest risk:", str(row.get("Biggest Risk", "")))
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, "Master Scores", new_x="LMARGIN", new_y="NEXT")
    for lbl, key in [("Investment", "Investment Score"), ("Opportunity", "Opportunity Score"),
                     ("Position Trade", "Position Trade Score"), ("Health", "Health Score"),
                     ("Quality", "Quality Score"), ("Valuation", "Valuation Score"),
                     ("Growth", "Growth Score"), ("Momentum", "Momentum Score"),
                     ("Risk Control", "Risk Score"), ("Conviction", "Conviction Score")]:
        line(f"{lbl}:", f"{row.get(key,'')}/100")
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, "Bull case", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    for b in bull:
        pdf.multi_cell(0, 5, _latin1(f"- {b}"))
    pdf.ln(1)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, "Bear case", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    for b in bear:
        pdf.multi_cell(0, 5, _latin1(f"- {b}"))

    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(120)
    pdf.multi_cell(0, 4, _latin1("Research aid only - not financial advice. Generated by Mastermind Quant Terminal."))

    return bytes(pdf.output())


def compare_page():
    st.title("Compare Stocks")
    st.caption("Put 2–4 stocks head-to-head — factor shapes overlaid, key metrics side by side.")

    default = ", ".join(load_watchlist()[:3]) or "MSFT, NVDA, GOOGL"
    raw = st.text_input("Tickers to compare (2–4, comma-separated)", default)
    tickers = [x.strip().upper() for x in raw.replace(";", ",").split(",") if x.strip()][:4]

    if st.button("Compare", type="primary"):
        if len(tickers) < 2:
            st.warning("Enter at least two tickers.")
            return
        with st.spinner("Scoring..."):
            df, live = build_watchlist_analysis(tickers)
        if df.empty or len(df) < 2:
            st.warning("Couldn't score enough of those tickers to compare.")
            return
        df = enhance_research_columns(df)

        st.subheader("Factor shapes")
        st.plotly_chart(factor_radar_multi(df), width="stretch")

        st.subheader("Side-by-side")
        metrics = [
            "Company", "Sector", "Price", "Fair Value", "Upside %", "Overall Quant Score",
            "Conviction Score", "Investment Score", "Opportunity Score", "Health Score",
            "Quality Score", "Valuation Score", "Growth Score", "Momentum Score", "Risk Score",
            "P/E", "PEG", "FCF Yield %", "ROIC Proxy %", "Debt/Equity", "Revenue Growth %",
            "Data Source",
        ]
        table = df.set_index("Ticker")[[m for m in metrics if m in df.columns]].T
        st.dataframe(table, width="stretch")
        if live:
            st.caption(f"Scored live (not in last saved scan): {', '.join(map(str, live))}")


def main():
    apply_custom_style()
    app_header()
    auth_sidebar()
    st.sidebar.divider()
    page = st.sidebar.radio(
        "Choose Page",
        ["🏠 Daily Briefing", "Market Command Center", "My Watchlist", "Compare Stocks", "Research Queue", "Portfolio Manager AI", "Position Sizer", "Quant Opportunity Engine", "Quant Stock Deep Dive", "ETF Explorer", "Valuation Lab", "Strategy Builder", "Research Journal", "Paper Trading", "Backtesting Lab", "Learning Center"]
    )
    st.sidebar.divider()
    st.sidebar.write("**Goal:** Full quant stock evaluation")
    st.sidebar.write("**Master Scores:** Investment, Opportunity, Position Trade, Health, Expected Return")
    st.sidebar.write("**Focus:** Undervalued + growth + quality + momentum + risk control")

    if page == "🏠 Daily Briefing":
        daily_briefing_page()
    elif page == "Market Command Center":
        market_command_center()
    elif page == "My Watchlist":
        watchlist_page()
    elif page == "Compare Stocks":
        compare_page()
    elif page == "Research Queue":
        research_queue_page()
    elif page == "Portfolio Manager AI":
        portfolio_manager_page()
    elif page == "Position Sizer":
        position_sizer_page()
    elif page == "Quant Opportunity Engine":
        opportunity_engine()
    elif page == "Quant Stock Deep Dive":
        stock_deep_dive()
    elif page == "ETF Explorer":
        etf_explorer_page()
    elif page == "Valuation Lab":
        valuation_lab_page()
    elif page == "Strategy Builder":
        strategy_builder_page()
    elif page == "Research Journal":
        research_journal_page()
    elif page == "Paper Trading":
        paper_trading_page()
    elif page == "Backtesting Lab":
        backtesting_page()
    else:
        learning_center()


if __name__ == "__main__":
    main()
