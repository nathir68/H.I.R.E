from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import PyPDF2, re, smtplib, sqlite3, os, imaplib, email, json, pickle, threading, io
from email.header import decode_header
from datetime import datetime
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from collections import Counter

# --- TENSORFLOW IMPORTS ---
import tensorflow as tf
import numpy as np
from tensorflow.keras.preprocessing.sequence import pad_sequences

app = Flask(__name__)
app.secret_key = "hire_master_key_2026"

# 1. Load Sentence Transformer (For Job Matching)
model = SentenceTransformer('all-MiniLM-L6-v2')

# 2. Load Custom TensorFlow Model (For Role Prediction)
try:
    # compile=False prevents the watchdog crash!
    tf_model = tf.keras.models.load_model('resume_classifier.h5', compile=False)
    with open('tokenizer.pickle', 'rb') as handle:
        tf_tokenizer = pickle.load(handle)
    print("✅ Custom TensorFlow Brain Loaded!")
except Exception as e:
    print("⚠️ TF Model not found. Run train_tf_model.py first.")
    tf_model, tf_tokenizer = None, None

role_names = {0: "AI/ML Specialist", 1: "Database/Backend Admin", 2: "Web Developer"}

# --- CONFIG ---
SENDER_EMAIL = "nathirvkp@gmail.com" 
SENDER_PASSWORD = "vnmgsjrpubpgqdrb" 
LOG_FILE = "system_logs.json"

def get_db():
    conn = sqlite3.connect('portal.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT, email TEXT UNIQUE, role TEXT, password TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY, title TEXT, skills TEXT, company TEXT, hr_email TEXT)')
    conn.commit(); conn.close()

def clean_ghost_jobs():
    conn = get_db()
    conn.execute('DELETE FROM jobs WHERE hr_email NOT IN (SELECT email FROM users WHERE role = "HR")')
    conn.commit(); conn.close()

init_db()
clean_ghost_jobs()

