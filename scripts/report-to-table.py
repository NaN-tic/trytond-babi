pool = globals().get('pool', None)
transaction = globals().get('transaction', None)

Report = pool.get('babi.report')
Table = pool.get('babi.table')
Field = pool.get('babi.field')
Pivot = pool.get('babi.pivot')
RowDimension = pool.get('babi.pivot.row_dimension')
ColumnDimension = pool.get('babi.pivot.column_dimension')
Measure = pool.get('babi.pivot.measure')
Property = pool.get('babi.pivot.property')
Order = pool.get('babi.pivot.order')
Cron = pool.get('ir.cron')

reports = Report.search([])

def add_field(fields, table, record):
    field = Field()
    field.table = table
    field.expression = record.expression
    field.name = record.name
    # Names must be unique
    count = [x.name for x in fields].count(field.name)
    if count:
        field.name = '%s (%s)' % (field.name, count)
        print('Count:', count)
    field.on_change_name()
    count = [x.internal_name for x in fields].count(field.internal_name)
    if count:
        field.internal_name = '%s_%s' % (field.internal_name, count)
    field.save()
    fields.append(field)
    return field

counter = 0
total = len(reports)
for report in reports:
    counter += 1
    print('Working on report: %s (%s/%s)' % (report.name, counter, total))
    table = Table()
    table.name = report.name
    table.on_change_name()
    table.type = 'model'
    table.model = report.model
    table.filter = report.filter
    table.timeout = report.timeout
    table.save()

    pivot = Pivot()
    pivot.table = table
    pivot.save()

    fields = []
    mapping = {}
    for dimension in report.dimensions:
        if dimension.group_by:
            existing = add_field(fields, table, dimension)
            new = RowDimension(pivot=pivot, field=fields[-1], sequence=dimension.sequence)
            new.save()
            mapping[dimension] = new
        else:
            existing = add_field(fields, table, dimension)
            new = Property(pivot=pivot, field=fields[-1], sequence=dimension.sequence)
            new.save()
            mapping[dimension] = new

    for column in report.columns:
        existing = add_field(fields, table, column)
        new = ColumnDimension(pivot=pivot, field=fields[-1], sequence=column.sequence)
        new.save()

    for measure in report.measures:
        existing = add_field(fields, table, measure)
        new = Measure(pivot=pivot, field=fields[-1], sequence=measure.sequence)
        new.save()
        mapping[measure] = new

    for order in report.order:
        f = order.dimension or order.measure
        new = Order(pivot=pivot, element=mapping[f], sequence=order.sequence,
            order=order.order.lower())
        new.save()

    for cron in report.crons:
        Cron.copy([cron], default={
                'babi_report': report.id,
                'babi_table': table.id,
                })

transaction.commit()
