from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import PyPDF2, re, smtplib, sqlite3, os, imaplib, email, json, threading, io, time
from email.header import decode_header
from datetime import datetime
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from collections import Counter
import google.generativeai as genai

app = Flask(__name__)
app.secret_key = "hire_master_key_2026"

# --- 🤖 AGENTIC AI WORKFLOW SETUP (CLOUD API) ---
GENAI_API_KEY = "AIzaSyD-2R1p1nVZttghf-eWg-nQY5ehTHUVsUE"
genai.configure(api_key=GENAI_API_KEY)

class HireAIAgent:
    def __init__(self):
        self.model = genai.GenerativeModel('gemini-1.5-flash')

    def predict_role(self, resume_text):
        try:
            prompt = f"Analyze this resume snippet and determine the primary job role. Reply strictly with just the job title in 1 to 4 words maximum.\n\nResume Snippet: {resume_text[:1500]}"
            response = self.model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            return "Professional"

    def process_candidate(self, role, required_skills, resume_text, score, is_selected):
        try:
            analysis_prompt = f"Analyze this candidate for '{role}'. Required Skills: {required_skills}. Resume: {resume_text[:1500]}. Match Score: {score}%. Identify 1 good skill they have, and 1 missing skill. Keep it to 2 short sentences."
            analysis_notes = self.model.generate_content(analysis_prompt).text

            if is_selected:
                email_prompt = f"Write a warm 3-line email to a candidate SHORTLISTED for '{role}'. Incorporate these insights: {analysis_notes}. Tell them HR will contact them soon. No placeholders."
            else:
                email_prompt = f"Write a polite, constructive 3-line rejection email for '{role}'. Tell them WHY they were not selected using these insights: {analysis_notes}. Encourage upskilling. No placeholders."
            
            return self.model.generate_content(email_prompt).text.strip()
        except Exception as e:
            if is_selected:
                return f"Hello,\n\nYour resume matched {score}% for the '{role}' role. You are officially shortlisted and HR will contact you shortly.\n\nBest regards,\nH.I.R.E. AI"
            else:
                return f"Hello,\n\nYour match score ({score}%) for '{role}' didn't meet the threshold this time. Keep learning and try again!\n\nBest regards,\nH.I.R.E. AI"

ai_agent = HireAIAgent()
model = SentenceTransformer('all-MiniLM-L6-v2')

# --- CONFIG ---
SENDER_EMAIL = "nathirvkp@gmail.com" 
SENDER_PASSWORD = "vnmgsjrpubpgqdrb" 
LOG_FILE = "system_logs.json"
IMAP_LOG_FILE = "imap_history.json" 

def get_db():
    conn = sqlite3.connect('portal.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT, email TEXT UNIQUE, role TEXT, password TEXT, company TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY, title TEXT, skills TEXT, company TEXT, hr_email TEXT)')
    conn.commit(); conn.close()

init_db()

