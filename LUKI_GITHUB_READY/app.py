from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3, os, hashlib
from datetime import datetime, timedelta

app=Flask(__name__)
app.secret_key="filepoint-change-this-secret"
BASE=os.path.dirname(os.path.abspath(__file__))
DB=os.path.join(BASE,"filepoint.db")
UPLOAD=os.path.join(BASE,"uploads")
os.makedirs(UPLOAD,exist_ok=True)

def conn():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def init():
    c=conn()
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
        points INTEGER DEFAULT 0, role TEXT DEFAULT 'user', created_at TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS files(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        title TEXT NOT NULL, category TEXT NOT NULL, filename TEXT NOT NULL,
        description TEXT, points INTEGER DEFAULT 100, created_at TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS history(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        text TEXT NOT NULL, amount INTEGER NOT NULL, icon TEXT NOT NULL,
        created_at TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS redemptions(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        reward TEXT NOT NULL, cost INTEGER NOT NULL, status TEXT DEFAULT 'Diproses',
        created_at TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS downloads(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        day TEXT NOT NULL, count INTEGER DEFAULT 0, UNIQUE(user_id,day))""")
    # Lightweight migrations for columns added after the first release
    for stmt in ("ALTER TABLE users ADD COLUMN premium_until TEXT",
                 "ALTER TABLE files ADD COLUMN premium_only INTEGER DEFAULT 0",
                 "ALTER TABLE files ADD COLUMN file_hash TEXT"):
        try: c.execute(stmt)
        except sqlite3.OperationalError: pass
    admin=c.execute("SELECT id FROM users WHERE username='admin'").fetchone()
    if not admin:
        c.execute("INSERT INTO users(username,email,password,points,role,created_at) VALUES(?,?,?,?,?,?)",
                  ("admin","admin@filepoint.local",generate_password_hash("admin123"),0,"admin",now()))
    c.commit(); c.close()

def now(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def user():
    if "uid" not in session:return None
    c=conn(); x=c.execute("SELECT * FROM users WHERE id=?",(session["uid"],)).fetchone(); c.close(); return x
def admin_required():
    u=user()
    return u and u["role"]=="admin"

# ===== Fitur Premium =====
FREE_UPLOAD_POINTS=100
PREMIUM_UPLOAD_POINTS=150          # bonus +50% poin setiap upload
FREE_DAILY_DOWNLOAD_LIMIT=8        # user biasa dibatasi 8 unduhan/hari
PREMIUM_BENEFITS=[
    {"icon":"⚡","title":"Bonus +50% Poin Upload","desc":f"Setiap file yang kamu upload memberi {PREMIUM_UPLOAD_POINTS} poin, bukan {FREE_UPLOAD_POINTS} poin."},
    {"icon":"⬇️","title":"Download Tanpa Batas Harian","desc":f"User biasa dibatasi {FREE_DAILY_DOWNLOAD_LIMIT} unduhan/hari, member Premium unlimited."},
    {"icon":"🔒","title":"Upload Koleksi Eksklusif","desc":"Bisa menandai file sebagai 'Premium Only' — hanya sesama member Premium yang bisa mengunduhnya."},
    {"icon":"⭐","title":"Lencana Premium","desc":"Nama kamu tampil dengan lencana ⭐ Premium di dashboard dan daftar file."},
]

def is_premium(u):
    if not u or not u["premium_until"]: return False
    try: return datetime.strptime(u["premium_until"],"%Y-%m-%d %H:%M:%S")>datetime.now()
    except (ValueError,TypeError): return False

def premium_days_left(u):
    if not is_premium(u): return 0
    delta=datetime.strptime(u["premium_until"],"%Y-%m-%d %H:%M:%S")-datetime.now()
    return max(1,delta.days+(1 if delta.seconds>0 else 0))

REWARDS = [
    # -- Uang & Saldo --
    {"name":"Pulsa Elektrik Rp20.000","cost":2200,"icon":"📱","category":"Uang & Saldo","desc":"Pulsa untuk semua operator, dikirim ke nomor kamu."},
    {"name":"Saldo E-Wallet Rp25.000","cost":2500,"icon":"💵","category":"Uang & Saldo","desc":"Saldo DANA / OVO / GoPay dikirim ke akun kamu."},
    {"name":"Saldo E-Wallet Rp50.000","cost":5000,"icon":"💰","category":"Uang & Saldo","desc":"Saldo DANA / OVO / GoPay dikirim ke akun kamu."},
    {"name":"Saldo E-Wallet Rp100.000","cost":9500,"icon":"🏦","category":"Uang & Saldo","desc":"Saldo DANA / OVO / GoPay dikirim ke akun kamu."},
    # -- Alat Tulis Kampus --
    {"name":"Pulpen Gel Set (5 pcs)","cost":800,"icon":"🖊️","category":"Alat Tulis Kampus","desc":"Set pulpen gel hitam & biru untuk catatan kuliah."},
    {"name":"Buku Tulis Kuliah 100 Lembar","cost":1000,"icon":"📔","category":"Alat Tulis Kampus","desc":"Buku tulis bergaris, pas untuk mata kuliah favoritmu."},
    {"name":"Binder A5 Ring Kuliah","cost":1800,"icon":"📓","category":"Alat Tulis Kampus","desc":"Binder rings A5 + refill kertas, rapi buat semua mapel."},
    {"name":"Stabilo Highlighter Set","cost":900,"icon":"🖍️","category":"Alat Tulis Kampus","desc":"5 warna stabilo untuk menandai materi penting."},
    # -- Merchandise Kampus --
    {"name":"Gantungan Kunci Kampus","cost":500,"icon":"🔑","category":"Merchandise Kampus","desc":"Gantungan kunci eksklusif FilePoint."},
    {"name":"Totebag Kanvas Kampus","cost":2200,"icon":"👜","category":"Merchandise Kampus","desc":"Totebag kanvas tebal, muat buku & laptop tipis."},
    {"name":"Tas Ransel Laptop Kampus","cost":6000,"icon":"🎒","category":"Merchandise Kampus","desc":"Ransel kuat dengan kompartemen laptop, siap ke kampus."},
    # -- Langganan & Sertifikat --
    {"name":"Premium 7 Hari","cost":2500,"icon":"⭐","category":"Langganan & Sertifikat","desc":"Bonus poin upload, download unlimited, & akses koleksi eksklusif selama 7 hari."},
    {"name":"Sertifikat Kontributor","cost":3000,"icon":"🏆","category":"Langganan & Sertifikat","desc":"Sertifikat digital sebagai kontributor aktif."},
]
CATEGORY_META = {
    "Uang & Saldo":{"icon":"💰","color":"#1f9d55"},
    "Alat Tulis Kampus":{"icon":"🖊️","color":"#e2892e"},
    "Merchandise Kampus":{"icon":"🎒","color":"#8b5cf6"},
    "Langganan & Sertifikat":{"icon":"⭐","color":"#3b67df"},
}

init()

@app.route("/")
def home():
    return redirect(url_for("dashboard") if user() else url_for("login"))

@app.route("/register",methods=["GET","POST"])
def register():
    if request.method=="POST":
        u=request.form["username"].strip(); e=request.form["email"].strip().lower()
        p=request.form["password"]; cp=request.form["confirm"]
        if len(u)<3 or len(p)<5: flash("Username minimal 3 karakter dan password minimal 5 karakter.","error")
        elif p!=cp: flash("Konfirmasi password tidak sama.","error")
        else:
            c=conn()
            try:
                c.execute("INSERT INTO users(username,email,password,created_at) VALUES(?,?,?,?)",(u,e,generate_password_hash(p),now()))
                c.commit(); flash("Akun berhasil dibuat. Silakan login.","success"); return redirect(url_for("login"))
            except sqlite3.IntegrityError: flash("Username atau email sudah digunakan.","error")
            finally:c.close()
    return render_template("register.html")

@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        name=request.form["username"].strip(); p=request.form["password"]
        c=conn(); u=c.execute("SELECT * FROM users WHERE username=?",(name,)).fetchone(); c.close()
        if u and check_password_hash(u["password"],p):
            session["uid"]=u["id"]
            return redirect(url_for("admin") if u["role"]=="admin" else url_for("dashboard"))
        flash("Username atau password salah.","error")
    return render_template("login.html")

@app.route("/logout")
def logout(): session.clear(); return redirect(url_for("login"))

@app.route("/dashboard")
def dashboard():
    u=user()
    if not u:return redirect(url_for("login"))
    c=conn()
    fs=c.execute("SELECT * FROM files WHERE user_id=? ORDER BY id DESC",(u["id"],)).fetchall()
    hs=c.execute("SELECT * FROM history WHERE user_id=? ORDER BY id DESC",(u["id"],)).fetchall()
    rs=c.execute("SELECT * FROM redemptions WHERE user_id=? ORDER BY id DESC",(u["id"],)).fetchall()
    c.close()
    categories=[]
    for r in REWARDS:
        if r["category"] not in categories: categories.append(r["category"])
    return render_template("dashboard.html",user=u,files=fs,history=hs,redemptions=rs,
                            rewards=REWARDS,categories=categories,cat_meta=CATEGORY_META,
                            is_premium=is_premium(u),premium_days=premium_days_left(u),
                            premium_benefits=PREMIUM_BENEFITS,free_upload_pts=FREE_UPLOAD_POINTS,
                            premium_upload_pts=PREMIUM_UPLOAD_POINTS,free_dl_limit=FREE_DAILY_DOWNLOAD_LIMIT)

@app.route("/upload",methods=["POST"])
def upload():
    u=user()
    if not u:return redirect(url_for("login"))
    f=request.files.get("file"); title=request.form["title"].strip()
    if not f or not f.filename or not title:
        flash("Judul dan file wajib diisi.","error"); return redirect(url_for("dashboard"))

    content=f.read()
    file_hash=hashlib.sha256(content).hexdigest()
    f.seek(0)

    c=conn()
    dup=c.execute("""SELECT files.title,users.username FROM files
                      JOIN users ON users.id=files.user_id WHERE files.file_hash=?""",(file_hash,)).fetchone()
    if dup:
        c.close()
        if dup["username"]==u["username"]:
            flash(f"File ini sudah pernah kamu upload sebagai '{dup['title']}'. Ganti nama file tidak akan lolos deteksi duplikat. 🚫","error")
        else:
            flash(f"File ini sudah ada di sistem (diupload sebagai '{dup['title']}' oleh {dup['username']}). Upload ditolak. 🚫","error")
        return redirect(url_for("dashboard"))

    premium=is_premium(u)
    pts=PREMIUM_UPLOAD_POINTS if premium else FREE_UPLOAD_POINTS
    premium_only=1 if (premium and request.form.get("premium_only")=="on") else 0
    safe=secure_filename(f.filename)
    fname=f"{u['id']}_{int(datetime.now().timestamp())}_{safe}"
    f.save(os.path.join(UPLOAD,fname))
    c.execute("INSERT INTO files(user_id,title,category,filename,description,points,created_at,premium_only,file_hash) VALUES(?,?,?,?,?,?,?,?,?)",
              (u["id"],title,request.form["category"],fname,request.form.get("description",""),pts,now(),premium_only,file_hash))
    c.execute("UPDATE users SET points=points+? WHERE id=?",(pts,u["id"]))
    c.execute("INSERT INTO history(user_id,text,amount,icon,created_at) VALUES(?,?,?,?,?)",(u["id"],"Upload "+title,pts,"📤",now()))
    c.commit();c.close()
    flash(f"Upload berhasil! +{pts} poin 🎉"+(" (bonus Premium)" if premium else ""),"success"); return redirect(url_for("dashboard"))

@app.route("/download/<int:id>")
def download(id):
    u=user()
    if not u:return redirect(url_for("login"))
    c=conn(); f=c.execute("SELECT * FROM files WHERE id=?",(id,)).fetchone()
    if not f:
        c.close(); return "File tidak ditemukan",404
    premium=is_premium(u)
    if f["premium_only"] and not premium and u["role"]!="admin" and u["id"]!=f["user_id"]:
        c.close(); flash("File ini khusus member Premium. Tukar poin kamu dengan reward Premium 7 Hari untuk membukanya. 🔒","error")
        return redirect(url_for("dashboard")+"#reward")
    if not premium and u["role"]!="admin":
        day=datetime.now().strftime("%Y-%m-%d")
        row=c.execute("SELECT count FROM downloads WHERE user_id=? AND day=?",(u["id"],day)).fetchone()
        used=row["count"] if row else 0
        if used>=FREE_DAILY_DOWNLOAD_LIMIT:
            c.close(); flash(f"Kamu sudah mencapai batas {FREE_DAILY_DOWNLOAD_LIMIT} unduhan hari ini. Upgrade ke Premium untuk unduh tanpa batas. 🔒","error")
            return redirect(url_for("dashboard")+"#reward")
        if row: c.execute("UPDATE downloads SET count=count+1 WHERE user_id=? AND day=?",(u["id"],day))
        else: c.execute("INSERT INTO downloads(user_id,day,count) VALUES(?,?,1)",(u["id"],day))
        c.commit()
    c.close()
    return send_from_directory(UPLOAD,f["filename"],as_attachment=True)

@app.route("/redeem",methods=["POST"])
def redeem():
    u=user()
    if not u:return redirect(url_for("login"))
    reward=request.form["reward"]
    match=next((r for r in REWARDS if r["name"]==reward),None)
    if not match:
        flash("Reward tidak ditemukan.","error"); return redirect(url_for("dashboard"))
    cost=match["cost"]
    c=conn(); fresh=c.execute("SELECT * FROM users WHERE id=?",(u["id"],)).fetchone()
    if fresh["points"]<cost:
        c.close(); flash("Poin belum cukup.","error"); return redirect(url_for("dashboard"))
    c.execute("UPDATE users SET points=points-? WHERE id=?",(cost,u["id"]))
    status="Selesai" if match["category"]=="Langganan & Sertifikat" else "Diproses"
    c.execute("INSERT INTO redemptions(user_id,reward,cost,status,created_at) VALUES(?,?,?,?,?)",(u["id"],reward,cost,status,now()))
    c.execute("INSERT INTO history(user_id,text,amount,icon,created_at) VALUES(?,?,?,?,?)",(u["id"],"Menukar "+reward,-cost,"🎁",now()))
    if reward=="Premium 7 Hari":
        base=datetime.now()
        if fresh["premium_until"]:
            try:
                cur=datetime.strptime(fresh["premium_until"],"%Y-%m-%d %H:%M:%S")
                if cur>base: base=cur
            except (ValueError,TypeError): pass
        new_until=(base+timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute("UPDATE users SET premium_until=? WHERE id=?",(new_until,u["id"]))
        c.commit();c.close()
        flash("Premium aktif! ⭐ Nikmati bonus poin, download unlimited, dan koleksi eksklusif selama 7 hari.","success")
        return redirect(url_for("dashboard"))
    c.commit();c.close()
    flash("Reward berhasil diminta. Menunggu proses admin.","success"); return redirect(url_for("dashboard"))

@app.route("/admin")
def admin():
    if not admin_required(): return redirect(url_for("dashboard"))
    q=request.args.get("q","").strip()
    c=conn()
    users=c.execute("SELECT id,username,email,points,role,created_at FROM users ORDER BY id DESC").fetchall()
    if q:
        like=f"%{q}%"
        files=c.execute("""SELECT files.*,users.username FROM files
                           JOIN users ON users.id=files.user_id
                           WHERE files.title LIKE ? OR files.filename LIKE ? OR users.username LIKE ?
                           ORDER BY files.id DESC""",(like,like,like)).fetchall()
    else:
        files=c.execute("""SELECT files.*,users.username FROM files
                           JOIN users ON users.id=files.user_id
                           ORDER BY files.id DESC""").fetchall()
    reds=c.execute("""SELECT redemptions.*,users.username FROM redemptions
                      JOIN users ON users.id=redemptions.user_id ORDER BY redemptions.id DESC""").fetchall()
    stats=(c.execute("SELECT COUNT(*) n FROM users WHERE role='user'").fetchone()["n"],
           c.execute("SELECT COUNT(*) n FROM files").fetchone()["n"],
           c.execute("SELECT COUNT(*) n FROM redemptions").fetchone()["n"])
    c.close()
    return render_template("admin.html",users=users,files=files,reds=reds,stats=stats,search=q)

@app.route("/admin/file/view/<int:id>")
def admin_file_view(id):
    if not admin_required(): return redirect(url_for("login"))
    c=conn()
    f=c.execute("SELECT * FROM files WHERE id=?",(id,)).fetchone()
    c.close()
    if not f:
        return "File tidak ditemukan",404
    path=os.path.join(UPLOAD,f["filename"])
    if not os.path.isfile(path):
        return "File fisik tidak ditemukan",404
    return send_from_directory(UPLOAD,f["filename"],as_attachment=False)

@app.route("/admin/reward/<int:id>",methods=["POST"])
def admin_reward(id):
    if not admin_required():return redirect(url_for("login"))
    status=request.form["status"]; c=conn()
    c.execute("UPDATE redemptions SET status=? WHERE id=?",(status,id)); c.commit();c.close()
    flash("Status reward diperbarui.","success"); return redirect(url_for("admin"))

@app.route("/admin/file/<int:id>",methods=["POST"])
def admin_file(id):
    if not admin_required():return redirect(url_for("login"))
    c=conn(); f=c.execute("SELECT * FROM files WHERE id=?",(id,)).fetchone()
    if f:
        path=os.path.join(UPLOAD,f["filename"])
        if os.path.exists(path): os.remove(path)
        c.execute("DELETE FROM files WHERE id=?",(id,))
    c.commit();c.close(); flash("File dihapus admin.","success"); return redirect(url_for("admin"))

if __name__=="__main__":
    app.run(debug=True)
