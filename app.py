import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import openai
import re
import os
import glob

# ─── 페이지 설정 ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Executive Leadership Coach (MD)",
    page_icon="👑",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── 커스텀 CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stMetricValue"], [data-testid="stMetricValue"] > div {
    white-space: normal !important;
    word-break: keep-all !important;
    overflow-wrap: break-word !important;
    font-size: 1.3rem !important;
    line-height: 1.4 !important;
    overflow: visible !important;
    text-overflow: clip !important;
}
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] > div {
    white-space: normal !important;
    word-break: keep-all !important;
    overflow-wrap: break-word !important;
    overflow: visible !important;
    text-overflow: clip !important;
}
div[data-testid="metric-container"], div[data-testid="metric-container"] > div {
    height: auto !important;
    overflow: visible !important;
}
</style>
""", unsafe_allow_html=True)

# ─── API Key ───────────────────────────────────────────────────────────────────
try:
    OPENAI_API_KEY = st.secrets["JYL"]
except (FileNotFoundError, KeyError):
    OPENAI_API_KEY = None

# ─── SKMS 지식 베이스 ──────────────────────────────────────────────────────────
SKMS_KNOWLEDGE_BASE = """
[SKMS(SK Management System) 및 사내 고유 철학 핵심 요약]
본 자료는 SK의 경영철학이자 기업문화의 근간인 SKMS 원문 및 Workbook의 핵심 내용입니다. 리더십 코칭 시 아래 개념들을 적극 인용하여 조언하세요.

1. 경영의 궁극적 목적: '구성원의 지속적인 행복 창출'
   - 회사는 구성원이 함께 모여 일하며 스스로의 행복을 지속적으로 키워나가는 공동체입니다.
   - 리더는 구성원들이 행복 경영의 주체로서 역할을 다할 수 있도록 이끌어야 합니다.

2. SUPEX (Super Excellent)
   - 인간의 능력으로 도달할 수 있는 최고의 수준을 의미합니다.
   - 기존의 틀을 깨는 혁신적인 목표를 세우고 달성하려는 지향점입니다.

3. VWBE (Voluntarily, Willingly, Brain Engagement)
   - '자발적이고 의욕적인 두뇌활용'을 뜻합니다.
   - 구성원이 스스로 동기부여되어 업무에 몰입하는 상태로, SUPEX 달성을 위한 필수 조건입니다.
   - 리더의 핵심 역할은 구성원이 VWBE 할 수 있는 환경을 조성하는 것입니다.

4. 패기 (일과 싸워 이기는 기질)
   - 스스로 높은 목표를 세우고(도전), 기존의 틀을 깨며(혁신), 끝까지 완수하는(실행) 태도입니다.

5. Teamwork (팀워크)
   - 공동의 목표 달성을 위해 서로 소통하고 협력하는 과정입니다.
   - 리더는 신뢰 기반의 협력을 촉진하고 긍정적인 조직 문화를 구축해야 합니다.

6. 리더의 역할과 솔선수범
   - 리더는 구성원의 성장과 행복을 지원하는 조력자이자 코치입니다.
   - 리더 스스로 SKMS를 깊이 이해하고 행동으로 실천(솔선수범)하여 구성원의 귀감이 되어야 합니다.
