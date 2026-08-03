from html import escape
from typing import Dict, List, Optional

import streamlit as st


PAGE_HOME = "home"
PAGE_TRANSACTION = "transaction"
PAGE_ANALYSIS = "analysis"
PAGE_CONSULTATION = "consultation"
PAGE_DOWNLOAD = "download"

NAV_ITEMS: List[Dict[str, str]] = [
    {"page": PAGE_HOME, "icon": "⌂", "label": "홈"},
    {"page": PAGE_TRANSACTION, "icon": "▤", "label": "거래 분석"},
    {"page": PAGE_ANALYSIS, "icon": "▥", "label": "환율 전망·위험"},
    {"page": PAGE_CONSULTATION, "icon": "▣", "label": "금융지원 추천"},
    {"page": PAGE_DOWNLOAD, "icon": "⇩", "label": "상담 준비·보고서"},
]

PAGE_LABELS: Dict[str, str] = {
    PAGE_HOME: "홈",
    PAGE_TRANSACTION: "거래 분석",
    PAGE_ANALYSIS: "환율 전망·위험",
    PAGE_CONSULTATION: "금융지원 추천",
    PAGE_DOWNLOAD: "상담 준비·보고서",
}


def set_active_page(page: str) -> None:
    if page not in PAGE_LABELS:
        raise ValueError("지원하지 않는 화면입니다: {}".format(page))
    st.session_state["active_page"] = page


def active_page() -> str:
    value = str(st.session_state.get("active_page", PAGE_HOME))
    return value if value in PAGE_LABELS else PAGE_HOME


def _mobile_page_changed() -> None:
    selected = st.session_state.get("mobile_navigation_widget")
    for page, label in PAGE_LABELS.items():
        if selected == label:
            set_active_page(page)
            return


def _page_enabled(
    page: str,
    *,
    has_journey: bool,
    has_confirmation: bool,
    has_consultation: bool,
) -> bool:
    # Navigation must never become a dead end. Each destination renders its
    # own prerequisite guidance while preserving the current analysis state.
    return page in PAGE_LABELS


def render_sidebar_navigation(
    *,
    has_journey: bool,
    has_confirmation: bool,
    has_consultation: bool,
) -> None:
    current = active_page()
    st.markdown(
        "<div class='sidebar-brand'><span class='mark'>KB</span>"
        "<strong>KBaiAgent</strong>"
        "<p>수출입 거래 금융 리스크 분석</p></div>"
        "<div class='sidebar-section-label'>Workspace</div>",
        unsafe_allow_html=True,
    )
    for item in NAV_ITEMS:
        page = item["page"]
        st.button(
            "{}  {}".format(item["icon"], item["label"]),
            key="nav_{}".format(page),
            type="primary" if page == current else "secondary",
            disabled=not _page_enabled(
                page,
                has_journey=has_journey,
                has_confirmation=has_confirmation,
                has_consultation=has_consultation,
            ),
            on_click=set_active_page,
            args=(page,),
            width="stretch",
            help=(
                None
                if _page_enabled(
                    page,
                    has_journey=has_journey,
                    has_confirmation=has_confirmation,
                    has_consultation=has_consultation,
                )
                else "앞 단계의 확인을 완료하면 이동할 수 있습니다."
            ),
        )


def render_mobile_navigation(
    *,
    has_journey: bool,
    has_confirmation: bool,
    has_consultation: bool,
) -> None:
    enabled_pages = [
        item["page"]
        for item in NAV_ITEMS
        if _page_enabled(
            item["page"],
            has_journey=has_journey,
            has_confirmation=has_confirmation,
            has_consultation=has_consultation,
        )
    ]
    current = active_page()
    if current not in enabled_pages:
        current = PAGE_HOME
        set_active_page(current)
    selected_label = PAGE_LABELS[current]
    if st.session_state.get("mobile_navigation_widget") != selected_label:
        st.session_state["mobile_navigation_widget"] = selected_label
    with st.container(key="mobile_navigation"):
        st.radio(
            "화면 이동",
            [PAGE_LABELS[page] for page in enabled_pages],
            key="mobile_navigation_widget",
            on_change=_mobile_page_changed,
            label_visibility="collapsed",
            horizontal=True,
        )


