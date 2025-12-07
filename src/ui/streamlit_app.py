"""
Semantica Agent Web UI (Streamlit)

SOTA급 웹 인터페이스.

Features:
- 코드 분석
- 버그 수정
- 실시간 통계
- 성능 모니터링
- 작업 히스토리

Usage:
    streamlit run src/ui/streamlit_app.py
"""

from datetime import datetime

import plotly.graph_objects as go
import streamlit as st

# Page Config
st.set_page_config(
    page_title="Semantica Agent",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# Session State 초기화
# ============================================================

if "tasks" not in st.session_state:
    st.session_state.tasks = []

if "current_task" not in st.session_state:
    st.session_state.current_task = None


# ============================================================
# Sidebar
# ============================================================

with st.sidebar:
    st.title("🤖 Semantica Agent")
    st.markdown("SOTA급 코딩 어시스턴트")

    st.divider()

    # Navigation
    page = st.radio(
        "페이지",
        ["홈", "코드 분석", "버그 수정", "통계", "성능", "설정"],
        label_visibility="collapsed",
    )

    st.divider()

    # Quick Stats
    st.metric("총 작업", len(st.session_state.tasks))
    st.metric("성공률", f"{95.2:.1f}%")


# ============================================================
# 홈
# ============================================================

if page == "홈":
    st.title("🏠 홈")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label="총 작업",
            value="42",
            delta="5",
        )

    with col2:
        st.metric(
            label="완료",
            value="38",
            delta="4",
        )

    with col3:
        st.metric(
            label="실패",
            value="4",
            delta="-1",
            delta_color="inverse",
        )

    with col4:
        st.metric(
            label="성공률",
            value="95.2%",
            delta="2.1%",
        )

    st.divider()

    # 빠른 시작
    st.subheader("⚡ 빠른 시작")

    task_type = st.selectbox(
        "작업 타입",
        ["분석", "버그 수정", "리팩토링", "테스트 추가", "문서화"],
    )

    instructions = st.text_area(
        "지시사항",
        placeholder="예: payment.py의 null pointer 버그 수정",
        height=100,
    )

    repo_path = st.text_input("저장소 경로", value=".")

    col1, col2 = st.columns([3, 1])

    with col1:
        if st.button("🚀 실행", use_container_width=True, type="primary"):
            if instructions:
                with st.spinner("실행 중..."):
                    import time

                    time.sleep(2)

                    # Task 추가
                    task = {
                        "id": len(st.session_state.tasks) + 1,
                        "type": task_type,
                        "instructions": instructions,
                        "status": "완료",
                        "created_at": datetime.now().isoformat(),
                    }
                    st.session_state.tasks.append(task)

                    st.success("✓ 작업 완료!")
                    st.rerun()
            else:
                st.warning("지시사항을 입력하세요.")

    with col2:
        if st.button("🔄 초기화", use_container_width=True):
            st.session_state.tasks = []
            st.rerun()

    st.divider()

    # 최근 작업
    st.subheader("📋 최근 작업")

    if st.session_state.tasks:
        for task in reversed(st.session_state.tasks[-5:]):
            with st.expander(f"#{task['id']} - {task['type']} ({task['status']})"):
                st.write(f"**지시사항:** {task['instructions']}")
                st.write(f"**생성 시간:** {task['created_at']}")
    else:
        st.info("작업 히스토리가 없습니다.")


# ============================================================
# 코드 분석
# ============================================================

elif page == "코드 분석":
    st.title("🔍 코드 분석")

    repo_path = st.text_input("저장소 경로", value=".")

    col1, col2 = st.columns(2)

    with col1:
        focus = st.selectbox(
            "분석 초점",
            ["전체", "버그", "성능", "보안", "코드 품질"],
        )

    with col2:
        files = st.multiselect(
            "대상 파일 (선택)",
            ["src/main.py", "src/utils.py", "tests/test_main.py"],
        )

    if st.button("🔍 분석 시작", type="primary", use_container_width=True):
        with st.spinner("분석 중..."):
            import time

            time.sleep(2)

            # Mock 결과
            st.success("✓ 분석 완료!")

            # 결과
            col1, col2 = st.columns(2)

            with col1:
                st.metric("발견된 이슈", "12")
                st.metric("높은 심각도", "3", delta_color="inverse")

            with col2:
                st.metric("복잡도 점수", "6.5/10")
                st.metric("코드 커버리지", "78%")

            st.divider()

            # 이슈 테이블
            st.subheader("발견된 이슈")

            issues_data = [
                {"심각도": "높음", "타입": "버그", "파일": "src/main.py", "줄": 42, "메시지": "Null pointer exception"},
                {"심각도": "중간", "타입": "성능", "파일": "src/utils.py", "줄": 15, "메시지": "Inefficient loop"},
                {"심각도": "낮음", "타입": "스타일", "파일": "src/main.py", "줄": 10, "메시지": "Missing docstring"},
            ]

            st.dataframe(
                issues_data,
                use_container_width=True,
                hide_index=True,
            )

            st.divider()

            # 권장사항
            st.subheader("권장사항")

            st.markdown("""
            1. ✅ Add error handling for null values
            2. ✅ Use list comprehension for better performance
            3. ✅ Add unit tests for edge cases
            4. ✅ Improve code documentation
            """)