"""

# ─── 리더십 4대 영역 정의 ──────────────────────────────────────────────────────
AREAS = [
    "①SKMS에 대한 확신과 열정",
    "②혁신적 전략 수립",
    "③과감한 돌파와 실행",
    "④VWBE 문화 구축",
]
AREA_LABELS = [
    "①SKMS에 대한<br>확신과 열정",
    "②혁신적<br>전략 수립",
    "③과감한<br>돌파와 실행",
    "④VWBE<br>문화 구축",
]

DEFAULT_MD_DIR = "진단_App/DID별_진단결과"

# ─── MD 파싱 함수 ──────────────────────────────────────────────────────────────
def parse_value(val_str):
    """문자열 값을 float로 변환. %, 정수, 소수, '-' 처리."""
    if val_str in ('-', '', 'None', None):
        return None
    val_str = str(val_str).strip()
    if val_str.endswith('%'):
        try:
            return float(val_str[:-1])
        except ValueError:
            return None
    try:
        return float(val_str)
    except ValueError:
        return None


def _parse_table_block(block_text):
    """
    마크다운 테이블 블록에서 {행레이블: {열레이블: float}} 딕셔너리와
    열 이름 리스트를 반환.
    """
    lines = [l for l in block_text.split('\n') if l.strip().startswith('|')]
    if len(lines) < 3:
        return {}, []

    header_cells = [c.strip() for c in lines[0][1:-1].split('|')]
    col_names = header_cells[1:]

    result = {}
    for line in lines[2:]:  # 헤더와 구분자(separator) 건너뜀
        cells = [c.strip() for c in line[1:-1].split('|')]
        if not cells or not cells[0]:
            continue
        # 구분자 행 제거
        if re.match(r'^[:\-]+$', cells[0]):
            continue
        label = cells[0]
        row = {}
        for i, col in enumerate(col_names):
            val_str = cells[i + 1] if i + 1 < len(cells) else '-'
            row[col] = parse_value(val_str)
        result[label] = row

    return result, col_names


def _parse_basic_info(section_text, data):
    for line in section_text.split('\n'):
        if not line.strip().startswith('|'):
            continue
        cells = [c.strip() for c in line[1:-1].split('|')]
        if len(cells) == 2:
            key, val = cells
            if key and not re.match(r'^[:\-]+$', key) and key not in ('항목',):
                data['meta'][key] = val


def _parse_diagnostic_section(section_text, data, group):
    """구성원 또는 동료 섹션을 파싱하여 scores/pctile/factors를 채움."""
    subsections = re.split(r'\n(?=### )', section_text)
    for sub in subsections:
        sub = sub.strip()
        if not sub:
            continue
        sub_heading = sub.split('\n')[0].strip()

        if '리더십 영역별 점수' in sub_heading:
            table, years = _parse_table_block(sub)
            if years and not data['years']:
                data['years'] = years
            for factor, year_vals in table.items():
                for year, val in year_vals.items():
                    data[f'{group}_scores'].setdefault(year, {})[factor] = val

        elif '백분위' in sub_heading:
            table, _ = _parse_table_block(sub)
            for factor, year_vals in table.items():
                for year, val in year_vals.items():
                    data[f'{group}_pctile'].setdefault(year, {})[factor] = val

        elif '행동요인별 점수' in sub_heading:
            table, _ = _parse_table_block(sub)
            for factor, year_vals in table.items():
                for year, val in year_vals.items():
                    data[f'{group}_factors'].setdefault(year, {})[factor] = val


def _parse_self_section(section_text, data):
    """본인 진단(2025년) 섹션 - 2열 테이블(요인, 점수)."""
    for line in section_text.split('\n'):
        if not line.strip().startswith('|'):
            continue
        cells = [c.strip() for c in line[1:-1].split('|')]
        if len(cells) == 2:
            key, val_str = cells
            if key and not re.match(r'^[:\-]+$', key) and key not in ('요인', '항목'):
                val = parse_value(val_str)
                if val is not None:
                    data['self_scores'][key] = val


def _parse_texts_section(section_text, data):
    """주관식 응답 섹션 → {year: {label: text}}."""
    year_sections = re.split(r'\n(?=### )', section_text)
    for ys in year_sections:
        ys = ys.strip()
        if not ys:
            continue
        ys_first = ys.split('\n')[0].strip()
        m = re.match(r'###\s+(\d{4})년', ys_first)
        if not m:
            continue
        year = m.group(1)

        year_texts = {}
        current_label = None
        text_acc = []

        for line in ys.split('\n')[1:]:
            bold_m = re.match(r'^\*\*(.+)\*\*$', line.strip())
            if bold_m:
                if current_label and text_acc:
                    year_texts[current_label] = '\n'.join(text_acc).strip()
                current_label = bold_m.group(1)
                text_acc = []
            elif current_label:
                text_acc.append(line)

        if current_label and text_acc:
            year_texts[current_label] = '\n'.join(text_acc).strip()

        if year_texts:
            data['texts'][year] = year_texts


def parse_leader_data(md_text):
    """
    MD 파일 전체 텍스트를 파싱하여 구조화된 딕셔너리 반환.
    반환 구조:
      meta: {항목: 값}
      member_scores / peer_scores: {year: {factor: float}}
      member_pctile / peer_pctile: {year: {factor: float}}
      member_factors / peer_factors: {year: {factor: float}}
      self_scores: {factor: float}
      texts: {year: {label: text}}
      years: [year_str, ...]
    """
    data = {
        'meta': {},
        'member_scores': {}, 'member_pctile': {}, 'member_factors': {},
        'peer_scores': {}, 'peer_pctile': {}, 'peer_factors': {},
        'self_scores': {},
        'texts': {},
        'years': [],
    }

    md_text = md_text.replace('\r\n', '\n').replace('\r', '\n')
    top_sections = re.split(r'\n(?=## )', '\n' + md_text)

    for section in top_sections:
        section = section.strip()
        if not section:
            continue
        heading = section.split('\n')[0].strip()

        if heading == '## 기본 정보':
            _parse_basic_info(section, data)
        elif heading == '## 구성원 진단':
            _parse_diagnostic_section(section, data, 'member')
        elif heading == '## 동료 진단':
            _parse_diagnostic_section(section, data, 'peer')
        elif '## 본인 진단' in heading:
            _parse_self_section(section, data)
        elif heading == '## 주관식 응답':
            _parse_texts_section(section, data)

    return data


# ─── 파일 스캔 & 로드 ──────────────────────────────────────────────────────────
@st.cache_data
def scan_leaders(md_dir):
    """md_dir 내 .md 파일을 스캔하여 {표시명: 파일경로} 반환."""
    leaders = {}
    for fp in sorted(glob.glob(os.path.join(md_dir, "*.md"))):
        fname = os.path.basename(fp)
        if fname.startswith('sample_'):
            continue
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
            m = re.match(r'^#\s+(.+?)\s+\((\d+)\)', first_line)
            if m:
                name, did = m.group(1), m.group(2)
                leaders[f"{name} ({did})"] = fp
        except Exception:
            pass
    return leaders


@st.cache_data
def load_and_parse(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return parse_leader_data(f.read())


def load_from_upload(uploaded_file):
    content = uploaded_file.read().decode('utf-8')
    return parse_leader_data(content)


# ─── 사이드바 ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("👑 임원 리더십 코칭")

    if not OPENAI_API_KEY:
        user_key = st.text_input("🔑 OpenAI API Key 입력", type="password", placeholder="sk-...")
        if user_key:
            OPENAI_API_KEY = user_key
            st.success("API Key 적용 완료!")

    st.divider()

    # 데이터 소스 선택 (업로드 전용)
    selected_display = None
    parsed_data = None

    st.info("본인의 리더십 진단 결과(`.md` 파일)를 업로드해주세요.")
    uploaded = st.file_uploader("📄 MD 파일 업로드", type=["md"], accept_multiple_files=False)
    if uploaded:
        parsed_data = load_from_upload(uploaded)
        # 파일 첫 줄에서 이름 추출
        uploaded.seek(0)
        first = uploaded.read().decode('utf-8').split('\n')[0]
        m = re.match(r'^#\s+(.+?)\s+\((\d+)\)', first.strip())
        selected_display = m.group(1) if m else uploaded.name

    # 임원 변경 시 세션 초기화
    if 'current_leader' not in st.session_state:
        st.session_state.current_leader = None

    if selected_display != st.session_state.current_leader:
        st.session_state.current_leader = selected_display
        st.session_state.dash_summary = None
        st.session_state.qualitative_analysis = None
        st.session_state.messages = []

    if parsed_data and not OPENAI_API_KEY:
        st.warning("⚠️ API Key 미설정 (AI 기능 제한)")


# ─── 메인 로직 ────────────────────────────────────────────────────────────────
if parsed_data and selected_display:
    ld = parsed_data
    meta = ld['meta']

    # 연도 목록
    sorted_years = ld['years']
    if not sorted_years:
        st.error("진단 연도 데이터를 찾을 수 없습니다.")
        st.stop()

    latest_year = sorted_years[-1]
    prev_year = sorted_years[-2] if len(sorted_years) > 1 else None

    # ── 4대 영역 점수 by year ───────────────────────────────────────────────
    grouped_scores = {}
    for year in sorted_years:
        grouped_scores[year] = {}
        for area, label in zip(AREAS, AREA_LABELS):
            val = ld['member_scores'].get(year, {}).get(area)
            grouped_scores[year][label] = val if (val and val > 0) else 0.0

    # ── 연도별 평균 점수 ─────────────────────────────────────────────────────
    avg_scores = {}
    for year in sorted_years:
        vals = [v for v in grouped_scores[year].values() if v > 0]
        avg_scores[year] = sum(vals) / len(vals) if vals else 0.0

    # ── 백분위 (0~100 스케일) ────────────────────────────────────────────────
    percentiles = {}
    for year in sorted_years:
        pct = ld['member_pctile'].get(year, {}).get('종합 백분위')
        percentiles[year] = pct if pct is not None else 0.0

    # ── 최신 연도 동료 점수 ──────────────────────────────────────────────────
    latest_peer_group = {}
    for area, label in zip(AREAS, AREA_LABELS):
        val = ld['peer_scores'].get(latest_year, {}).get(area)
        latest_peer_group[label] = val if (val and val > 0) else 0.0

    # ── 행동요인 강점/약점 ───────────────────────────────────────────────────
    all_factors = {
        k: v for k, v in ld['member_factors'].get(latest_year, {}).items()
        if v is not None and v > 0
    }
    if all_factors:
        top_comp = max(all_factors, key=all_factors.get)
        bot_comp = min(all_factors, key=all_factors.get)
    else:
        top_comp, bot_comp = "-", "-"

    curr_score = avg_scores[latest_year]
    delta_total = (curr_score - avg_scores[prev_year]) if prev_year else 0.0

    # ─── 리더명 추출 ──────────────────────────────────────────────────────────
    leader_name = meta.get('이름', selected_display)
    st.title(f"📊 {leader_name} 님 리더십 진단 분석")

    tab1, tab2, tab3 = st.tabs(["📈 종합 대시보드", "📝 주관식 심층분석", "🤖 AI 코칭"])

    # ═══════════════════════════════════════════════════════════════════════════
    # [TAB 1] 종합 대시보드
    # ═══════════════════════════════════════════════════════════════════════════
    with tab1:
        st.subheader("Overview (구성원 응답 기준)")

        m1, m2, m3 = st.columns(3)
        m1.metric(
            f"{latest_year} 종합 점수",
            f"{curr_score:.2f}",
            f"{delta_total:+.2f} ({prev_year} 대비)" if prev_year else None
        )
        m2.metric("최고 강점", top_comp)
        m3.metric("보완 필요", bot_comp)

        # 기본 정보 expander
        with st.expander("👤 기본 정보 보기"):
            info_cols = st.columns(4)
            info_items = [
                ("회사명", meta.get('회사명', '-')),
                ("직책", meta.get('직책', '-')),
                ("리더십 모델", meta.get('리더십진단 모델', '-')),
                ("EMD 여부", meta.get('EMD 여부', '-')),
            ]
            for col, (k, v) in zip(info_cols, info_items):
                col.metric(k, v)

        st.divider()

        c1, c2, c3 = st.columns([1, 1, 1.4])

        with c1:
            st.markdown("##### 📅 종합 점수 추이")
            trend_df_data = {"Year": sorted_years, "Score": [avg_scores[y] for y in sorted_years]}
            import pandas as pd
            fig_bar = px.bar(
                pd.DataFrame(trend_df_data), x="Year", y="Score", text="Score"
            )
            fig_bar.update_traces(
                marker_color='#2563eb', textposition="outside", texttemplate='%{text:.2f}'
            )
            fig_bar.update_yaxes(range=[3, 5])
            fig_bar.update_layout(margin={"t": 30, "b": 30, "l": 20, "r": 20})
            st.plotly_chart(fig_bar, use_container_width=True)

        with c2:
            st.markdown("##### 📈 백분위 추이 (상위 %)")
            perc_df = pd.DataFrame({
                "Year": sorted_years,
                "Percentile": [percentiles[y] for y in sorted_years]
            })
            fig_perc = px.line(perc_df, x="Year", y="Percentile", markers=True, text="Percentile")
            fig_perc.update_traces(
                line_color='#10b981', line_width=3,
                textposition="top center", texttemplate='%{text:.1f}%'
            )
            fig_perc.update_yaxes(range=[105, -5])
            fig_perc.update_layout(margin={"t": 30, "b": 30, "l": 20, "r": 20})
            st.plotly_chart(fig_perc, use_container_width=True)

        with c3:
            st.markdown("##### 🎯 리더십 영역별 변화")
            fig_db = go.Figure()
            colors = ['#cbd5e1', '#94a3b8', '#2563eb', '#1e3a8a', '#0f0a1e']
            cats = AREA_LABELS

            # 배경 연결선 (min~max)
            for cat in cats:
                cat_vals = [grouped_scores[y].get(cat, 0) for y in sorted_years]
                cat_vals = [v for v in cat_vals if v > 0]
                if cat_vals:
                    fig_db.add_trace(go.Scatter(
                        x=[min(cat_vals), max(cat_vals)], y=[cat, cat],
                        mode="lines",
                        line={"color": "#e2e8f0", "width": 4},
                        showlegend=False, hoverinfo="skip"
                    ))

            for i, year in enumerate(sorted_years):
                y_data, x_data = [], []
                for cat in cats:
                    v = grouped_scores[year].get(cat, 0)
                    if v > 0:
                        y_data.append(cat)
                        x_data.append(v)

                is_latest = (year == latest_year)
                c_color = colors[i] if i < len(colors) else '#000000'

                fig_db.add_trace(go.Scatter(
                    x=x_data, y=y_data,
                    mode="markers+text" if is_latest else "markers",
                    text=[f"{v:.2f}" for v in x_data] if is_latest else None,
                    textposition="top center",
                    name=str(year),
                    marker={
                        "color": c_color,
                        "size": 14 if is_latest else 10,
                        "line": {"color": "white", "width": 1} if is_latest else None
                    }
                ))

            fig_db.update_layout(
                xaxis={"range": [3, 5], "showgrid": True, "gridcolor": "#f1f5f9"},
                yaxis={"autorange": "reversed", "showgrid": False},
                showlegend=True,
                legend={"orientation": "h", "yanchor": "top", "y": -0.15, "xanchor": "center", "x": 0.5},
                margin={"t": 40, "b": 40, "l": 100, "r": 20},
                height=400
            )
            st.plotly_chart(fig_db, use_container_width=True)

        st.divider()
        st.markdown(f"##### 👥 평가자 그룹 간 비교 (구성원 vs 동료) - {latest_year}")
        mem_vals = [grouped_scores[latest_year].get(cat, 0) for cat in AREA_LABELS]
        peer_vals = [latest_peer_group.get(cat, 0) for cat in AREA_LABELS]

        if any(v > 0 for v in peer_vals):
            gap_df = pd.DataFrame({
                "Category": AREA_LABELS * 2,
                "Score": mem_vals + peer_vals,
                "Rater": ["구성원"] * len(AREA_LABELS) + ["동료"] * len(AREA_LABELS)
            })
            fig_gap = px.bar(
                gap_df, x="Category", y="Score", color="Rater", barmode="group",
                text_auto='.2f', range_y=[3, 5],
                color_discrete_map={"구성원": "#2563eb", "동료": "#f59e0b"}
            )
            fig_gap.update_traces(textposition="outside")
            fig_gap.update_layout(
                legend_title_text="", xaxis_title="", yaxis_title="Score",
                margin=dict(t=20, b=0)
            )
            st.plotly_chart(fig_gap, use_container_width=True)
        else:
            st.info("해당 연도의 동료 평가 데이터가 없습니다.")

        # 본인 vs 구성원 비교 (25년 데이터 있을 때)
        if ld['self_scores']:
            st.divider()
            st.markdown(f"##### 🪞 본인 vs 구성원 비교 (2025년)")
            self_area_scores = []
            for area in AREAS:
                val = ld['self_scores'].get(area) or ld['self_scores'].get(area.lstrip('①②③④'))
                self_area_scores.append(val or 0.0)

            if any(v > 0 for v in self_area_scores):
                self_df = pd.DataFrame({
                    "Category": AREA_LABELS * 2,
                    "Score": mem_vals + self_area_scores,
                    "Rater": ["구성원"] * len(AREA_LABELS) + ["본인"] * len(AREA_LABELS)
                })
                fig_self = px.bar(
                    self_df, x="Category", y="Score", color="Rater", barmode="group",
                    text_auto='.2f', range_y=[3, 5],
                    color_discrete_map={"구성원": "#2563eb", "본인": "#8b5cf6"}
                )
                fig_self.update_traces(textposition="outside")
                fig_self.update_layout(
                    legend_title_text="", xaxis_title="", yaxis_title="Score",
                    margin=dict(t=20, b=0)
                )
                st.plotly_chart(fig_self, use_container_width=True)

        st.divider()
        st.markdown(f"##### 💬 {latest_year} 주요 피드백 하이라이트")

        latest_texts_ctx = ""
        raw_preview = []
        latest_text_data = ld['texts'].get(latest_year, {})

        member_labels = ['조직 특성', '리더십 이미지', '강점', '개발 필요점', '최근 변화 노력']
        peer_labels = ['강점 (동료)', '개발 필요점 (동료)']

        for label in member_labels:
            val = latest_text_data.get(label, '').strip()
            if val and val not in ('-', 'None', ''):
                latest_texts_ctx += f"- [구성원/{label}] {val}\n"
                raw_preview.append(f"👤 **구성원 ({label}):** {val[:200]}{'...' if len(val) > 200 else ''}")

        for label in peer_labels:
            val = latest_text_data.get(label, '').strip()
            if val and val not in ('-', 'None', ''):
                latest_texts_ctx += f"- [동료/{label}] {val}\n"
                raw_preview.append(f"🤝 **동료 ({label}):** {val[:200]}{'...' if len(val) > 200 else ''}")

        if latest_texts_ctx.strip():
            if st.session_state.get('dash_summary'):
                st.info(st.session_state.dash_summary)
                with st.expander("원문 피드백 보기"):
                    for c in raw_preview:
                        st.markdown(f"- {c}")
            else:
                st.markdown(
                    "<span style='color:#666; font-size:0.9rem;'>최근 평가에 접수된 주관식 코멘트입니다.</span>",
                    unsafe_allow_html=True
                )
                for c in raw_preview[:3]:
                    st.markdown(f"> {c}")
                if len(raw_preview) > 3:
                    st.caption(f"...외 {len(raw_preview) - 3}건의 피드백이 있습니다.")
                st.write("")

                if st.button("🤖 AI 3줄 핵심 요약 보기"):
                    if OPENAI_API_KEY:
                        with st.spinner("핵심 내용을 요약하고 있습니다..."):
                            try:
                                client = openai.OpenAI(api_key=OPENAI_API_KEY)
                                prompt = f"""
                                다음은 특정 임원의 {latest_year}년도 다면평가 주관식 피드백 원문입니다.
                                대시보드에서 한눈에 볼 수 있도록 다음 3가지 항목으로 아주 간결하게(각 1줄씩) 요약해주세요.
                                1. 주요 강점:
                                2. 주요 보완점:
                                3. 종합 제언:

                                [피드백 원문]
                                {latest_texts_ctx}
                                """
                                res = client.chat.completions.create(
                                    model="gpt-4.1-mini",
                                    messages=[{"role": "user", "content": prompt}]
                                )
                                st.session_state.dash_summary = res.choices[0].message.content
                                st.rerun()
                            except Exception as e:
                                st.error(f"오류: {e}")
                    else:
                        st.warning("API Key가 필요합니다.")
        else:
            st.info("해당 연도의 주관식 데이터가 없습니다.")

    # ═══════════════════════════════════════════════════════════════════════════
    # [TAB 2] 주관식 심층분석
    # ═══════════════════════════════════════════════════════════════════════════
    with tab2:
        st.subheader("📝 주관식 피드백 심층 분석 (3개년)")

        # 분석용 텍스트 컨텍스트 구성
        data_context = ""
        analysis_years = sorted_years[-3:]

        data_context += "### [1] 구성원 주관식 응답 (3개년)\n"
        for year in analysis_years:
            data_context += f"\n<{year}년 구성원>\n"
            text_data = ld['texts'].get(year, {})
            for label in member_labels:
                val = text_data.get(label, '').strip()
                if val and val not in ('-', 'None', ''):
                    data_context += f"- {label}: {val}\n"

        data_context += "\n### [2] 동료 주관식 응답 (3개년)\n"
        for year in analysis_years:
            data_context += f"\n<{year}년 동료>\n"
            text_data = ld['texts'].get(year, {})
            for label in peer_labels:
                val = text_data.get(label, '').strip()
                if val and val not in ('-', 'None', ''):
                    data_context += f"- {label}: {val}\n"

        data_context += f"\n### [3] 객관식 점수 변화 추이\n"
        data_context += f"- {latest_year} 종합 점수: {curr_score:.2f}, 최고 강점: {top_comp}, 보완 필요: {bot_comp}\n"
        for year in analysis_years:
            data_context += f"- {year} 점수: " + ", ".join(
                f"{a.replace('<br>', ' ')}: {grouped_scores[year].get(l, 0):.2f}"
                for a, l in zip(AREAS, AREA_LABELS)
                if grouped_scores[year].get(l, 0) > 0
            ) + "\n"

        btn_text = "🤖 AI 심층 분석 재실행" if st.session_state.get('qualitative_analysis') else "🤖 AI 심층 분석 실행"

        if st.button(btn_text):
            if not OPENAI_API_KEY:
                st.error("API Key가 필요합니다.")
            else:
                with st.spinner("AI가 3년치 데이터를 통합 분석 중입니다..."):
                    try:
                        client = openai.OpenAI(api_key=OPENAI_API_KEY)
                        prompt = f"""
                        당신은 대기업 임원 리더십 평가 전문가입니다.
                        주관식 피드백과 객관식 점수를 분석하여 아래 4개의 내용을 작성하세요.

                        [요청 항목]
                        1. 주관식 키워드 주요 변화 (연도별 긍정/부정 뉘앙스 차이 등)
                        2. 변화 원인 추적 (점수 하락/상승과 코멘트 내용 연결)
                        3. 구성원 vs 동료 인식 비교 (바라보는 시각 Gap)
                        4. 종합 심층 분석 (위 3가지를 뒷받침하는 맥락과 근거, 리더십 제언 2-3문단)

                        **중요 지시사항:**
                        1. 1-3번은 PPT 슬라이드처럼 단어 중심의 짧은 Bullet 2-3개로 작성. (종결어미: "-함")
                        2. 핵심 키워드는 **굵은 글씨(Bold)** 처리.
                        3. 4번은 상세하고 구체적인 서술형 2-3문단.
                        4. 숫자 넘버링이나 소제목은 절대 쓰지 말 것. 본문만 바로 시작.
                        5. 물결표(~) 기호 사용 금지. 연도 범위는 하이픈(-)으로 표시.
                        6. 각 항목 사이에 '|||' (수직선 3개)를 구분자로 1번씩 삽입. (구분자 총 3번)

                        [분석 대상 데이터]
                        {data_context}
                        """
                        res = client.chat.completions.create(
                            model="gpt-5.2",
                            messages=[{"role": "user", "content": prompt}]
                        )
                        raw_ans = res.choices[0].message.content
                        parts = [p.strip() for p in raw_ans.split('|||')]
                        parts = [re.sub(r'^\d+\.\s*', '', p, flags=re.MULTILINE).strip() for p in parts]

                        if len(parts) >= 4:
                            st.session_state['qualitative_analysis'] = parts[:4]
                        elif len(parts) >= 3:
                            parts.append("상세 설명 내용이 생성되지 않았습니다.")
                            st.session_state['qualitative_analysis'] = parts[:4]
                        else:
                            st.session_state['qualitative_analysis'] = raw_ans

                        st.rerun()
                    except Exception as e:
                        st.error(f"오류 발생: {e}")

        if st.session_state.get('qualitative_analysis'):
            qa = st.session_state['qualitative_analysis']
            st.write("")
            st.markdown("""
            <div style="padding: 12px 20px; background-color: #f8fafc; border-left: 5px solid #1e3a8a; border-radius: 4px; margin-bottom: 25px;">
                <span style="color: #0f172a; font-weight: 600; font-size: 1.15rem;">📊 Executive Summary: Qualitative Feedback Analysis</span>
            </div>
            """, unsafe_allow_html=True)

            if isinstance(qa, list) and len(qa) >= 4:
                c1, c2, c3 = st.columns(3)
                with c1:
                    with st.container(border=True):
                        st.markdown("<div style='border-top: 4px solid #2563eb; margin-bottom: 10px;'></div>", unsafe_allow_html=True)
                        st.markdown("##### 🎯 키워드 변화 트렌드")
                        st.markdown(qa[0])
                with c2:
                    with st.container(border=True):
                        st.markdown("<div style='border-top: 4px solid #64748b; margin-bottom: 10px;'></div>", unsafe_allow_html=True)
                        st.markdown("##### 🔍 점수-코멘트 연관성")
                        st.markdown(qa[1])
                with c3:
                    with st.container(border=True):
                        st.markdown("<div style='border-top: 4px solid #0f172a; margin-bottom: 10px;'></div>", unsafe_allow_html=True)
                        st.markdown("##### ⚖️ 그룹 간 인식 갭(Gap)")
                        st.markdown(qa[2])

                st.write("")
                st.markdown("##### 📝 심층 분석 및 Leadership 제언")
                with st.container(border=True):
                    st.markdown(qa[3])
            else:
                st.markdown(qa if isinstance(qa, str) else '\n'.join(qa))

        with st.expander("원본 데이터 보기"):
            st.text(data_context)

    # ═══════════════════════════════════════════════════════════════════════════
    # [TAB 3] AI 코칭
    # ═══════════════════════════════════════════════════════════════════════════
    with tab3:
        st.subheader("💬 AI 리더십 코칭")
        chat_container = st.container()

        if not st.session_state.messages:
            welcome = f"{leader_name} 임원님, 반갑습니다. 리더십 분석을 완료했습니다.\n\n"
            welcome += f"최근({latest_year}) 종합 점수는 **{curr_score:.2f}점**입니다. "
            if delta_total > 0:
                welcome += "전년 대비 상승세입니다. 📈\n\n"
            elif delta_total < 0:
                welcome += "전년 대비 하락세가 관찰됩니다. 📉\n\n"
            else:
                welcome += "\n\n"
            welcome += "현재 가장 고민되시는 리더십 이슈는 무엇인가요? 편하게 말씀해 주시면 대화를 시작하겠습니다.\n\n"
            welcome += """---