def render_workflow_navigation() -> None:
    """Render the business steps with the canonical application page state.

    Native ``st.tabs`` retain their selected index in the browser and cannot
    be moved by a server-side callback.  Using buttons here keeps sidebar,
    confirmation, consultation, and download transitions on one state path.
    """

    current = active_page()
    items = [
        (PAGE_TRANSACTION, "거래 분석"),
        (PAGE_ANALYSIS, "환율 전망·위험"),
        (PAGE_CONSULTATION, "금융지원 추천"),
        (PAGE_DOWNLOAD, "상담 준비·보고서"),
    ]
    with st.container(key="workflow_navigation"):
        columns = st.columns(len(items), gap="small")
        for index, (page, label) in enumerate(items):
            columns[index].button(
                label,
                key="workflow_nav_{}".format(page),
                type="primary" if current == page else "secondary",
                on_click=set_active_page,
                args=(page,),
                width="stretch",
            )


def render_workflow_panel_visibility(page: str) -> None:
    """Expose exactly one workflow panel without discarding its state."""

    panel_by_page = {
        PAGE_TRANSACTION: "workflow_transaction",
        PAGE_ANALYSIS: "workflow_analysis",
        PAGE_CONSULTATION: "workflow_consultation",
        PAGE_DOWNLOAD: "workflow_download",
    }
    selected = panel_by_page.get(page, "workflow_transaction")
    selectors = [
        ".st-key-{}".format(container_key)
        for container_key in panel_by_page.values()
    ]
    wrapper_selectors = [
        "[data-testid='stLayoutWrapper']:has(> {})".format(selector)
        for selector in selectors
    ]
    with st.container(key="workflow_visibility_style"):
        st.markdown(
            "<style>"
            "[data-testid='stLayoutWrapper']:has(> "
            ".st-key-workflow_visibility_style){{display:none;}}"
            "{all_wrappers}{{display:none;}}"
            "[data-testid='stLayoutWrapper']:has(> .st-key-{selected})"
            "{{display:flex;}}"
            "{all_panels}{{display:none;}}"
            ".st-key-{selected}{{display:block;}}"
            "</style>".format(
                all_wrappers=", ".join(wrapper_selectors),
                all_panels=", ".join(selectors),
                selected=selected,
            ),
            unsafe_allow_html=True,
        )


def render_page_header(
    *,
    step: str,
    title: str,
    description: str,
) -> None:
    st.markdown(
        "<header class='page-header'><span class='page-step'>{}</span>"
        "<div><h1>{}</h1><p>{}</p></div></header>".format(
            escape(step),
            escape(title),
            escape(description),
        ),
        unsafe_allow_html=True,
    )


def render_step_indicator(active_step: int, completed_step: int) -> None:
    labels = [
        "거래 분석",
        "환율 전망·위험",
        "금융지원 추천",
        "상담 준비·보고서",
    ]
    cells: List[str] = []
    for index, label in enumerate(labels, start=1):
        state_class = (
            "done"
            if completed_step >= index
            else "current"
            if active_step == index
            else "todo"
        )
        icon = "✓" if completed_step >= index else str(index)
        cells.append(
            "<div class='journey-step {}'><span class='journey-dot'>{}</span>"
            "<span>{}</span></div>".format(
                state_class,
                icon,
                escape(label),
            )
        )
    st.markdown(
        "<div class='journey-track'>{}</div>".format("".join(cells)),
        unsafe_allow_html=True,
    )


def render_sample_info_card(title: str, description: str) -> None:
    st.markdown(
        "<div class='sample-info-card'><span class='sample-icon'>▤</span>"
        "<div><strong>{}</strong><p>{}</p></div></div>".format(
            escape(title),
            escape(description),
        ),
        unsafe_allow_html=True,
    )


def render_demo_summary(items: Dict[str, str]) -> None:
    rows = "".join(
        "<div class='provider-row'><span>{}</span><strong>{}</strong></div>".format(
            escape(label),
            escape(value),
        )
        for label, value in items.items()
    )
    st.markdown(
        "<div class='home-settings-panel'><h3>3분 동안 확인할 내용</h3>"
        "{}<p>기술 설정과 원본 데이터는 필요한 경우에만 펼쳐볼 수 "
        "있습니다.</p>"
        "</div>".format(rows),
        unsafe_allow_html=True,
    )


def render_warning_banner(message: str) -> None:
    st.markdown(
        "<div class='warning-banner'><span class='warning-icon'>△</span>"
        "<span>{}</span></div>".format(escape(message)),
        unsafe_allow_html=True,
    )


def render_empty_state(title: str, description: str) -> None:
    st.markdown(
        "<div class='state-banner warning'><span class='state-icon'>!</span>"
        "<div><strong>{}</strong><p>{}</p></div></div>".format(
            escape(title),
            escape(description),
        ),
        unsafe_allow_html=True,
    )
