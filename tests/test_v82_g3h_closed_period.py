"""G3H SQL period boundary: new purchase-order documents cannot be backdated into sealed month."""
import os
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run():
    with tempfile.TemporaryDirectory(prefix='ramses-g3h-monthclose-') as tmp:
        os.environ.update(RAMSES_DB_PATH=str(Path(tmp)/'sql-boundary.sqlite3'),
                          RAMSES_ADMIN_USER='owner',RAMSES_ADMIN_PASSWORD='synthetic-g3h-sql-owner')
        from bootstrap import initialize,connect
        initialize()
        day=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
        with connect() as c:
            c.execute("INSERT INTO inventory_vendors(code,name) VALUES('G3H-SEALED','Synthetic legacy vendor')")
            vid=c.execute('SELECT id FROM inventory_vendors WHERE code="G3H-SEALED"').fetchone()[0]
            owner=c.execute('SELECT id FROM users WHERE username="owner"').fetchone()[0]
            c.execute('INSERT INTO periods(period,closed_by,closed_at) VALUES(?,?,?)',(day[:7],owner,day))
            c.commit()
            try:
                c.execute("""INSERT INTO inventory_purchase_orders
                  (vendor_id,ordered_on,order_ref,evidence_ref,created_by,created_at)
                  VALUES(?,?,?,?,?,?)""",(vid,day,'G3H-SEALED-PO','SIGNED-SEALED-PURCHASE',owner,day))
            except sqlite3.IntegrityError:c.rollback()
            else:raise AssertionError('Direct SQLite inserted PO in sealed period')
        print('PASS G3H direct SQL cannot backdate purchasing source into closed month')

if __name__=='__main__':run()
