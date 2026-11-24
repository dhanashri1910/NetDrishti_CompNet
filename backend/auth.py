import re
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User

bp = Blueprint("auth", __name__)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_registration(name, email, pw, pw2):
    errors = []
    if len(name.strip()) < 2:
        errors.append("Full name must have at least 2 characters.")
    if not EMAIL_RE.match(email):
        errors.append("Enter a valid email address.")
    if len(pw) < 8:
        errors.append("Password must have at least 8 characters.")
    if pw != pw2:
        errors.append("Password and confirmation do not match.")
    if not errors and User.query.filter_by(email=email).first():
        errors.append("An account with this email already exists.")
    return errors


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("views.dashboard"))
    if request.method == "POST":
        f = request.form
        name, email = f.get("full_name", "").strip(), f.get("email", "").strip().lower()
        errors = validate_registration(name, email, f.get("password", ""), f.get("confirm_password", ""))
        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("register.html", name=name, email=email), 400
        db.session.add(User(full_name=name, email=email, password_hash=generate_password_hash(f["password"])))
        db.session.commit()
        flash("Account created. Please sign in.", "success")
        return redirect(url_for("auth.login"))
    return render_template("register.html", name="", email="")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("views.dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, request.form.get("password", "")):
            login_user(user)
            nxt = request.args.get("next", "")
            return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("views.dashboard"))
        flash("Incorrect email or password.", "danger")
        return render_template("login.html"), 401
    return render_template("login.html")


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))