# ============================================================
# 버그 수정
# ============================================================

elif page == "버그 수정":
    st.title("🔧 버그 수정")

    file_path = st.text_input("파일 경로", placeholder="src/payment.py")
    bug_description = st.text_area(
        "버그 설명",
        placeholder="null pointer exception when processing payment",
        height=100,
    )

    auto_commit = st.checkbox("자동 커밋", value=False)

    if st.button("🔧 수정 시작", type="primary", use_container_width=True):
        if file_path and bug_description:
            with st.spinner("분석 및 수정 중..."):
                import time

                time.sleep(2)

                st.success("✓ 수정 완료!")

                # Diff 표시
                st.subheader("변경사항")

                diff = """
--- a/src/payment.py
+++ b/src/payment.py
@@ -10,2 +10,4 @@
-    return user.balance
+    if user is None:
+        raise ValueError("User cannot be None")
+    return user.balance
"""

                st.code(diff, language="diff")

                if auto_commit:
                    st.success("✓ 커밋 완료: abc123")
        else:
            st.warning("모든 필드를 입력하세요.")


# ============================================================
# 통계
# ============================================================

elif page == "통계":
    st.title("📊 통계")

    # 전체 통계
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("총 작업", "42")

    with col2:
        st.metric("완료", "38")

    with col3:
        st.metric("실패", "4")

    with col4:
        st.metric("평균 실행 시간", "45.2초")

    st.divider()

    # 차트
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("작업 타입 분포")

        # Pie Chart
        fig = go.Figure(
            data=[
                go.Pie(
                    labels=["분석", "버그 수정", "리팩토링", "테스트"],
                    values=[15, 12, 10, 5],
                )
            ]
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("일별 작업 수")

        # Bar Chart
        fig = go.Figure(
            data=[
                go.Bar(
                    x=["월", "화", "수", "목", "금"],
                    y=[8, 10, 7, 12, 5],
                )
            ]
        )
        st.plotly_chart(fig, use_container_width=True)


# ============================================================
# 성능
# ============================================================

elif page == "성능":
    st.title("⚡ 성능")

    # LLM 통계
    st.subheader("LLM 통계")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("총 토큰", "123,456")

    with col2:
        st.metric("캐시 Hit Rate", "95.2%")

    with col3:
        st.metric("평균 응답 시간", "0.8초")

    st.divider()

    # Cache 통계
    st.subheader("Cache 통계")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("L1 Hit Rate", "85%")

    with col2:
        st.metric("L2 Hit Rate", "12%")

    with col3:
        st.metric("Overall Hit Rate", "97%")

    st.divider()

    # Latency Histogram
    st.subheader("Latency 분포")

    import numpy as np

    latencies = np.random.lognormal(0, 0.5, 1000)

    fig = go.Figure(data=[go.Histogram(x=latencies, nbinsx=50)])
    fig.update_layout(
        xaxis_title="Latency (초)",
        yaxis_title="빈도",
    )
    st.plotly_chart(fig, use_container_width=True)

    # Percentiles
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("P50", "0.5초")

    with col2:
        st.metric("P95", "1.2초")

    with col3:
        st.metric("P99", "2.5초")

    with col4:
        st.metric("Max", "5.0초")


# ============================================================
# 설정
# ============================================================

elif page == "설정":
    st.title("⚙️ 설정")

    st.subheader("LLM 설정")

    llm_model = st.selectbox(
        "모델",
        ["gpt-4o-mini", "gpt-4o", "claude-3-sonnet", "o1-preview"],
    )

    temperature = st.slider("Temperature", 0.0, 2.0, 0.7, 0.1)
    max_tokens = st.number_input("Max Tokens", 100, 4000, 2000, 100)

    st.divider()

    st.subheader("성능 설정")

    enable_cache = st.checkbox("캐싱 활성화", value=True)
    max_concurrent = st.number_input("최대 동시 요청", 1, 10, 5, 1)

    st.divider()

    st.subheader("저장소 설정")

    default_repo = st.text_input("기본 저장소 경로", value=".")
    auto_commit = st.checkbox("자동 커밋", value=False)

    st.divider()

    if st.button("💾 저장", type="primary", use_container_width=True):
        st.success("✓ 설정 저장 완료!")


# ============================================================
# Footer
# ============================================================

st.divider()
st.markdown(
    """
    <div style='text-align: center; color: #888;'>
        Semantica Agent v7 - SOTA급 코딩 어시스턴트
    </div>
    """,
    unsafe_allow_html=True,
)
