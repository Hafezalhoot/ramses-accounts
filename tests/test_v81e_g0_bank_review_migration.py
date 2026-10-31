"""Bank reviewer grant is additive and never inherited from earlier submit grants."""
import os,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def run():
 with tempfile.TemporaryDirectory() as tmp:
  from fixture_backup_key import configure as test_backup_key
  test_backup_key(tmp)
  os.environ['RAMSES_DB_PATH']=str(Path(tmp)/'upgrade.sqlite3')
  os.environ['RAMSES_ADMIN_USER']='owner'
  os.environ['RAMSES_ADMIN_PASSWORD']='strong_migration_test_password_2026'
  from bootstrap import initialize,connect
  initialize()
  with connect() as c:
   owner=c.execute("SELECT id FROM users WHERE role='owner'").fetchone()[0]
   c.execute("INSERT INTO users(username,password_hash,role,created_at) SELECT ?,password_hash,'reviewer',created_at FROM users WHERE id=?",('reviewer-old',owner))
   reviewer=c.execute("SELECT id FROM users WHERE username='reviewer-old'").fetchone()[0]
   bank=c.execute("SELECT id FROM funds WHERE kind='bank'").fetchone()[0]
   c.execute("INSERT INTO user_fund_grants(user_id,fund_id,can_submit,changed_by,changed_at,reason) VALUES (?,?,?,?,?,?)",(reviewer,bank,1,owner,'2026-10-01','legacy submit-only grant'))
   c.execute('ALTER TABLE user_fund_grants DROP COLUMN can_approve')
   assert 'can_approve' not in [r[1] for r in c.execute('PRAGMA table_info(user_fund_grants)')]
  initialize()
  with connect() as c:
   flag=c.execute('SELECT can_submit,can_approve FROM user_fund_grants WHERE user_id=? AND fund_id=?',(reviewer,bank)).fetchone()
   assert (flag[0],flag[1])==(1,0),tuple(flag)
   assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
  print('PASS G0: upgrade old submit grant without granting historical approval rights')
if __name__=='__main__':run()