def log_activity(user_email, role, action, details=""):
    entry = {"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "email": user_email, "role": role, "action": action, "details": details}
    try:
        with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f: logs = json.load(f)
    except: logs = []
    logs.append(entry)
    with open(LOG_FILE, 'w', encoding='utf-8') as f: json.dump(logs, f, indent=4)

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

def send_mail(to_email, subject, body, attachment=None, filename="resume.pdf"):
    try:
        msg = MIMEMultipart()
        msg['Subject'], msg['From'], msg['To'] = subject, SENDER_EMAIL, to_email
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        if attachment:
            attachment.seek(0)
            part = MIMEApplication(attachment.read(), Name=filename)
            part['Content-Disposition'] = f'attachment; filename="{filename}"'
            msg.attach(part)
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
            s.login(SENDER_EMAIL, SENDER_PASSWORD)
            s.sendmail(SENDER_EMAIL, to_email, msg.as_string())
        return True
    except Exception as e: print(f"Email Error: {e}"); return False

def send_mail_async(to_email, subject, body, attachment_data, filename):
    attachment_stream = io.BytesIO(attachment_data)
    send_mail(to_email, subject, body, attachment_stream, filename)

# --- 🚀 ADVANCED IMAP AUTOMATION CORE ---
def run_imap_core():
    try:
        mail = imaplib.IMAP4_SSL('imap.gmail.com')
        mail.login(SENDER_EMAIL, SENDER_PASSWORD)
        mail.select('inbox')
        status, messages = mail.search(None, '(UNSEEN)')
        if not messages[0]: return []
        
        processed_list = []
        conn = get_db()
        jobs = {str(j['id']): dict(j) for j in conn.execute('SELECT * FROM jobs').fetchall()}
        conn.close()

        for num in messages[0].split():
            _, data = mail.fetch(num, '(RFC822)')
            msg = email.message_from_bytes(data[0][1])
            
            subj_data, encoding = decode_header(msg['Subject'])[0]
            if isinstance(subj_data, bytes):
                subj = subj_data.decode(encoding if encoding else 'utf-8', errors='ignore')
            else:
                subj = str(subj_data)
            
            match = re.search(r'JOB\s*-\s*(\d+)', subj.upper())
            if not match: continue
            job_id = match.group(1)
            if job_id not in jobs: continue
            
            target_job = jobs[job_id]
            
            for part in msg.walk():
                if part.get_filename() and part.get_filename().endswith('.pdf'):
                    pdf_bytes = part.get_payload(decode=True)
                    text, s_email = extract_clean_text(io.BytesIO(pdf_bytes))
                    
                    if not text: continue
                    is_fake, _ = detect_fake_resume(text)
                    if is_fake: continue 
                    
                    print(f"\n--- 🧠 ZERO-TOUCH AI VERIFICATION FOR: {s_email} ---")
                    
                    emb = model.encode([target_job['skills'], text])
                    score = round(float(cosine_similarity([emb[0]], emb[1:])[0][0])*100, 2)
                    
                    print(f"✅ Final Match Score: {score}%\n----------------------------------")
                    
                    if s_email:
                        is_selected = score > 40
                        if is_selected:
                            send_mail(target_job['hr_email'], f"H.I.R.E Auto-Match: {target_job['title']}", f"AI auto-routed a resume from email. Score: {score}%", io.BytesIO(pdf_bytes), part.get_filename())
                            processed_list.append({
                                "email": s_email,
                                "job": target_job['title'],
                                "score": f"{score}%",
                                "timestamp": datetime.now().strftime("%I:%M %p")
                            })
                            
                        cand_subj = f"Application Update: {target_job['title']}"
                        cand_body = ai_agent.process_candidate(target_job['title'], target_job['skills'], text, score, is_selected)
                        threading.Thread(target=send_mail, args=(s_email, cand_subj, cand_body)).start()

        mail.close(); mail.logout()
        
        if processed_list:
            try:
                with open(IMAP_LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f: history = json.load(f)
            except: history = []
            history.extend(processed_list)
            with open(IMAP_LOG_FILE, 'w', encoding='utf-8') as f: json.dump(history, f, indent=4)
            log_activity(SENDER_EMAIL, "ADMIN", "Zero-Touch Sync", f"Routed {len(processed_list)} resumes automatically")
        
        return processed_list
    except Exception as e:
        print(f"IMAP Error: {e}")
        return []

# --- 🤖 THE NEVER-SLEEPING BACKGROUND THREAD ---
def auto_imap_worker():
    print("🚀 BACKGROUND ENGINE: Zero-Touch IMAP Automation Started! (Checking every 10s)")
    while True:
        try: 
            processed = run_imap_core()
            if processed:
                print(f"📥 BACKGROUND ENGINE: Successfully processed {len(processed)} new resumes!")
        except Exception as e: 
            print(f"⚠️ BACKGROUND ENGINE ERROR: {e}")
        time.sleep(10) # Checks exactly every 10 seconds

# Boot the thread immediately
threading.Thread(target=auto_imap_worker, daemon=True).start()

@app.route('/sync_inbox')
def sync_inbox():
    if session.get('email') != SENDER_EMAIL: return jsonify({"status": "Unauthorized"})
    new_resumes = run_imap_core()
    if new_resumes: return jsonify({"status": f"Successfully processed {len(new_resumes)} new resumes!"})
    return jsonify({"status": "Inbox checked. No new matching resumes found at this moment."})

@app.route('/get_imap_history')
def get_imap_history():
    try:
        with open(IMAP_LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f: history = json.load(f)
        return jsonify(history[::-1]) 
    except: return jsonify([])

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
        company_name = d.get('company', 'N/A') 
        conn = get_db()
        conn.execute('INSERT INTO users (name, email, role, password, company) VALUES (?,?,?,?,?)', 
                     (d['name'], d['email'], actual_role, d['pass'], company_name))
        conn.commit(); conn.close()
        log_activity(d['email'], actual_role, "Account Created")
        return jsonify({"status": "Success"})
    except: return jsonify({"status": "Fail"})

@app.route('/post_job', methods=['POST'])
def post_job():
    d = request.json
    conn = get_db()
    hr_info = conn.execute('SELECT company FROM users WHERE email = ?', (session['email'],)).fetchone()
    company_name = hr_info['company'] if hr_info else d['company']
    conn.execute('INSERT INTO jobs (title, skills, company, hr_email) VALUES (?,?,?,?)', (d['title'], d['skills'], company_name, session['email']))
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
    # 🚀 We fetch the ID so the Seeker UI can show "JOB-X"
    j = conn.execute('SELECT id, title, skills, company FROM jobs WHERE hr_email IN (SELECT email FROM users WHERE role = "HR")').fetchall()
    conn.close()
    return jsonify([dict(row) for row in j])

@app.route('/rank', methods=['POST'])
def rank():
    role, jd = request.form.get('role'), request.form.get('jd')
    files = request.files.getlist('resumes')
    conn = get_db()
    hr_info = conn.execute('SELECT company FROM users WHERE email = ?', (session['email'],)).fetchone()
    conn.close()
    company_name = hr_info['company'] if (hr_info and hr_info['company'] != 'N/A') else "our organization"
    
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
        else:
            is_selected = m > 40
            status = "Shortlisted ✅" if is_selected else "Rejected"
            score_disp = f"{m}%"
            if r['email']: 
                subject = f"Interview Status: {role} at {company_name}"
                body = ai_agent.process_candidate(role, jd, r['text'], m, is_selected)
                threading.Thread(target=send_mail, args=(r['email'], subject, body)).start()
        out.append({"name": r['name'], "score": score_disp, "status": status})
    
    log_activity(session['email'], "HR", "Ran AI Screening", f"Processed {len(resumes_data)} resumes")
    return jsonify(sorted(out, key=lambda x: str(x['score']), reverse=True))

@app.route('/recommend', methods=['POST'])
def recommend():
    name = session.get('name')
    file = request.files.get('resume')
    file_bytes = file.read()
    txt, _ = extract_clean_text(io.BytesIO(file_bytes))
    
    ai_prediction = ai_agent.predict_role(txt)
    conn = get_db()
    jobs = conn.execute('SELECT * FROM jobs WHERE hr_email IN (SELECT email FROM users WHERE role = "HR")').fetchall()
    conn.close()
    
    if not jobs: return jsonify({"predicted_role": ai_prediction, "matches": []})
    
    job_skills = [j['skills'] for j in jobs]
    emb = model.encode([txt] + job_skills)
    scores = cosine_similarity([emb[0]], emb[1:])[0]
    res = []
    
    for i, s in enumerate(scores):
        val = round(s*100, 2)
        if val > 40: 
            subject = f"H.I.R.E. AI Auto-Screened: {jobs[i]['title']}"
            body = f"Hello HR,\n\nThe H.I.R.E. AI Ecosystem has routed a top candidate!\n👤 Candidate: {name}\n🎯 Match: {val}%\n🧠 AI Classification: {ai_prediction}\n\nReview the attached resume."
            threading.Thread(target=send_mail_async, args=(jobs[i]['hr_email'], subject, body, file_bytes, file.filename)).start()
        res.append({"title": jobs[i]['title'], "company": jobs[i]['company'], "score": f"{val}%"})
        
    return jsonify({"predicted_role": ai_prediction, "matches": sorted(res, key=lambda x: float(x['score'].strip('%')), reverse=True)})

@app.route('/delete_account', methods=['POST'])
def delete_account():
    user_id = session.get('user_id')
    hr_email = session.get('email')
    if not user_id: return jsonify({"status": "Unauthorized"})
    conn = get_db()
    if session.get('role') == 'HR': conn.execute('DELETE FROM jobs WHERE hr_email = ?', (hr_email,))
    conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit(); conn.close()
    session.clear()
    return jsonify({"status": "Account Deleted"})

@app.route('/admin_page')
def admin_page(): return render_template('admin.html')

@app.route('/api/god_view')
def api_god_view():
    conn = get_db()
    u = conn.execute('SELECT id, name, email, role, company FROM users').fetchall()
    j = conn.execute('SELECT * FROM jobs').fetchall()
    conn.close()
    try:
        with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f: l = json.load(f)
    except: l = []
    return jsonify({"users": [dict(x) for x in u], "jobs": [dict(x) for x in j], "logs": l[::-1]}) 

@app.route('/recruiter_page')
def recruiter_page(): return render_template('recruiter.html')

@app.route('/seeker_page')
def seeker_page(): return render_template('seeker.html')

if __name__ == '__main__':
    app.run(debug=False, port=5000)