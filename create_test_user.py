import sqlite3
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

conn = sqlite3.connect('/app/Daisy_server/sqlite.db')
cursor = conn.cursor()

username = "test_user"
password = "Test123!@#"
hashed_password = pwd_context.hash(password)

cursor.execute("INSERT OR REPLACE INTO users (id, username, hashed_password, is_active, is_superuser) VALUES (?, ?, ?, ?, ?)", 
               (3, username, hashed_password, 1, 0))
conn.commit()

print(f"Updated user: {username}")
print(f"Password: {password}")

conn.close()
