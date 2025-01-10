import sqlite3
import psycopg2

# Connect to SQLite
sqlite_conn = sqlite3.connect('tasks.db')
sqlite_cursor = sqlite_conn.cursor()

# Connect to PostgreSQL
pg_conn = psycopg2.connect(
    dbname='todo_list_db_88z8',
    user='todo_list_db_88z8_user',
    password='JJlkuTZm2hDNwBvcQYSVNb9STtuTNg9Z',
    host='dpg-cu0hqcdumphs7384bkog-a.oregon-postgres.render.com',
    port='5432'
)
pg_cursor = pg_conn.cursor()

# Fetch data from SQLite
sqlite_cursor.execute("SELECT * FROM user")
users = sqlite_cursor.fetchall()

# Insert data into PostgreSQL
for user in users:
    pg_cursor.execute("INSERT INTO user (id, username, email, password, email_verified, verification_token, token_expiration) VALUES (%s, %s, %s, %s, %s, %s, %s)", user)

# Commit and close connections
pg_conn.commit()
sqlite_conn.close()
pg_conn.close() 