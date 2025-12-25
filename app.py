import streamlit as st
import json
from pathlib import Path
from datetime import date, datetime
import uuid

# =============================
# ファイル
# =============================
ACCOUNTS_FILE = Path("accounts.json")
TX_FILE = Path("transactions.json")
FIXED_FILE = Path("fixed_costs.json")

# =============================
# JSON I/O
# =============================
def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default

def save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

# =============================
# ユーティリティ
# =============================
def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"

def parse_date_safe(s: str):
    """YYYY-MM-DD を date に。無理なら None"""
    try:
        return date.fromisoformat(str(s)[:10])
    except Exception:
        return None

def sort_transactions_inplace(transactions: list[dict]):
    """日付→同日なら作成順（id）で安定ソート"""
    def key(t):
        d = parse_date_safe(t.get("date", ""))
        # Noneは末尾へ
        return (d is None, d or date.max, str(t.get("id", "")))
    transactions.sort(key=key)

def ensure_ids(accounts, transactions, fixed_costs):
    """古いデータにidが無ければ補完して保存"""
    changed = False

    for a in accounts:
        if "id" not in a:
            a["id"] = new_id("acc")
            changed = True
        if "balance" not in a:
            a["balance"] = 0
            changed = True
        if "name" not in a:
            a["name"] = "未設定口座"
            changed = True

    for t in transactions:
        if "id" not in t:
            t["id"] = new_id("tx")
            changed = True
        # date/account/amount/memoの最低限補完
        if "date" not in t:
            t["date"] = str(date.today())
            changed = True
        if "account" not in t:
            t["account"] = ""
            changed = True
        if "amount" not in t:
            t["amount"] = 0
            changed = True
        if "memo" not in t:
            t["memo"] = ""
            changed = True

    for fc in fixed_costs:
        if "id" not in fc:
            fc["id"] = new_id("fc")
            changed = True
        if "day" not in fc:
            fc["day"] = 1
            changed = True
        if "memo" not in fc:
            fc["memo"] = ""
            changed = True

    return changed

# =============================
# 読み込み
# =============================
accounts = load_json(ACCOUNTS_FILE, [])
transactions = load_json(TX_FILE, [])
fixed_costs = load_json(FIXED_FILE, [])

# id補完
if ensure_ids(accounts, transactions, fixed_costs):
    save_json(ACCOUNTS_FILE, accounts)
    save_json(TX_FILE, transactions)
    save_json(FIXED_FILE, fixed_costs)

# 取引は常にソート
sort_transactions_inplace(transactions)

# =============================
# UI
# =============================
st.set_page_config(page_title="ウロチャン家計アプリ", page_icon="💰", layout="wide")
st.title("💰 ウロチャン家計アプリ")

