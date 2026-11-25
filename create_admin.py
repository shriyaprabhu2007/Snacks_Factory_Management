
from app import get_db
from werkzeug.security import generate_password_hash
from getpass import getpass

username = input("Enter admin username: ").strip()
password = getpass("Enter admin password: ")

if not username or not password:
    print("Username and password cannot be empty.")
else:
    db = get_db()
    cursor = db.cursor()

    password_hash = generate_password_hash(password)

    cursor.execute("""
        INSERT INTO admin_users (username, password_hash)
        VALUES (%s, %s)
    """, (username, password_hash))

    db.commit()

    cursor.close()
    db.close()

    print("Admin account created successfully!")
