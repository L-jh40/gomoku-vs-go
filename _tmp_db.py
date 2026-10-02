# -*- coding: utf-8 -*-
import sqlite3, sys
p = r"C:\Users\lin\Desktop\gomoku-vs-go\tools\rapfi\yixin-gui\rapfi.db"
con = sqlite3.connect("file:%s?mode=ro" % p.replace("\\", "/"), uri=True)
cur = con.cursor()
cur.execute("select name, sql from sqlite_master where type='table'")
for name, sql in cur.fetchall():
    print("TABLE", name)
    print("  ", (sql or "").replace(chr(10), " ")[:200])
    try:
        cur.execute("select * from %s limit 3" % name)
        cols = [d[0] for d in cur.description]
        print("   cols:", cols)
        for row in cur.fetchall():
            vals = []
            for v in row:
                s = repr(v)
                vals.append(s[:80])
            print("   row:", vals)
    except Exception as e:
        print("   err", e)
con.close()