# =============================
# サイドバー：固定費
# =============================
with st.sidebar:
    st.header("📌 固定費")

    # --- 固定費テンプレ追加（上） ---
    with st.expander("固定費テンプレを追加", expanded=True):
        if len(accounts) == 0:
            st.info("先に口座を作ってね（下の「＋ 口座を追加」から）")
        else:
            with st.form("add_fixed"):
                fc_name = st.text_input("固定費名（例：奨学金 / Paidy / NURO光）")
                fc_account = st.selectbox("引き落とし口座", [a["name"] for a in accounts])
                fc_amount = st.number_input("金額（出金はマイナス）", value=-1000, step=100)
                fc_memo = st.text_input("メモ（任意）", value="固定費")
                fc_day = st.selectbox("毎月何日に追加する？", options=list(range(1, 32)), index=24)

                if st.form_submit_button("テンプレを追加"):
                    if fc_name.strip() == "":
                        st.error("固定費名を入れてね")
                    else:
                        fixed_costs.append({
                            "id": new_id("fc"),
                            "name": fc_name.strip(),
                            "account": fc_account,
                            "amount": int(fc_amount),
                            "memo": fc_memo.strip(),
                            "day": int(fc_day),
                        })
                        save_json(FIXED_FILE, fixed_costs)
                        st.success("固定費テンプレを追加した！")
                        st.rerun()

    st.divider()

    # --- 固定費テンプレ一覧（左） ---
    st.subheader("📋 固定費テンプレ一覧")
    if len(fixed_costs) == 0:
        st.info("固定費テンプレがまだないよ")
    else:
        for fc in fixed_costs:
            day = int(fc.get("day", 1))
            memo = str(fc.get("memo", "")).strip()
            text = f"・{fc.get('name','')} / {fc.get('account','')} / {int(fc.get('amount',0)):,}円 / 毎月{day}日"
            if memo:
                text += f" / {memo}"

            col1, col2 = st.columns([7, 3])
            with col1:
                st.write(text)
            with col2:
                if st.button("削除", key=f"del_fc_{fc.get('id')}"):
                    fixed_costs = [x for x in fixed_costs if x.get("id") != fc.get("id")]
                    save_json(FIXED_FILE, fixed_costs)
                    st.success("テンプレを削除した！")
                    st.rerun()

    st.divider()

    # --- 今月一括追加（ボタンは一番下） ---
    if len(fixed_costs) == 0:
        st.info("固定費テンプレがまだないよ（上で追加してね）")
    else:
        if st.button("📌 今月の固定費を一括追加（重複はスキップ）"):
            month_prefix = date.today().strftime("%Y-%m")
            today_day = date.today().day

            added = 0
            skipped_future = 0
            skipped_dup = 0
            skipped_no_account = 0

            # 口座名→参照
            acc_map = {a["name"]: a for a in accounts}

            for fc in fixed_costs:
                day = int(fc.get("day", 1))

                # まだ当日じゃない固定費はスキップ（ルール）
                if today_day < day:
                    skipped_future += 1
                    continue

                tx_date = f"{month_prefix}-{day:02d}"
                tx_account = str(fc.get("account", "")).strip()
                amount = int(fc.get("amount", 0))
                name = str(fc.get("name", "")).strip()
                memo2 = str(fc.get("memo", "")).strip()

                tx_memo = f"固定費:{name}"
                if memo2:
                    tx_memo += f" / {memo2}"

                # 重複チェック（同じ日付・口座・金額・メモ）
                dup = False
                for t in transactions:
                    if (
                        str(t.get("date", "")) == tx_date
                        and str(t.get("account", "")).strip() == tx_account
                        and int(t.get("amount", 0)) == amount
                        and str(t.get("memo", "")).strip() == tx_memo
                    ):
                        dup = True
                        break
                if dup:
                    skipped_dup += 1
                    continue

                # 口座存在チェック
                if tx_account not in acc_map:
                    skipped_no_account += 1
                    continue

                # 取引追加
                transactions.append({
                    "id": new_id("tx"),
                    "date": tx_date,
                    "account": tx_account,
                    "amount": amount,
                    "memo": tx_memo,
                })

                # 残高反映
                acc_map[tx_account]["balance"] = int(acc_map[tx_account].get("balance", 0)) + amount
                added += 1

            # 並び替えて保存
            sort_transactions_inplace(transactions)
            save_json(TX_FILE, transactions)
            save_json(ACCOUNTS_FILE, accounts)

            st.success(
                f"追加:{added}件 / 未到来:{skipped_future}件 / 重複:{skipped_dup}件 / 口座なし:{skipped_no_account}件"
            )
            st.rerun()

# =============================
# メトリクス（上）
# =============================
total_balance = sum(int(a.get("balance", 0)) for a in accounts)

month_prefix = date.today().strftime("%Y-%m")
month_income = sum(int(t.get("amount", 0)) for t in transactions
                   if str(t.get("date","")).startswith(month_prefix) and int(t.get("amount",0)) > 0)
month_expense = -sum(int(t.get("amount", 0)) for t in transactions
                     if str(t.get("date","")).startswith(month_prefix) and int(t.get("amount",0)) < 0)

c1, c2, c3 = st.columns(3)
c1.metric("💰 合計残高", f"{total_balance:,}円")
c2.metric("🟩 今月の収入", f"{int(month_income):,}円")
c3.metric("🟥 今月の支出", f"{int(month_expense):,}円")

st.divider()

