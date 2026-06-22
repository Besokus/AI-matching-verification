"""AKShare 数据 Provider - 获取 A 股行情数据"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import akshare as ak
import pandas as pd

from ..models.market import KLine, DailyKLine


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

        # 从 AKShare 获取数据
        # 注意：AKShare 分钟线接口一次最多获取 5 天数据
        all_klines = []
        current_start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")

        while current_start <= end:
            current_end = min(current_start + timedelta(days=4), end)
            try:
                df = ak.stock_zh_a_hist_min_em(
                    symbol=security_id,
                    start_date=current_start.strftime("%Y-%m-%d %H:%M:%S"),
                    end_date=current_end.strftime("%Y-%m-%d %H:%M:%S"),
                    period="1",
                    adjust="qfq",
                )
                if df is not None and not df.empty:
                    klines = self._parse_minute_df(df, security_id)
                    all_klines.extend(klines)
            except Exception as e:
                print(f"[AKShare] 获取分钟线失败: {security_id} {current_start}-{current_end}: {e}")

            current_start = current_end + timedelta(days=1)

        # 写入缓存
        if all_klines:
            self._cache_minute_klines(all_klines)

        return all_klines

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
            df = ak.stock_zh_a_hist(
                symbol=security_id,
                period="daily",
                start_date=start_date,
                end_date=end_date,
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
        """解析分钟线 DataFrame"""
        klines = []
        for _, row in df.iterrows():
            try:
                ts = pd.to_datetime(row["时间"])
                klines.append(KLine(
                    security_id=security_id,
                    timestamp=ts,
                    open=float(row["开盘"]),
                    high=float(row["最高"]),
                    low=float(row["最低"]),
                    close=float(row["收盘"]),
                    volume=int(row["成交量"]),
                    amount=float(row.get("成交额", 0)),
                ))
            except (KeyError, ValueError) as e:
                print(f"[AKShare] 解析分钟线行失败: {e}")
                continue
        return klines

    def _parse_daily_df(self, df: pd.DataFrame, security_id: str) -> list[DailyKLine]:
        """解析日线 DataFrame"""
        klines = []
        for _, row in df.iterrows():
            try:
                klines.append(DailyKLine(
                    security_id=security_id,
                    date=str(row["日期"]),
                    open=float(row["开盘"]),
                    high=float(row["最高"]),
                    low=float(row["最低"]),
                    close=float(row["收盘"]),
                    volume=int(row["成交量"]),
                    amount=float(row.get("成交额", 0)),
                    turnover_rate=float(row.get("换手率", 0)),
                ))
            except (KeyError, ValueError) as e:
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
