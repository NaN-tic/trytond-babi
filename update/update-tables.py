pool = globals()['pool']
transaction = globals()['transaction']


Table = pool.get('babi.table')
tables = Table.search([])
counter = 0
for table in tables:
    counter += 1
    print(f'Doing table {table.name} ({counter}')
    table.name = table.name
    table.save()

transaction.commit()
