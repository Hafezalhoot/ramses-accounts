"""Atomic owner-only snapshot of Ramses accounting data to private Google Sheets.

Five reserved tabs are a read-only mirror. The SQLite database is authoritative.
No clearing a visible snapshot before its replacement is fully written.
"""
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

TABS = ("Ramses_Vouchers", "Ramses_Funds", "Ramses_Payroll", "Ramses_Audit", "Ramses_Sync_Status")
BASE = "https://sheets.googleapis.com/v4/spreadsheets"
MAX_SNAPSHOT_CELLS = 350000  # ponytail: upgrade to incremental replication beyond this size.
PREVIEW_STAGING_SHEET_ID = "1BIjVrtYUlt8lOtaarZPyz4Cci0XIp5eWIJwOCfUfTTk"


def verify_preview_sheet():
    """Fail closed: a temporary public-link trial must never write to the owner's ledger."""
    if os.getenv("RAMSES_ENVIRONMENT") == "free-preview":
        if os.getenv("GOOGLE_SHEET_ID", "").strip() != PREVIEW_STAGING_SHEET_ID:
            raise ValueError("Free preview may sync only to the isolated STAGING sheet")



def get_session():
    verify_preview_sheet()
    try:
        from google.oauth2.service_account import Credentials
        from google.auth.transport.requests import AuthorizedSession
    except ImportError as exc:
        raise RuntimeError("Google dependencies are not installed") from exc
    path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not path or not Path(path).is_file():
        raise ValueError("Service-account JSON path is not configured on the server")
    if not os.getenv("GOOGLE_SHEET_ID"):
        raise ValueError("Google Sheet ID is not configured on the server")
    creds = Credentials.from_service_account_file(
        path, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return AuthorizedSession(creds)


def req(sess, method, url, **kwargs):
    response = sess.request(method, url, timeout=30, **kwargs)
    response.raise_for_status()
    return response.json() if response.content else {}


def text(value):
    return "" if value is None else str(value)


def datasets_for(db):
    vouchers = [["id", "voucher_no", "date", "kind", "department", "category",
                 "from_fund", "to_fund", "amount_piasters", "status", "employee",
                 "salary_period", "description", "reference_no", "creator", "reviewer", "reversal_of_id"]]
    for row in db.execute("""SELECT v.id,v.voucher_no,v.date,v.kind,d.name,ca.name,f.name,tf.name,
        v.amount_piasters,v.status,e.name,v.salary_period,v.description,v.reference_no,
        u.username,ru.username,v.reversal_of_id FROM vouchers v
        LEFT JOIN departments d ON d.id=v.department_id
        LEFT JOIN categories ca ON ca.id=v.category_id
        JOIN funds f ON f.id=v.from_fund_id
        LEFT JOIN funds tf ON tf.id=v.to_fund_id
        LEFT JOIN employees e ON e.id=v.employee_id
        JOIN users u ON u.id=v.created_by
        LEFT JOIN users ru ON ru.id=v.reviewed_by ORDER BY v.id"""):
        vouchers.append([value if i in (0, 8, 16) and value is not None else text(value)
                         for i, value in enumerate(row)])

    funds = [["id", "code", "fund_name", "kind", "opening_piasters",
              "movements_piasters", "balance_piasters"]]
    for row in db.execute("""SELECT f.id,f.code,f.name,f.kind,f.opening_piasters,
        coalesce(sum(m.amount_piasters),0),f.opening_piasters+coalesce(sum(m.amount_piasters),0)
        FROM funds f LEFT JOIN fund_movements m ON m.fund_id=f.id
        GROUP BY f.id ORDER BY f.id"""):
        funds.append(list(row))

    payroll = [["id", "employee", "period", "base_piasters", "additions_piasters",
                "deductions_piasters", "net_piasters", "approved_at", "pay_type", "hourly_rate_piasters", "worked_minutes", "work_entries_count", "adjustments_add_piasters", "adjustments_deduct_piasters", "signoff_status"]]
    for row in db.execute("""SELECT p.id,e.name,p.period,p.base_piasters,
        p.additions_piasters,p.deductions_piasters,p.net_piasters,p.approved_at,
        p.pay_type,p.hourly_rate_piasters,p.worked_minutes,p.work_entries_count,
        p.adjustment_additions_piasters,p.adjustment_deductions_piasters,p.signoff_status
        FROM payroll_accruals p JOIN employees e ON e.id=p.employee_id
        ORDER BY p.period,p.id"""):
        payroll.append(list(row))

    audit = [["id", "timestamp_utc", "actor", "action", "entity", "entity_id", "details_json"]]
    for row in db.execute("""SELECT a.id,a.created_at,u.username,a.action,a.entity,a.entity_id,a.details
        FROM audit_log a LEFT JOIN users u ON u.id=a.actor_id ORDER BY a.id"""):
        audit.append([text(value) for value in row])

    revision = db.execute("SELECT revision FROM sync_status WHERE id=1").fetchone()[0]
    status = [["last_sync_utc", "revision", "voucher_count", "fund_count",
               "payroll_count", "audit_count", "sync_version"],
              [datetime.now(timezone.utc).isoformat(timespec="seconds"), revision,
               len(vouchers)-1, len(funds)-1, len(payroll)-1, len(audit)-1, "V8.1C"]]
    return dict(zip(TABS, (vouchers, funds, payroll, audit, status)))


def cell(value):
    # User-authored text always uses stringValue, never formulaValue (formula injection safe).
    if value is None:
        return {}
    if isinstance(value, bool):
        return {"userEnteredValue": {"boolValue": value}}
    if isinstance(value, (int, float)):
        return {"userEnteredValue": {"numberValue": value}}
    return {"userEnteredValue": {"stringValue": str(value)}}


def sync_to_google(db):
    verify_preview_sheet()
    # Payroll, audit details, voucher references and employee names can be PII.
    # A configured Google Sheet alone is NOT a privacy approval. Free preview
    # is restricted by verify_preview_sheet() to its isolated synthetic demo.
    if os.getenv('RAMSES_ENVIRONMENT') != 'free-preview' and os.getenv('RAMSES_GOOGLE_SYNC_SENSITIVE_APPROVED') != '1':
        raise ValueError('Sensitive Google mirror disabled: requires documented consent and RAMSES_GOOGLE_SYNC_SENSITIVE_APPROVED=1')
    session = get_session()
    spreadsheet_id = os.environ["GOOGLE_SHEET_ID"].strip()
    base = BASE + "/" + quote(spreadsheet_id, safe="")
    meta = req(session, "GET", base, params={
        "fields": "spreadsheetId,sheets(properties(sheetId,title,gridProperties(rowCount,columnCount)))"
    })
    if meta.get("spreadsheetId") not in (None, spreadsheet_id):
        raise ValueError("Google returned an unexpected spreadsheet ID")
    remote = {s["properties"]["title"]: s["properties"] for s in meta.get("sheets", [])}
    missing = set(TABS).difference(remote)
    if missing:
        raise ValueError("Required private mirror tabs are missing: " + ", ".join(sorted(missing)))

    snapshots = datasets_for(db)
    total_cells = sum(len(rows) * len(rows[0]) for rows in snapshots.values())
    if total_cells > MAX_SNAPSHOT_CELLS:
        raise ValueError("Mirror exceeded safe single-batch size; use incremental export")

    operations = []
    for title in TABS:
        rows = snapshots[title]
        props = remote[title]
        sid = props["sheetId"]
        grid = props.get("gridProperties") or {}
        row_count, col_count = grid.get("rowCount", 0), grid.get("columnCount", 0)
        needed_rows, needed_cols = len(rows), len(rows[0])
        if needed_rows > row_count:
            operations.append({"appendDimension": {
                "sheetId": sid, "dimension": "ROWS", "length": needed_rows - row_count
            }})
        if needed_cols > col_count:
            operations.append({"appendDimension": {
                "sheetId": sid, "dimension": "COLUMNS", "length": needed_cols - col_count
            }})
        operations.append({"updateCells": {
            "start": {"sheetId": sid, "rowIndex": 0, "columnIndex": 0},
            "rows": [{"values": [cell(v) for v in row]} for row in rows],
            "fields": "userEnteredValue"
        }})
        # Clear any older surplus records atomically in the SAME batch.
        # Empty cell + userEnteredValue field only: keep colors, formulas elsewhere, and CF.
        if row_count > needed_rows:
            operations.append({"repeatCell": {
                "range": {"sheetId": sid, "startRowIndex": needed_rows,
                          "endRowIndex": row_count, "startColumnIndex": 0,
                          "endColumnIndex": needed_cols},
                "cell": {}, "fields": "userEnteredValue"
            }})

    # spreadsheets.batchUpdate validates all operations and applies them atomically.
    # A failed request leaves the previous mirror intact; no batchClear ever runs.
    result = req(session, "POST", base + ":batchUpdate", json={"requests": operations})
    if len(result.get("replies", [])) != len(operations):
        raise RuntimeError("Google Sheets did not acknowledge all snapshot writes")
    return {title: len(rows)-1 for title, rows in snapshots.items()}
