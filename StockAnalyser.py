# REQUIREMENTS: pip install streamlit yfinance matplotlib pandas textblob beautifulsoup4 streamlit-authenticator

import streamlit as st
import yfinance as yf
import matplotlib.pyplot as plt
from datetime import datetime
import pandas as pd
import requests
import random
from textblob import TextBlob
from bs4 import BeautifulSoup
import json
import time

# 导入认证系统（使用模拟版本进行测试）
from auth_system_mock import (
    check_authentication, get_current_user, show_user_info,
    show_login_form, show_register_form, logout_user,
    supabase_request
)

# 配置 matplotlib 字体，保证在 Windows 上正常显示中文
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun"]
plt.rcParams["axes.unicode_minus"] = False

# Supabase 配置
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")

def get_user_portfolio(username):
    """获取用户的股票组合"""
    result = supabase_request("GET", f"user_portfolio?user_email=eq.{username}")
    if result and len(result) > 0:
        return result[0]  # 返回第一条记录
    return None

def create_user_portfolio(username, stock_list=""):
    """创建用户股票组合记录"""
    data = {
        "user_email": username,  # 使用 username 作为标识
        "stock_list": stock_list,
        "updated_at": datetime.now().isoformat()
    }
    return supabase_request("POST", "user_portfolio", data)

def update_user_portfolio(username, stock_list):
    """更新用户股票组合"""
    data = {
        "stock_list": stock_list,
        "updated_at": datetime.now().isoformat()
    }
    return supabase_request("PATCH", f"user_portfolio?user_email=eq.{username}", data)

def sync_portfolio_to_cloud(username, stock_list):
    """同步股票组合到云端数据库（使用 upsert 逻辑）"""
    # 先尝试更新，如果失败则创建
    update_result = update_user_portfolio(username, stock_list)
    if update_result:
        return update_result
    else:
        # 更新失败，可能是记录不存在，尝试创建
        return create_user_portfolio(username, stock_list)


def fetch_stock_history(symbol: str, period: str = "30d", interval: str = "1d"):
    """获取指定股票在给定周期和时间粒度下的历史数据。"""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period, interval=interval)
        if hist is None or hist.empty:
            return None
        return hist
    except Exception as e:
        st.error(f"获取 {symbol} 数据时出现错误：{e}")
        return None


def get_sp500_daily_change():
    """获取标普 500 指数 (^GSPC) 今天相对前一交易日的涨跌幅百分比。"""
    try:
        ticker = yf.Ticker("^GSPC")
        hist = ticker.history(period="2d", interval="1d")
        if hist is None or hist.empty or len(hist) < 2:
            return None
        prev_close = float(hist["Close"].iloc[-2])
        last_close = float(hist["Close"].iloc[-1])
        if prev_close == 0:
            return None
        return (last_close - prev_close) / prev_close * 100.0
    except Exception:
        return None


def compute_ma(series, window: int = 5):
    """计算移动平均线。"""
    return series.rolling(window=window).mean()


def compute_rsi(series, period: int = 14):
    """计算相对强弱指标 RSI。"""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def compute_macd(series, fast: int = 12, slow: int = 26, signal: int = 9):
    """计算 MACD 指标（返回 MACD 线、信号线和柱状图）。"""
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def compute_bollinger(series, window: int = 20, num_std: float = 2.0):
    """计算布林带（中轨、上轨、下轨）。"""
    mid = series.rolling(window=window).mean()
    std = series.rolling(window=window).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return mid, upper, lower


# 作为动态热门获取失败时的备选：标普 500 中市值较大的部分股票
FALLBACK_SP500_TOP30 = [
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "META",
    "TSLA",
    "NVDA",
    "BRK-B",
    "UNH",
    "JPM",
    "JNJ",
    "V",
    "XOM",
    "AVGO",
    "PG",
    "MA",
    "CVX",
    "HD",
    "MRK",
    "ABBV",
    "PEP",
    "KO",
    "LLY",
    "BAC",
    "COST",
    "PFE",
    "TMO",
    "DIS",
    "CSCO",
]


