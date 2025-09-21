import os
from itsdangerous import URLSafeTimedSerializer
import psycopg2
import psycopg2.extras
import cloudinary
import cloudinary.uploader
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, flash, session, Response
from flask_bcrypt import Bcrypt
from flask_mail import Mail, Message

# --- App Configuration ---
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'default-fallback-key-for-local-dev')
bcrypt = Bcrypt(app)

# --- Mail Configuration ---
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
mail = Mail(app)

# --- Cloudinary Configuration ---
cloudinary.config(
    cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key = os.environ.get('CLOUDINARY_API_KEY'),
    api_secret = os.environ.get('CLOUDINARY_API_SECRET')
)

# --- Helper Functions & Global Data ---
def get_db_connection():
    database_url = os.environ.get('DATABASE_URL')
    conn = psycopg2.connect(database_url)
    return conn

def get_token_serializer():
    return URLSafeTimedSerializer(app.config['SECRET_KEY'])

CURRENCIES = {'PKR': 'Rs', 'AED': 'AED', 'USD': '$', 'SAR': 'SR', 'INR': '₹'}

@app.context_processor
def inject_user_settings():
    settings = None
    if 'user_id' in session:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute('SELECT app_title, logo_filename FROM settings WHERE user_id = %s', (session['user_id'],))
        settings = cursor.fetchone()
        cursor.close()
        conn.close()
    return dict(settings=settings)

