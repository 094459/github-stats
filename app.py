from flask import Flask, render_template, request, jsonify, redirect, url_for
import sqlite3
import requests
import os
from datetime import datetime, timedelta
import json
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-key')

DATABASE = 'github_traffic.db'
DEBUG = os.environ.get('DEBUG', 'true').lower() == 'true'

def init_db():
    conn = sqlite3.connect(DATABASE)
    conn.execute('''CREATE TABLE IF NOT EXISTS repos (
        id INTEGER PRIMARY KEY,
        owner TEXT NOT NULL,
        name TEXT NOT NULL,
        UNIQUE(owner, name)
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS traffic (
        id INTEGER PRIMARY KEY,
        repo_id INTEGER,
        date TEXT,
        views INTEGER,
        unique_views INTEGER,
        clones INTEGER,
        unique_clones INTEGER,
        FOREIGN KEY(repo_id) REFERENCES repos(id),
        UNIQUE(repo_id, date)
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    conn.commit()
    conn.close()

def get_github_token():
    conn = sqlite3.connect(DATABASE)
    result = conn.execute('SELECT value FROM settings WHERE key = ?', ('github_token',)).fetchone()
    conn.close()
    return result[0] if result else None

def collect_traffic_data():
    token = get_github_token()
    if not token:
        if DEBUG:
            print("GitHub token not set. Please set it in the settings.")
        return
    
    conn = sqlite3.connect(DATABASE)
    repos = conn.execute('SELECT id, owner, name FROM repos').fetchall()
    
    headers = {'Authorization': f'token {token}'}
    today = datetime.now().strftime('%Y-%m-%d')
    
    for repo_id, owner, name in repos:
        # Get views
        views_url = f'https://api.github.com/repos/{owner}/{name}/traffic/views'
        if DEBUG:
            print(f"GitHub API Call: GET {views_url}")
        views_resp = requests.get(views_url, headers=headers)
        if DEBUG:
            print(f"Response: {views_resp.status_code}")
        
        # Get clones
        clones_url = f'https://api.github.com/repos/{owner}/{name}/traffic/clones'
        if DEBUG:
            print(f"GitHub API Call: GET {clones_url}")
        clones_resp = requests.get(clones_url, headers=headers)
        if DEBUG:
            print(f"Response: {clones_resp.status_code}")
        
        if views_resp.status_code == 200 and clones_resp.status_code == 200:
            views_data = views_resp.json()
            clones_data = clones_resp.json()
            
            # Store daily breakdown data
            views_daily = {v['timestamp'][:10]: v for v in views_data.get('views', [])}
            clones_daily = {c['timestamp'][:10]: c for c in clones_data.get('clones', [])}
            
            # Get all dates from both datasets
            all_dates = set(views_daily.keys()) | set(clones_daily.keys())
            
            for date in all_dates:
                views_entry = views_daily.get(date, {'count': 0, 'uniques': 0})
                clones_entry = clones_daily.get(date, {'count': 0, 'uniques': 0})
                
                conn.execute('''INSERT OR REPLACE INTO traffic 
                               (repo_id, date, views, unique_views, clones, unique_clones)
                               VALUES (?, ?, ?, ?, ?, ?)''',
                            (repo_id, date, views_entry['count'], views_entry['uniques'],
                             clones_entry['count'], clones_entry['uniques']))
    
    conn.commit()
    conn.close()

@app.route('/')
def dashboard():
    return render_template('dashboard.html')

@app.route('/settings')
def settings():
    return render_template('settings.html')

@app.route('/api/token', methods=['POST'])
def save_token():
    token = request.json.get('token')
    conn = sqlite3.connect(DATABASE)
    conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', 
                ('github_token', token))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/repos', methods=['GET', 'POST', 'DELETE'])
def manage_repos():
    conn = sqlite3.connect(DATABASE)
    
    if request.method == 'GET':
        repos = conn.execute('SELECT owner, name FROM repos').fetchall()
        conn.close()
        return jsonify([{'owner': r[0], 'name': r[1]} for r in repos])
    
    elif request.method == 'POST':
        data = request.json
        try:
            conn.execute('INSERT INTO repos (owner, name) VALUES (?, ?)',
                        (data['owner'], data['name']))
            conn.commit()
            conn.close()
            return jsonify({'success': True})
        except sqlite3.IntegrityError:
            conn.close()
            return jsonify({'error': 'Repository already exists'}), 400
    
    elif request.method == 'DELETE':
        data = request.json
        conn.execute('DELETE FROM repos WHERE owner = ? AND name = ?',
                    (data['owner'], data['name']))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

@app.route('/api/traffic/<period>')
def get_traffic(period):
    days = {'7d': 7, '30d': 30, '90d': 90}.get(period, 30)
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    conn = sqlite3.connect(DATABASE)
    data = conn.execute('''
        SELECT r.owner, r.name, t.date, t.views, t.unique_views, t.clones, t.unique_clones
        FROM traffic t
        JOIN repos r ON t.repo_id = r.id
        WHERE t.date >= ?
        ORDER BY t.date
    ''', (start_date,)).fetchall()
    conn.close()
    
    result = {}
    for row in data:
        repo_key = f"{row[0]}/{row[1]}"
        if repo_key not in result:
            result[repo_key] = []
        result[repo_key].append({
            'date': row[2],
            'views': row[3],
            'unique_views': row[4],
            'clones': row[5],
            'unique_clones': row[6]
        })
    
    return jsonify(result)

@app.route('/api/traffic/aggregate/<period>')
def get_aggregated_traffic(period):
    days = {'7d': 7, '30d': 30, '90d': 90}.get(period, 30)
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    conn = sqlite3.connect(DATABASE)
    data = conn.execute('''
        SELECT t.date, SUM(t.views) as total_views, SUM(t.clones) as total_clones
        FROM traffic t
        WHERE t.date >= ?
        GROUP BY t.date
        ORDER BY t.date
    ''', (start_date,)).fetchall()
    conn.close()
    
    result = [{
        'date': row[0],
        'views': row[1],
        'clones': row[2]
    } for row in data]
    
    return jsonify(result)

@app.route('/api/collect')
def manual_collect():
    collect_traffic_data()
    return jsonify({'success': True})

@app.route('/api/totals/<period>')
def get_totals(period):
    days = {'7d': 7, '30d': 30, '90d': 90}.get(period, 30)
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    conn = sqlite3.connect(DATABASE)
    result = conn.execute('SELECT SUM(views), SUM(clones) FROM traffic WHERE date >= ?', (start_date,)).fetchone()
    conn.close()
    return jsonify({'total_views': result[0] or 0, 'total_clones': result[1] or 0})

@app.route('/api/repos/data', methods=['DELETE'])
def delete_repo_data():
    data = request.json
    conn = sqlite3.connect(DATABASE)
    repo_id = conn.execute('SELECT id FROM repos WHERE owner = ? AND name = ?',
                          (data['owner'], data['name'])).fetchone()
    if repo_id:
        conn.execute('DELETE FROM traffic WHERE repo_id = ?', (repo_id[0],))
        conn.commit()
    conn.close()
    return jsonify({'success': True})

if __name__ == '__main__':
    init_db()
    
    scheduler = BackgroundScheduler()
    scheduler.add_job(collect_traffic_data, 'interval', hours=24)
    scheduler.start()
    
    app.run(host='127.0.0.1', port=5001, debug=True)