def fetch_trending_tickers(limit: int = 20):
    """尝试从 Yahoo Finance Trending 接口获取热门股票代码。"""
    url = "https://query1.finance.yahoo.com/v1/finance/trending/US"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        quotes = (
            data.get("finance", {})
            .get("result", [{}])[0]
            .get("quotes", [])
        )
        symbols = []
        for q in quotes:
            sym = q.get("symbol")
            if sym and isinstance(sym, str):
                symbols.append(sym.upper())
        return symbols[:limit]
    except Exception:
        # 动态获取失败时返回空列表，后续使用备选池
        return []


@st.cache_data(ttl=3600)
def get_stock_pool(limit: int = 20):
    """获取今日 AI 雷达使用的股票池：优先使用热门股票，否则回退到备选池。"""
    trending = fetch_trending_tickers(limit=limit)
    if trending:
        return trending
    return FALLBACK_SP500_TOP30[:limit]


def analyze_news_sentiment(news_items, max_items: int = 5):
    """
    使用 TextBlob 对新闻标题做情感分析。
    返回 (平均极性, 情绪标签, 新闻摘要)。
    """
    if not news_items:
        return None, "⚪ 中性", "暂无新闻"

    titles = [item.get("title") for item in news_items if item.get("title")]
    titles = titles[:max_items]
    if not titles:
        return None, "⚪ 中性", "暂无新闻标题"

    polarities = []
    for t in titles:
        try:
            pol = TextBlob(t).sentiment.polarity
            polarities.append(pol)
        except Exception:
            continue

    if not polarities:
        summary = "；".join(titles[:2])
        return None, "⚪ 中性", summary[:160]

    avg_pol = sum(polarities) / len(polarities)

    if avg_pol > 0.1:
        label = "🟢 利好"
    elif avg_pol < -0.1:
        label = "🔴 利空"
    else:
        label = "⚪ 中性"

    summary = "；".join(titles[:2])
    return avg_pol, label, summary[:160]


@st.cache_data(ttl=1800)
def fetch_news_from_finviz(symbol: str, max_items: int = 5):
    """
    从 Finviz 抓取单只股票的最新新闻标题。
    返回形如 [{"title": "..."}] 的列表。
    """
    url = f"https://finviz.com/quote.ashx?t={symbol}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://finviz.com/",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Finviz 新闻表格通常在 id="news-table" 或 class="fullview-news-outer"
        news_table = soup.find("table", id="news-table")
        if news_table is None:
            news_table = soup.find("table", class_="fullview-news-outer")
        if news_table is None:
            return []

        items = []
        for row in news_table.find_all("tr"):
            link = row.find("a")
            if not link or not link.text:
                continue
            title = link.text.strip()
            if title:
                items.append({"title": title})
            if len(items) >= max_items:
                break

        return items
    except Exception:
        # 抓取失败时返回空列表，由上层逻辑决定如何处理
        return []


