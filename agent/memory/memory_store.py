"""决策记录存储

使用 SQLite 存储和查询历史决策记录。
"""

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import MemoryRecord


class MemoryStore:
    """决策记录存储

    提供决策记录的存储、查询和统计功能。
    """

    def __init__(self, db_path: str = "~/.tradeagent/memory.db"):
        """
        Args:
            db_path: SQLite 数据库路径
        """
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """初始化数据库"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_records (
                    record_id TEXT PRIMARY KEY,
                    security_id TEXT NOT NULL,
                    trade_date TEXT,
                    timestamp TEXT NOT NULL,
                    action TEXT NOT NULL,
                    price REAL,
                    volume INTEGER,
                    confidence REAL,
                    reason TEXT,
                    technical_signal TEXT,
                    fundamental_valuation TEXT,
                    sentiment_flow TEXT,
                    news_sentiment REAL,
                    debate_consensus TEXT,
                    debate_confidence REAL,
                    risk_approved BOOLEAN,
                    risk_reason TEXT,
                    result_pnl REAL,
                    result_price REAL,
                    result_timestamp TEXT,
                    reflection TEXT,
                    is_success BOOLEAN
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_security_date
                ON memory_records(security_id, trade_date)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp
                ON memory_records(timestamp)
            """)
            conn.commit()

    def record_decision(self, record: MemoryRecord) -> str:
        """记录决策

        Args:
            record: 决策记录

        Returns:
            记录 ID
        """
        if not record.record_id:
            record.record_id = str(uuid.uuid4())[:8]

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO memory_records
                (record_id, security_id, trade_date, timestamp, action, price, volume,
                 confidence, reason, technical_signal, fundamental_valuation,
                 sentiment_flow, news_sentiment, debate_consensus, debate_confidence,
                 risk_approved, risk_reason, result_pnl, result_price,
                 result_timestamp, reflection, is_success)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.record_id,
                record.security_id,
                record.trade_date,
                record.timestamp.isoformat(),
                record.action,
                record.price,
                record.volume,
                record.confidence,
                record.reason,
                record.technical_signal,
                record.fundamental_valuation,
                record.sentiment_flow,
                record.news_sentiment,
                record.debate_consensus,
                record.debate_confidence,
                record.risk_approved,
                record.risk_reason,
                record.result_pnl,
                record.result_price,
                record.result_timestamp.isoformat() if record.result_timestamp else None,
                record.reflection,
                record.is_success,
            ))
            conn.commit()

        return record.record_id

    def update_result(
        self,
        record_id: str,
        result_pnl: float,
        result_price: float,
        is_success: bool | None = None,
    ):
        """更新决策结果

        Args:
            record_id: 记录 ID
            result_pnl: 盈亏
            result_price: 结果价格
            is_success: 是否成功
        """
        if is_success is None:
            is_success = result_pnl > 0

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE memory_records
                SET result_pnl = ?, result_price = ?, result_timestamp = ?, is_success = ?
                WHERE record_id = ?
            """, (result_pnl, result_price, datetime.now().isoformat(), is_success, record_id))
            conn.commit()

    def update_reflection(self, record_id: str, reflection: str):
        """更新反思

        Args:
            record_id: 记录 ID
            reflection: 反思内容
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE memory_records
                SET reflection = ?
                WHERE record_id = ?
            """, (reflection, record_id))
            conn.commit()

    def query_history(
        self,
        security_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        action: str | None = None,
        is_success: bool | None = None,
        limit: int = 100,
    ) -> list[MemoryRecord]:
        """查询历史记录

        Args:
            security_id: 股票代码（可选）
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）
            action: 操作类型（可选）
            is_success: 是否成功（可选）
            limit: 返回数量限制

        Returns:
            决策记录列表
        """
        conditions = []
        params = []

        if security_id:
            conditions.append("security_id = ?")
            params.append(security_id)
        if start_date:
            conditions.append("trade_date >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("trade_date <= ?")
            params.append(end_date)
        if action:
            conditions.append("action = ?")
            params.append(action)
        if is_success is not None:
            conditions.append("is_success = ?")
            params.append(is_success)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(f"""
                SELECT * FROM memory_records
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT ?
            """, params + [limit])

            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()

            records = []
            for row in rows:
                data = dict(zip(columns, row))
                # 转换布尔值
                if data.get("risk_approved") is not None:
                    data["risk_approved"] = bool(data["risk_approved"])
                if data.get("is_success") is not None:
                    data["is_success"] = bool(data["is_success"])
                records.append(MemoryRecord.from_dict(data))

            return records

    def get_statistics(
        self,
        security_id: str | None = None,
        days: int = 30,
    ) -> dict:
        """获取统计信息

        Args:
            security_id: 股票代码（可选）
            days: 统计天数

        Returns:
            统计信息字典
        """
        conditions = []
        params = []

        if security_id:
            conditions.append("security_id = ?")
            params.append(security_id)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        with sqlite3.connect(self.db_path) as conn:
            # 总交易次数
            cursor = conn.execute(f"""
                SELECT COUNT(*) FROM memory_records
                WHERE {where_clause} AND action != 'HOLD'
            """, params)
            total_trades = cursor.fetchone()[0]

            # 盈利次数
            cursor = conn.execute(f"""
                SELECT COUNT(*) FROM memory_records
                WHERE {where_clause} AND is_success = 1
            """, params)
            win_count = cursor.fetchone()[0]

            # 总 PnL
            cursor = conn.execute(f"""
                SELECT SUM(result_pnl) FROM memory_records
                WHERE {where_clause} AND result_pnl IS NOT NULL
            """, params)
            total_pnl = cursor.fetchone()[0] or 0.0

            # 平均盈亏
            cursor = conn.execute(f"""
                SELECT AVG(result_pnl) FROM memory_records
                WHERE {where_clause} AND result_pnl IS NOT NULL AND result_pnl != 0
            """, params)
            avg_pnl = cursor.fetchone()[0] or 0.0

            # 最大单笔盈利
            cursor = conn.execute(f"""
                SELECT MAX(result_pnl) FROM memory_records
                WHERE {where_clause}
            """, params)
            max_win = cursor.fetchone()[0] or 0.0

            # 最大单笔亏损
            cursor = conn.execute(f"""
                SELECT MIN(result_pnl) FROM memory_records
                WHERE {where_clause}
            """, params)
            max_loss = cursor.fetchone()[0] or 0.0

            win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0.0

            return {
                "total_trades": total_trades,
                "win_count": win_count,
                "loss_count": total_trades - win_count,
                "win_rate": win_rate,
                "total_pnl": total_pnl,
                "avg_pnl": avg_pnl,
                "max_win": max_win,
                "max_loss": max_loss,
            }
