# Copyright 2018 Therp BV <https://therp.nl>
# Copyright 2019-2020 initOS GmbH <https://initos.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo.http import request

try:
    from radicale.auth import BaseAuth
except ImportError:
    BaseAuth = None


class Auth(BaseAuth):
    def is_authenticated2(self, login, user, password):
        env = request.env
        if not (uid := request.session.authenticate(env.cr.dbname, user, password)):
            users = request.env['res.users']
            if (user := users.search(users._get_login_domain(login), order=users._get_login_order(), limit=1)):
                uid = users.with_user(user)._check_credentials(password, env)       
        if uid:
            request._env = env(user=uid)
        return bool(uid)