@st.cache_data(ttl=3600)
def scan_stock_universe(symbols, short_mode: bool = False):
    """
    批量获取股票数据并计算综合得分（技术面 + 消息面，总分 100）。
    返回列表，每个元素是包含 symbol / total_score / news_summary 等信息的字典。
    """
    results = []

    for symbol in symbols:
        # 根据模式选择数据粒度：日线或 15 分钟短线
        if short_mode:
            hist = fetch_stock_history(symbol, period="5d", interval="15m")
        else:
            hist = fetch_stock_history(symbol)
        if hist is None or "Close" not in hist.columns:
            continue

        closes = hist["Close"]
        if closes.empty:
            continue

        ma5 = compute_ma(closes, 5)
        rsi_14 = compute_rsi(closes, period=14)
        macd_line, macd_signal, macd_hist = compute_macd(closes, fast=12, slow=26, signal=9)
        bb_mid, bb_upper, bb_lower = compute_bollinger(closes, window=20, num_std=2.0)

        latest_price = float(closes.iloc[-1])
        latest_ma5 = float(ma5.iloc[-1]) if not ma5.dropna().empty else None

        def last_valid_local(series):
            non_na = series.dropna()
            return float(non_na.iloc[-1]) if not non_na.empty else None

        latest_rsi = last_valid_local(rsi_14)
        latest_macd = last_valid_local(macd_line)
        latest_macd_signal = last_valid_local(macd_signal)
        latest_bb_mid = last_valid_local(bb_mid)

        prev_close = float(closes.iloc[-2]) if len(closes) > 1 else None
        if prev_close:
            diff = latest_price - prev_close
            pct = diff / prev_close * 100
            diff_str = f"{diff:+.2f} ({pct:+.2f}%)"
        else:
            diff_str = "N/A"

        # --- 技术面打分：共 60 分 ---
        tech_score = 0.0

        # 1) RSI：超卖加分（短线模式下采用更敏感的 80/20 阈值）
        if latest_rsi is not None:
            if short_mode:
                if latest_rsi < 20:
                    tech_score += 20  # 短线明显超卖
                elif latest_rsi < 40:
                    tech_score += 10
                elif latest_rsi < 60:
                    tech_score += 5
            else:
                if latest_rsi < 30:
                    tech_score += 20  # 明显超卖
                elif latest_rsi < 40:
                    tech_score += 10  # 偏超卖
                elif latest_rsi < 60:
                    tech_score += 5   # 中性略偏多

        # 2) MACD：金叉加分
        if (
            latest_macd is not None
            and latest_macd_signal is not None
            and latest_macd > latest_macd_signal
        ):
            tech_score += 20

        # 3) 布林带 + 5 日均线：共 20 分
        if latest_bb_mid is not None and latest_price < latest_bb_mid:
            tech_score += 10  # 价格低于中轨，有一定安全垫
        if latest_ma5 is not None and latest_price > latest_ma5:
            tech_score += 10  # 价格站上 5 日均线，短期趋势向上

        # 限制在 0~60
        tech_score = max(0.0, min(60.0, tech_score))

        # --- 短线动能分析：基于 15 分钟数据的量能、波动和突破情况 ---
        short_momentum_state = "—"
        if short_mode and len(hist) > 5:
            # 成交量爆发：当前成交量相对过去 50 个周期放大 2 倍以上
            vol = hist["Volume"] if "Volume" in hist.columns else None
            volume_spike = False
            if vol is not None and len(vol) > 1:
                if len(vol) > 51:
                    base_vol = vol.iloc[-51:-1]
                else:
                    base_vol = vol.iloc[:-1]
                base_mean = base_vol.mean() if len(base_vol) > 0 else 0
                cur_vol = vol.iloc[-1]
                if base_mean > 0 and cur_vol >= 2 * base_mean:
                    volume_spike = True

            # ATR 波动分析
            high = hist["High"] if "High" in hist.columns else None
            low = hist["Low"] if "Low" in hist.columns else None
            atr_pct = None
            atr_high = False
            if high is not None and low is not None and "Close" in hist.columns:
                close_series = hist["Close"]
                prev_close_series = close_series.shift(1)
                tr1 = high - low
                tr2 = (high - prev_close_series).abs()
                tr3 = (low - prev_close_series).abs()
                tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
                atr = tr.rolling(window=14, min_periods=10).mean()
                atr_valid = atr.dropna()
                if not atr_valid.empty:
                    latest_atr = float(atr_valid.iloc[-1])
                    if latest_price > 0:
                        atr_pct = latest_atr / latest_price * 100.0
                        if atr_pct >= 2.0:
                            atr_high = True

            # 短线突破：最新价突破过去 4 小时（约 16 根 15m K）最高点
            breakout = False
            if "High" in hist.columns and len(hist) > 16:
                recent_highs = hist["High"].iloc[-17:-1]  # 过去 ~4 小时，不含当前
                if not recent_highs.empty:
                    past_high = recent_highs.max()
                    if latest_price > past_high:
                        breakout = True

            # 结合三项信号给出短线动能状态
            if volume_spike and atr_high and breakout:
                short_momentum_state = "🚀 爆发中"
            elif (not volume_spike and not breakout) and (atr_pct is not None and atr_pct < 1.0):
                short_momentum_state = "📉 衰竭"
            else:
                short_momentum_state = "💤 平淡"

        # --- 消息面打分：共 40 分 ---
        news_avg_pol = None
        news_label = "⚪ 中性"
        news_summary = "暂无新闻"

        try:
            news_items = fetch_news_from_finviz(symbol, max_items=5)
            news_avg_pol, news_label, news_summary = analyze_news_sentiment(news_items)
        except Exception:
            # 新闻获取失败时，保持默认中性状态
            pass

        if news_avg_pol is None:
            news_score = 20.0  # 无法评估时，视为中性
        else:
            # polarity ∈ [-1,1]，线性映射到 [0,40]，0 为 20 分
            news_score = 20.0 + news_avg_pol * 20.0
            news_score = max(0.0, min(40.0, news_score))

        total_score = tech_score + news_score

        results.append(
            {
                "symbol": symbol,
                "total_score": total_score,
                "tech_score": tech_score,
                "news_score": news_score,
                "latest_price": latest_price,
                "latest_ma5": latest_ma5,
                "latest_rsi": latest_rsi,
                "latest_macd": latest_macd,
                "latest_macd_signal": latest_macd_signal,
                "latest_bb_mid": latest_bb_mid,
                "diff_str": diff_str,
                "news_summary": news_summary,
                "news_label": news_label,
                "short_momentum_state": short_momentum_state,
            }
        )

    return results


