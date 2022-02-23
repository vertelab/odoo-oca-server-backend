# Copyright 2018 Therp BV <https://therp.nl>
# Copyright 2019-2020 initOS GmbH <https://initos.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo.http import request

try:
    from radicale.auth import BaseAuth
except ImportError:
    BaseAuth = None

PLUGIN_CONFIG_SCHEMA = {"auth": {
    "password": {"value": "", "type": str}}}


class Auth(BaseAuth):
    def login(self, login: str, password: str) -> str:
        env = request.env
        uid = request.session.authenticate(env.cr.dbname, login, password)
        user_id = env['res.users'].browse(uid)
        if uid:
            request._env = env(user=uid)
        return user_id.login
