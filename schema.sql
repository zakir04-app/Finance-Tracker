-- Dropping tables in reverse order of dependency
DROP TABLE IF EXISTS repayments;
DROP TABLE IF EXISTS loans;
DROP TABLE IF EXISTS transactions;
DROP TABLE IF EXISTS settings;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL
);

CREATE TABLE settings (
    user_id INTEGER PRIMARY KEY,
    currency TEXT NOT NULL DEFAULT 'PKR',
    app_title TEXT NOT NULL DEFAULT 'Finance Tracker',
    logo_filename TEXT,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE transactions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    currency TEXT NOT NULL,
    type TEXT NOT NULL,
    amount REAL NOT NULL,
    category TEXT NOT NULL,
    date TEXT NOT NULL,
    description TEXT,
    payment_method TEXT,
    attachment_filename TEXT,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE loans (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    currency TEXT NOT NULL,
    type TEXT NOT NULL,
    person TEXT NOT NULL,
    initial_amount REAL NOT NULL,
    current_balance REAL NOT NULL,
    date TEXT NOT NULL,
    account_details TEXT,
    bank_name TEXT,
    payment_method TEXT,
    description TEXT,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE repayments (
    id SERIAL PRIMARY KEY,
    loan_id INTEGER NOT NULL,
    currency TEXT NOT NULL,
    amount REAL NOT NULL,
    date TEXT NOT NULL,
    description TEXT,
    attachment_filename TEXT,
    FOREIGN KEY (loan_id) REFERENCES loans (id)
);