def main():
    st.set_page_config(
        page_title="我的 AI 股票分析站",
        page_icon="📈",
        layout="centered",
    )

    st.title("我的 AI 股票分析站")
    st.markdown("一个极简的 30 天趋势分析小工具，结合多指标与新闻情绪给出综合建议。")

    # 🔐 用户认证系统
    st.sidebar.title("🔐 用户中心")
    
    # 调试模式开关
    if 'debug_mode' not in st.session_state:
        st.session_state.debug_mode = False
    debug_mode = st.sidebar.checkbox("🔧 调试模式", value=st.session_state.debug_mode)
    st.session_state.debug_mode = debug_mode
    
    # 检查认证状态
    if not check_authentication():
        # 显示登录或注册表单
        if st.session_state.get('show_register', False):
            show_register_form()
        else:
            show_login_form()
        
        # 未登录时显示提示信息
        st.warning("🔒 请先登录以访问完整功能")
        st.info("登录后您可以：")
        st.markdown("- 📊 保存和管理个人持仓")
        st.markdown("- 🔄 自动同步持仓数据到云端")
        st.markdown("- 📈 获取个性化投资建议")
        return
    
    # 已登录状态
    show_user_info()

    # 🎯 今日 AI 雷达扫描（动态热门 + 新闻情感）
    st.subheader("🎯 今日 AI 雷达扫描")
    with st.spinner("正在获取热门股票并扫描多指标 + 新闻情绪..."):
        pool = get_stock_pool(limit=20)
        radar_results = scan_stock_universe(pool, short_mode=False)

    if radar_results:
        # 按综合得分排序，取前 5 名
        radar_results = sorted(
            radar_results, key=lambda x: (-x["total_score"], x["symbol"])
        )
        top_n = radar_results[:5]

        df = pd.DataFrame(
            [
                {
                    "股票代码": item["symbol"],
                    "总分(0-100)": round(item["total_score"], 1),
                    "技术面得分(0-60)": round(item["tech_score"], 1),
                    "消息面得分(0-40)": round(item["news_score"], 1),
                    "最新价格(USD)": round(item["latest_price"], 2),
                    "最新新闻摘要": item.get("news_summary", "暂无新闻"),
                    "情绪标签": item.get("news_label", "⚪ 中性"),
                }
                for item in top_n
            ]
        )

        st.dataframe(
            df,
            use_container_width=True,
        )
    else:
        st.info("今日市场数据不足或网络异常，AI 雷达暂未生成榜单。")

    # 💼 我的持仓分析诊断
    st.divider()
    st.subheader("💼 我的持仓分析诊断")

    # 如果用户已登录，尝试从云端拉取股票列表
    default_holdings = ""
    username, user_info = get_current_user()
    if username:
        with st.spinner("正在从云端加载您的持仓数据..."):
            portfolio = get_user_portfolio(username)
            if portfolio and portfolio.get('stock_list'):
                default_holdings = portfolio['stock_list']
                st.info(f"✅ 已从云端加载您的持仓：{default_holdings}")

    with st.container():
        pos_col1, pos_col2 = st.columns([3, 1.2])
        with pos_col1:
            holdings_input = st.text_input(
                "请输入您目前持有的股票代码（用英文逗号隔开，例如：AAPL, TSLA, NVDA）",
                value=default_holdings,
            )
            short_mode = st.toggle("短线模式（5 日 15 分钟 K 线诊断）", value=False)
        with pos_col2:
            diagnose_holdings = st.button("一键诊断持仓")

    if diagnose_holdings:
        raw_codes = [c.strip().upper() for c in holdings_input.split(",") if c.strip()]
        unique_codes = []
        for c in raw_codes:
            if c not in unique_codes:
                unique_codes.append(c)

        if not unique_codes:
            st.warning("请先输入至少一个有效的股票代码，再点击诊断。")
        else:
            # 如果用户已登录，同步到云端
            if username:
                stock_list_str = ",".join(unique_codes)
                with st.spinner("正在同步持仓到云端..."):
                    sync_result = sync_portfolio_to_cloud(username, stock_list_str)
                    if sync_result:
                        st.success("✅ 持仓已同步到云端")
                    else:
                        st.error("❌ 云端同步失败，但本地分析仍可继续")

            spinner_text = (
                "正在对您的持仓进行短线诊断（5 日 15 分钟数据）..."
                if short_mode
                else "正在对您的持仓进行全面诊断，请稍候..."
            )
            with st.spinner(spinner_text):
                diag_results = scan_stock_universe(unique_codes, short_mode=short_mode)

            if not diag_results:
                st.warning("未能获取到任何持仓标的的数据，请检查代码是否正确。")
            else:
                returned_symbols = {item["symbol"] for item in diag_results}
                invalid_symbols = [c for c in unique_codes if c not in returned_symbols]
                for sym in invalid_symbols:
                    st.warning(f"未能获取到 {sym} 的行情或新闻数据，已跳过该标的。")

                # 持仓深度鉴定（毒舌版）
                avg_score = sum(float(i["total_score"]) for i in diag_results) / len(diag_results)
                best_item = max(diag_results, key=lambda x: x["total_score"])
                worst_item = min(diag_results, key=lambda x: x["total_score"])
                best_symbol = best_item["symbol"]
                worst_symbol = worst_item["symbol"]
                worst_score = float(worst_item["total_score"])

                scenario = "other"
                if avg_score > 75:
                    scenario = "all_green"
                elif avg_score < 35:
                    scenario = "all_red"
                elif worst_score < 25 and avg_score >= 40:
                    scenario = "single_bomb"
                elif 40 <= avg_score <= 60:
                    scenario = "mediocre"

                msgs = {
                    "all_green": [
                        "😏 哟，在这儿装什么股神呢？整体均分都混到 {avg:.1f} 分了，{best} 还在持仓里蹦跶，是想让巴菲特给你端茶倒水吗？记住了，运气好不代表你有脑子，利润落袋才是钱。",
                        "🟢 这持仓红到晃眼，{best} 带队起飞，{worst} 都不好意思拖后腿。现在最大的风险，就是你开始相信自己是股神。",
                        "🚀 全线基本在起飞区，均分 {avg:.1f} 分，这阵容拿去朋友圈晒都嫌炫耀过头。麻烦你记得，一个回撤就能教人重新做人。",
                    ],
                    "all_red": [
                        "💀 均分只有 {avg:.1f} 分，{worst} 这票直接在地板上刨坑。你这选股眼光是跟谁学的？是闭着眼睛在键盘上乱按的吗？",
                        "🩸 这仓位叫持股吗？叫情绪受难现场。{worst} 一个坑，{best} 也只是勉强站着。真心建议你先学会止损，再学会睡觉。",
                        "🥀 整体评分 {avg:.1f}，已经不是绿油油，是一片荒漠。{worst} 负责爆雷，{best} 负责陪葬，你负责充当韭菜。",
                    ],
                    "single_bomb": [
                        "🎯 整体水平还凑合，均分 {avg:.1f}，结果被 {worst} 这只 只有 {worst_score:.1f} 分的票拖成了家庭负资产。它就是你持仓里的害群之马。",
                        "🧨 看得出来你不是完全没眼光，至少 {best} 还撑着场面。但 {worst} 这只股，你是认真的吗？它在拖后腿，你在拖它，是在演什么苦情剧？",
                        "⚠️ 这仓位最大的风险不在整体，而在细节：{worst} 一只票的拉胯程度 ({worst_score:.1f} 分) 足够写进《如何亲手毁掉一段本来还不错的持仓》。",
                    ],
                    "mediocre": [
                        "😴 均分 {avg:.1f}，{best} 顶多算个优秀员工，{worst} 勉强不被开除。这样的持仓，你是打算买来养老吗？建议找个班上，比它靠谱。",
                        "🟡 不上不下最折磨人。{best} 没强到让你兴奋，{worst} 又没烂到让你下定决心砍掉。你和你的持仓，都处在‘将就’的关系里。",
                        "📉 这种毫无波澜的持仓组合，连赌场都嫌无聊。{best} 不够惊艳，{worst} 一直拖后腿，结果就是账户曲线像心电图里的‘平坦期’。",
                    ],
                    "other": [
                        "🤨 持仓均分 {avg:.1f}，{best} 在前面拼命拉车，{worst} 在后面拼命放刹车。你这不是投资组合，是团队协作失败案例。",
                        "🧮 这仓位的故事很简单：{best} 苦苦支撑颜值，{worst} 专职拉低平均分。你要么学会换人，要么习惯被它们一起教育。",
                        "🌀 你的持仓告诉我一件事：{best} 想带你飞，{worst} 想拉你睡大觉。均分 {avg:.1f}，说明市场还在给你机会，但你得先对这帮队友下点狠心。",
                    ],
                }

                chosen = random.choice(msgs[scenario]).format(
                    avg=avg_score,
                    best=best_symbol,
                    worst=worst_symbol,
                    worst_score=worst_score,
                )

                with st.chat_message("assistant"):
                    st.markdown(f"### 💬 持仓深度鉴定（毒舌版）")
                    st.markdown(chosen)

                rows = []
                for item in diag_results:
                    total_score = float(item["total_score"])
                    price = float(item["latest_price"])
                    momentum_state = item.get("short_momentum_state", "—")

                    if total_score >= 70:
                        advice = "🟢 强势特征，建议继续持有或逢低加仓。"
                    elif total_score >= 40:
                        advice = "🟡 震荡或分歧，建议观望或逢高减持。"
                    else:
                        advice = "🔴 破位/情绪悲观，建议严格执行止损或清仓。"

                    rows.append(
                        {
                            "股票代码": item["symbol"],
                            "最新价格(USD)": round(price, 2),
                            "总分(0-100)": round(total_score, 1),
                            "短线动能状态": momentum_state,
                            "操作建议": advice,
                        }
                    )

                df_positions = pd.DataFrame(rows)
                st.dataframe(df_positions, use_container_width=True)

    st.divider()

    # 顶部输入与按钮区域（单只股票深度分析）
    with st.container():
        col1, col2 = st.columns([3, 1.2])
        with col1:
            symbol = st.text_input(
                "股票代码（例如：AAPL、MSFT、TSLA）",
                value="AAPL",
            ).strip().upper()
        with col2:
            analyze = st.button("开始分析", type="primary")

    if not analyze:
        st.info("请输入股票代码，然后点击“开始分析”。")
        return

    if not symbol:
        st.warning("股票代码不能为空。")
        return

    # 获取数据
    with st.spinner(f"正在获取 {symbol} 最近 30 天的数据..."):
        hist = fetch_stock_history(symbol)

    if hist is None:
        st.warning("暂时无法获取该股票的数据，请稍后重试或检查股票代码是否正确。")
        return

    if "Close" not in hist.columns:
        st.error("返回的数据中缺少收盘价（Close）列，无法继续分析。")
        return

    closes = hist["Close"]
    ma5 = compute_ma(closes, 5)

    if ma5.isna().all():
        st.warning("5 日均线数据不足，请稍后重试。")
        return

    # 计算技术指标：RSI、MACD、布林带
    rsi_14 = compute_rsi(closes, period=14)
    macd_line, macd_signal, macd_hist = compute_macd(closes, fast=12, slow=26, signal=9)
    bb_mid, bb_upper, bb_lower = compute_bollinger(closes, window=20, num_std=2.0)

    # 最新价格与 5 日均线
    latest_price = float(closes.iloc[-1])
    latest_ma5 = float(ma5.iloc[-1])

    # 最新指标值（使用最后一个非空值）
    def last_valid(series):
        non_na = series.dropna()
        return float(non_na.iloc[-1]) if not non_na.empty else None

    latest_rsi = last_valid(rsi_14)
    latest_macd = last_valid(macd_line)
    latest_macd_signal = last_valid(macd_signal)
    latest_bb_mid = last_valid(bb_mid)

    # 计算与前一日的涨跌幅
    prev_close = float(closes.iloc[-2]) if len(closes) > 1 else None
    if prev_close:
        diff = latest_price - prev_close
        pct = diff / prev_close * 100
        diff_str = f"{diff:+.2f} ({pct:+.2f}%)"
    else:
        diff_str = "N/A"

    # 信息展示区域
    col_a, col_b = st.columns(2)
    with col_a:
        st.metric("最新价格 (USD)", f"{latest_price:.2f}", diff_str if diff_str != "N/A" else None)
    with col_b:
        st.metric("当前 5 日均线", f"{latest_ma5:.2f}")

    # 附加指标展示
    indi_col1, indi_col2 = st.columns(2)
    with indi_col1:
        if latest_rsi is not None:
            st.metric("14 日 RSI", f"{latest_rsi:.2f}")
    with indi_col2:
        if latest_macd is not None and latest_macd_signal is not None:
            st.metric("MACD (快线 / 信号线)", f"{latest_macd:.4f} / {latest_macd_signal:.4f}")

    # 最新市场情绪（新闻 + 情感分析）
    st.subheader("📰 最新市场情绪")

    news_avg_pol_single = None
    news_overall_label = "⚪ 整体中性"
    news_rows = []

    try:
        news_items_single = fetch_news_from_finviz(symbol, max_items=5)
    except Exception:
        news_items_single = []

    if not news_items_single:
        st.info("暂未获取到近期新闻。")
    else:
        scores = []
        for item in news_items_single[:5]:
            title = item.get("title")
            if not title:
                continue
            try:
                polarity = TextBlob(title).sentiment.polarity
            except Exception:
                continue

            scores.append(polarity)
            if polarity > 0:
                label = "🟢 利好"
            elif polarity < 0:
                label = "🔴 利空"
            else:
                label = "⚪ 中性"

            news_rows.append(
                {
                    "标题": title,
                    "情绪得分": round(polarity, 3),
                    "情绪标签": label,
                }
            )

        if scores:
            news_avg_pol_single = sum(scores) / len(scores)
            if news_avg_pol_single > 0:
                news_overall_label = "🟢 整体偏利好"
            elif news_avg_pol_single < 0:
                news_overall_label = "🔴 整体偏利空"
            else:
                news_overall_label = "⚪ 整体中性"

            st.metric(
                "平均情绪得分 (-1 ~ 1)",
                f"{news_avg_pol_single:.3f}",
                news_overall_label,
            )

            with st.expander("展开查看最近新闻与情绪标签"):
                df_news = pd.DataFrame(news_rows)
                st.dataframe(df_news, use_container_width=True)
        else:
            st.info("已获取新闻，但暂无法完成情感分析。")

    # 多指标共振推荐逻辑（打分）
    score = 0

    # 1) RSI < 30 或 MACD 金叉 (MACD > Signal)
    cond_rsi = latest_rsi is not None and latest_rsi < 30
    cond_macd_golden = (
        latest_macd is not None
        and latest_macd_signal is not None
        and latest_macd > latest_macd_signal
    )
    if cond_rsi or cond_macd_golden:
        score += 1

    # 2) 最新价格低于布林带中轨
    if latest_bb_mid is not None and latest_price < latest_bb_mid:
        score += 1

    # 3) 最新价格高于 5 日均线
    if latest_price > latest_ma5:
        score += 1

    if score >= 2:
        st.success(
            f"🌟 强烈推荐：多指标共振买入信号\n\n"
            f"- 当前得分：{score} / 3\n"
            f"- 最新价：{latest_price:.2f}，5 日均线：{latest_ma5:.2f}"
        )
    elif score == 1:
        st.warning(
            f"⚠️ 建议观望：信号不明确\n\n"
            f"- 当前得分：{score} / 3\n"
            f"- 最新价：{latest_price:.2f}，5 日均线：{latest_ma5:.2f}"
        )
    else:
        st.error(
            f"🔴 风险较高：处于下行趋势或信号偏弱\n\n"
            f"- 当前得分：{score} / 3\n"
            f"- 最新价：{latest_price:.2f}，5 日均线：{latest_ma5:.2f}"
        )

    st.divider()

    # 走势图：收盘价 + 5 日均线 + 布林带中轨（如可用）
    st.subheader("最近 30 天收盘价与 5 日均线走势图")

    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(hist.index, closes, label="收盘价", color="tab:blue", linewidth=1.6)
    ax.plot(hist.index, ma5, label="5 日均线", color="tab:orange", linewidth=1.4)
    if bb_mid is not None and not bb_mid.dropna().empty:
        ax.plot(hist.index, bb_mid, label="布林带中轨(20 日)", color="tab:green", linewidth=1.2, alpha=0.8)

    ax.set_title(f"{symbol} 过去 30 天收盘价与 5 日均线")
    ax.set_xlabel("日期")
    ax.set_ylabel("价格 (USD)")
    ax.legend()
    ax.grid(alpha=0.2)
    fig.autofmt_xdate()

    st.pyplot(fig, clear_figure=True)

    # 技术指标图：展示 RSI 走势
    if rsi_14 is not None and not rsi_14.dropna().empty:
        st.subheader("技术指标：14 日 RSI 走势")
        fig2, ax2 = plt.subplots(figsize=(9, 3))
        ax2.plot(hist.index, rsi_14, label="14 日 RSI", color="tab:purple", linewidth=1.4)
        ax2.axhline(30, color="tab:red", linestyle="--", linewidth=1, alpha=0.6, label="超卖 30")
        ax2.axhline(70, color="tab:orange", linestyle="--", linewidth=1, alpha=0.6, label="超买 70")
        ax2.set_ylim(0, 100)
        ax2.set_xlabel("日期")
        ax2.set_ylabel("RSI")
        ax2.grid(alpha=0.2)
        ax2.legend()
        fig2.autofmt_xdate()

        st.pyplot(fig2, clear_figure=True)

    st.caption(
        f"数据来源：Yahoo Finance · 更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    # 💾 添加到持仓功能（仅对已登录用户显示）
    username, user_info = get_current_user()
    if username:
        st.divider()
        st.subheader("💾 添加到持仓")
        
        col_add1, col_add2, col_add3 = st.columns([2, 1, 1])
        with col_add1:
            st.info(f"当前分析的股票：{symbol}")
        with col_add2:
            add_to_portfolio = st.button("添加到我的持仓", type="secondary")
        with col_add3:
            st.markdown(f"**评分：{score}/3**")
        
        if add_to_portfolio:
            # 获取当前用户持仓
            current_portfolio = get_user_portfolio(username)
            current_stocks = ""
            
            if current_portfolio and current_portfolio.get('stock_list'):
                current_stocks = current_portfolio['stock_list']
                # 检查是否已存在
                existing_stocks = [s.strip().upper() for s in current_stocks.split(",") if s.strip()]
                if symbol in existing_stocks:
                    st.warning(f"{symbol} 已在您的持仓中")
                else:
                    # 添加新股票
                    updated_stocks = current_stocks + "," + symbol if current_stocks else symbol
                    sync_result = update_user_portfolio(username, updated_stocks)
                    if sync_result:
                        st.success(f"✅ {symbol} 已添加到您的持仓")
                        # 清除缓存以便下次刷新
                        if 'portfolio_cache' in st.session_state:
                            del st.session_state.portfolio_cache
                    else:
                        st.error("❌ 添加失败，请重试")
            else:
                # 创建新持仓
                sync_result = create_user_portfolio(username, symbol)
                if sync_result:
                    st.success(f"✅ {symbol} 已添加到您的持仓")
                else:
                    st.error("❌ 添加失败，请重试")


if __name__ == "__main__":
    main()

