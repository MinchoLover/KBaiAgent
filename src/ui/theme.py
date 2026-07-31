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

  .home-hero {
    padding: 1.1rem 0.25rem 0.75rem;
    text-align: left;
  }

  .home-hero h1 {font-size: 1.9rem;}
  .home-hero p {font-size: 0.88rem;}

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

  .transaction-core-item strong {font-size: 1rem;}
  .impact-card {min-height: 0;}

  div[class*="st-key-consultation_top3_"]
    [data-testid="stHorizontalBlock"] {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.3rem;
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
