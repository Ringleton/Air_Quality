# This provides simple annual stats of total days > specific pm2.5 readings
# Connects to the "air.db" database.

# FYI: Initial guesstimate is that one year of = approx 18Mb database

import time
from datetime import datetime, timedelta
import sqlite3

conn = sqlite3.connect("air.db", detect_types=sqlite3.PARSE_DECLTYPES)
cursor = conn.cursor()

print("\nAnnual Days of High PM2.5 Levels")
print("\nYear  150+  250+  Total")

query = """
SELECT
    strftime('%Y', time) AS year,
    SUM(CASE WHEN pm2_5 > 150 THEN 1 ELSE 0 END),
    SUM(CASE WHEN pm2_5 > 250 THEN 1 ELSE 0 END)
FROM readings
GROUP BY year
ORDER BY year ASC;
"""

cursor.execute(query)
results = cursor.fetchall()

# Divisor used below of 1440 = # of minutes in a day.
for row in results:
    print(f"{row[0]} {(row[1]-row[2])/1440:5.1f} {row[2]/1440:5.1f}  {row[1]/1440:5.1f}")

print("\n")

# DB clearnup
cursor.close()
conn.close()
