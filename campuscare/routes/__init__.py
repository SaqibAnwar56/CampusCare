from functools import wraps

from flask import abort
from flask_login import current_user

from ..extensions import login_manager


def role_required(*roles):
    """Allow only authenticated users with one of the given roles (RBAC)."""
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return login_manager.unauthorized()
            if current_user.role not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapper
    return decorator