# =============================
# 口座一覧
# =============================
st.subheader("🏦 口座一覧")
if len(accounts) == 0:
    st.info("まだ口座がありません（下の「＋ 口座を追加」から）")
else:
    for acc in accounts:
        col1, col2 = st.columns([8, 2])
        with col1:
            st.write(f"・{acc.get('name','')}（残高：{int(acc.get('balance',0)):,}円）")
        with col2:
            if st.button("口座削除", key=f"del_acc_{acc.get('id')}"):
                # 口座削除（※その口座の取引は残す。必要なら後で連動削除もできる）
                accounts = [a for a in accounts if a.get("id") != acc.get("id")]
                save_json(ACCOUNTS_FILE, accounts)
                st.success("口座を削除した！")
                st.rerun()

# 「口座追加」は普段隠す（＋で出る）
with st.expander("➕ 口座を追加（ここを開いた時だけ表示）", expanded=False):
    with st.form("add_account"):
        name = st.text_input("口座名（例：SMBC / SBI / 現金）")
        balance = st.number_input("開始残高（円）", value=0, step=1000)
        if st.form_submit_button("追加する"):
            if name.strip() == "":
                st.error("口座名を入れてね")
            else:
                accounts.append({
                    "id": new_id("acc"),
                    "name": name.strip(),
                    "balance": int(balance)
                })
                save_json(ACCOUNTS_FILE, accounts)
                st.success("口座を追加した！")
                st.rerun()

st.divider()

# =============================
# 取引追加
# =============================
st.subheader("🧾 収入・支出を追加（残高が増減する）")
if len(accounts) == 0:
    st.info("先に口座を作ってね")
else:
    with st.form("add_tx"):
        d = st.date_input("日付", value=date.today())
        acc_name = st.selectbox("口座", [a["name"] for a in accounts], key="tx_account")
        amount = st.number_input("金額（出金はマイナス、入金はプラス）", value=0, step=1000)
        memo = st.text_input("メモ（任意）", key="tx_memo")

        if st.form_submit_button("取引を追加"):
            # 残高反映
            for a in accounts:
                if a["name"] == acc_name:
                    a["balance"] = int(a.get("balance", 0)) + int(amount)
                    break

            # 取引追加
            transactions.append({
                "id": new_id("tx"),
                "date": str(d),
                "account": acc_name,
                "amount": int(amount),
                "memo": memo.strip()
            })

            # 並び替えて保存
            sort_transactions_inplace(transactions)
            save_json(ACCOUNTS_FILE, accounts)
            save_json(TX_FILE, transactions)

            st.success("取引を追加した！（時系列に並べ替え済み）")
            st.rerun()

st.divider()

# =============================
# 取引一覧（時系列：古い→新しい）
# =============================
st.subheader("📊 取引一覧（時系列：古い → 新しい）")
if len(transactions) == 0:
    st.info("まだ取引がありません")
else:
    # ここは表示用にコピー（安全）
    display_txs = list(transactions)
    sort_transactions_inplace(display_txs)

    for t in display_txs:
        col1, col2 = st.columns([8, 2])
        amt = int(t.get("amount", 0))
        sign = "+" if amt > 0 else ""
        with col1:
            st.write(f"{t.get('date','')} | {t.get('account','')} | {sign}{amt:,}円 | {t.get('memo','')}")
        with col2:
            if st.button("削除", key=f"del_tx_{t.get('id')}"):
                # 実データから該当IDを削除
                tx_id = t.get("id")
                target = None
                for x in transactions:
                    if x.get("id") == tx_id:
                        target = x
                        break

                if target is not None:
                    # 残高を巻き戻す
                    for a in accounts:
                        if a.get("name") == target.get("account"):
                            a["balance"] = int(a.get("balance", 0)) - int(target.get("amount", 0))
                            break

                    transactions = [x for x in transactions if x.get("id") != tx_id]

                    sort_transactions_inplace(transactions)
                    save_json(ACCOUNTS_FILE, accounts)
                    save_json(TX_FILE, transactions)

                    st.success("取引を削除して残高を戻した！")
                    st.rerun()