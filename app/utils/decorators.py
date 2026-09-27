from functools import wraps

from flask import abort
from flask_login import current_user


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if not current_user.is_admin:
            abort(403)
        return fn(*args, **kwargs)

    return wrapper


def scanner_or_admin_required(fn):
    """Scanner staff and admins may use the scanning endpoints; scanners get no
    other privileges (see AdminUser.role and the admin routes which are all
    admin_required-only)."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if not (current_user.is_admin or current_user.is_scanner):
            abort(403)
        return fn(*args, **kwargs)

    return wrapper
