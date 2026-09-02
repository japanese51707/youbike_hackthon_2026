"""
密碼雜湊（core.security）
==========================
用 bcrypt 對密碼做單向雜湊——資料庫只存雜湊值，絕不存原文。
就算 DB 外洩，攻擊者拿到的是無法反推的亂碼（呼應 steering §11 資安、Zeabur 教訓）。

為什麼直接用 bcrypt 而非 passlib：
  passlib 1.7.4 已多年未更新，與 bcrypt 5.x 不相容（讀不到版本、>72 bytes 行為改變）。
  bcrypt 套件 API 簡單穩定，也是業界標準，少一層過時 wrapper 更可靠。

bcrypt 特性：
  - 加鹽（gensalt 每次不同）：同密碼也得到不同雜湊，防查表破解
  - 刻意變慢（cost factor，預設 12）：讓暴力猜密碼不划算
  - 上限 72 bytes：超過會報錯，這裡先截斷到 72 bytes（bcrypt 慣例）

對外暴露：
    hash_password(plain) -> str        # 存進 DB 的雜湊
    verify_password(plain, hashed)     # 登入時比對
"""

from __future__ import annotations
import os
import bcrypt

# bcrypt 單次最多處理 72 bytes，超過需先截斷（業界慣例）
_MAX_BYTES = 72

# cost factor（rounds）：正式預設 12（安全）；測試可用環境變數 BCRYPT_ROUNDS 調低加速。
# 調低只影響「運算慢度」，不影響雜湊正確性與安全語意。
_ROUNDS = int(os.environ.get("BCRYPT_ROUNDS", "12"))


def _truncate(plain: str) -> bytes:
    return plain.encode("utf-8")[:_MAX_BYTES]


def hash_password(plain: str) -> str:
    """把明文密碼雜湊成可存 DB 的字串（含鹽）。"""
    if not plain:
        raise ValueError("密碼不可為空")
    return bcrypt.hashpw(_truncate(plain), bcrypt.gensalt(rounds=_ROUNDS)).decode("utf-8")


def verify_password(plain: str, hashed: str | None) -> bool:
    """比對明文密碼與 DB 存的雜湊。hashed 為 None（未設密碼）一律回 False。"""
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(_truncate(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False