def log_activity(user_email, role, action, details=""):
    entry = {"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "email": user_email, "role": role, "action": action, "details": details}
    try:
        with open(LOG_FILE, 'r') as f: logs = json.load(f)
    except: logs = []
    logs.append(entry)
    with open(LOG_FILE, 'w') as f: json.dump(logs, f, indent=4)

def extract_clean_text(file_stream):
    try:
        pdf = PyPDF2.PdfReader(file_stream)
        text = " ".join([p.extract_text() for p in pdf.pages if p.extract_text()])
        email_match = re.search(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,4}\b', text)
        clean = re.sub(r'[^a-zA-Z\s]', ' ', text).lower()
        return " ".join(clean.split()), (email_match.group(0).strip() if email_match else None)
    except: return "", None

def detect_fake_resume(text):
    flags = []
    words = text.lower().split()
    if len(words) > 2000: flags.append("Suspicious Length")
    for p in ["lorem ipsum", "enter your name", "objective goes here"]:
        if p in text.lower(): flags.append("Template Placeholders")
    counts = Counter([w for w in words if len(w) > 3])
    if counts and counts.most_common(1)[0][1] > 40: flags.append(f"Spam ('{counts.most_common(1)[0][0]}')")
    return (True, " | ".join(flags)) if flags else (False, "Authentic")

def predict_job_role(text):
    if not tf_model or not tf_tokenizer: return "Unknown Role"
    seq = tf_tokenizer.texts_to_sequences([text])
    pad_seq = pad_sequences(seq, maxlen=30, padding='post')
    prediction = tf_model.predict(pad_seq)
    class_index = np.argmax(prediction[0])
    return role_names.get(class_index, "Unknown Role")

def send_mail(to_email, subject, body, attachment=None, filename="resume.pdf"):
    try:
        msg = MIMEMultipart()
        msg['Subject'], msg['From'], msg['To'] = subject, SENDER_EMAIL, to_email
        msg.attach(MIMEText(body, 'plain'))
        if attachment:
            attachment.seek(0)
            part = MIMEApplication(attachment.read(), Name=filename)
            part['Content-Disposition'] = f'attachment; filename="{filename}"'
            msg.attach(part)
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
            s.login(SENDER_EMAIL, SENDER_PASSWORD)
            s.sendmail(SENDER_EMAIL, to_email, msg.as_string())
        return True
    except Exception as e: print(e); return False

# --- BACKGROUND THREAD WORKER ---
def send_mail_async(to_email, subject, body, attachment_data, filename):
    attachment_stream = io.BytesIO(attachment_data)
    send_mail(to_email, subject, body, attachment_stream, filename)

@app.route('/')
def home(): return render_template('front.html')

@app.route('/auth')
def auth(): return render_template('index.html')

@app.route('/logout')
def logout():
    if 'email' in session: 
        actual_role = "ADMIN" if session['email'] == SENDER_EMAIL else session['role']
        log_activity(session['email'], actual_role, "Logout")
    session.clear()
    return redirect(url_for('home'))

@app.route('/login', methods=['POST'])
def login():
    d = request.json
    conn = get_db()
    u = conn.execute('SELECT * FROM users WHERE email = ? AND password = ?', (d['email'], d['pass'])).fetchone()
    conn.close()
    if u:
        actual_role = "ADMIN" if u['email'] == SENDER_EMAIL else u['role']
        session['user_id'], session['role'], session['name'], session['email'] = u['id'], actual_role, u['name'], u['email']
        log_activity(u['email'], actual_role, "Login Successful")
        return jsonify({"status": "ok", "role": actual_role})
    return jsonify({"status": "fail"})

@app.route('/register', methods=['POST'])
def register():
    d = request.json
    try:
        actual_role = "ADMIN" if d['email'] == SENDER_EMAIL else d['role']
        conn = get_db()
        conn.execute('INSERT INTO users (name, email, role, password) VALUES (?,?,?,?)', (d['name'], d['email'], actual_role, d['pass']))
        conn.commit(); conn.close()
        log_activity(d['email'], actual_role, "Account Created")
        return jsonify({"status": "Success"})
    except: return jsonify({"status": "Fail"})

@app.route('/post_job', methods=['POST'])
def post_job():
    d = request.json
    conn = get_db()
    conn.execute('INSERT INTO jobs (title, skills, company, hr_email) VALUES (?,?,?,?)', (d['title'], d['skills'], d['company'], session['email']))
    conn.commit(); conn.close()
    log_activity(session['email'], "HR", "Posted Job", d['title'])
    return jsonify({"status": "Success"})

@app.route('/delete_job/<int:job_id>', methods=['POST'])
def delete_job(job_id):
    conn = get_db()
    conn.execute('DELETE FROM jobs WHERE id = ? AND hr_email = ?', (job_id, session['email']))
    conn.commit(); conn.close()
    log_activity(session['email'], "HR", "Deleted Job", f"ID: {job_id}")
    return jsonify({"status": "Deleted"})

@app.route('/get_my_jobs')
def get_my_jobs():
    conn = get_db()
    j = conn.execute('SELECT * FROM jobs WHERE hr_email = ?', (session['email'],)).fetchall()
    conn.close()
    return jsonify([dict(row) for row in j])

@app.route('/get_public_jobs')
def get_public_jobs():
    conn = get_db()
    j = conn.execute('SELECT * FROM jobs WHERE hr_email IN (SELECT email FROM users WHERE role = "HR")').fetchall()
    conn.close()
    return jsonify([dict(row) for row in j])

@app.route('/contact_hr', methods=['POST'])
def contact_hr():
    d = request.json
    body = f"Message from Seeker ({session['email']}):\n\n{d['message']}"
    send_mail(d['hr_email'], f"Inquiry for Job: {d['job_title']}", body)
    log_activity(session['email'], "Seeker", "Contacted HR", d['hr_email'])
    return jsonify({"status": "Sent"})

# --- HR AI SCREENING (FIXED BUGS & NEW COMPANY EMAIL FEATURE) ---
@app.route('/rank', methods=['POST'])
def rank():
    role, jd = request.form.get('role'), request.form.get('jd')
    files = request.files.getlist('resumes')
    
    # Fetch the Company Name from the Database
    conn = get_db()
    job_info = conn.execute('SELECT company FROM jobs WHERE hr_email = ? AND title = ?', (session['email'], role)).fetchone()
    conn.close()
    
    company_name = job_info['company'] if job_info else "our organization"
    
    resumes_data = []
    for f in files:
        t, s_email = extract_clean_text(f)
        if t: resumes_data.append({"name": f.filename, "text": t, "email": s_email})
        
    if not resumes_data: return jsonify([])
    
    emb = model.encode([re.sub(r'[^a-zA-Z\s]', ' ', jd).lower()] + [r['text'] for r in resumes_data])
    scores = cosine_similarity([emb[0]], emb[1:])[0]
    
    out = []
    for i in range(len(resumes_data)):
        m, r = round(float(scores[i])*100, 2), resumes_data[i]
        is_fake, reason = detect_fake_resume(r['text'])
        
        if is_fake: status, score_disp = f"🚩 Fake: {reason}", "N/A"
        elif m > 40:
            status, score_disp = "Shortlisted ✅", f"{m}%"
            
            # --- UPDATED: Perfect HR Professional Phrasing ---
            if r['email']: 
                subject = f"Interview Shortlist: {role} at {company_name}"
                body = (f"Hello,\n\n"
                        f"Congratulations! Your resume has been successfully screened by our AI Engine.\n\n"
                        f"You have been officially shortlisted for the interview for the '{role}' position at {company_name}.\n"
                        f"🎯 AI Match Score: {m}%\n\n"
                        f"The HR team ({session['email']}) will contact you shortly to schedule your interview.\n\n"
                        f"Best regards,\nH.I.R.E. Automated Recruitment System")
                
                # Send email in the background instantly
                threading.Thread(target=send_mail, args=(r['email'], subject, body)).start()
                
        else: status, score_disp = "Rejected", f"{m}%"
            
        out.append({"name": r['name'], "score": score_disp, "status": status})
    
    log_activity(session['email'], "HR", "Ran AI Screening", f"Processed {len(resumes_data)} resumes")
    return jsonify(sorted(out, key=lambda x: str(x['score']), reverse=True))

@app.route('/sync_inbox')
def sync_inbox():
    if session.get('email') != SENDER_EMAIL: return jsonify({"status": "Unauthorized"})
    try:
        mail = imaplib.IMAP4_SSL('imap.gmail.com')
        mail.login(SENDER_EMAIL, SENDER_PASSWORD)
        mail.select('inbox')
        status, messages = mail.search(None, '(UNSEEN)')
        processed = 0
        
        conn = get_db()
        jobs = {str(j['id']): dict(j) for j in conn.execute('SELECT * FROM jobs').fetchall()}
        conn.close()

        for num in messages[0].split():
            _, data = mail.fetch(num, '(RFC822)')
            msg = email.message_from_bytes(data[0][1])
            subj = decode_header(msg['Subject'])[0][0]
            if isinstance(subj, bytes): subj = subj.decode()
            
            match = re.search(r'JOB-(\d+)', str(subj).upper())
            if not match: continue
            job_id = match.group(1)
            if job_id not in jobs: continue
            
            target_job = jobs[job_id]
            
            for part in msg.walk():
                if part.get_filename() and part.get_filename().endswith('.pdf'):
                    import io
                    pdf_bytes = part.get_payload(decode=True)
                    text, s_email = extract_clean_text(io.BytesIO(pdf_bytes))
                    
                    if not text: continue
                    is_fake, _ = detect_fake_resume(text)
                    if is_fake: continue 
                    
                    emb = model.encode([target_job['skills'], text])
                    score = round(float(cosine_similarity([emb[0]], emb[1:])[0][0])*100, 2)
                    
                    if score > 40:
                        send_mail(target_job['hr_email'], f"H.I.R.E Auto-Match: {target_job['title']}", f"AI auto-routed a resume from email. Score: {score}%", io.BytesIO(pdf_bytes), part.get_filename())
                        processed += 1
        mail.close(); mail.logout()
        log_activity(SENDER_EMAIL, "ADMIN", "Inbox Synced", f"Auto-routed {processed} resumes")
        return jsonify({"status": f"Successfully processed and routed {processed} new email resumes!"})
    except Exception as e: return jsonify({"status": f"Error: {str(e)}"})

@app.route('/recommend', methods=['POST'])
def recommend():
    name = session.get('name')
    file = request.files.get('resume')
    
    # Read file instantly for background threads
    file_bytes = file.read()
    file_stream = io.BytesIO(file_bytes)
    
    txt, _ = extract_clean_text(file_stream)
    tf_prediction = predict_job_role(txt)
    
    conn = get_db()
    jobs = conn.execute('SELECT * FROM jobs WHERE hr_email IN (SELECT email FROM users WHERE role = "HR")').fetchall()
    conn.close()
    if not jobs: return jsonify({"predicted_role": tf_prediction, "matches": []})
    
    job_skills = [j['skills'] for j in jobs]
    emb = model.encode([txt] + job_skills)
    scores = cosine_similarity([emb[0]], emb[1:])[0]
    res = []
    
    for i, s in enumerate(scores):
        val = round(s*100, 2)
        if val > 40: 
            subject = f"H.I.R.E. AI Auto-Screened: {jobs[i]['title']}"
            body = (f"Hello HR,\n\n"
                    f"The H.I.R.E. AI Ecosystem has automatically screened and routed a top candidate to you!\n\n"
                    f"👤 Candidate Name: {name}\n"
                    f"🎯 Skill Match Score: {val}%\n"
                    f"🧠 Neural Net Classification: {tf_prediction}\n\n"
                    f"Please find the analyzed resume attached for your review.")
            
            # Fire and forget! Send email in the background.
            threading.Thread(
                target=send_mail_async, 
                args=(jobs[i]['hr_email'], subject, body, file_bytes, file.filename)
            ).start()
            
        res.append({"title": jobs[i]['title'], "company": jobs[i]['company'], "score": f"{val}%"})
        
    sorted_matches = sorted(res, key=lambda x: float(x['score'].strip('%')), reverse=True)
    return jsonify({"predicted_role": tf_prediction, "matches": sorted_matches})

@app.route('/delete_account', methods=['POST'])
def delete_account():
    user_id = session.get('user_id')
    hr_email = session.get('email')
    if not user_id: return jsonify({"status": "Unauthorized"})
    
    conn = get_db()
    if session.get('role') == 'HR':
        conn.execute('DELETE FROM jobs WHERE hr_email = ?', (hr_email,))
        
    conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit(); conn.close()
    session.clear()
    return jsonify({"status": "Account Deleted"})

@app.route('/admin_page')
def admin_page(): return render_template('admin.html')

@app.route('/api/god_view')
def api_god_view():
    conn = get_db()
    u = conn.execute('SELECT id, name, email, role FROM users').fetchall()
    j = conn.execute('SELECT * FROM jobs').fetchall()
    conn.close()
    try:
        with open(LOG_FILE, 'r') as f: l = json.load(f)
    except: l = []
    return jsonify({"users": [dict(x) for x in u], "jobs": [dict(x) for x in j], "logs": l[::-1]}) 

@app.route('/recruiter_page')
def recruiter_page(): return render_template('recruiter.html')

@app.route('/seeker_page')
def seeker_page(): return render_template('seeker.html')

if __name__ == '__main__':
    app.run(debug=False, port=5000)