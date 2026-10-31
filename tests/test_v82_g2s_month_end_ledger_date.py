"""Month close must reject a night posted in another month despite invoice date."""
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app  # Import the FastAPI entry point before its attached bed router.
from bed_stays import month_close_bed_issue

def run():
    c=sqlite3.connect(':memory:')
    c.row_factory=sqlite3.Row
    c.executescript('''
    CREATE TABLE bed_stays(id INTEGER,case_id INTEGER,start_date TEXT,end_date TEXT);
    CREATE TABLE bed_night_charges(id INTEGER PRIMARY KEY,stay_id INTEGER,night_date TEXT,case_line_id INTEGER);
    CREATE TABLE billing_invoice_draft_lines(case_line_id INTEGER,draft_id INTEGER);
    CREATE TABLE billing_invoices(draft_id INTEGER,issued_date TEXT,journal_id INTEGER);
    CREATE TABLE gl_journals(id INTEGER,status TEXT,entry_date TEXT);
    INSERT INTO bed_stays VALUES(1,7,'2026-09-29','2026-10-01');
    INSERT INTO bed_night_charges VALUES(1,1,'2026-09-29',101),(2,1,'2026-09-30',102);
    INSERT INTO billing_invoice_draft_lines VALUES(101,8),(102,8);
    INSERT INTO billing_invoices VALUES(8,'2026-09-30',14);
    INSERT INTO gl_journals VALUES(14,'posted','2026-10-01');
    ''')
    issue=month_close_bed_issue(c,'2026-09')
    assert issue and issue['kind']=='not_invoiced',issue
    c.execute("UPDATE gl_journals SET entry_date='2026-09-30' WHERE id=14")
    assert month_close_bed_issue(c,'2026-09') is None
    print('PASS G2S: month-end recognizes invoice only with posted GL in matching period')

if __name__=='__main__':run()