💡 추가 제안 (클릭하여 복사 후 질문해주세요)
* 📚 이론 학습: 현재 약점과 관련된 최신 리더십 이론 추천
* 🗓️ W/S 제안: 조직문화 개선을 위한 워크숍 아젠다 제안
* 🎯 SKMS 적용: 사내 철학(VWBE, SUPEX 등)을 내 팀에 적용하는 방법
"""
            st.session_state.messages.append({"role": "assistant", "content": welcome})

        with chat_container:
            for msg in st.session_state.messages:
                with st.chat_message(msg["role"]):
                    st.write(msg["content"])

        if prompt := st.chat_input("질문 입력..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with chat_container:
                with st.chat_message("user"):
                    st.write(prompt)

            if OPENAI_API_KEY:
                try:
                    client = openai.OpenAI(api_key=OPENAI_API_KEY)
                    qual_ctx = st.session_state.get('qualitative_analysis', "주관식 분석 결과 없음")

                    score_summary = {y: avg_scores[y] for y in sorted_years}
                    area_summary = {
                        a.replace('<br>', ' '): grouped_scores[latest_year].get(a, 0)
                        for a in AREA_LABELS
                    }

                    sys_msg = f"""
당신은 임원 전용 리더십 코치입니다. 대상: {leader_name}
회사: {meta.get('회사명', '-')}, 직책: {meta.get('직책', '-')}, 모델: {meta.get('리더십진단 모델', '-')}

