import os
from itsdangerous import URLSafeTimedSerializer
import psycopg2
import psycopg2.extras # Important for dictionary-like database rows
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
# (These routes are correct and have no changes)
@app.route('/', methods=['GET', 'POST'])
def login(): # ...
    pass
@app.route('/register', methods=['GET', 'POST'])
def register(): # ...
    pass
@app.route('/logout')
def logout(): # ...
    pass
@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password(): # ...
    pass
@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token): # ...
    pass


# --- Core Application Routes ---
@app.route('/dashboard')
def dashboard():
    # (This route is correct and has no changes)
    # ...
    pass

# --- Data Entry Routes ---
# (These routes are correct and have no changes)
@app.route('/add_transaction', methods=['POST'])
def add_transaction(): # ...
    pass
@app.route('/add_loan', methods=['POST'])
def add_loan(): # ...
    pass
@app.route('/record_repayment', methods=['POST'])
def record_repayment(): # ...
    pass


# --- Viewing & Downloading (THIS SECTION IS NOW COMPLETE AND FIXED) ---
@app.route('/view/<record_type>')
def view_records(record_type):
    if 'user_id' not in session: return redirect(url_for('login'))
    
    user_id, currency = session['user_id'], session['currency_code']
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    records, title, headers = [], "Unknown Records", []
    
    if record_type == 'income':
        title, headers = "Total Income Records", ['Date', 'Category', 'Amount', 'Description', 'Payment Method']
        cursor.execute("SELECT * FROM transactions WHERE user_id = %s AND currency = %s AND type = 'income' ORDER BY date DESC", (user_id, currency))
        records = cursor.fetchall()
    elif record_type == 'expenses':
        title, headers = "Total Expense Records", ['Date', 'Category', 'Amount', 'Description', 'Payment Method']
        cursor.execute("SELECT * FROM transactions WHERE user_id = %s AND currency = %s AND type = 'expense' AND category != 'Money Sent Home' ORDER BY date DESC", (user_id, currency))
        records = cursor.fetchall()
    elif record_type == 'sent_home':
        title, headers = "Money Sent Home Records", ['Date', 'Amount', 'Description', 'Payment Method']
        cursor.execute("SELECT * FROM transactions WHERE user_id = %s AND currency = %s AND category = 'Money Sent Home' ORDER BY date DESC", (user_id, currency))
        records = cursor.fetchall()
    elif record_type == 'loans_taken':
        title, headers = "Loans Taken Records", ['Date', 'Person', 'Initial Amount', 'Current Balance', 'Bank Name', 'Description']
        cursor.execute("SELECT * FROM loans WHERE user_id = %s AND currency = %s AND type = 'taken' ORDER BY date DESC", (user_id, currency))
        records = cursor.fetchall()
    elif record_type == 'loans_given':
        title, headers = "Loans Given Records", ['Date', 'Person', 'Initial Amount', 'Current Balance', 'Bank Name', 'Description']
        cursor.execute("SELECT * FROM loans WHERE user_id = %s AND currency = %s AND type = 'given' ORDER BY date DESC", (user_id, currency))
        records = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template('view_records.html', records=records, title=title, record_type=record_type, headers=headers)

@app.route('/download/<record_type>')
def download_records(record_type):
    if 'user_id' not in session: return redirect(url_for('login'))
    
    user_id, currency = session['user_id'], session['currency_code']
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    records, filename = [], f"report_{record_type}.csv"
    
    # Logic to fetch the correct data for each type
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
    cursor.close()
    conn.close()

    if not records:
        flash('No records to download.', 'warning')
        return redirect(url_for('dashboard'))
    
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