# --- Authentication & Password Reset Routes ---

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email, password = request.form['email'], request.form['password']
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
        user = cursor.fetchone()
        if user and bcrypt.check_password_hash(user['password'], password):
            session['user_id'], session['username'] = user['id'], user['username']
            cursor.execute('SELECT currency FROM settings WHERE user_id = %s', (user['id'],))
            settings = cursor.fetchone()
            session['currency_code'] = settings['currency'] if settings else 'PKR'
            cursor.close()
            conn.close()
            return redirect(url_for('dashboard'))
        else:
            cursor.close(); conn.close(); flash('Invalid email or password.', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username, email, password = request.form['username'], request.form['email'], request.form['password']
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO users (username, email, password) VALUES (%s, %s, %s) RETURNING id', (username, email, hashed_password))
            user_id = cursor.fetchone()[0]
            cursor.execute('INSERT INTO settings (user_id, currency, app_title) VALUES (%s, %s, %s)', (user_id, 'PKR', 'Finance Tracker'))
            conn.commit(); flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except psycopg2.IntegrityError:
            conn.rollback(); flash('Email address already registered.', 'error')
        finally:
            cursor.close(); conn.close()
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear(); flash('You have been successfully logged out.', 'success'); return redirect(url_for('login'))

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        cursor.close(); conn.close()
        if user:
            s = get_token_serializer()
            token = s.dumps(email, salt='password-reset-salt')
            reset_url = url_for('reset_password', token=token, _external=True)
            msg = Message('Password Reset Request', sender=app.config['MAIL_USERNAME'], recipients=[email])
            msg.body = f'To reset your password, please visit the following link:\n\n{reset_url}\n\nThis link is valid for one hour.'
            try:
                mail.send(msg)
                flash('A password reset link has been sent to your email.', 'success')
            except Exception as e:
                flash(f'Failed to send email. Error: {e}', 'error')
        else:
            flash('Email address not found.', 'error')
        return redirect(url_for('login'))
    return render_template('forgot_password.html')

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    s = get_token_serializer()
    try:
        email = s.loads(token, salt='password-reset-salt', max_age=3600)
    except Exception:
        flash('The password reset link is invalid or has expired.', 'error'); return redirect(url_for('forgot_password'))
    if request.method == 'POST':
        password = request.form.get('password')
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute("UPDATE users SET password = %s WHERE email = %s", (hashed_password, email))
        conn.commit(); cursor.close(); conn.close()
        flash('Your password has been updated! You can now log in.', 'success'); return redirect(url_for('login'))
    return render_template('reset_password.html', token=token)

# --- Core Application Routes ---

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session: return redirect(url_for('login'))
    user_id, currency = session['user_id'], session['currency_code']
    conn = get_db_connection(); cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    queries = {
        'total_income': "SELECT SUM(amount) FROM transactions WHERE user_id = %s AND currency = %s AND type = 'income'",
        'total_expenses': "SELECT SUM(amount) FROM transactions WHERE user_id = %s AND currency = %s AND type = 'expense'",
        'money_sent_home': "SELECT SUM(amount) FROM transactions WHERE user_id = %s AND currency = %s AND category = 'Money Sent Home'",
        'loan_taken': "SELECT SUM(current_balance) FROM loans WHERE user_id = %s AND currency = %s AND type = 'taken'",
        'loan_given': "SELECT SUM(current_balance) FROM loans WHERE user_id = %s AND currency = %s AND type = 'given'"
    }
    summaries = {}
    for key, query in queries.items():
        cursor.execute(query, (user_id, currency)); summaries[key] = cursor.fetchone()[0] or 0
    cursor.execute("SELECT * FROM loans WHERE user_id = %s AND currency = %s AND current_balance > 0", (user_id, currency))
    outstanding_loans = cursor.fetchall()
    cursor.close(); conn.close()
    return render_template('dashboard.html', summaries=summaries, currencies=CURRENCIES, outstanding_loans=outstanding_loans)

@app.route('/add_transaction', methods=['POST'])
def add_transaction():
    if 'user_id' not in session: return redirect(url_for('login'))
    file_url = None
    if 'attachment' in request.files:
        file = request.files['attachment']
        if file and file.filename != '':
            try:
                upload_result = cloudinary.uploader.upload(file); file_url = upload_result.get('secure_url')
            except Exception as e: flash(f"Attachment upload failed: {e}", "error")
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute('INSERT INTO transactions (user_id, currency, type, amount, category, date, description, payment_method, attachment_filename) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)',
                 (session['user_id'], session['currency_code'], request.form['type'], request.form['amount'], request.form['category'], request.form['date'], request.form.get('description'), request.form.get('payment_method'), file_url))
    conn.commit(); cursor.close(); conn.close()
    flash(f"{request.form['type'].capitalize()} added successfully!", 'success'); return redirect(url_for('dashboard'))

@app.route('/add_loan', methods=['POST'])
def add_loan():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute('INSERT INTO loans (user_id, currency, type, person, initial_amount, current_balance, date, account_details, bank_name, payment_method, description) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                 (session['user_id'], session['currency_code'], request.form['type'], request.form['person'], float(request.form['amount']), float(request.form['amount']), request.form['date'], request.form['account_details'], request.form['bank_name'], request.form['payment_method'], request.form.get('description')))
    conn.commit(); cursor.close(); conn.close()
    flash('Loan recorded successfully!', 'success'); return redirect(url_for('dashboard'))

@app.route('/record_repayment', methods=['POST'])
def record_repayment():
    if 'user_id' not in session: return redirect(url_for('login'))
    file_url = None
    if 'attachment' in request.files:
        file = request.files['attachment']
        if file and file.filename != '':
            try:
                upload_result = cloudinary.uploader.upload(file); file_url = upload_result.get('secure_url')
            except Exception as e: flash(f"Attachment upload failed: {e}", "error")
    loan_id, amount = request.form['loan_id'], float(request.form['amount'])
    conn = get_db_connection(); cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        cursor.execute('SELECT current_balance FROM loans WHERE id = %s AND user_id = %s', (loan_id, session['user_id']))
        loan = cursor.fetchone()
        if not loan: flash('Loan not found.', 'error'); return redirect(url_for('dashboard'))
        cursor.execute('INSERT INTO repayments (loan_id, currency, amount, date, description, attachment_filename) VALUES (%s, %s, %s, %s, %s, %s)',
                     (loan_id, session['currency_code'], amount, request.form['date'], request.form.get('description'), file_url))
        cursor.execute('UPDATE loans SET current_balance = %s WHERE id = %s', (loan['current_balance'] - amount, loan_id))
        conn.commit(); flash('Repayment recorded successfully!', 'success')
    except Exception as e:
        conn.rollback(); flash(f'An error occurred: {e}', 'error')
    finally:
        cursor.close(); conn.close()
    return redirect(url_for('dashboard'))

@app.route('/view/<record_type>')
def view_records(record_type):
    if 'user_id' not in session: return redirect(url_for('login'))
    user_id, currency = session['user_id'], session['currency_code']
    conn = get_db_connection(); cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    records, title, headers = [], "Unknown Records", []
    if record_type == 'income':
        title, headers = "Total Income Records", ['Date', 'Category', 'Amount', 'Description', 'Payment Method']
        cursor.execute("SELECT * FROM transactions WHERE user_id = %s AND currency = %s AND type = 'income' ORDER BY date DESC", (user_id, currency)); records = cursor.fetchall()
    elif record_type == 'expenses':
        title, headers = "Total Expense Records", ['Date', 'Category', 'Amount', 'Description', 'Payment Method']
        cursor.execute("SELECT * FROM transactions WHERE user_id = %s AND currency = %s AND type = 'expense' AND category != 'Money Sent Home' ORDER BY date DESC", (user_id, currency)); records = cursor.fetchall()
    elif record_type == 'sent_home':
        title, headers = "Money Sent Home Records", ['Date', 'Amount', 'Description', 'Payment Method']
        cursor.execute("SELECT * FROM transactions WHERE user_id = %s AND currency = %s AND category = 'Money Sent Home' ORDER BY date DESC", (user_id, currency)); records = cursor.fetchall()
    elif record_type == 'loans_taken':
        title, headers = "Loans Taken Records", ['Date', 'Person', 'Initial Amount', 'Current Balance', 'Bank Name', 'Description']
        cursor.execute("SELECT * FROM loans WHERE user_id = %s AND currency = %s AND type = 'taken' ORDER BY date DESC", (user_id, currency)); records = cursor.fetchall()
    elif record_type == 'loans_given':
        title, headers = "Loans Given Records", ['Date', 'Person', 'Initial Amount', 'Current Balance', 'Bank Name', 'Description']
        cursor.execute("SELECT * FROM loans WHERE user_id = %s AND currency = %s AND type = 'given' ORDER BY date DESC", (user_id, currency)); records = cursor.fetchall()
    cursor.close(); conn.close()
    return render_template('view_records.html', records=records, title=title, record_type=record_type, headers=headers)

@app.route('/download/<record_type>')
def download_records(record_type):
    if 'user_id' not in session: return redirect(url_for('login'))
    user_id, currency = session['user_id'], session['currency_code']
    conn = get_db_connection(); cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    filename = f"report_{record_type}.csv"
    if record_type == 'income':
        cursor.execute("SELECT date, category, amount, description, payment_method FROM transactions WHERE user_id = %s AND currency = %s AND type = 'income'", (user_id, currency))
    elif record_type == 'expenses':
        cursor.execute("SELECT date, category, amount, description, payment_method FROM transactions WHERE user_id = %s AND currency = %s AND type = 'expense' AND category != 'Money Sent Home'", (user_id, currency))
    elif record_type == 'sent_home':
        cursor.execute("SELECT date, amount, description, payment_method FROM transactions WHERE user_id = %s AND currency = %s AND category = 'Money Sent Home'", (user_id, currency))
    elif record_type == 'loans_taken':
        cursor.execute("SELECT date, person, initial_amount, current_balance, bank_name, description FROM loans WHERE user_id = %s AND currency = %s AND type = 'taken'", (user_id, currency))
    elif record_type == 'loans_given':
        cursor.execute("SELECT date, person, initial_amount, current_balance, bank_name, description FROM loans WHERE user_id = %s AND currency = %s AND type = 'given'", (user_id, currency))
    db_records = cursor.fetchall()
    records = [dict(row) for row in db_records]
    cursor.close(); conn.close()
    if not records: flash('No records to download.', 'warning'); return redirect(url_for('dashboard'))
    df = pd.DataFrame(records)
    return Response(df.to_csv(index=False), mimetype="text/csv", headers={"Content-disposition": f"attachment; filename={filename}"})

# --- Settings & Utilities ---

@app.route('/settings', methods=['GET'])
def settings():
    if 'user_id' not in session: return redirect(url_for('login'))
    return render_template('settings.html')

@app.route('/update_settings', methods=['POST'])
def update_settings():
    if 'user_id' not in session: return redirect(url_for('login'))
    app_title = request.form['app_title']
    conn = get_db_connection(); cursor = conn.cursor()
    if 'logo' in request.files:
        file = request.files['logo']
        if file and file.filename != '':
            try:
                upload_result = cloudinary.uploader.upload(file); logo_url = upload_result.get('secure_url')
                cursor.execute('UPDATE settings SET logo_filename = %s WHERE user_id = %s', (logo_url, session['user_id']))
            except Exception as e: flash(f"Logo upload failed: {e}", "error")
    cursor.execute('UPDATE settings SET app_title = %s WHERE user_id = %s', (app_title, session['user_id']))
    conn.commit(); cursor.close(); conn.close()
    flash('Settings updated successfully!', 'success'); return redirect(url_for('settings'))

@app.route('/update_currency', methods=['POST'])
def update_currency():
    if 'user_id' not in session: return redirect(url_for('login'))
    currency = request.form.get('currency')
    if currency in CURRENCIES:
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute('UPDATE settings SET currency = %s WHERE user_id = %s', (currency, session['user_id']))
        conn.commit(); cursor.close(); conn.close()
        session['currency_code'] = currency
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True)