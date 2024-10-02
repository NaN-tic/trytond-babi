# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
from trytond.protocols.wrappers import with_pool, with_transaction, allow_null_origin
from trytond.wsgi import app
from trytond.transaction import Transaction

@app.route('/<database_name>/babi/pivot/<path:path>')
@app.auth_required
@allow_null_origin
@with_pool
@with_transaction(user='request', readonly=False)
def pivot(request, pool, path):
    Site = pool.get('www.site')
    site_type = 'babi_pivot'
    return Site.dispatch(site_type, None, request, Transaction().user)
