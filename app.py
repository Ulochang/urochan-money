import streamlit as st
import json
from pathlib import Path
from datetime import date

# ----------------------------
# ファイル
# ----------------------------
ACCOUNTS_FILE = Path("accounts.json")
TX_FILE = Path("transactions.json")
FIXED_FILE = Path("fixed_costs.json")

# ----------------------------
# JSON I/O
# ----------------------------
def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default

def save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

# ----------------------------
# データ読み込み
# ----------------------------
accounts = load_json(ACCOUNTS_FILE, [])
transactions = load_json(TX_FILE, [])
fixed_costs = load_json(FIXED_FILE, [])

# ----------------------------
# タイトル
# ----------------------------
st.title("💰 ウロチャン家計アプリ")

# ============================================================
# ✅ サイドバー：固定費（テンプレ追加 / 一括追加 / 一覧）
# ============================================================
with st.sidebar:
    st.header("📌 固定費")

    # --- テンプレ追加 & 今月一括追加 ---
    with st.expander("固定費テンプレ / 今月一括追加", expanded=True):

        # テンプレ追加フォーム
        if len(accounts) == 0:
            st.info("固定費テンプレを作るには、先に口座を作ってね")
        else:
            with st.form("add_fixed"):
                fc_name = st.text_input("固定費名（例：奨学金 / Paidy / NURO光）")
                fc_account = st.selectbox("引き落とし口座", [a["name"] for a in accounts])
                fc_amount = st.number_input("金額（出金はマイナス）", value=-1000, step=100)
                fc_memo = st.text_input("メモ（任意）", value="固定費")
                fc_day = st.selectbox("毎月何日に追加する？", options=list(range(1, 32)), index=24)

                submitted = st.form_submit_button("テンプレを追加")

            if submitted:
                if fc_name.strip() == "":
                    st.error("固定費名を入れてね")
                else:
                    fixed_costs.append({
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

        # 今月一括追加（重複防止 + 日付指定 + 残高反映）
        if len(fixed_costs) == 0:
            st.info("固定費テンプレがまだないよ")
        else:
            if st.button("📌 今月の固定費を一括追加"):
                month_prefix = date.today().strftime("%Y-%m")
                today_day = date.today().day

                added = 0
                skipped_future = 0
                skipped_dup = 0
                skipped_no_account = 0

                for fc in fixed_costs:
                    day = int(fc.get("day", 1))

                    # 今日がその日になるまで追加しない
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

                    # --- 重複チェック（同じ月・同じ日・同じ口座・同じ金額・同じメモなら追加しない） ---
                    dup = False
                    for t in transactions:
                        if (
                            str(t.get("date", "")).startswith(month_prefix)
                            and str(t.get("date", "")) == tx_date
                            and str(t.get("account", "")).strip() == tx_account
                            and int(t.get("amount", 0)) == amount
                            and str(t.get("memo", "")).strip() == tx_memo
                        ):
                            dup = True
                            break

                    if dup:
                        skipped_dup += 1
                        continue

                    # --- 口座存在チェック & 残高反映 ---
                    acc_found = False
                    for a in accounts:
                        if str(a.get("name", "")).strip() == tx_account:
                            a["balance"] = int(a.get("balance", 0)) + amount
                            acc_found = True
                            break

                    if not acc_found:
                        skipped_no_account += 1
                        continue

                    # --- 取引追加 ---
                    transactions.append({
                        "date": tx_date,
                        "account": tx_account,
                        "amount": amount,
                        "memo": tx_memo,
                    })
                    added += 1

                # 保存
                save_json(TX_FILE, transactions)
                save_json(ACCOUNTS_FILE, accounts)

                st.success(
                    f"今月の固定費を追加: {added}件 / "
                    f"未到来スキップ: {skipped_future}件 / "
                    f"重複スキップ: {skipped_dup}件 / "
                    f"口座なしスキップ: {skipped_no_account}件"
                )
                st.rerun()

    st.divider()

    # --- 固定費テンプレ一覧（サイドバー下） ---
    st.subheader("📋 固定費テンプレ一覧")

    if len(fixed_costs) == 0:
        st.info("固定費テンプレがまだありません")
    else:
        for i, fc in enumerate(fixed_costs):
            col1, col2 = st.columns([8, 2])

            day = int(fc.get("day", 1))
            memo = str(fc.get("memo", "")).strip()
            text = (
                f"・{fc.get('name','')} / {fc.get('account','')} / "
                f"{int(fc.get('amount',0)):,}円 / 毎月{day}日"
            )
            if memo:
                text += f" / {memo}"

            with col1:
                st.write(text)

            with col2:
                if st.button("削除", key=f"del_fc_{i}"):
                    fixed_costs.pop(i)
                    save_json(FIXED_FILE, fixed_costs)
                    st.success("テンプレを削除した！")
                    st.rerun()

# ============================================================
# ✅ メイン：合計残高 & 今月の収入/支出
# ============================================================
total_balance = sum(int(a.get("balance", 0)) for a in accounts)

month_prefix = date.today().strftime("%Y-%m")
month_income = sum(
    int(t.get("amount", 0)) for t in transactions
    if str(t.get("date", "")).startswith(month_prefix) and int(t.get("amount", 0)) > 0
)
month_expense = -sum(
    int(t.get("amount", 0)) for t in transactions
    if str(t.get("date", "")).startswith(month_prefix) and int(t.get("amount", 0)) < 0
)

c1, c2, c3 = st.columns(3)
c1.metric("💰 合計残高", f"{total_balance:,}円")
c2.metric("🟩 今月の収入", f"{int(month_income):,}円")
c3.metric("🟥 今月の支出", f"{int(month_expense):,}円")

st.divider()

# ============================================================
# ✅ 口座一覧（削除付き）
# ============================================================
st.subheader("🏦 口座一覧")
if len(accounts) == 0:
    st.info("まだ口座がありません")
else:
    for i, acc in enumerate(accounts):
        col1, col2 = st.columns([8, 2])
        with col1:
            st.write(f"・{acc.get('name','')}（残高：{int(acc.get('balance',0)):,}円）")
        with col2:
            if st.button("口座削除", key=f"del_acc_{i}"):
                accounts.pop(i)
                save_json(ACCOUNTS_FILE, accounts)
                st.success("口座を削除した！")
                st.rerun()

st.divider()

# ============================================================
# ✅ 口座追加
# ============================================================
st.subheader("➕ 口座を追加")
with st.form("add_account"):
    name = st.text_input("口座名（例：SMBC / SBI / 現金）")
    balance = st.number_input("開始残高（円）", value=0, step=1000)
    if st.form_submit_button("追加する"):
        if name.strip() == "":
            st.error("口座名を入れてね")
        else:
            accounts.append({"name": name.strip(), "balance": int(balance)})
            save_json(ACCOUNTS_FILE, accounts)
            st.success("口座を追加した！")
            st.rerun()

st.divider()

# ============================================================
# ✅ 取引追加（残高反映）
# ============================================================
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
            # 残高更新
            for a in accounts:
                if a["name"] == acc_name:
                    a["balance"] = int(a.get("balance", 0)) + int(amount)
                    break

            transactions.append({
                "date": str(d),
                "account": acc_name,
                "amount": int(amount),
                "memo": memo.strip(),
            })

            save_json(ACCOUNTS_FILE, accounts)
            save_json(TX_FILE, transactions)
            st.success("取引を追加した！")
            st.rerun()

st.divider()

# ============================================================
# ✅ 取引一覧（削除付き）
# ============================================================
st.subheader("📊 取引一覧（最新が上）")
if len(transactions) == 0:
    st.info("まだ取引がありません")
else:
    for idx, t in enumerate(reversed(transactions)):
        col1, col2 = st.columns([8, 2])
        amt = int(t.get("amount", 0))
        sign = "+" if amt > 0 else ""
        with col1:
            st.write(f"{t.get('date','')} | {t.get('account','')} | {sign}{amt:,}円 | {t.get('memo','')}")
        with col2:
            if st.button("削除", key=f"del_tx_{idx}"):
                real_index = len(transactions) - 1 - idx
                tx = transactions.pop(real_index)

                # 残高を巻き戻す
                for a in accounts:
                    if a.get("name") == tx.get("account"):
                        a["balance"] = int(a.get("balance", 0)) - int(tx.get("amount", 0))
                        break

                save_json(ACCOUNTS_FILE, accounts)
                save_json(TX_FILE, transactions)
                st.success("取引を削除して残高を戻した！")
                st.rerun()