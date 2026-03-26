import os
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
import io
import base64
import qrcode
import requests
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from authlib.integrations.flask_client import OAuth

app = Flask(__name__)
app.config['SECRET_KEY'] = 'raja_buddy_ai_master_key'

# --- 1. DATABASE SETUP (PostgreSQL / SQLite Fallback) ---
uri = os.getenv("DATABASE_URL")
if uri and uri.startswith("postgres://"):
    uri = uri.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = uri or 'sqlite:///buddy_master.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- 2. GITHUB OAUTH SETUP ---
oauth = OAuth(app)
github = oauth.register(
    name='github',
    client_id='Ov23lirf0qiWHScOLZ44',
    client_secret=os.getenv('GITHUB_CLIENT_SECRET'),
    access_token_url='https://github.com/login/oauth/access_token',
    authorize_url='https://github.com/login/oauth/authorize',
    api_base_url='https://api.github.com/',
    client_kwargs={'scope': 'user:email'},
)

# --- 3. API KEY (Groq) ---
GROQ_API_KEY = "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"

# --- 4. DATABASE MODELS ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    contact = db.Column(db.String(120), nullable=True) # Email/Mobile
    age = db.Column(db.Integer, default=22)
    year = db.Column(db.String(20), default="2026")
    gender = db.Column(db.String(20), default="None")
    is_pro = db.Column(db.Boolean, default=False)
    expiry_date = db.Column(db.DateTime, nullable=True)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    role = db.Column(db.String(10)) # 'user' or 'bot'
    content = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- 5. AUTHENTICATION ROUTES ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if not user:
            # User illana direct-ah signup-ku poga sollu
            return "User doesn't exist! Redirecting to Signup... <script>setTimeout(function(){ window.location.href='/signup'; }, 2000);</script>"
            
        if user.password == password:
            login_user(user)
            return redirect(url_for('index'))
        else:
            return "Wrong password macha! Try again."
            
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        contact = request.form.get('contact')
        if User.query.filter_by(username=username).first():
            return "User already exists! Please login."
        new_user = User(username=username, password=password, contact=contact)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- 6. GITHUB OAUTH ROUTES ---
@app.route('/login/github')
def github_login():
    return github.authorize_redirect(url_for('github_authorize', _external=True))

@app.route('/auth/github/callback')
def github_authorize():
    token = github.authorize_access_token()
    resp = github.get('user')
    user_info = resp.json()
    user = User.query.filter_by(username=user_info['login']).first()
    if not user:
        user = User(username=user_info['login'], password='oauth_password_secure', contact=user_info.get('email', 'github_user'))
        db.session.add(user)
        db.session.commit()
    login_user(user)
    return redirect(url_for('index'))

# --- 7. MAIN APP ROUTES ---
@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
@login_required
def chat():
    user_msg = request.json.get("message")
    if not user_msg: return jsonify({"reply": "Message empty da macha."})
    db.session.add(Message(user_id=current_user.id, role='user', content=user_msg))
    db.session.commit()

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": "You are Buddy AI, Raja's best friend. Speak in Tanglish slang. You can use Emojis. Be witty and helpful."},
            {"role": "user", "content": user_msg}
        ],
        "temperature": 0.7
    }
    try:
        response = requests.post(url, headers=headers, json=payload)
        bot_reply = response.json()['choices'][0]['message']['content'].strip()
    except:
        bot_reply = "Macha, server konjam busy ah irukku! 🥲"

    db.session.add(Message(user_id=current_user.id, role='bot', content=bot_reply))
    db.session.commit()
    return jsonify({"reply": bot_reply})

@app.route('/get_history')
@login_required
def get_history():
    messages = Message.query.filter_by(user_id=current_user.id).order_by(Message.timestamp.asc()).all()
    return jsonify([{"role": m.role, "content": m.content} for m in messages])

# --- 8. PROFILE & PAYMENT ---
@app.route('/update_profile', methods=['POST'])
@login_required
def update_profile():
    new_username = request.form.get('username')
    if new_username and new_username != current_user.username:
        if not User.query.filter_by(username=new_username).first():
            current_user.username = new_username
    current_user.contact = request.form.get('email', current_user.contact)
    current_user.age = request.form.get('age', current_user.age)
    current_user.year = request.form.get('year', current_user.year)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/get_payment_qr/<plan>')
@login_required
def get_payment_qr(plan):
    upi_id = "rajug11bank@okaxis" 
    amounts = {'1week': '19', '1month': '49', '1year': '99'} 
    amt = amounts.get(plan, '19')
    upi_url = f"upi://pay?pa={upi_id}&pn=Raja&am={amt}&cu=INR"
    qr = qrcode.make(upi_url)
    buf = io.BytesIO()
    qr.save(buf)
    return jsonify({"qr_code": base64.b64encode(buf.getvalue()).decode('utf-8'), "amount": amt})

@app.route('/confirm_payment', methods=['POST'])
@login_required
def confirm_payment():
    current_user.is_pro = True
    db.session.commit()
    return jsonify({"status": "success", "message": "PRO Activated! ✨"})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000, host='127.0.0.1')
    # ... (matha code ellam mela irukkum)

# Idhu dhaan un database tables-ah automatic-ah create pannum
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)