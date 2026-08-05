"""
Sale Scout — Web App
Merit House · themerithouse.com
"""

import os
import bcrypt
from flask import Flask, render_template, redirect, url_for, request, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime

# ── App setup ─────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///salescout.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please sign in to access Sale Scout."

# ── Models ─────────────────────────────────────────────────────────────────────

class Creator(UserMixin, db.Model):
    id                  = db.Column(db.Integer, primary_key=True)
    email               = db.Column(db.String(255), unique=True, nullable=False)
    password_hash       = db.Column(db.String(255), nullable=False)
    name                = db.Column(db.String(255))
    storefront_handle   = db.Column(db.String(255))
    affiliate_tag       = db.Column(db.String(255))
    amazon_access_key   = db.Column(db.String(512))
    amazon_secret_key   = db.Column(db.String(512))
    alert_email         = db.Column(db.String(255))
    gmail_address       = db.Column(db.String(255))
    gmail_app_password  = db.Column(db.String(255))
    threshold_pct       = db.Column(db.Integer, default=25)
    active              = db.Column(db.Boolean, default=True)
    setup_complete      = db.Column(db.Boolean, default=False)
    created_at          = db.Column(db.DateTime, default=datetime.utcnow)
    runs                = db.relationship("SaleRun", backref="creator", lazy=True)

    def set_password(self, password):
        self.password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    def check_password(self, password):
        return bcrypt.checkpw(password.encode(), self.password_hash.encode())


class SaleRun(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    creator_id   = db.Column(db.Integer, db.ForeignKey("creator.id"), nullable=False)
    ran_at       = db.Column(db.DateTime, default=datetime.utcnow)
    items_found  = db.Column(db.Integer, default=0)
    status       = db.Column(db.String(50), default="success")
    error        = db.Column(db.Text)


@login_manager.user_loader
def load_user(user_id):
    return Creator.query.get(int(user_id))


# ── Routes — Auth ──────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        name     = request.form.get("name", "").strip()

        if not email or not password:
            flash("Email and password are required.", "error")
            return render_template("signup.html")

        if Creator.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "error")
            return render_template("signup.html")

        creator = Creator(email=email, name=name)
        creator.set_password(password)
        db.session.add(creator)
        db.session.commit()
        login_user(creator)
        return redirect(url_for("setup"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        creator  = Creator.query.filter_by(email=email).first()

        if creator and creator.check_password(password):
            login_user(creator)
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "error")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))


# ── Routes — Setup ─────────────────────────────────────────────────────────────

@app.route("/setup", methods=["GET", "POST"])
@login_required
def setup():
    if request.method == "POST":
        current_user.name               = request.form.get("name", "").strip()
        current_user.storefront_handle  = request.form.get("storefront_handle", "").strip()
        current_user.affiliate_tag      = request.form.get("affiliate_tag", "").strip()
        current_user.amazon_access_key  = request.form.get("amazon_access_key", "").strip()
        current_user.amazon_secret_key  = request.form.get("amazon_secret_key", "").strip()
        current_user.alert_email        = request.form.get("alert_email", "").strip()
        current_user.gmail_address      = request.form.get("gmail_address", "").strip()
        current_user.gmail_app_password = request.form.get("gmail_app_password", "").strip()
        threshold = request.form.get("threshold_pct", "25")
        current_user.threshold_pct      = int(threshold) if threshold.isdigit() else 25
        current_user.setup_complete     = True
        db.session.commit()
        flash("Setup complete! You're ready to run Sale Scout.", "success")
        return redirect(url_for("dashboard"))

    return render_template("setup.html")


