from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import PyPDF2, re, smtplib, sqlite3, os
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

app = Flask(__name__)
app.secret_key = "hire_master_key_2026"
model = SentenceTransformer('all-MiniLM-L6-v2')

# --- CONFIG ---
SENDER_EMAIL = "nathirvkp@gmail.com" 
SENDER_PASSWORD = "vnmgsjrpubpgqdrb" 

def get_db():
    conn = sqlite3.connect('portal.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT, email TEXT UNIQUE, role TEXT, password TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY, title TEXT, skills TEXT, company TEXT, hr_email TEXT)')
    conn.commit()
    conn.close()

init_db()

def extract_clean_text(file):
    try:
        pdf = PyPDF2.PdfReader(file)
        text = " ".join([p.extract_text() for p in pdf.pages if p.extract_text()])
        email_match = re.search(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,4}\b', text)
        clean = re.sub(r'[^a-zA-Z\s]', ' ', text).lower()
        return " ".join(clean.split()), (email_match.group(0).strip() if email_match else None)
    except: return "", None

def send_resume_to_hr(hr_email, seeker_name, job_title, resume_file):
    try:
        msg = MIMEMultipart()
        msg['Subject'] = f"H.I.R.E. MATCH: {job_title}"
        msg['From'], msg['To'] = SENDER_EMAIL, hr_email
        msg.attach(MIMEText(f"Hello HR,\n\nCandidate '{seeker_name}' matched for {job_title} with >40% accuracy via the H.I.R.E. Ecosystem.", 'plain'))
        resume_file.seek(0)
        part = MIMEApplication(resume_file.read(), Name=resume_file.filename)
        part['Content-Disposition'] = f'attachment; filename="{resume_file.filename}"'
        msg.attach(part)
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
            s.login(SENDER_EMAIL, SENDER_PASSWORD)
            s.sendmail(SENDER_EMAIL, hr_email, msg.as_string())
        return True
    except: return False

# --- NAVIGATION ROUTES ---
@app.route('/')
def home(): return render_template('front.html') # NEW FRONT PAGE

@app.route('/auth')
def auth(): return render_template('index.html') # LOGIN/REGISTER PAGE

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# --- AUTH ROUTES ---
@app.route('/login', methods=['POST'])
def login():
    d = request.json
    conn = get_db()
    u = conn.execute('SELECT * FROM users WHERE email = ? AND password = ?', (d['email'], d['pass'])).fetchone()
    conn.close()
    if u:
        session['user_id'], session['role'], session['name'], session['email'] = u['id'], u['role'], u['name'], u['email']
        return jsonify({"status": "ok", "role": u['role']})
    return jsonify({"status": "fail"})

@app.route('/register', methods=['POST'])
def register():
    d = request.json
    try:
        conn = get_db()
        conn.execute('INSERT INTO users (name, email, role, password) VALUES (?,?,?,?)', (d['name'], d['email'], d['role'], d['pass']))
        conn.commit(); conn.close()
        return jsonify({"status": "Success"})
    except: return jsonify({"status": "Fail"})

@app.route('/delete_account', methods=['POST'])
def delete_account():
    user_id = session.get('user_id')
    if not user_id: return jsonify({"status": "Unauthorized"})
    conn = get_db()
    conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
    if session.get('role') == 'HR':
        conn.execute('DELETE FROM jobs WHERE hr_email = ?', (session['email'],))
    conn.commit(); conn.close()
    session.clear()
    return jsonify({"status": "Account Deleted"})

# --- HR MANAGEMENT ROUTES ---
@app.route('/post_job', methods=['POST'])
def post_job():
    d = request.json
    conn = get_db()
    conn.execute('INSERT INTO jobs (title, skills, company, hr_email) VALUES (?,?,?,?)', (d['title'], d['skills'], d['company'], session['email']))
    conn.commit(); conn.close()
    return jsonify({"status": "Success"})

@app.route('/delete_job/<int:job_id>', methods=['POST'])
def delete_job(job_id):
    conn = get_db()
    conn.execute('DELETE FROM jobs WHERE id = ? AND hr_email = ?', (job_id, session['email']))
    conn.commit(); conn.close()
    return jsonify({"status": "Deleted"})

@app.route('/update_job/<int:job_id>', methods=['POST'])
def update_job(job_id):
    d = request.json
    conn = get_db()
    conn.execute('UPDATE jobs SET title=?, skills=?, company=? WHERE id=? AND hr_email=?', (d['title'], d['skills'], d['company'], job_id, session['email']))
    conn.commit(); conn.close()
    return jsonify({"status": "Updated"})

@app.route('/get_my_jobs')
def get_my_jobs():
    conn = get_db()
    j = conn.execute('SELECT * FROM jobs WHERE hr_email = ?', (session['email'],)).fetchall()
    conn.close()
    return jsonify([dict(row) for row in j])

@app.route('/get_public_jobs')
def get_public_jobs():
    conn = get_db()
    j = conn.execute('SELECT * FROM jobs').fetchall()
    conn.close()
    return jsonify([dict(row) for row in j])

# --- AI MATCHING & RANKING ROUTES ---
@app.route('/rank', methods=['POST'])
def rank():
    role, jd = request.form.get('role'), request.form.get('jd')
    files = request.files.getlist('resumes')
    resumes_data = []
    for f in files:
        t, _ = extract_clean_text(f)
        if t: resumes_data.append({"name": f.filename, "text": t})
    if not resumes_data: return jsonify([])
    
    emb = model.encode([re.sub(r'[^a-zA-Z\s]', ' ', jd).lower()] + [r['text'] for r in resumes_data])
    scores = cosine_similarity([emb[0]], emb[1:])[0]
    
    results = [{"name": resumes_data[i]['name'], "score": float(scores[i])} for i in range(len(resumes_data))]
    sorted_res = sorted(results, key=lambda x: x['score'], reverse=True)
    
    out = []
    for i, r in enumerate(sorted_res):
        m = round(r['score']*100, 2)
        out.append({"rank": i+1, "name": r['name'], "score": f"{m}%", "status": "Shortlisted" if m > 40 else "Rejected"})
    return jsonify(out)

@app.route('/recommend', methods=['POST'])
def recommend():
    name = session.get('name')
    file = request.files.get('resume')
    txt, _ = extract_clean_text(file)
    conn = get_db()
    jobs = conn.execute('SELECT * FROM jobs').fetchall()
    conn.close()
    if not jobs: return jsonify([])
    
    job_skills = [j['skills'] for j in jobs]
    emb = model.encode([txt] + job_skills)
    scores = cosine_similarity([emb[0]], emb[1:])[0]
    res = []
    for i, s in enumerate(scores):
        val = round(s*100, 2)
        if val > 40: send_resume_to_hr(jobs[i]['hr_email'], name, jobs[i]['title'], file)
        res.append({"title": jobs[i]['title'], "company": jobs[i]['company'], "score": f"{val}%"})
    return jsonify(sorted(res, key=lambda x: float(x['score'].strip('%')), reverse=True))

@app.route('/recruiter_page')
def recruiter_page(): return render_template('recruiter.html')

@app.route('/seeker_page')
def seeker_page(): return render_template('seeker.html')

if __name__ == '__main__':
    app.run(debug=True, port=5000)