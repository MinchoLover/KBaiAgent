import streamlit as st


KB_WORKSPACE_CSS = """
<style>
:root {
  --kb-navy: #062b5c;
  --kb-navy-hover: #123f74;
  --kb-gold: #f5b800;
  --kb-blue: #1261c9;
  --kb-green: #13875c;
  --kb-orange: #d66a00;
  --kb-red: #c9362b;
  --surface: #ffffff;
  --surface-muted: #f4f6f9;
  --border: #d9e0e8;
  --text-primary: #0b2347;
  --text-secondary: #526279;
  --shadow-sm: 0 5px 16px rgba(9, 37, 75, 0.08);
  --radius-card: 15px;
  --space-xs: 0.35rem;
  --space-sm: 0.65rem;
  --space-md: 1rem;
  --space-lg: 1.5rem;
  --space-xl: 2.25rem;
}

html, body, [class*="css"] {
  color: var(--text-primary);
}

[data-testid="stAppViewContainer"] {
  background: var(--surface-muted);
}

[data-testid="stHeader"] {
  background: rgba(244, 246, 249, 0.92);
}

[data-testid="stToolbar"] {
  opacity: 0.72;
}

.block-container {
  width: 100%;
  max-width: 1320px;
  padding: 1.1rem 2rem 4rem;
}

section[data-testid="stSidebar"] {
  position: fixed !important;
  top: 0;
  bottom: 0;
  width: 13.75rem !important;
  min-width: 13.75rem !important;
  border-right: 0;
  background:
    radial-gradient(circle at 50% 0%, #124a84 0, transparent 28%),
    linear-gradient(180deg, #072d5f 0%, #052650 100%);
  box-shadow: 8px 0 28px rgba(6, 43, 92, 0.12);
}

section[data-testid="stMain"] {
  width: calc(100% - 13.75rem);
  margin-left: 13.75rem;
}

section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
  padding: 0.75rem 0.65rem 1rem;
}

section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] small,
section[data-testid="stSidebar"] summary,
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
  color: rgba(255, 255, 255, 0.86);
}

section[data-testid="stSidebar"] hr {
  border-color: rgba(255, 255, 255, 0.15);
}

.sidebar-brand {
  padding: 0.45rem 0.45rem 1.15rem;
  text-align: left;
}

.sidebar-brand .mark {
  display: flex;
  width: 2.8rem;
  height: 2.8rem;
  align-items: center;
  justify-content: center;
  margin: 0 0 0.55rem;
  border: 1px solid rgba(245, 184, 0, 0.58);
  border-radius: 13px;
  color: var(--kb-gold);
  background: rgba(255, 255, 255, 0.06);
  font-size: 0.9rem;
  font-weight: 900;
  letter-spacing: -0.04em;
}

.sidebar-brand strong {
  display: block;
  color: #ffffff;
  font-size: 1.02rem;
  letter-spacing: -0.025em;
}

.sidebar-brand p {
  margin: 0.18rem 0 0;
  color: rgba(255, 255, 255, 0.62) !important;
  font-size: 0.7rem;
  line-height: 1.45;
}

.sidebar-section-label {
  margin: 0.45rem 0.55rem 0.35rem;
  color: rgba(255, 255, 255, 0.48);
  font-size: 0.66rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

section[data-testid="stSidebar"] div[class*="st-key-nav_"] button {
  min-height: 2.7rem;
  justify-content: flex-start;
  padding: 0.55rem 0.7rem;
  border: 1px solid transparent;
  border-radius: 10px;
  color: rgba(255, 255, 255, 0.84);
  background: transparent;
  box-shadow: none;
  font-size: 0.83rem;
}

section[data-testid="stSidebar"] div[class*="st-key-nav_"] button:hover,
section[data-testid="stSidebar"] div[class*="st-key-nav_"] button:focus-visible {
  border-color: rgba(255, 255, 255, 0.18);
  color: #ffffff;
  background: rgba(255, 255, 255, 0.09);
  transform: none;
  outline: 2px solid rgba(245, 184, 0, 0.72);
  outline-offset: 1px;
}

section[data-testid="stSidebar"] div[class*="st-key-nav_"] button[kind="primary"] {
  border-color: rgba(255, 255, 255, 0.08);
  border-left: 4px solid var(--kb-gold);
  color: #ffffff;
  background: var(--kb-navy-hover);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.03);
}

section[data-testid="stSidebar"] div[class*="st-key-nav_"] button:disabled {
  color: rgba(255, 255, 255, 0.38);
  background: transparent;
  opacity: 1;
}

section[data-testid="stSidebar"] .st-key-new_analysis button {
  justify-content: flex-start;
  border-color: rgba(255, 255, 255, 0.22);
  color: #ffffff;
  background: rgba(255, 255, 255, 0.07);
  box-shadow: none;
}

section[data-testid="stSidebar"] .st-key-new_analysis button:hover,
section[data-testid="stSidebar"] .st-key-new_analysis button:focus-visible {
  border-color: var(--kb-gold);
  color: #ffffff;
  background: rgba(255, 255, 255, 0.12);
}

section[data-testid="stSidebar"] [data-testid="stExpander"] {
  border-color: rgba(255, 255, 255, 0.18);
  background: rgba(255, 255, 255, 0.06);
}

section[data-testid="stSidebar"] [data-testid="stExpander"] details[open] {
  background: #ffffff;
  border-radius: 11px;
}

section[data-testid="stSidebar"] [data-testid="stExpander"] details[open] p,
section[data-testid="stSidebar"] [data-testid="stExpander"] details[open] label,
section[data-testid="stSidebar"] [data-testid="stExpander"] details[open] small,
section[data-testid="stSidebar"] [data-testid="stExpander"] details[open] summary {
  color: var(--text-secondary);
}

.sidebar-summary {
  margin: 0.9rem 0 0.65rem;
  padding: 0.75rem;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 11px;
  background: rgba(255, 255, 255, 0.06);
}

.sidebar-summary small {
  color: rgba(255, 255, 255, 0.58) !important;
}

.sidebar-summary strong {
  color: #ffffff;
  font-size: 0.84rem;
}

.st-key-sidebar_support {
  margin-top: 1.4rem;
  padding-top: 0.8rem;
  border-top: 1px solid rgba(255, 255, 255, 0.14);
}

.st-key-sidebar_support button {
  justify-content: flex-start;
  color: rgba(255, 255, 255, 0.82) !important;
  border-color: transparent !important;
  background: transparent !important;
  box-shadow: none !important;
}

.st-key-workflow_navigation {
  position: sticky;
  top: 0.5rem;
  z-index: 40;
  padding: 0.35rem;
  margin-bottom: 0.8rem;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.97);
  box-shadow: var(--shadow-sm);
}

.st-key-workflow_navigation [data-testid="stHorizontalBlock"] {
  gap: 0.25rem;
}

.st-key-workflow_navigation button {
  min-height: 2.65rem !important;
  box-shadow: none !important;
}

.st-key-mobile_navigation {
  display: none;
}

.page-header {
  display: flex;
  min-height: 3.2rem;
  align-items: center;
  gap: 0.75rem;
  margin: 0 0 1rem;
}

.page-header .page-step {
  display: inline-flex;
  width: 2.35rem;
  height: 2.35rem;
  flex: 0 0 2.35rem;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  color: #ffffff;
  background: var(--kb-navy);
  box-shadow: 0 4px 10px rgba(6, 43, 92, 0.2);
  font-size: 1rem;
  font-weight: 900;
}

.page-header h1 {
  margin: 0;
  color: var(--text-primary);
  font-size: 1.55rem;
  line-height: 1.2;
}

.page-header p {
  margin: 0.18rem 0 0;
  color: var(--text-secondary);
  font-size: 0.84rem;
  line-height: 1.45;
}

.st-key-workflow_analysis .page-header h1 {
  font-size: 1.8rem;
  font-weight: 700;
}

.st-key-workflow_analysis .page-header {
  align-items: flex-start;
  gap: 0.85rem;
  margin-bottom: 1rem;
}

.st-key-workflow_analysis .page-header .page-step {margin-top: 0.1rem;}

.st-key-workflow_analysis .page-header p {
  margin-top: 0.3rem;
  font-size: 0.9375rem;
  line-height: 1.5;
}

.home-hero {
  padding: 2.1rem 1.9rem 1.5rem;
  text-align: center;
}

.home-hero .eyebrow {
  color: var(--kb-blue);
}

.home-hero h1 {
  margin: 0.5rem 0 0.75rem;
  color: var(--text-primary);
  font-size: clamp(2rem, 4.2vw, 3.05rem);
  line-height: 1.12;
}

.home-hero p {
  max-width: 680px;
  margin: 0 auto;
  color: var(--text-secondary);
  font-size: 1rem;
}

.workspace-card,
.home-settings-panel,
.sample-info-card,
.download-action-panel {
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
}

.home-settings-panel {
  min-height: 100%;
  padding: 1.1rem;
}

.home-settings-panel h3 {
  margin: 0 0 0.85rem;
  color: var(--text-primary);
  font-size: 1rem;
}

.provider-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.65rem 0;
  border-bottom: 1px solid var(--border);
  font-size: 0.78rem;
}

.provider-row:last-child {
  border-bottom: 0;
}

.provider-row span {
  color: var(--text-secondary);
}

.provider-row strong {
  color: var(--text-primary);
  text-align: right;
}

.sample-info-card {
  display: flex;
  gap: 0.85rem;
  align-items: flex-start;
  padding: 1rem 1.1rem;
  margin: 0.75rem 0 1rem;
  border-color: #b9d5f5;
  background: #f5faff;
  box-shadow: none;
}

.sample-info-card .sample-icon {
  display: inline-flex;
  width: 2.5rem;
  height: 2.5rem;
  flex: 0 0 2.5rem;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  color: var(--kb-blue);
  background: #e5f1ff;
  font-size: 1.2rem;
}

.sample-info-card strong {
  display: block;
  color: #0d4b9b;
}

.sample-info-card p {
  margin: 0.2rem 0 0;
  color: var(--text-secondary);
  font-size: 0.8rem;
}

.journey-track {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.35rem;
  padding: 0.9rem 0.8rem;
  border: 1px solid var(--border);
  border-radius: 13px;
  background: var(--surface);
}

.journey-track .journey-step {
  position: relative;
  min-height: 2.2rem;
}

.journey-track .journey-step:not(:last-child)::after {
  position: absolute;
  top: 50%;
  right: -0.25rem;
  width: 0.5rem;
  border-top: 2px dotted #c9d2dd;
  content: "";
}

.trade-identity {
  display: flex;
  align-items: center;
  gap: 0.85rem;
  padding: 0.85rem 1rem 0.2rem;
}

.trade-identity .direction-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0.55rem 1.2rem;
  border-radius: 8px;
  color: #ffffff;
  background: var(--kb-blue);
  font-size: 1rem;
  font-weight: 900;
}

.trade-identity strong {
  color: var(--text-primary);
  font-size: 1.12rem;
}

.transaction-summary-heading {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  justify-content: space-between;
}

.validation-status-badge {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  padding: 0.32rem 0.65rem;
  border: 1px solid #a7f3d0;
  border-radius: 999px;
  background: #ecfdf5;
  color: #047857;
  font-size: 0.72rem;
  font-weight: 800;
}

.st-key-transaction_confirmation_workspace
  [data-testid="stHorizontalBlock"] {
  flex-direction: row-reverse;
  align-items: flex-start;
  gap: 1rem;
}

.st-key-transaction_confirmation_card
  [data-testid="stVerticalBlock"] {
  gap: 0.45rem;
}

.transaction-core-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin: 0.85rem 0;
  padding: 0.6rem 0;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
}

.transaction-core-item {
  min-width: 0;
  padding: 0.7rem 1rem;
  border-right: 1px solid var(--border);
}

.transaction-core-item:last-child {
  border-right: 0;
}

.transaction-core-item small {
  display: block;
  margin-bottom: 0.4rem;
  color: var(--text-secondary);
  font-size: 0.7rem;
  font-weight: 700;
}

.transaction-core-item strong {
  display: block;
  overflow-wrap: anywhere;
  color: var(--text-primary);
  font-size: 1.1rem;
  line-height: 1.35;
}

.transaction-confirmed-facts {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  margin: -0.25rem 0 0.75rem;
}

.transaction-confirmed-facts span {
  display: flex;
  gap: 0.4rem;
  align-items: baseline;
  padding: 0.38rem 0.62rem;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: #f8fafc;
}

.transaction-confirmed-facts small {color: var(--text-secondary);}
.transaction-confirmed-facts strong {color: var(--text-primary); font-size: 0.76rem;}

.warning-banner {
  display: flex;
  gap: 0.7rem;
  align-items: center;
  padding: 0.9rem 1rem;
  margin: 0.75rem 0;
  border: 1px solid #efc36f;
  border-radius: 10px;
  color: #a64d00;
  background: #fffaf0;
  font-weight: 800;
}

.warning-banner .warning-icon {
  font-size: 1.05rem;
}

.result-grid {
  gap: 1rem;
}

.impact-card {
  min-height: 245px;
  padding: 1.15rem 1.2rem;
  border-top-width: 1px;
  box-shadow: var(--shadow-sm);
}

.impact-card.warning,
.impact-card.safe {
  border-top-width: 1px;
}

.impact-card.fx {border-color: #abc9f3;}
.impact-card.cash {border-color: #b8ddcf;}
.impact-card.collection {border-color: #f0ceb0;}

.impact-card .metric-heading {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  margin-bottom: 0.85rem;
  font-weight: 900;
}

.impact-card .metric-icon {
  display: inline-flex;
  width: 2rem;
  height: 2rem;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  color: #ffffff;
  background: var(--kb-blue);
}

.impact-card.cash .metric-icon {background: var(--kb-green);}
.impact-card.collection .metric-icon {background: var(--kb-orange);}
.impact-card.fx .metric-heading {color: var(--kb-blue);}
.impact-card.cash .metric-heading {color: var(--kb-green);}
.impact-card.collection .metric-heading {color: var(--kb-orange);}

.impact-card .hero-metric {
  margin: 1.2rem 0 0.8rem;
  color: var(--text-primary);
  font-size: 1.05rem;
  line-height: 1.5;
  text-align: center;
}

.impact-card .hero-metric b {
  display: block;
  color: var(--kb-blue);
  font-size: 1.65rem;
}

.impact-card .metric-row {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.48rem 0;
  border-bottom: 1px solid var(--border);
}

.impact-card .metric-row:last-child {border-bottom: 0;}
.impact-card .metric-row span {color: var(--text-secondary);}
.impact-card .metric-row b {color: var(--text-primary); text-align: right;}
.impact-card .metric-row b.danger {color: var(--kb-red);}

.fx-forecast-hero {
  position: relative;
  overflow: hidden;
  padding: 1.1rem 1.25rem 0.95rem;
  margin: 0.25rem 0 0.55rem;
  border: 1px solid #c8d7e8;
  border-top: 4px solid var(--kb-blue);
  border-radius: 17px;
  background: linear-gradient(135deg, #ffffff 0%, #f7faff 100%);
  box-shadow: 0 10px 26px rgba(9, 37, 75, 0.08);
}

.fx-forecast-hero.down {border-top-color: var(--kb-blue);}
.fx-forecast-hero.up {border-top-color: var(--kb-orange);}

.fx-forecast-top {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(14rem, 0.48fr);
  gap: 1.25rem;
  align-items: stretch;
}

.fx-forecast-copy .eyebrow {
  display: inline-flex;
  gap: 0.45rem;
  align-items: center;
  color: var(--text-secondary);
  font-size: 0.875rem;
  font-weight: 600;
  letter-spacing: 0.04em;
}

.fx-forecast-copy .eyebrow b {
  display: inline-flex;
  width: 1.65rem;
  height: 1.65rem;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  color: var(--kb-navy);
  background: var(--kb-gold);
  font-size: 0.62rem;
  letter-spacing: 0;
}

.fx-direction-line {
  display: flex;
  gap: 0.8rem;
  align-items: center;
  margin-top: 0.55rem;
}

.fx-direction-line .direction-symbol {
  display: inline-flex;
  width: 2.5rem;
  height: 2.5rem;
  flex: 0 0 2.5rem;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  color: #ffffff;
  background: var(--kb-blue);
  box-shadow: 0 6px 14px rgba(18, 97, 201, 0.2);
  font-size: 1.3rem;
  font-weight: 900;
}

.fx-forecast-hero.up .direction-symbol {
  background: var(--kb-orange);
  box-shadow: 0 6px 14px rgba(214, 106, 0, 0.18);
}

.fx-forecast-copy h2 {
  margin: 0;
  color: var(--text-primary);
  font-size: clamp(2rem, 2.5vw, 2.2rem);
  font-weight: 700;
  line-height: 1.15;
  letter-spacing: -0.035em;
}

.fx-forecast-copy p {
  margin: 0.3rem 0 0;
  color: var(--text-secondary);
  font-size: 0.875rem;
  line-height: 1.5;
}

.fx-primary-metric {
  display: flex;
  min-width: 0;
  flex-direction: column;
  justify-content: center;
  padding: 0.9rem 1rem;
  border: 1px solid #d2deeb;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.9);
}

.fx-primary-metric small {
  color: var(--text-secondary);
  font-size: 0.875rem;
  font-weight: 400;
  line-height: 1.35;
}

.fx-primary-metric strong {
  display: block;
  margin-top: 0.25rem;
  color: var(--text-primary);
  font-size: 2.05rem;
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  line-height: 1.15;
  letter-spacing: -0.035em;
  white-space: nowrap;
}

.fx-primary-metric .move-badge {
  align-self: flex-start;
  padding: 0.25rem 0.5rem;
  margin-top: 0.55rem;
  border-radius: 999px;
  color: #1558a4;
  background: #e9f2ff;
  font-size: 0.78rem;
  font-weight: 600;
}

.fx-forecast-hero.up .fx-primary-metric .move-badge {
  color: #994b00;
  background: #fff0df;
}

.fx-forecast-metrics {
  display: grid;
  grid-template-columns: minmax(0, 0.8fr) minmax(0, 0.8fr) minmax(0, 1.4fr);
  gap: 0.45rem;
  margin-top: 0.7rem;
}

.fx-forecast-metrics > div {
  min-width: 0;
  padding: 0.6rem 0.75rem;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: rgba(248, 250, 252, 0.88);
}

.fx-forecast-metrics small {
  display: block;
  margin-bottom: 0.22rem;
  color: var(--text-secondary);
  font-size: 0.875rem;
  font-weight: 400;
  line-height: 1.35;
}

.fx-forecast-metrics strong {
  display: block;
  color: var(--text-primary);
  font-size: 1.2rem;
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  line-height: 1.3;
  white-space: nowrap;
}

.fx-forecast-metrics strong i {
  padding: 0 0.2rem;
  color: #8a98aa;
  font-style: normal;
  font-weight: 500;
}

.fx-forecast-metrics > div > span {
  display: block;
  margin-top: 0.2rem;
  color: #718096;
  font-size: 0.875rem;
  line-height: 1.45;
}

.fx-forecast-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-top: 0.6rem;
}

.fx-forecast-meta span {
  display: inline-flex;
  gap: 0.28rem;
  padding: 0.3rem 0.5rem;
  border: 1px solid #e0e7ef;
  border-radius: 999px;
  color: var(--text-secondary);
  background: #ffffff;
  font-size: 0.8125rem;
  line-height: 1.25;
}

.fx-forecast-meta b {
  color: #344861;
  font-weight: 700;
}

.fx-horizon-note {
  display: flex;
  gap: 0.55rem;
  align-items: flex-start;
  padding: 0.55rem 0.7rem;
  margin: -0.1rem 0 0.7rem;
  border: 1px solid #d7e2ef;
  border-radius: 10px;
  color: var(--text-secondary);
  background: #f6f9fc;
}

.fx-horizon-note > span {
  display: inline-flex;
  width: 1.15rem;
  height: 1.15rem;
  flex: 0 0 1.15rem;
  align-items: center;
  justify-content: center;
  margin-top: 0.03rem;
  border-radius: 999px;
  color: #ffffff;
  background: #6f849d;
  font-size: 0.62rem;
  font-weight: 900;
}

.fx-horizon-note p {
  margin: 0;
  font-size: 0.68rem;
  line-height: 1.45;
}

.fx-horizon-note strong {color: #344861;}

.fx-range-chart {
  padding: 0.75rem 1rem;
  margin: 0 0 0.55rem;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: var(--surface);
  box-shadow: 0 5px 16px rgba(9, 37, 75, 0.05);
}

.fx-range-chart .range-heading {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: baseline;
  margin-bottom: 0.55rem;
}

.fx-range-chart .range-heading strong {
  color: var(--text-primary);
  font-size: 1.1rem;
  font-weight: 700;
}

.fx-range-chart .range-heading span {
  color: var(--text-secondary);
  font-size: 0.875rem;
  line-height: 1.45;
  text-align: right;
}

.fx-range-chart .range-labels {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
}

.fx-range-chart .range-labels > span:last-child {text-align: right;}

.fx-range-chart .range-labels small {
  display: block;
  color: var(--text-secondary);
  font-size: 0.875rem;
  line-height: 1.35;
}

.fx-range-chart .range-labels b {
  display: block;
  margin-top: 0.1rem;
  color: var(--text-primary);
  font-size: 0.98rem;
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  white-space: nowrap;
}

.fx-range-chart .range-track {
  position: relative;
  height: 0.68rem;
  margin: 1.4rem 0.45rem 1.5rem;
  border-radius: 999px;
  background: linear-gradient(90deg, #d6e8ff 0%, #f8e8a8 52%, #ffe1ca 100%);
  box-shadow: inset 0 0 0 1px rgba(9, 37, 75, 0.04);
}

.fx-range-chart .range-current,
.fx-range-chart .range-center {
  position: absolute;
  top: -0.35rem;
  display: flex;
  transform: translateX(-50%);
  flex-direction: column;
  align-items: center;
  color: var(--text-primary);
  font-size: 0.8125rem;
  font-weight: 600;
  white-space: nowrap;
}

.fx-range-chart .range-current i,
.fx-range-chart .range-center i {
  width: 0.8rem;
  height: 0.8rem;
  margin-bottom: 0.35rem;
  border: 3px solid #ffffff;
  border-radius: 999px;
  background: var(--kb-navy);
  box-shadow: 0 2px 5px rgba(9, 37, 75, 0.25);
}

.fx-range-chart .range-center i {background: var(--kb-gold);}

.fx-business-impact {
  display: grid;
  grid-template-columns: minmax(14rem, 0.8fr) minmax(0, 1.2fr);
  gap: 0.8rem;
  align-items: center;
  padding: 0.7rem 0.9rem;
  margin-bottom: 0.5rem;
  border: 1px solid #f0dfaa;
  border-radius: 13px;
  background: #fffbef;
}

.fx-business-impact .impact-copy {
  display: flex;
  gap: 0.65rem;
  align-items: center;
}

.fx-business-impact .impact-icon {
  display: inline-flex;
  width: 2.1rem;
  height: 2.1rem;
  flex: 0 0 2.1rem;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  color: var(--kb-navy);
  background: var(--kb-gold);
  font-size: 0.85rem;
  font-weight: 900;
}

.fx-business-impact .impact-copy strong {
  display: block;
  color: var(--text-primary);
  font-size: 1.05rem;
  font-weight: 700;
}

.fx-business-impact .impact-copy small {
  display: block;
  margin-top: 0.18rem;
  color: var(--text-secondary);
  font-size: 0.875rem;
  line-height: 1.45;
}

.fx-business-impact .impact-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.35rem;
}

.fx-business-impact .impact-metrics span {
  min-width: 0;
  padding-left: 0.75rem;
  border-left: 1px solid #eadba9;
}

.fx-business-impact .impact-metrics small {
  display: block;
  color: var(--text-secondary);
  font-size: 0.875rem;
  font-weight: 400;
  line-height: 1.35;
}

.fx-business-impact .impact-metrics b {
  display: block;
  margin-top: 0.16rem;
  color: var(--text-primary);
  font-size: 1.18rem;
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  line-height: 1.3;
  white-space: nowrap;
}

.fx-calculation-basis {
  color: var(--text-secondary);
  font-size: 0.875rem;
  line-height: 1.55;
}

.fx-calculation-basis ul {
  margin: 0.15rem 0 0.65rem;
  padding-left: 1.2rem;
}

.fx-calculation-basis li {margin: 0.15rem 0;}
.fx-calculation-basis p {margin: 0.45rem 0 0;}
.fx-calculation-basis strong {color: var(--text-primary);}

.st-key-workflow_analysis
  [data-testid="stExpander"]:has(.fx-calculation-basis) summary p {
  font-size: 0.9375rem;
  font-weight: 600;
}

.fx-forecast-notice {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  padding: 0.48rem 0.7rem;
  margin: 0 0 0.75rem;
  border: 1px solid #d7e2ef;
  border-radius: 9px;
  color: #344861;
  background: #f5f8fc;
}

.fx-forecast-notice > span {
  display: inline-flex;
  width: 1.05rem;
  height: 1.05rem;
  flex: 0 0 1.05rem;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  color: #ffffff;
  background: #6f849d;
  font-size: 0.65rem;
  font-weight: 800;
}

.fx-forecast-notice p {
  margin: 0;
  font-size: 0.9rem;
  line-height: 1.45;
}

.news-card-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.8rem;
  margin: 0.75rem 0 1.2rem;
}

.news-card {
  min-width: 0;
  padding: 1rem;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: var(--surface);
  box-shadow: var(--shadow-sm);
}

.news-card .news-meta {
  display: flex;
  justify-content: space-between;
  gap: 0.5rem;
  color: var(--text-secondary);
  font-size: 0.65rem;
}

.news-card h3 {
  display: -webkit-box;
  margin: 0.55rem 0;
  overflow: hidden;
  overflow-wrap: anywhere;
  color: var(--text-primary);
  font-size: 0.94rem;
  line-height: 1.4;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.news-card p,
.news-card small {
  display: block;
  color: var(--text-secondary);
  font-size: 0.75rem;
  line-height: 1.5;
}

.news-card .news-pressure {
  display: inline-flex;
  padding: 0.26rem 0.48rem;
  border-radius: 999px;
  color: #17436f;
  background: #eaf3ff;
  font-size: 0.68rem;
  font-weight: 800;
}

.news-tags {display: flex; flex-wrap: wrap; gap: 0.3rem; margin: 0.65rem 0;}
.news-tags span {
  padding: 0.2rem 0.4rem;
  border-radius: 6px;
  color: #725200;
  background: #fff4c7;
  font-size: 0.64rem;
  font-weight: 700;
}

.news-card a {display: inline-block; margin-top: 0.65rem; font-size: 0.75rem; font-weight: 800;}
.fx-empty-state,
.news-empty-state {
  padding: 1rem 1.1rem;
  margin: 0.5rem 0 1.1rem;
  border: 1px dashed #b8c5d5;
  border-radius: 13px;
  background: #f8fafc;
}
.fx-empty-state strong,
.news-empty-state strong {color: var(--text-primary);}
.fx-empty-state p,
.news-empty-state p {margin: 0.35rem 0 0; color: var(--text-secondary); font-size: 0.8rem;}

.consultation-card {
  min-height: 0;
  padding: 0.95rem 1rem;
  border-color: var(--border);
  box-shadow: 0 3px 10px rgba(9, 37, 75, 0.05);
}

.consultation-card .rank {
  margin: 0 0.55rem 0 0;
  vertical-align: middle;
}

.consultation-card .rank.rank-2 {background: var(--kb-green);}
.consultation-card .rank.rank-3 {background: var(--kb-orange);}

.consultation-card h4 {
  display: inline;
  min-height: 0;
  vertical-align: middle;
  font-size: 1rem;
}

.consultation-card .consultation-purpose-label {
  display: block;
  margin: 0.35rem 0 0.15rem;
  color: var(--text-secondary);
}

.consultation-card .consultation-next-action {
  padding: 0.65rem 0.75rem;
  border-top: 0;
  border-radius: 9px;
  background: #fff9e6;
}

.consultation-card .rationale-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem 0.8rem;
  margin-top: 0.65rem;
}

.consultation-card .rationale-grid p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 0.75rem;
}

.consultation-card .rationale-grid small,
.consultation-card .rationale-grid strong {
  display: inline;
  margin: 0;
  font-size: inherit;
}

.consultation-card .rationale-grid strong {
  margin-left: 0.25rem;
  color: var(--text-primary);
}

.consultation-card .decision {
  margin-top: 0.5rem;
  padding-top: 0.45rem;
}

.consultation-card .decision p {
  margin-top: 0.15rem;
}

div[class*="st-key-consultation_top3_"] [data-testid="stVerticalBlockBorderWrapper"] {
  border: 0;
  background: transparent;
}

.st-key-consultation_workspace [data-testid="stHorizontalBlock"] {
  align-items: flex-start;
}

.download-action-panel {
  padding: 1.05rem;
}

.st-key-stage5_download_panel [data-testid="stVerticalBlockBorderWrapper"] {
  padding: 1.15rem;
  border-color: var(--border);
  border-radius: var(--radius-card);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
}

.download-action-panel h3 {
  margin: 0;
  color: var(--text-primary);
  font-size: 1.1rem;
}

.download-action-panel p {
  margin: 0.35rem 0 0.9rem;
  color: var(--text-secondary);
  font-size: 0.8rem;
}

.official-candidate-list {
  margin: 0.8rem 0;
  padding-top: 0.75rem;
  border-top: 1px solid var(--border);
}

.official-candidate {
  display: flex;
  gap: 0.55rem;
  align-items: flex-start;
  padding: 0.55rem 0;
  border-bottom: 1px solid var(--border);
  color: var(--text-primary);
  font-size: 0.75rem;
}

.official-candidate .candidate-rank {
  display: inline-flex;
  width: 1.4rem;
  height: 1.4rem;
  flex: 0 0 1.4rem;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  color: #ffffff;
  background: var(--kb-blue);
  font-size: 0.68rem;
  font-weight: 900;
}

div[data-testid="stButton"] > button,
div[data-testid="stDownloadButton"] > button,
div[data-testid="stFormSubmitButton"] > button {
  border-radius: 9px;
  font-weight: 800;
}

div[data-testid="stButton"] > button[kind="primary"],
div[data-testid="stDownloadButton"] > button[kind="primary"],
div[data-testid="stFormSubmitButton"] > button[kind="primary"],
div[data-testid="stFormSubmitButton"] > button[kind="primaryFormSubmit"] {
  background: linear-gradient(135deg, #07366f, #0c4a8f);
  box-shadow: 0 7px 16px rgba(6, 43, 92, 0.2);
}

div[data-testid="stButton"] > button:focus-visible,
div[data-testid="stDownloadButton"] > button:focus-visible,
div[data-testid="stFormSubmitButton"] > button:focus-visible {
  outline: 3px solid rgba(245, 184, 0, 0.72);
  outline-offset: 2px;
}

@media (max-width: 900px) {
  section[data-testid="stMain"] {
    width: 100%;
    margin-left: 0;
  }

  .block-container {
    padding-left: 1rem;
    padding-right: 1rem;
  }

  .st-key-mobile_navigation {
    display: block;
    position: sticky;
    top: 0.45rem;
    z-index: 50;
    padding: 0.35rem;
    margin-bottom: 0.75rem;
    border: 1px solid var(--border);
    border-radius: 12px;
    background: rgba(255, 255, 255, 0.96);
    box-shadow: var(--shadow-sm);
  }

  .st-key-mobile_navigation [role="radiogroup"] {
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem 0.7rem;
  }

  .st-key-workflow_navigation {
    position: static;
    padding: 0.25rem;
  }

  .st-key-workflow_navigation [data-testid="stHorizontalBlock"] {
    display: grid;
    grid-template-columns: 1fr 1fr;
  }

  .st-key-workflow_navigation [data-testid="stHorizontalBlock"]
    > div[data-testid="stColumn"] {
    width: 100% !important;
    min-width: 0 !important;
    flex: none !important;
  }

  .transaction-core-grid,
  .result-grid {
    grid-template-columns: 1fr;
  }

  .fx-forecast-metrics {grid-template-columns: repeat(2, minmax(0, 1fr));}
  .fx-forecast-metrics .period {grid-column: span 2;}
  .news-card-grid {grid-template-columns: repeat(2, minmax(0, 1fr));}

  .transaction-core-item {
    border-right: 0;
    border-bottom: 1px solid var(--border);
  }

  .transaction-core-item:last-child {border-bottom: 0;}

  .st-key-consultation_workspace [data-testid="stHorizontalBlock"] {
    display: grid;
    grid-template-columns: 1fr;
    gap: 1rem;
  }

  .st-key-consultation_workspace [data-testid="stHorizontalBlock"]
    > div[data-testid="stColumn"] {
    width: 100% !important;
    min-width: 0 !important;
    flex: none !important;
  }
}

@media (max-width: 640px) {
  .block-container {
    max-width: 100vw;
    padding: 0.65rem 0.75rem 3rem;
  }

  .page-header {
    align-items: flex-start;
    margin-bottom: 0.7rem;
  }

  .page-header .page-step {
    width: 2rem;
    height: 2rem;
    flex-basis: 2rem;
    font-size: 0.86rem;
  }

  .page-header h1 {font-size: 1.25rem;}
  .page-header p {font-size: 0.76rem;}

  .st-key-workflow_analysis .page-header h1 {font-size: 1.55rem;}
  .st-key-workflow_analysis .page-header {
    gap: 0.7rem;
    margin-bottom: 0.9rem;
  }
  .st-key-workflow_analysis .page-header p {font-size: 0.875rem;}

  .home-hero {
    padding: 1.1rem 0.25rem 0.75rem;
    text-align: left;
  }

  .home-hero h1 {font-size: 1.9rem;}
  .home-hero p {font-size: 0.88rem;}

  .fx-forecast-hero {padding: 0.8rem;}
  .fx-forecast-top {grid-template-columns: 1fr; gap: 0.55rem;}
  .fx-forecast-copy h2 {font-size: 1.8rem;}
  .fx-primary-metric {padding: 0.7rem 0.8rem;}
  .fx-primary-metric small,
  .fx-forecast-metrics small,
  .fx-forecast-metrics > div > span,
  .fx-range-chart .range-labels small,
  .fx-business-impact .impact-metrics small {font-size: 0.8125rem;}
  .fx-primary-metric strong {font-size: 1.75rem;}
  .fx-forecast-metrics {grid-template-columns: 1fr;}
  .fx-forecast-metrics .period {grid-column: auto;}
  .fx-forecast-metrics strong {font-size: 1.1rem;}
  .fx-range-chart .range-heading {
    align-items: flex-start;
    flex-direction: column;
    gap: 0.25rem;
  }
  .fx-range-chart .range-heading span {text-align: left;}
  .news-card-grid {grid-template-columns: 1fr;}
  .fx-business-impact {grid-template-columns: 1fr; gap: 0.7rem;}
  .fx-business-impact .impact-metrics {grid-template-columns: 1fr;}
  .fx-business-impact .impact-metrics span {
    padding-left: 0;
    border-left: 0;
  }
  .fx-business-impact .impact-metrics b {font-size: 1.08rem;}
  .fx-forecast-notice {
    align-items: flex-start;
    padding: 0.45rem 0.6rem;
  }
  .fx-forecast-notice p {font-size: 0.875rem;}

  .st-key-official_candidate_cards [data-testid="stHorizontalBlock"],
  .st-key-official_candidate_input_profile_form
    [data-testid="stHorizontalBlock"] {
    display: grid;
    grid-template-columns: 1fr;
    gap: 0.65rem;
  }

  .st-key-official_candidate_cards [data-testid="stHorizontalBlock"]
    > div[data-testid="stColumn"],
  .st-key-official_candidate_input_profile_form
    [data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
    width: 100% !important;
    min-width: 0 !important;
    flex: none !important;
  }

  .journey-track {
    grid-template-columns: 1fr 1fr;
  }

  .journey-track .journey-step::after {display: none;}

  .trade-identity {
    align-items: flex-start;
    flex-direction: column;
    gap: 0.5rem;
    padding-left: 0;
    padding-right: 0;
  }

  .transaction-summary-heading {
    align-items: flex-start;
    flex-direction: column;
  }

  .transaction-core-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .transaction-core-item {
    border-right: 1px solid var(--border);
    border-bottom: 0;
  }

  .transaction-core-item:nth-child(-n + 2) {
    border-bottom: 1px solid var(--border);
  }

  .transaction-core-item:nth-child(2n) {
    border-right: 0;
  }

  .st-key-transaction_confirmation_workspace
    [data-testid="stHorizontalBlock"] {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 0.75rem;
  }

  .st-key-transaction_confirmation_workspace
    [data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
    width: 100% !important;
    min-width: 0 !important;
    flex: none !important;
  }

  .transaction-core-item strong {font-size: 1rem;}
  .impact-card {min-height: 0;}

  div[class*="st-key-consultation_top3_"]
    [data-testid="stHorizontalBlock"] {
    display: grid;
    grid-template-columns: 1fr;
    gap: 0.65rem;
  }

  div[class*="st-key-consultation_top3_"]
    [data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
    width: 100% !important;
    min-width: 0 !important;
    flex: none !important;
  }

  div[class*="st-key-consultation_top3_"]
    [data-testid="stPopover"] button {
    min-height: 2.4rem;
    padding: 0.35rem 0.2rem;
    font-size: 0.68rem;
    white-space: nowrap;
  }

  .sample-info-card {
    padding: 0.85rem;
  }

  [data-testid="stDataFrame"] {
    width: 100% !important;
    max-width: calc(100vw - 1.5rem);
    overflow-x: auto;
  }

  button, [role="button"] {
    max-width: 100%;
    white-space: normal;
    overflow-wrap: anywhere;
  }
}
</style>
"""


def apply_kb_workspace_theme() -> None:
    st.markdown(KB_WORKSPACE_CSS, unsafe_allow_html=True)