# ── Routes — Dashboard ─────────────────────────────────────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
    runs = SaleRun.query.filter_by(creator_id=current_user.id)\
                        .order_by(SaleRun.ran_at.desc()).limit(10).all()
    return render_template("dashboard.html", runs=runs)


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        current_user.name               = request.form.get("name", "").strip()
        current_user.storefront_handle  = request.form.get("storefront_handle", "").strip()
        current_user.affiliate_tag      = request.form.get("affiliate_tag", "").strip()
        current_user.amazon_access_key  = request.form.get("amazon_access_key", "").strip()
        current_user.amazon_secret_key  = request.form.get("amazon_secret_key", "").strip()
        current_user.alert_email        = request.form.get("alert_email", "").strip()
        current_user.gmail_address      = request.form.get("gmail_address", "").strip()
        if request.form.get("gmail_app_password"):
            current_user.gmail_app_password = request.form.get("gmail_app_password", "").strip()
        threshold = request.form.get("threshold_pct", "25")
        current_user.threshold_pct = int(threshold) if threshold.isdigit() else 25
        db.session.commit()
        flash("Settings saved.", "success")

    return render_template("settings.html")


# ── Routes — Run Now ───────────────────────────────────────────────────────────

@app.route("/run", methods=["POST"])
@login_required
def run_now():
    if not current_user.setup_complete:
        flash("Please complete your setup first.", "error")
        return redirect(url_for("setup"))

    # The scrape takes minutes — run it in the background so the request
    # returns immediately instead of being killed by the gunicorn timeout.
    import threading
    threading.Thread(target=_run_in_background, args=(current_user.id,), daemon=True).start()

    flash("Sale Scout is running — this takes a few minutes. Refresh to see the result.", "success")
    return redirect(url_for("dashboard"))


def _run_in_background(creator_id):
    """Re-fetch the creator inside the thread — request-bound objects don't survive."""
    with app.app_context():
        creator = db.session.get(Creator, creator_id)
        if creator:
            run_for_creator(creator)


# ── Pipeline runner ────────────────────────────────────────────────────────────

def run_for_creator(creator):
    """Run the full Sale Scout pipeline for one creator."""
    import os, sys, time
    from dataclasses import dataclass

    # Temporarily set env vars for this creator
    os.environ["AMAZON_ACCESS_KEY"]   = creator.amazon_access_key or ""
    os.environ["AMAZON_SECRET_KEY"]   = creator.amazon_secret_key or ""
    os.environ["AMAZON_PARTNER_TAG"]  = creator.affiliate_tag or ""
    os.environ["AMAZON_API_VERSION"]  = "v3.1"
    os.environ["GMAIL_ADDRESS"]       = creator.gmail_address or ""
    os.environ["GMAIL_APP_PASSWORD"]  = creator.gmail_app_password or ""

    try:
        from scrape_storefront import scrape_storefront
        from sale_report import build_api, get_sale_items
        from email_notify import send_sale_email

        asins = scrape_storefront(creator.storefront_handle)
        if not asins:
            _log_run(creator.id, 0, "success")
            return

        api = build_api()
        sale_items = get_sale_items(api, asins, creator.threshold_pct)
        sale_items.sort(key=lambda x: x.pct_off, reverse=True)

        if sale_items:
            send_sale_email(
                sale_items,
                to_address=creator.alert_email,
                creator_name=creator.name or "Your Store",
            )

        _log_run(creator.id, len(sale_items), "success")

    except Exception as e:
        import traceback
        _log_run(creator.id, 0, "error", traceback.format_exc() or repr(e))


def _log_run(creator_id, items_found, status, error=None):
    with app.app_context():
        run = SaleRun(
            creator_id=creator_id,
            items_found=items_found,
            status=status,
            error=error,
        )
        db.session.add(run)
        db.session.commit()


# ── Daily scheduler ────────────────────────────────────────────────────────────

def run_all_creators():
    """Called by scheduler every morning — runs pipeline for all active creators."""
    with app.app_context():
        creators = Creator.query.filter_by(active=True, setup_complete=True).all()
        for creator in creators:
            try:
                run_for_creator(creator)
            except Exception as e:
                _log_run(creator.id, 0, "error", str(e))


scheduler = BackgroundScheduler()
scheduler.add_job(run_all_creators, "cron", hour=8, minute=0)
scheduler.start()


# ── Init ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5001)
