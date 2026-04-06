# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
from datetime import datetime

from trytond.protocols.wrappers import (
    HTTPStatus, abort, redirect, with_pool, with_transaction, allow_null_origin,
)
from trytond.wsgi import app
from trytond.transaction import Transaction


def _get_babi_site(pool, request):
    Site = pool.get('www.site')

    sites = Site.search([('type', '=', 'babi_pivot')], limit=1)
    if sites:
        return sites[0]

    site = Site()
    site.name = 'babi_pivot'
    site.type = 'babi_pivot'
    site.url = request.url_root
    site.save()
    return site

@app.route('/<database_name>/babi/pivot/<path:path>')
@app.auth_required
@allow_null_origin
@with_pool
@with_transaction(user='request', readonly=False)
def pivot(request, pool, path):
    Site = pool.get('www.site')
    site_type = 'babi_pivot'
    return Site.dispatch(site_type, None, request, Transaction().user,
        f'/{Transaction().database.name}/babi/pivot')


@app.route('/<database_name>/babi/voyager/<path:path>')
@allow_null_origin
@with_pool
@with_transaction(user=0, readonly=False)
def voyager(request, pool, path):
    Session = pool.get('www.session')
    Site = pool.get('www.site')

    site = _get_babi_site(pool, request)
    with Transaction().set_context(site=site.id):
        session = Session.get(request)
    if not request.user_id and not session.system_user:
        abort(HTTPStatus.UNAUTHORIZED)
    return Site.dispatch(site.type, site.id, request, request.user_id,
        f'/{Transaction().database.name}/babi/voyager')


@app.route('/<database_name>/babi/voyager-login/<string:token>')
@with_pool
@with_transaction(user=0, readonly=False)
def voyager_login(request, pool, token):
    OpenSession = pool.get('babi.voyager.open_session')
    Session = pool.get('www.session')
    Table = pool.get('babi.table')

    if not token:
        abort(HTTPStatus.UNAUTHORIZED)

    open_sessions = OpenSession.search([
            ('token', '=', token),
            ('expiration_date', '>=', datetime.now()),
            ], limit=1)
    if not open_sessions:
        abort(HTTPStatus.UNAUTHORIZED)

    open_session, = open_sessions
    user = open_session.user
    OpenSession.delete([open_session])

    site = _get_babi_site(pool, request)
    with Transaction().set_context(site=site.id):
        session = Session.new()
        session.set_system_user(user)

    with Transaction().set_user(user.id), Transaction().set_context(
            _request=request.context):
        tables = Table.search([], order=[('name', 'ASC')], limit=1)
    if not tables:
        abort(HTTPStatus.NOT_FOUND)
    table, = tables

    response = redirect(
        f'/{Transaction().database.name}/babi/voyager/{table.table_name}/null',
        HTTPStatus.FOUND)
    response.set_cookie('session_id', session.session_id)
    return response
