# Copyright 2018 Therp BV <https://therp.nl>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import logging
from configparser import RawConfigParser as ConfigParser

import werkzeug
from odoo import http
from odoo.http import request
from odoo.addons.web.controllers.main import ensure_db
from odoo.exceptions import AccessError

try:
    import radicale
except ImportError:
    radicale = None

PREFIX = '/.dav'


class Main(http.Controller):

    @http.route('/', type='http', auth="none")
    def index(self, s_action=None, db=None, **kw):
        return http.local_redirect('/web', query=request.params, keep_hash=True)

    # ideally, this route should be `auth="user"` but that don't work in non-monodb mode.
    @http.route('/web', type='http', auth="none")
    def web_client(self, s_action=None, **kw):
        ensure_db()
        if not request.session.uid:
            return werkzeug.utils.redirect('/web/login', 303)
        if kw.get('redirect'):
            return werkzeug.utils.redirect(kw.get('redirect'), 303)

        request.uid = request.session.uid
        try:
            context = request.env['ir.http'].webclient_rendering_context()
            response = request.render('web.webclient_bootstrap', qcontext=context)
            response.headers['X-Frame-Options'] = 'DENY'
            return response
        except AccessError:
            return werkzeug.utils.redirect('/web/login?error=access')

    @http.route(
        ['/.well-known/carddav', '/.well-known/caldav', '/.well-known/webdav'],
        type='http', auth='none', csrf=False,
    )
    def handle_well_known_request(self):
        return werkzeug.utils.redirect(PREFIX, 301)

    @http.route(
        [PREFIX, '%s/<path:davpath>' % PREFIX], type='http', auth='none',
        csrf=False,
    )
    def handle_dav_request(self, davpath=None):
        config = ConfigParser()
        for section, values in radicale.config.INITIAL_CONFIG.items():
            config.add_section(section)
            for key, data in values.items():
                config.set(section, key, data["value"])
        config.set('auth', 'type', 'odoo.addons.base_dav.radicale.auth')
        config.set('storage', 'type', 'odoo.addons.base_dav.radicale.collection')
        config.set('rights', 'type', 'odoo.addons.base_dav.radicale.rights')
        config.set('web', 'type', 'none')
        application = radicale.Application(
            config, logging.getLogger('radicale'),
        )

        response = None

        def start_response(status, headers):
            nonlocal response
            response = http.Response(status=status, headers=headers)

        result = application(
            dict(
                request.httprequest.environ,
                HTTP_X_SCRIPT_NAME=PREFIX,
                PATH_INFO=davpath or '',
            ),
            start_response,
        )
        response.stream.write(result and result[0] or b'')
        return response
