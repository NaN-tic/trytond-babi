# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
from trytond.protocols.wrappers import with_pool, with_transaction, allow_null_origin
from trytond.wsgi import app

@app.route('/<database_name>/babi/pivot/<path:path>')
@allow_null_origin
@with_pool
@with_transaction(readonly=False)
def pivot(request, pool, path):
    print('== PIVOT FUNCTION ==')
    Site = pool.get('www.site')

    site_type = 'babi_pivot'
    site_id = 1

    return Site.dispatch(site_type, site_id, request)