[연도별 점수] {score_summary}
[최근 영역별 점수] {area_summary}
[강점] {top_comp} | [보완 필요] {bot_comp}
[주관식 분석] {qual_ctx}

{SKMS_KNOWLEDGE_BASE}

[코칭 가이드]
1. 깊이 있는 통찰을 제공하세요.
2. 필요 시 SKMS 철학(VWBE, SUPEX, 구성원 행복 등)을 자연스럽게 인용하세요.
3. 이론/워크숍 등을 필요 시 추천하세요.
4. 답변 끝에 항상 GROW 코칭 질문을 던져 대화를 이어가세요.
"""
                    msgs = [{"role": "system", "content": sys_msg}] + st.session_state.messages

                    with chat_container:
                        with st.chat_message("assistant"):
                            with st.spinner("AI가 답변을 준비 중입니다..."):
                                stream = client.chat.completions.create(
                                    model="gpt-4.1-mini", messages=msgs, stream=True
                                )
                            res = st.write_stream(stream)

                    st.session_state.messages.append({"role": "assistant", "content": res})
                except Exception as e:
                    st.error(f"오류: {e}")
            else:
                st.warning("API Key 미설정")

# ─── 초기 랜딩 화면 ────────────────────────────────────────────────────────────
else:
    st.title("👑 Executive Leadership AI Coach")
    st.markdown("---")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown("""
        ### 📊 플랫폼 소개
        본 플랫폼은 임원 리더십 진단 결과 **(.md 파일)** 을 기반으로 다각적인 통찰과 **맞춤형 진단**을 제공합니다.

        * **정량 데이터 시각화:** 리더십 점수 흐름 및 영역별 밸런스 분석
        * **주관식 심층 분석:** AI를 통한 구성원/동료 코멘트 핵심 요약
        * **AI 코치와의 대화:** 리더십 Gap 극복을 위한 1:1 코칭
        """)

    with col2:
        st.info("""
        ### 🚀 시작하는 방법
        1. 좌측 사이드바에서 **임원을 선택**하세요. (기존 데이터)
        2. 또는 **[MD 파일 업로드]** 버튼을 클릭하여 새로운 진단 결과 **.md 파일**을 업로드하세요.
        3. 선택 또는 업로드 완료 후 자동으로 대시보드가 열립니다.
        """)

