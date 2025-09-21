import os
import sqlite3

# --- Define the same data directory as in app.py ---
DATA_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'data')
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# --- Connect to the database file inside the data directory ---
db_path = os.path.join(DATA_DIR, 'database.db')
connection = sqlite3.connect(db_path)

# Open the schema file and execute it
with open('schema.sql') as f:
    connection.executescript(f.read())

# Close the connection
connection.close()

print(f"Database initialized successfully at {db_path}")