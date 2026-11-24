
from functools import wraps

from flask import Blueprint, render_template, redirect, url_for, abort
from flask_login import login_required, current_user

from models import User, Network

bp = Blueprint("views", __name__)

PAGES = {
    "dashboard": "Dashboard",
    "topology": "Topology Builder",
    "faults": "Fault Lab",
    "routing": "Routing",
    "tools": "Subnet, TCP & UDP",
    "reports": "Network Reports",
}


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


@bp.route("/")
def index():
    return redirect(url_for("views.dashboard"))


def _make(name, title):
    def view():
        return render_template(
            f"{name}.html",
            page=name,
            title=title
        )

    view.__name__ = name
    bp.add_url_rule(
        "/" + name.replace("_", "-"),
        name,
        login_required(view)
    )


for _n, _t in PAGES.items():
    _make(_n, _t)


@bp.route("/admin/users")
@admin_required
def admin_users():
    users = User.query.order_by(User.created.desc()).all()

    user_data = []
    for user in users:
        network_count = Network.query.filter_by(
            user_id=user.id
        ).count()

        user_data.append({
            "id": user.id,
            "name": user.full_name,
            "email": user.email,
            "created": user.created,
            "is_admin": user.is_admin,
            "networks": network_count
        })

    return render_template(
        "admin_users.html",
        page="admin_users",
        title="User Management",
        users=user_data,
        total_users=len(users)
    )
