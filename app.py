import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import numpy as np
import time

# 设置页面配置
st.set_page_config(
    page_title="SlotInsight - 游戏数据分析看板",
    page_icon="🎰",
    layout="wide"
)

# 隐藏 Streamlit 默认的菜单和页脚
hide_streamlit_style = """
<style>
#MainMenu {visibility: hidden;}
header {visibility: hidden;}
footer {visibility: hidden;}
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 1. 数据加载与处理
# -----------------------------------------------------------------------------
@st.cache_data
def load_data(file):
    """
    读取上传的 Excel 文件并进行预处理。
    """
    try:
        # 读取 Excel
        df = pd.read_excel(file, engine='openpyxl')
        
        # 确保 create_date 是 datetime 类型
        df['create_date'] = pd.to_datetime(df['create_date'])
        
        # 兼容性检查：是否存在 pool 列
        if 'pool' in df.columns:
            df['real_pool'] = df['pool'] / 100
            df['has_pool'] = True
        else:
            df['has_pool'] = False
        
        # 标记类型
        df['type'] = df['amount'].apply(lambda x: 'Bet (下注)' if x < 0 else 'Win (中奖)')
        
        return df
    except Exception as e:
        st.error(f"文件读取失败 (File Read Error): {e}")
        return None

# 辅助函数：计算用户标签
def calculate_user_tags(user_data, all_avg_bet):
    tags = []
    total_bet = abs(user_data[user_data['amount'] < 0]['amount'].sum())
    total_pnl = user_data['amount'].sum()
    
    if total_bet > all_avg_bet * 10:
        tags.append("Whale (大R)")
    elif total_bet < all_avg_bet * 0.1:
        tags.append("Minnow (小R)")
    
    if total_pnl > 0:
        tags.append("Winner (赢家)")
    else:
        tags.append("Loser (输家)")
        
    return " | ".join(tags)

# -----------------------------------------------------------------------------
# 2. 侧边栏配置
# -----------------------------------------------------------------------------
st.sidebar.title("🎰 SlotInsight 配置")

# 多文件上传
uploaded_files = st.sidebar.file_uploader(
    "上传游戏日志 Excel (.xlsx)", 
    type=["xlsx"], 
    accept_multiple_files=True
)

if not uploaded_files:
    st.info("👋 欢迎使用 SlotInsight！")
    st.warning("请在左侧上传 Excel 文件 (Please upload Excel file on the left)。")
    st.markdown("""
    ### 使用说明 (Instructions)
    - 支持多文件上传切换。
    - 自动识别 `pool` 字段。
    - **金额单位**: Token/金币 (无货币符号)。
    """)
else:
    # 文件选择
    file_map = {f.name: f for f in uploaded_files}
    selected_filename = st.sidebar.selectbox("当前分析文件 (Current File)", list(file_map.keys()))
    selected_file = file_map[selected_filename]

    # 加载数据
    df = load_data(selected_file)
    
    if df is not None:
        # -------------------------------------------------------------------------
        # 侧边栏筛选
        # -------------------------------------------------------------------------
        st.sidebar.header("🔍 数据筛选 (Filters)")
        
        # 日期筛选
        if not df['create_date'].empty:
            min_date = df['create_date'].min().date()
            max_date = df['create_date'].max().date()
            date_range = st.sidebar.date_input(
                "日期范围 (Date Range)",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date
            )
        else:
            st.error("数据中没有有效的时间记录 (No valid date records found)")
            st.stop()
        
        # 游戏ID 筛选
        unique_gids = sorted(df['gid'].unique())
        selected_gids = st.sidebar.multiselect(
            "选择游戏 ID (Select GID)",
            options=unique_gids,
            default=unique_gids
        )
        
        # 应用筛选
        mask_gid = df['gid'].isin(selected_gids)
        
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_date, end_date = date_range
            mask_date = (df['create_date'].dt.date >= start_date) & (df['create_date'].dt.date <= end_date)
        elif isinstance(date_range, tuple) and len(date_range) == 1:
            start_date = date_range[0]
            mask_date = (df['create_date'].dt.date >= start_date)
        else:
            mask_date = (df['create_date'].dt.date == date_range)

        filtered_df = df[mask_date & mask_gid].copy()

        # -------------------------------------------------------------------------
        # 主界面
        # -------------------------------------------------------------------------
        st.title(f"📊 SlotInsight - {selected_filename}")
        
        if filtered_df.empty:
            st.warning("当前筛选条件下没有数据 (No data under current filters)。")
        else:
            # 使用 Tabs 组织内容
            tab1, tab2, tab3, tab4 = st.tabs([
                "全局概览 (Overview)", 
                "游戏分析 (Game Analysis)", 
                "玩家分析 (Player Analysis)", 
                "数据明细 (Data Detail)"
            ])
            
            # 基础数据准备
            bet_df = filtered_df[filtered_df['amount'] < 0].copy()
            win_df = filtered_df[filtered_df['amount'] > 0].copy()
            
            # 全局变量
            spin_count = len(bet_df)
            total_turnover = abs(bet_df['amount'].sum())
            avg_bet = (total_turnover / spin_count) if spin_count > 0 else 0.0

            # =====================================================================
            # Tab 1: 全局概览 (Overview)
            # =====================================================================
            with tab1:
                st.subheader("📈 核心指标 (KPI Metrics)")
                
                total_payout = win_df['amount'].sum()
                ggr = total_turnover - total_payout
                
                rtp = (total_payout / total_turnover * 100) if total_turnover > 0 else 0.0
                win_rate = (len(win_df) / spin_count * 100) if spin_count > 0 else 0.0
                
                col1, col2, col3, col4, col5, col6 = st.columns(6)
                col1.metric("总流水 (Turnover)", f"{total_turnover:,.0f}", help="所有下注金额的绝对值总和")
                col2.metric("总营收 (GGR)", f"{ggr:,.0f}", help="总流水 - 总派彩")
                
                col3.metric("RTP (返还率)", f"{rtp:.2f}%", help="(总派彩 / 总流水) * 100%")
                if rtp > 100: col3.error("亏损预警 (RTP > 100%)")
                
                col4.metric("总局数 (Spins)", f"{spin_count:,}", help="玩家下注的总次数")
                col5.metric("平均下注 (Avg Bet)", f"{avg_bet:,.1f}", help="总流水 / 总局数")
                col6.metric("中奖率 (Hit Rate)", f"{win_rate:.2f}%", help="中奖次数 / 总局数")
                
                st.divider()
                
                st.subheader("🚀 运营健康度 (Operational Health)")
                
                # DAU (Daily Active Users)
                filtered_df['date_str'] = filtered_df['create_date'].dt.date
                dau_series = filtered_df.groupby('date_str')['user_id'].nunique()
                avg_dau = dau_series.mean()
                
                # 新增用户 (New Users)
                user_first_seen = df.groupby('user_id')['create_date'].min().dt.date.reset_index()
                user_first_seen.columns = ['user_id', 'first_seen_date']
                new_users_daily = user_first_seen.groupby('first_seen_date')['user_id'].count()
                
                # 留存率 (Next Day Retention)
                retention_data = []
                unique_dates = sorted(filtered_df['date_str'].unique())
                for i in range(len(unique_dates) - 1):
                    current_day = unique_dates[i]
                    next_day = unique_dates[i+1]
                    
                    users_current = set(filtered_df[filtered_df['date_str'] == current_day]['user_id'])
                    users_next = set(filtered_df[filtered_df['date_str'] == next_day]['user_id'])
                    
                    retained = len(users_current.intersection(users_next))
                    rate = (retained / len(users_current) * 100) if len(users_current) > 0 else 0
                    retention_data.append({'date': current_day, 'retention_rate': rate})
                
                avg_retention = np.mean([x['retention_rate'] for x in retention_data]) if retention_data else 0
                
                total_users = filtered_df['user_id'].nunique()
                spins_per_user = spin_count / total_users if total_users > 0 else 0
                
                k1, k2, k3, k4, k5 = st.columns(5)
                k1.metric("平均日活 (Avg DAU)", f"{avg_dau:.0f}", help="每日活跃用户数的平均值")
                k2.metric("日均新增 (Avg New Users)", f"{new_users_daily.mean():.0f}", help="每日首次出现的玩家数量")
                k3.metric("次日留存 (Next Day Retention)", f"{avg_retention:.1f}%", help="前一天活跃用户在第二天继续活跃的比例")
                k4.metric("人均局数 (Spins/User)", f"{spins_per_user:.0f}", help="总局数 / 总玩家数")
                k5.metric("总玩家数 (Total Users)", f"{total_users}")

                # --- 新增：大户累计下注统计 ---
                st.markdown("### 💎 累计下注用户分布 (Cumulative Bet Analysis)")
                
                # 计算每个用户的总下注(绝对值)
                user_cum_bet = bet_df.groupby('user_id')['amount'].sum().abs()
                
                # 定义档位 (1万, 10万... 200万)
                thresholds = [10000, 100000, 200000, 500000, 1000000, 2000000]
                t_cols = st.columns(len(thresholds))
                
                for idx, t in enumerate(thresholds):
                    count = (user_cum_bet >= t).sum()
                    label = f"≥ {int(t/10000)}万"
                    t_cols[idx].metric(label, f"{count} 人", help=f"累计下注超过 {t:,} 的玩家数量")
                
                # DAU Chart
                fig_dau = px.bar(dau_series, title="每日活跃用户趋势 (DAU Trend)", labels={'value': 'DAU (活跃人数)', 'date_str': '日期 (Date)'})
                st.plotly_chart(fig_dau, use_container_width=True)

            # =====================================================================
            # Tab 2: 游戏分析 (Game Analysis)
            # =====================================================================
            with tab2:
                st.subheader("🎮 游戏维度深度分析 (Advanced Game Analysis)")
                
                def analyze_game_performance(x):
                    game_bet_df = x[x['amount'] < 0]
                    game_win_df = x[x['amount'] > 0]
                    
                    turnover = abs(game_bet_df['amount'].sum())
                    payout = game_win_df['amount'].sum()
                    ggr = turnover - payout
                    avg_bet_game = abs(game_bet_df['amount'].mean()) if not game_bet_df.empty else 1
                    
                    winners = x.groupby('user_id')['amount'].sum()
                    winner_count = (winners > 0).sum()
                    
                    multipliers = game_win_df['amount'] / avg_bet_game
                    
                    # 中奖类型分类
                    small_win = ((multipliers > 0) & (multipliers <= 5)).sum()
                    big_win = ((multipliers > 5) & (multipliers <= 20)).sum()
                    mega_win = ((multipliers > 20) & (multipliers <= 50)).sum()
                    super_win = (multipliers > 50).sum()
                    
                    return pd.Series({
                        'Turnover': turnover,
                        'Payout': payout, # Added for Pie Chart
                        'GGR': ggr,
                        'RTP': (payout / turnover * 100) if turnover > 0 else 0,
                        'Volatility': x['amount'].std(),
                        'Hit Rate': (len(game_win_df) / len(game_bet_df) * 100) if not game_bet_df.empty else 0,
                        'Winner %': (winner_count / x['user_id'].nunique() * 100) if x['user_id'].nunique() > 0 else 0,
                        'Small Win (0-5x)': small_win,
                        'Big Win (5-20x)': big_win,
                        'Mega Win (20-50x)': mega_win,
                        'Super Win (50x+)': super_win,
                        'Avg Multiplier': multipliers.mean() if not multipliers.empty else 0
                    })

                game_stats_detailed = filtered_df.groupby('gid').apply(analyze_game_performance).reset_index()
                
                # --- 新增：下注比例与中奖比例饼图 ---
                st.markdown("### 🥧 市场占比 (Market Share)")
                col_pie1, col_pie2 = st.columns(2)
                
                with col_pie1:
                    fig_pie_bet = px.pie(
                        game_stats_detailed, 
                        values='Turnover', 
                        names='gid', 
                        title="各游戏下注比例 (Turnover Share)",
                        hole=0.4
                    )
                    st.plotly_chart(fig_pie_bet, use_container_width=True)
                
                with col_pie2:
                    fig_pie_win = px.pie(
                        game_stats_detailed, 
                        values='Payout', 
                        names='gid', 
                        title="各游戏派彩比例 (Payout Share)",
                        hole=0.4
                    )
                    st.plotly_chart(fig_pie_win, use_container_width=True)

                st.markdown("### 📊 核心指标对比 (Key Metrics Comparison)")
                
                fig_rates = px.bar(
                    game_stats_detailed,
                    x='gid',
                    y=['Hit Rate', 'Winner %'],
                    barmode='group',
                    title="中奖率 vs 赢家比例 (Hit Rate vs Winner %)",
                    labels={'value': '百分比 (%)', 'variable': '指标 (Metric)', 'gid': '游戏ID'}
                )
                new_names = {'Hit Rate': '中奖率 (Hit Rate)', 'Winner %': '赢家比例 (Winner %)'}
                fig_rates.for_each_trace(lambda t: t.update(name = new_names.get(t.name, t.name)))
                st.plotly_chart(fig_rates, use_container_width=True)
                
                col_g1, col_g2 = st.columns(2)
                
                with col_g1:
                    fig_vol = px.bar(
                        game_stats_detailed,
                        x='gid',
                        y='Volatility',
                        title="游戏波动率 (Volatility) [说明: 越高代表波动越剧烈]",
                        color='Volatility',
                        color_continuous_scale='Blues',
                        labels={'gid': '游戏ID', 'Volatility': '波动率 (Volatility)'}
                    )
                    st.plotly_chart(fig_vol, use_container_width=True)
                    
                with col_g2:
                    fig_mul = px.bar(
                        game_stats_detailed,
                        x='gid',
                        y='Avg Multiplier',
                        title="平均中奖倍率 (Avg Win Multiplier)",
                        color='Avg Multiplier',
                        color_continuous_scale='Oranges',
                        labels={'gid': '游戏ID', 'Avg Multiplier': '平均倍率 (Avg Mult)'}
                    )
                    st.plotly_chart(fig_mul, use_container_width=True)

                st.markdown("### 💰 流水与营收 (Turnover vs GGR)")
                fig_finance = px.bar(
                    game_stats_detailed,
                    x='gid',
                    y=['Turnover', 'GGR'],
                    barmode='group',
                    title="各游戏流水与GGR对比",
                    log_y=True,
                    labels={'value': '金额 (Amount)', 'variable': '类型', 'gid': '游戏ID'}
                )
                fig_finance.update_layout(yaxis_title="金额 (Log Scale)")
                new_names_fin = {'Turnover': '总流水 (Turnover)', 'GGR': '总营收 (GGR)'}
                fig_finance.for_each_trace(lambda t: t.update(name = new_names_fin.get(t.name, t.name)))
                st.plotly_chart(fig_finance, use_container_width=True)

                st.markdown("### 🎰 中奖倍率结构 (Win Multiplier Structure)")
                win_cols = ['Small Win (0-5x)', 'Big Win (5-20x)', 'Mega Win (20-50x)', 'Super Win (50x+)']
                win_stats = game_stats_detailed[['gid'] + win_cols].copy()
                win_stats['Total Wins'] = win_stats[win_cols].sum(axis=1)
                for c in win_cols:
                    win_stats[c] = win_stats[c] / win_stats['Total Wins'] * 100
                
                fig_wins = px.bar(
                    win_stats, 
                    x='gid', 
                    y=win_cols, 
                    title="中奖类型分布百分比 (Win Category %)",
                    labels={'value': '占比 (%)', 'gid': '游戏ID', 'variable': '奖项类型 (Band)'}
                )
                st.plotly_chart(fig_wins, use_container_width=True)

            # =====================================================================
            # Tab 3: 玩家分析 (Player Analysis)
            # =====================================================================
            with tab3:
                st.subheader("👥 玩家行为分析 (Player Analysis)")
                
                st.markdown("### ⏱️ 玩家盈亏演变 (PnL Evolution)")
                
                # 优化: 仅取需要的列排序
                sorted_df = filtered_df[['create_date', 'user_id', 'amount']].sort_values('create_date')
                min_time = sorted_df['create_date'].min()
                max_time = sorted_df['create_date'].max()
                
                time_steps = []
                if min_time != max_time:
                    time_steps = pd.date_range(start=min_time, end=max_time, periods=100).to_pydatetime()
                else:
                    time_steps = [min_time]

                # 状态初始化: 默认展示最终结果 (Index at end)
                if 'current_time_index' not in st.session_state:
                    st.session_state.current_time_index = len(time_steps) - 1
                if 'is_playing' not in st.session_state:
                    st.session_state.is_playing = False

                # Limit time index bounds
                if st.session_state.current_time_index >= len(time_steps):
                     st.session_state.current_time_index = len(time_steps) - 1
                
                # 计算全量数据的范围，保持坐标轴固定
                max_bet_all = total_turnover * 0.1 if total_turnover > 0 else 1000
                min_pnl_all = 0
                max_pnl_all = 0
                if not sorted_df.empty:
                    final_user_agg = sorted_df.groupby('user_id')['amount'].agg(
                        cum_bet=lambda x: abs(x[x < 0].sum()),
                        cum_pnl='sum'
                    )
                    if not final_user_agg.empty:
                        max_bet_all = final_user_agg['cum_bet'].max() * 1.1
                        min_pnl_all = final_user_agg['cum_pnl'].min() * 1.1
                        max_pnl_all = final_user_agg['cum_pnl'].max() * 1.1

                col_ctrl1, col_ctrl2, col_ctrl3 = st.columns([1, 2, 4])
                
                with col_ctrl1:
                    play_btn = st.button("▶️ 播放 / ⏸️ 暂停" if not st.session_state.is_playing else "⏸️ 暂停 / ▶️ 播放")
                    if play_btn:
                        st.session_state.is_playing = not st.session_state.is_playing
                        # If at end, restart
                        if st.session_state.is_playing and st.session_state.current_time_index >= len(time_steps) - 1:
                            st.session_state.current_time_index = 0

                with col_ctrl2:
                    speed = st.select_slider("播放速度 (Speed)", options=["慢 (Slow)", "中 (Normal)", "快 (Fast)"], value="中 (Normal)")
                    # Optimized speeds
                    sleep_time = {"慢 (Slow)": 0.5, "中 (Normal)": 0.1, "快 (Fast)": 0.01}[speed]
                
                with col_ctrl3:
                    if st.session_state.is_playing:
                        st.progress(st.session_state.current_time_index / (len(time_steps) - 1) if len(time_steps) > 1 else 1.0)
                    else:
                        selected_time_idx = st.slider(
                            "时间轴 (Timeline)", 0, len(time_steps)-1, st.session_state.current_time_index,
                            format="%d"
                        )
                        st.session_state.current_time_index = selected_time_idx

                placeholder = st.empty()

                def plot_snapshot(curr_time):
                    # 优化性能: Use searchsorted for O(logN) slicing
                    idx = sorted_df['create_date'].searchsorted(curr_time, side='right')
                    subset_df = sorted_df.iloc[:idx]

                    if not subset_df.empty:
                        user_snapshot = subset_df.groupby('user_id')['amount'].agg(
                            cum_bet=lambda x: abs(x[x < 0].sum()),
                            cum_pnl='sum'
                        ).reset_index()
                        user_snapshot['status'] = user_snapshot['cum_pnl'].apply(lambda x: 'Winner (赢)' if x > 0 else 'Loser (输)')
                        
                        fig_snap = px.scatter(
                            user_snapshot, 
                            x='cum_bet', y='cum_pnl', color='status',
                            color_discrete_map={'Winner (赢)': '#E74C3C', 'Loser (输)': '#2ECC71'},
                            title=f"时刻: {curr_time.strftime('%Y-%m-%d %H:%M')}",
                            labels={'cum_bet': '累计下注', 'cum_pnl': '累计盈亏'},
                            range_x=[0, max_bet_all],
                            range_y=[min_pnl_all, max_pnl_all]
                        )
                        return fig_snap
                    return None

                if st.session_state.is_playing:
                    for i in range(st.session_state.current_time_index, len(time_steps)):
                        if not st.session_state.is_playing: break 
                        
                        st.session_state.current_time_index = i
                        fig = plot_snapshot(time_steps[i])
                        if fig:
                            placeholder.plotly_chart(fig, use_container_width=True)
                        
                        time.sleep(sleep_time)
                    
                    st.session_state.is_playing = False
                    st.rerun()
                else:
                    curr_time = time_steps[st.session_state.current_time_index]
                    st.caption(f"当前选定时刻: **{curr_time.strftime('%Y-%m-%d %H:%M')}**")
                    fig = plot_snapshot(curr_time)
                    if fig:
                        placeholder.plotly_chart(fig, use_container_width=True)
                    else:
                         placeholder.info("该时刻暂无数据 (No data at this moment)")

                st.divider()
                st.subheader("🕵️‍♂️ 单用户深度洞察 (Single User Insight)")
                
                # RTP Map & Spin Map
                user_agg_rtp = filtered_df.groupby('user_id').apply(lambda x: pd.Series({
                    'turnover': abs(x[x['amount'] < 0]['amount'].sum()),
                    'payout': x[x['amount'] > 0]['amount'].sum(),
                    'spins': len(x[x['amount'] < 0]) # 新增 spins
                })).reset_index()
                user_agg_rtp = user_agg_rtp[user_agg_rtp['turnover'] > 0]
                user_agg_rtp['rtp'] = user_agg_rtp['payout'] / user_agg_rtp['turnover'] * 100
                
                rtp_map = dict(zip(user_agg_rtp['user_id'], user_agg_rtp['rtp']))
                spin_map = dict(zip(user_agg_rtp['user_id'], user_agg_rtp['spins']))
                
                def format_user_option(uid):
                    u_rtp = rtp_map.get(uid, 0.0)
                    u_spins = spin_map.get(uid, 0)
                    return f"{uid} | RTP: {u_rtp:.1f}% | Spins: {u_spins}"
                
                target_user_raw = st.selectbox(
                    "选择或输入 User ID 查询 (Select User ID)",
                    options=sorted(filtered_df['user_id'].unique()),
                    format_func=format_user_option
                )
                
                if target_user_raw:
                    u_df = filtered_df[filtered_df['user_id'] == target_user_raw].sort_values('create_date')
                    
                    if not u_df.empty:
                        user_tags = calculate_user_tags(u_df, avg_bet)
                        st.markdown(f"**用户标签 (Tags):** `{user_tags}`")
                        
                        u_bet = abs(u_df[u_df['amount'] < 0]['amount'].sum())
                        u_pnl = u_df['amount'].sum()
                        u_spins = len(u_df[u_df['amount'] < 0])
                        u_max_win = u_df['amount'].max()
                        u_rtp = (u_df[u_df['amount'] > 0]['amount'].sum() / u_bet * 100) if u_bet > 0 else 0
                        
                        uc1, uc2, uc3, uc4, uc5, uc6 = st.columns(6)
                        uc1.metric("总下注", f"{u_bet:,.0f}")
                        uc2.metric("总盈亏", f"{u_pnl:,.0f}")
                        uc3.metric("总局数", f"{u_spins}")
                        uc4.metric("个人 RTP", f"{u_rtp:.2f}%")
                        uc5.metric("最大赢分", f"{u_max_win:,.0f}")
                        
                        ggr_share = (u_bet - u_df[u_df['amount']>0]['amount'].sum()) / ggr * 100 if ggr != 0 else 0
                        uc6.metric("GGR 贡献度", f"{ggr_share:.4f}%")
                        
                        u_df['cumulative_pnl'] = u_df['amount'].cumsum()
                        
                        # --- 优化 X 轴显示 ---
                        # 使用局数序号代替时间轴，以跳过空白时间
                        u_df = u_df.reset_index(drop=True)
                        u_df['spin_index'] = u_df.index + 1
                        
                        st.subheader(f"资金与行为曲线 (User Journey)")
                        st.caption("图中彩色标记点代表**切换游戏 (Game Switch)**。X 轴为游戏局数次序，已跳过非活跃时间。")
                        
                        # 检测 Game Switch 事件
                        u_df['prev_gid'] = u_df['gid'].shift(1)
                        u_df['prev_gid'] = u_df['prev_gid'].fillna(-1)
                        switch_events = u_df[u_df['gid'] != u_df['prev_gid']].copy()
                        
                        fig_journey = px.line(
                            u_df, x='spin_index', y='cumulative_pnl',
                            title="累计盈亏 (Cumulative PnL) - 按局数展示",
                            labels={'spin_index': '游戏局数 (Sequence)', 'cumulative_pnl': '累计盈亏', 'create_date': '时间'},
                            hover_data=['create_date', 'gid', 'amount']
                        )
                        
                        switch_events['gid_str'] = switch_events['gid'].astype(str)
                        
                        for g_id in switch_events['gid'].unique():
                            g_data = switch_events[switch_events['gid'] == g_id]
                            fig_journey.add_trace(go.Scatter(
                                x=g_data['spin_index'],
                                y=g_data['cumulative_pnl'],
                                mode='markers',
                                name=f"Game {g_id}", # Legend 显示
                                marker=dict(size=10, symbol='diamond'),
                                text=g_data['create_date'].dt.strftime('%Y-%m-%d %H:%M:%S') + f" <br>Switched to Game {g_id}",
                                hoverinfo='text+x+y'
                            ))

                        st.plotly_chart(fig_journey, use_container_width=True)
                        
                        if u_df['has_pool'].any():
                            fig_u_pool = px.line(
                                u_df, x='spin_index', y='real_pool', 
                                title="个人 Pool 水位 (Personal Pool Trend)", 
                                labels={'spin_index': '游戏局数 (Sequence)', 'real_pool': '水位', 'create_date': '时间'},
                                hover_data=['create_date']
                            )
                            fig_u_pool.update_traces(line_color='#F39C12')
                            st.plotly_chart(fig_u_pool, use_container_width=True)

            # =====================================================================
            # Tab 4: 数据明细 (修复缩进问题)
            # =====================================================================
            with tab4:
                st.subheader("📋 原始数据 (Raw Data)")
                cols = ['id', 'create_date', 'user_id', 'gid', 'amount', 'type']
                if 'real_pool' in filtered_df.columns:
                    cols.insert(5, 'real_pool')
                
                rename_dict = {
                    'create_date': '时间 (Time)',
                    'user_id': '用户ID (User ID)',
                    'gid': '游戏ID (Game ID)',
                    'amount': '金额 (Amount)',
                    'type': '类型 (Type)',
                    'real_pool': '奖池 (Pool)'
                }
                
                display_df = filtered_df[cols].sort_values('create_date', ascending=False).rename(columns=rename_dict)
                st.dataframe(display_df, use_container_width=True)
