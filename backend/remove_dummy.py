import mysql.connector
from config import settings

conn = mysql.connector.connect(
    host=settings.MYSQL_HOST,
    port=settings.MYSQL_PORT,
    user=settings.MYSQL_USER,
    password=settings.MYSQL_PASSWORD,
    database=settings.MYSQL_DB
)
cursor = conn.cursor()
cursor.execute("DELETE FROM students WHERE usn='1DS20CS001'")
conn.commit()
print('Dummy data deleted.')
cursor.close()
conn.close()
