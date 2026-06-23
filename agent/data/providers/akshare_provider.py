"""AKShare 数据 Provider - 获取 A 股行情数据"""

import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# 绕过系统代理（AKShare 不需要代理访问国内数据源）
for _proxy_key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_proxy_key, None)

import akshare as ak
import pandas as pd

from ..models.market import KLine, DailyKLine


_POSITIVE_KEYWORDS = frozenset([
    "增持", "回购", "业绩预增", "中标", "获批", "签约", "合作",
    "涨停", "大涨", "利好", "突破", "新高", "增长", "盈利",
    "分红", "送股", "转增", "预增", "扭亏", "减亏",
])

_NEGATIVE_KEYWORDS = frozenset([
    "减持", "质押", "业绩预减", "处罚", "诉讼", "违规", "暴跌",
    "跌停", "利空", "亏损", "下滑", "下降", "风险", "警告",
    "退市", "暂停", "终止", "立案", "调查", "罚款",
])


class AKShareProvider:
    """AKShare 数据 Provider，支持本地 SQLite 缓存"""

    def __init__(self, cache_dir: str = "~/.tradeagent/cache"):
        self.cache_dir = Path(cache_dir).expanduser()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.cache_dir / "akshare_cache.db"
        self._init_db()

    def _init_db(self):
        """初始化 SQLite 缓存数据库"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS minute_klines (
                    security_id TEXT,
                    timestamp TEXT,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume INTEGER,
                    amount REAL,
                    PRIMARY KEY (security_id, timestamp)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_klines (
                    security_id TEXT,
                    date TEXT,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume INTEGER,
                    amount REAL,
                    turnover_rate REAL,
                    PRIMARY KEY (security_id, date)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS financial_indicators (
                    security_id TEXT,
                    trade_date TEXT,
                    pe REAL,
                    pb REAL,
                    roe REAL,
                    revenue_growth REAL,
                    net_profit_growth REAL,
                    gross_margin REAL,
                    debt_ratio REAL,
                    PRIMARY KEY (security_id, trade_date)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS money_flow (
                    security_id TEXT,
                    trade_date TEXT,
                    main_net_inflow REAL,
                    retail_net_inflow REAL,
                    total_amount REAL,
                    main_ratio REAL,
                    PRIMARY KEY (security_id, trade_date)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS news (
                    security_id TEXT,
                    publish_time TEXT,
                    title TEXT,
                    source TEXT,
                    sentiment REAL,
                    PRIMARY KEY (security_id, publish_time, title)
                )
            """)
            conn.commit()

    def get_minute_klines(
        self,
        security_id: str,
        start_date: str,
        end_date: str,
        use_cache: bool = True,
    ) -> list[KLine]:
        """获取分钟 K 线数据

        Args:
            security_id: 股票代码，如 "600519"
            start_date: 开始日期，格式 "YYYY-MM-DD"
            end_date: 结束日期，格式 "YYYY-MM-DD"
            use_cache: 是否使用缓存

        Returns:
            分钟 K 线列表
        """
        if use_cache:
            cached = self._get_cached_minute_klines(security_id, start_date, end_date)
            if cached:
                return cached

        # 使用 stock_zh_a_minute 接口（新浪数据源，国内可直接访问）
        # 需要加市场前缀：sh/sz
        market = "sh" if security_id.startswith("6") else "sz"
        symbol = f"{market}{security_id}"

        try:
            df = ak.stock_zh_a_minute(symbol=symbol, period="1")
            if df is None or df.empty:
                return []

            # 解析并过滤日期范围
            all_klines = self._parse_minute_df_v2(df, security_id)
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)

            filtered = [k for k in all_klines if start_dt <= k.timestamp <= end_dt]

            # 写入缓存
            if filtered:
                self._cache_minute_klines(filtered)

            return filtered
        except Exception as e:
            print(f"[AKShare] 获取分钟线失败: {security_id}: {e}")
            return []

    def get_daily_klines(
        self,
        security_id: str,
        start_date: str,
        end_date: str,
        use_cache: bool = True,
    ) -> list[DailyKLine]:
        """获取日 K 线数据

        Args:
            security_id: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            use_cache: 是否使用缓存

        Returns:
            日 K 线列表
        """
        if use_cache:
            cached = self._get_cached_daily_klines(security_id, start_date, end_date)
            if cached:
                return cached

        try:
            # 使用新浪数据源（国内可直接访问）
            market = "sh" if security_id.startswith("6") else "sz"
            symbol = f"{market}{security_id}"
            df = ak.stock_zh_a_daily(
                symbol=symbol,
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
                adjust="qfq",
            )
            if df is None or df.empty:
                return []

            klines = self._parse_daily_df(df, security_id)
            self._cache_daily_klines(klines)
            return klines
        except Exception as e:
            print(f"[AKShare] 获取日线失败: {security_id}: {e}")
            return []

    def _parse_minute_df(self, df: pd.DataFrame, security_id: str) -> list[KLine]:
        """解析分钟线 DataFrame（东方财富格式）"""
        klines = []
        for row in df.itertuples(index=False):
            try:
                klines.append(KLine(
                    security_id=security_id,
                    timestamp=pd.to_datetime(row.时间),
                    open=float(row.开盘),
                    high=float(row.最高),
                    low=float(row.最低),
                    close=float(row.收盘),
                    volume=int(row.成交量),
                    amount=float(getattr(row, "成交额", 0)),
                ))
            except (AttributeError, ValueError) as e:
                print(f"[AKShare] 解析分钟线行失败: {e}")
                continue
        return klines

    def _parse_minute_df_v2(self, df: pd.DataFrame, security_id: str) -> list[KLine]:
        """解析分钟线 DataFrame（新浪格式：day/open/high/low/close/volume/amount）"""
        klines = []
        for row in df.itertuples(index=False):
            try:
                klines.append(KLine(
                    security_id=security_id,
                    timestamp=pd.to_datetime(row.day),
                    open=float(row.open),
                    high=float(row.high),
                    low=float(row.low),
                    close=float(row.close),
                    volume=int(row.volume),
                    amount=float(getattr(row, "amount", 0)),
                ))
            except (AttributeError, ValueError) as e:
                print(f"[AKShare] 解析分钟线行失败: {e}")
                continue
        return klines

    def _parse_daily_df(self, df: pd.DataFrame, security_id: str) -> list[DailyKLine]:
        """解析日线 DataFrame（兼容新浪和东方财富格式）"""
        klines = []
        for row in df.itertuples(index=False):
            try:
                # 新浪格式：date/open/high/low/close/volume/amount/turnover
                # 东方财富格式：日期/开盘/最高/最低/收盘/成交量/成交额/换手率
                date_val = getattr(row, "date", None) or getattr(row, "日期", "")
                open_val = getattr(row, "open", None) or getattr(row, "开盘", 0)
                high_val = getattr(row, "high", None) or getattr(row, "最高", 0)
                low_val = getattr(row, "low", None) or getattr(row, "最低", 0)
                close_val = getattr(row, "close", None) or getattr(row, "收盘", 0)
                volume_val = getattr(row, "volume", None) or getattr(row, "成交量", 0)
                amount_val = getattr(row, "amount", None) or getattr(row, "成交额", 0)
                turnover_val = getattr(row, "turnover", None) or getattr(row, "换手率", 0)

                klines.append(DailyKLine(
                    security_id=security_id,
                    date=str(date_val),
                    open=float(open_val),
                    high=float(high_val),
                    low=float(low_val),
                    close=float(close_val),
                    volume=int(volume_val),
                    amount=float(amount_val),
                    turnover_rate=float(turnover_val),
                ))
            except (AttributeError, ValueError) as e:
                print(f"[AKShare] 解析日线行失败: {e}")
                continue
        return klines

    def _get_cached_minute_klines(
        self, security_id: str, start_date: str, end_date: str
    ) -> Optional[list[KLine]]:
        """从缓存获取分钟线"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT security_id, timestamp, open, high, low, close, volume, amount
                FROM minute_klines
                WHERE security_id = ? AND timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp
                """,
                (security_id, start_date, end_date),
            )
            rows = cursor.fetchall()
            if not rows:
                return None
            return [
                KLine(
                    security_id=row[0],
                    timestamp=datetime.fromisoformat(row[1]),
                    open=row[2],
                    high=row[3],
                    low=row[4],
                    close=row[5],
                    volume=row[6],
                    amount=row[7],
                )
                for row in rows
            ]

    def _get_cached_daily_klines(
        self, security_id: str, start_date: str, end_date: str
    ) -> Optional[list[DailyKLine]]:
        """从缓存获取日线"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT security_id, date, open, high, low, close, volume, amount, turnover_rate
                FROM daily_klines
                WHERE security_id = ? AND date >= ? AND date <= ?
                ORDER BY date
                """,
                (security_id, start_date, end_date),
            )
            rows = cursor.fetchall()
            if not rows:
                return None
            return [
                DailyKLine(
                    security_id=row[0],
                    date=row[1],
                    open=row[2],
                    high=row[3],
                    low=row[4],
                    close=row[5],
                    volume=row[6],
                    amount=row[7],
                    turnover_rate=row[8],
                )
                for row in rows
            ]

    def _cache_minute_klines(self, klines: list[KLine]):
        """写入分钟线缓存"""
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO minute_klines
                (security_id, timestamp, open, high, low, close, volume, amount)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        k.security_id,
                        k.timestamp.isoformat(),
                        k.open,
                        k.high,
                        k.low,
                        k.close,
                        k.volume,
                        k.amount,
                    )
                    for k in klines
                ],
            )
            conn.commit()

    def _cache_daily_klines(self, klines: list[DailyKLine]):
        """写入日线缓存"""
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO daily_klines
                (security_id, date, open, high, low, close, volume, amount, turnover_rate)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        k.security_id,
                        k.date,
                        k.open,
                        k.high,
                        k.low,
                        k.close,
                        k.volume,
                        k.amount,
                        k.turnover_rate,
                    )
                    for k in klines
                ],
            )
            conn.commit()

    def get_financial_indicator(
        self,
        security_id: str,
        use_cache: bool = True,
    ) -> dict:
        """获取财务指标数据

        Args:
            security_id: 股票代码
            use_cache: 是否使用缓存

        Returns:
            财务指标字典，包含 pe, pb, roe, revenue_growth, net_profit_growth, gross_margin, debt_ratio
        """
        if use_cache:
            cached = self._get_cached_financial_indicator(security_id)
            if cached:
                return cached

        try:
            # 获取个股指标（PE/PB 等）
            df = ak.stock_a_indicator_lg(symbol=security_id)
            if df is None or df.empty:
                return self._default_financial_indicator(security_id)

            # 取最新一行
            latest = df.iloc[-1]
            result = {
                "security_id": security_id,
                "trade_date": str(latest.get("trade_date", "")),
                "pe": float(latest.get("pe", 0)) if pd.notna(latest.get("pe")) else 0.0,
                "pe_ttm": float(latest.get("pe_ttm", 0)) if pd.notna(latest.get("pe_ttm")) else 0.0,
                "pb": float(latest.get("pb", 0)) if pd.notna(latest.get("pb")) else 0.0,
                "ps": float(latest.get("ps", 0)) if pd.notna(latest.get("ps")) else 0.0,
                "ps_ttm": float(latest.get("ps_ttm", 0)) if pd.notna(latest.get("ps_ttm")) else 0.0,
                "dv_ratio": float(latest.get("dv_ratio", 0)) if pd.notna(latest.get("dv_ratio")) else 0.0,
                "dv_ttm": float(latest.get("dv_ttm", 0)) if pd.notna(latest.get("dv_ttm")) else 0.0,
                "total_mv": float(latest.get("total_mv", 0)) if pd.notna(latest.get("total_mv")) else 0.0,
            }

            # 尝试获取财务指标（ROE/营收增长等）
            try:
                fin_df = ak.stock_financial_analysis_indicator(symbol=security_id)
                if fin_df is not None and not fin_df.empty:
                    fin_latest = fin_df.iloc[0]  # 最新一期
                    result["roe"] = self._safe_float(fin_latest.get("净资产收益率(%)", 0))
                    result["gross_margin"] = self._safe_float(fin_latest.get("销售毛利率(%)", 0))
                    result["debt_ratio"] = self._safe_float(fin_latest.get("资产负债率(%)", 0))
                    result["net_profit_growth"] = self._safe_float(fin_latest.get("净利润增长率(%)", 0))
                    result["revenue_growth"] = self._safe_float(fin_latest.get("主营业务收入增长率(%)", 0))
            except Exception:
                # 财务指标获取失败，使用默认值
                result["roe"] = 0.0
                result["gross_margin"] = 0.0
                result["debt_ratio"] = 0.0
                result["net_profit_growth"] = 0.0
                result["revenue_growth"] = 0.0

            self._cache_financial_indicator(result)
            return result
        except Exception as e:
            print(f"[AKShare] 获取财务指标失败: {security_id}: {e}")
            return self._default_financial_indicator(security_id)

    def get_money_flow(
        self,
        security_id: str,
        use_cache: bool = True,
    ) -> dict:
        """获取资金流向数据

        Args:
            security_id: 股票代码
            use_cache: 是否使用缓存

        Returns:
            资金流向字典，包含 main_net_inflow, retail_net_inflow, total_amount, main_ratio
        """
        if use_cache:
            cached = self._get_cached_money_flow(security_id)
            if cached:
                return cached

        try:
            # 个股资金流向
            df = ak.stock_individual_fund_flow(stock=security_id, market="sh" if security_id.startswith("6") else "sz")
            if df is None or df.empty:
                return self._default_money_flow(security_id)

            # 取最新一行
            latest = df.iloc[-1]
            main_inflow = self._safe_float(latest.get("主力净流入-净额", 0))
            total_amount = self._safe_float(latest.get("成交额", 0))

            result = {
                "security_id": security_id,
                "trade_date": str(latest.get("日期", "")),
                "main_net_inflow": main_inflow,
                "retail_net_inflow": self._safe_float(latest.get("散户净流入-净额", 0)),
                "total_amount": total_amount,
                "main_ratio": (main_inflow / total_amount * 100) if total_amount > 0 else 0.0,
                "main_net_inflow_pct": self._safe_float(latest.get("主力净流入-净占比", 0)),
                "retail_net_inflow_pct": self._safe_float(latest.get("散户净流入-净占比", 0)),
            }

            self._cache_money_flow(result)
            return result
        except Exception as e:
            print(f"[AKShare] 获取资金流向失败: {security_id}: {e}")
            return self._default_money_flow(security_id)

    def get_news(
        self,
        security_id: str,
        use_cache: bool = True,
    ) -> list[dict]:
        """获取个股新闻

        Args:
            security_id: 股票代码
            use_cache: 是否使用缓存

        Returns:
            新闻列表，每条包含 title, source, publish_time, sentiment
        """
        if use_cache:
            cached = self._get_cached_news(security_id)
            if cached:
                return cached

        try:
            # 获取个股新闻
            df = ak.stock_news_em(symbol=security_id)
            if df is None or df.empty:
                return []

            news_list = []
            for row in df.itertuples(index=False):
                title = str(getattr(row, "新闻标题", ""))
                source = str(getattr(row, "新闻来源", ""))
                publish_time = str(getattr(row, "发布时间", ""))
                content = str(getattr(row, "新闻内容", ""))

                # 基于关键词的情绪评分
                sentiment = self._score_news_sentiment(title + " " + content)

                news_list.append({
                    "security_id": security_id,
                    "title": title,
                    "source": source,
                    "publish_time": publish_time,
                    "sentiment": sentiment,
                })

            self._cache_news(news_list)
            return news_list
        except Exception as e:
            print(f"[AKShare] 获取新闻失败: {security_id}: {e}")
            return []

    def _score_news_sentiment(self, text: str) -> float:
        """基于关键词的新闻情绪评分

        Args:
            text: 新闻标题+内容

        Returns:
            情绪得分 -1.0 ~ 1.0
        """
        score = 0.0
        for kw in _POSITIVE_KEYWORDS:
            if kw in text:
                score += 0.3
        for kw in _NEGATIVE_KEYWORDS:
            if kw in text:
                score -= 0.3

        return max(-1.0, min(1.0, score))

    def _safe_float(self, value) -> float:
        """安全转换为 float"""
        try:
            if pd.isna(value):
                return 0.0
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _default_financial_indicator(self, security_id: str) -> dict:
        """默认财务指标"""
        return {
            "security_id": security_id,
            "trade_date": "",
            "pe": 0.0,
            "pe_ttm": 0.0,
            "pb": 0.0,
            "ps": 0.0,
            "ps_ttm": 0.0,
            "dv_ratio": 0.0,
            "dv_ttm": 0.0,
            "total_mv": 0.0,
            "roe": 0.0,
            "gross_margin": 0.0,
            "debt_ratio": 0.0,
            "net_profit_growth": 0.0,
            "revenue_growth": 0.0,
        }

    def _default_money_flow(self, security_id: str) -> dict:
        """默认资金流向"""
        return {
            "security_id": security_id,
            "trade_date": "",
            "main_net_inflow": 0.0,
            "retail_net_inflow": 0.0,
            "total_amount": 0.0,
            "main_ratio": 0.0,
            "main_net_inflow_pct": 0.0,
            "retail_net_inflow_pct": 0.0,
        }

    def _get_cached_financial_indicator(self, security_id: str) -> Optional[dict]:
        """从缓存获取财务指标"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT security_id, trade_date, pe, pb, roe, revenue_growth,
                       net_profit_growth, gross_margin, debt_ratio
                FROM financial_indicators
                WHERE security_id = ?
                ORDER BY trade_date DESC
                LIMIT 1
                """,
                (security_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "security_id": row[0],
                "trade_date": row[1],
                "pe": row[2],
                "pb": row[3],
                "roe": row[4],
                "revenue_growth": row[5],
                "net_profit_growth": row[6],
                "gross_margin": row[7],
                "debt_ratio": row[8],
            }

    def _cache_financial_indicator(self, data: dict):
        """写入财务指标缓存"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO financial_indicators
                (security_id, trade_date, pe, pb, roe, revenue_growth,
                 net_profit_growth, gross_margin, debt_ratio)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["security_id"],
                    data.get("trade_date", ""),
                    data.get("pe", 0),
                    data.get("pb", 0),
                    data.get("roe", 0),
                    data.get("revenue_growth", 0),
                    data.get("net_profit_growth", 0),
                    data.get("gross_margin", 0),
                    data.get("debt_ratio", 0),
                ),
            )
            conn.commit()

    def _get_cached_money_flow(self, security_id: str) -> Optional[dict]:
        """从缓存获取资金流向"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT security_id, trade_date, main_net_inflow, retail_net_inflow,
                       total_amount, main_ratio
                FROM money_flow
                WHERE security_id = ?
                ORDER BY trade_date DESC
                LIMIT 1
                """,
                (security_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "security_id": row[0],
                "trade_date": row[1],
                "main_net_inflow": row[2],
                "retail_net_inflow": row[3],
                "total_amount": row[4],
                "main_ratio": row[5],
            }

    def _cache_money_flow(self, data: dict):
        """写入资金流向缓存"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO money_flow
                (security_id, trade_date, main_net_inflow, retail_net_inflow,
                 total_amount, main_ratio)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    data["security_id"],
                    data.get("trade_date", ""),
                    data.get("main_net_inflow", 0),
                    data.get("retail_net_inflow", 0),
                    data.get("total_amount", 0),
                    data.get("main_ratio", 0),
                ),
            )
            conn.commit()

    def _get_cached_news(self, security_id: str) -> Optional[list[dict]]:
        """从缓存获取新闻"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT security_id, publish_time, title, source, sentiment
                FROM news
                WHERE security_id = ?
                ORDER BY publish_time DESC
                LIMIT 20
                """,
                (security_id,),
            )
            rows = cursor.fetchall()
            if not rows:
                return None
            return [
                {
                    "security_id": row[0],
                    "publish_time": row[1],
                    "title": row[2],
                    "source": row[3],
                    "sentiment": row[4],
                }
                for row in rows
            ]

    def _cache_news(self, news_list: list[dict]):
        """写入新闻缓存"""
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO news
                (security_id, publish_time, title, source, sentiment)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        n["security_id"],
                        n.get("publish_time", ""),
                        n.get("title", ""),
                        n.get("source", ""),
                        n.get("sentiment", 0),
                    )
                    for n in news_list
                ],
            )
            conn.commit()
