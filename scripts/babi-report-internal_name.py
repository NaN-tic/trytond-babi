pool = globals().get('pool', None)
transaction = globals().get('transaction', None)

Report = pool.get('babi.report')
Table = pool.get('babi.table')
Configuration = pool.get('ir.configuration')

configuration = Configuration(1)
transaction.set_context(language=configuration.language)

reports = Report.search([])
tables = Table.search([])
internal_names = [t.internal_name for t in tables]
for report in reports:
    table = Table()
    table.name = report.name
    table.on_change_name()
    internal_name = table.internal_name
    if not internal_name in internal_names:
        print('Report %s (%s) not found %s in internal_name' % (report.name, report.id, internal_name))


