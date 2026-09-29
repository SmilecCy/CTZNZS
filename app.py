# -*- coding: utf-8 -*-
"""司法考试 AI 辅助学习系统 · Streamlit 管理端入口。

启动方式::

    streamlit run app.py

界面结构：
    顶部   课程切换
    侧栏   知识点筛选、难度选择、索引状态、题库状态
    主区   六个标签页：资料管理 / 预热与题库更新 / 练习模式 / 错题集 / 记忆闪卡 / 系统自检
"""

from __future__ import annotations

import sys

import streamlit as st

from app.config import COURSES, COURSE_KEYS
from app.frontend import (
    onboarding,
    sidebar,
    state,
    tab_materials,
    tab_memory,
    tab_practice,
    tab_selftest,
    tab_warmup,
    tab_wrongbook,
)

# 标签页名 -> 渲染函数
_RENDERERS = {
    "资料管理": tab_materials.render,
    "预热与题库更新": tab_warmup.render,
    "练习模式": tab_practice.render,
    "错题集": tab_wrongbook.render,
    "记忆闪卡": tab_memory.render,
    "系统自检": tab_selftest.render,
}


def _on_course_change() -> None:
    """课程下拉框的回调：在脚本主体执行前完成状态切换。"""
    state.switch_course(st.session_state["course_selector"])


def _render_course_switcher() -> None:
    """顶部课程切换。"""
    col_l, col_r = st.columns([1, 3])
    with col_l:
        st.selectbox(
            "课程",
            COURSE_KEYS,
            format_func=lambda k: COURSES[k]["name"],
            key="course_selector",
            on_change=_on_course_change,
        )
    with col_r:
        course = COURSES[state.current_course_key()]
        st.caption(f"出题侧重：{course['question_focus']}　｜　记忆策略：{course['memory_strategy']}")


def _render_nav() -> str:
    """主区域标签页导航。

    用 ``st.radio(horizontal=True)`` 而非 ``st.tabs``：后者无法用代码切换，
    而引导页的"一键跳转预热"需要程序化跳转能力。
    """
    return st.radio(
        "导航",
        state.TABS,
        horizontal=True,
        label_visibility="collapsed",
        key="nav",
    )


def main() -> None:
    """应用主函数。"""
    st.set_page_config(
        page_title="思政+法学 双课程 AI 辅助学习系统",
        page_icon="📚",
        layout="wide",
    )

    state.init_state()
    _render_course_switcher()
    sidebar.render()

    st.title("📚 双课程 AI 辅助学习系统")
    st.caption("题库优先 · LLM 兜底 · 来源可追溯")

    if onboarding.should_show():
        onboarding.render()

    active = _render_nav()
    st.divider()

    renderer = _RENDERERS.get(active)
    if renderer is None:  # 理论上不会发生，兜底避免白屏
        st.error(f"未知标签页：{active}")
        return
    renderer()


def _is_bare_mode() -> bool:
    """判断当前是不是在用 ``python app.py`` 直接跑，而不是 ``streamlit run app.py``。

    Streamlit 界面必须由 Streamlit 自己的运行时启动。直接 ``python app.py``
    会把所有 ``st.*`` 调用执行一遍，但因为没有运行时，它们只会打印
    "missing ScriptRunContext" 警告、然后什么都不显示——看起来像"运行出错"，
    其实是启动方式不对。

    判断依据是脚本运行上下文：``streamlit run`` 与测试用的 AppTest 都会建立它，
    直接 ``python app.py`` 则没有。

    **取不到判断依据时一律当作"正常运行"**——宁可漏报，也不要误伤真正的启动。
    """
    try:
        try:
            from streamlit.runtime.scriptrunner import get_script_run_ctx
        except ImportError:
            # Streamlit 内部模块路径随版本变过，两条都试
            from streamlit.runtime.scriptrunner_utils.script_run_context import (
                get_script_run_ctx,
            )
        return get_script_run_ctx() is None
    except Exception:  # noqa: BLE001 - 判断不出来就别拦
        return False


_BARE_MODE_HINT = """
============================================================
启动方式不对：请用 streamlit run app.py
============================================================

你刚才用的应该是 `python app.py`。这个跑不出界面。

Streamlit 应用必须由 Streamlit 自己的运行时启动：

    streamlit run app.py

如果提示找不到 streamlit 命令，用：

    python -m streamlit run app.py

（`python app.py` 会把所有界面调用执行一遍，但没有运行时接手，
  于是只打印 "missing ScriptRunContext" 警告然后什么都不显示。）
"""


if __name__ == "__main__":
    if _is_bare_mode():
        print(_BARE_MODE_HINT)
        sys.exit(1)
    main()