#cat modules/babi/cube.py | ./trytond/bin/trytond-console -d database -c trytond.conf
from tabulate import tabulate
from itertools import product
from collections import OrderedDict
from enum import Enum

# Crear clase cube
# Ha de contienr informació:
class Cube:
    def __init__(self, rows=None, columns=None, measures=None, table=None,
            order=None):
        self.table = table # We need the table name to make the query
        self.rows = rows
        self.columns = columns
        self.measures = measures
        self.order = order
        self.expansions = []

    def get_query_list(self, list):
        '''
        Given a list of elements, return a list of all possible coordinates.
        The structure the function receives is:
            list: ['Party Name 1', 'Party Name 2']
        And the structure the function returns is:
            list_coordinates: [[None, None], ['Party Name 1', None],
                ['Party Name 1', 'Party Name 2]]
        '''
        # Given a list of elements, return a list of all possible coordinates
        list_coordinates = []
        default_list_coordinates = [None]*len(list)
        list_coordinates.append(default_list_coordinates)

        index = 0
        for element in list:
            list_coordinates.append(list_coordinates[-1][:index] + [element] +
                list_coordinates[-1][index+1:])
            index += 1
        return list_coordinates

    def get_value_coordinate(self, result, rxc):
        '''
        Given a result of a cursor query and the list of coordinates, return
        the key of the dictornary of values we need to use. The strucutre we
        follow is:
            result: ('Party Name 1', Decimal('10.01'))
            rxc: ([None, None], ['party_name'])
        The key we end calculatin will be:
            ([None, None], ['Party Name 1'])
        '''
        index = 0
        key = []
        #TODO: we need to handle better the none columns, right now, we cant
        # know if a None comes from the name we give to him or from the query of the
        # database
        for rowxcolumn in rxc:
            rowxcolumn_coordinate = []
            for rowxcolumn_element in rowxcolumn:
                if not rowxcolumn_element:
                    rowxcolumn_coordinate.append(None)
                else:
                    #rowxcolumn_coordinate.append(Cell(result[index]))
                    rowxcolumn_coordinate.append(result[index])
                    index += 1
            key.append(tuple(rowxcolumn_coordinate))
        #h1 = Header(tuple(key))
        return tuple(key)

    def get_row_header(self, rows, cube_rows):
        '''
        Given a list of all the row headers ordered, return a list with the
        header cells. The structre we folllow is:
            rows: [[None, None], ['Party Name 1', None],
                ['Party Name 1', 'Party Name 2']]
        And the structure we return is:
            row_header: [['Party', '', ''], ['', 'Party Name 1', ''],
                ['', '', 'Party Name 2']]
        We have the variable "cube_rows" to make more generic this function,
        this way we can use the same function to get the column header
        '''
        row_header = []

        for r in rows:
            row = []
            # We add the first column outside the loop, that colum is
            # "None, None" and dont have a column name
            if r == tuple([None]*len(cube_rows)):
                row.append(cube_rows[0])
                row += ['']*len(cube_rows)
            else:
                # The empty row at the start represnet the column where we have
                # total
                row.append('')
                for element in r:
                    if element:
                        row.append(element)
                    else:
                        row.append('')
            row_header.append(row)
        return row_header


    def get_column_header(self, columns, cube_columns):
        '''
        Given a list of all the column headers, ordered, return a list with the
        column headers. The strucutre we follow is:
            columns: [[None, None], ['Party Name 1', None],
                ['Party Name 1', 'Party Name 2']]
        And the structure we return is:
            column_header: [['Party', '', ''],
                ['', 'Party Name 1', 'Party Name 2']]
        '''
        columns_in_rows = self.get_row_header(columns, cube_columns)

        # Get the extra rows we need to add at the start for each column header
        # represent the row headers
        row_extra_space = ['']*(len(cube.rows)+1)

        column_header = []
        # We need to add one extra number to the range to represent the total
        # cell (coordinate None)
        for i in range(len(cube_columns)+1):
            column = []
            for row in columns_in_rows:
                column.append(row[i])
                # We need to substrac 1 to the measure length because the firt
                # space is were the name of the column go
                for y in range(len(cube.measures)-1):
                    column.append('')
            column_header.append(row_extra_space + column)

        # Add the measure information row
        measure_names = [m[0] for m in cube.measures]
        column_length = len(column_header[0])-(len(cube.rows)+1)
        new_list = ((measure_names * (column_length // len(measure_names))) +
            measure_names[:column_length % len(measure_names)])
        column_header.append(row_extra_space + new_list)

        return column_header

class CellType(Enum):
    VALUE = 0
    ROW_HEADER = 1
    COLUMN_HEADER = 2


class Cell:
    __slots__ = ('value', 'type', 'expansion')

    def __init__(self, value, type=CellType.VALUE):
        self.value = value
        self.type = type # Utilitzar com a "type" un enum, es molt mes rápid que un diccionari
        self.expansion = None

    def __str__(self):
        if self.value is None:
            return '-'
        return str(self.value)

    def __eq__(self, value):
        if isinstance(value, Cell):
            return self.value == value.value and self.type == value.type
        return False

    def __hash__(self):
        return hash((self.value, self.type))

# Fer que les coordenades siguin un objecte "Header"
class Header:
    def __init__(self, *args):
        self.tuple = args

'''
class Coordinate:
    def __init__(self) -> None:
        pass
'''

###############################################################################
###############################################################################
###############################################################################
# Prepare the cube object. We need the table name, the list of rows and
# columns, the list of measures and the order we want to follow
cube = Cube(
    table='__productes_franquicies_per_tipus_de_vendes',
    rows=['franquicia', 'coordinador'],
    columns=['tipo_venda'],
    measures=[('sum', 'SUM'), ('total_line', 'SUM')],
    order=[(('franquicia'), 'ASC'), (('sum', 'SUM'), 'DESC')])

print(f'Cube table: {cube.table}\nCube rows: {cube.rows}\n'
    f'Cube columns: {cube.columns}\nCube measures: {cube.measures}\n'
    f'Cube order: {cube.order}\n')

rows = cube.get_query_list(cube.rows)
columns = cube.get_query_list(cube.columns)

# Get the cartesian product between the rows and columns
rxc = list(product(rows, columns))
print(f'ROWS COORDINATES: {rows}\nCOLUMNS COORDINATES: {columns}\nRxC: {rxc}')

# Format the measures to use them in the query
measures = ','.join([f'{measure[1]}({measure[0]})' for measure in cube.measures])

cursor = transaction.connection.cursor()
values = OrderedDict()
#values = {}
for rowxcolumn in rxc:
    print(f'  RC: {rowxcolumn}')
    # Transform the list of coordinates into a string to use it in the query
    groupby_columns = ','.join([rc for rowcolumn in rowxcolumn
        for rc in rowcolumn if rc != None])

    # In the case of having all the columns as "None", it means we are in the
    # first level and we dont need to do a group by
    if groupby_columns:
        query = (f'SELECT {groupby_columns}, {measures} FROM {cube.table} '
            f'GROUP BY {groupby_columns}')
    else:
        query = f'SELECT {measures} FROM {cube.table}'

    # Perpare the order we need to use in the query
    if cube.order:
        order_fields = []
        for order in cube.order:
            for groupby_column in groupby_columns.split(","):
                if groupby_column == order[0]:
                    order_fields.append(f'{order[0]} {order[1]}')
            if len(order) > 1:
                for measure in cube.measures:
                    if measure == order[0]:
                        order_fields.append(f'{order[0][1]}({order[0][0]}) {order[1]}')

        if order_fields:
            query += f' ORDER BY {",".join(order_fields)}'

    print(f'  QUERY: {query}')
    cursor.execute(query)
    results = cursor.fetchall()

    for result in results:
        result = [Cell(x) for x in result]
        # To know whick part of the result is the key and which is the value of
        # the measures we use the lenght of the "groupby_columns", this
        # variable is a string with the list of columns we use for the group by
        # in postgresql
        if groupby_columns:
            # If we have the groupby_columns attribute, we get all the values
            # since the last column that is not a group by column
            #values[cube.get_value_coordinate(result, rowxcolumn)] = tuple(
            #    [Cell(r) for r in result[len(groupby_columns.split(",")):]])
            values[cube.get_value_coordinate(result, rowxcolumn)] = (result[len(groupby_columns.split(",")):])
        else:
            # In the case we have all the columns as none, the result will
            # equal the number of measures we have
            #values[cube.get_value_coordinate(result, rowxcolumn)] = tuple(
            #    [Cell(r) for r in result])
            values[cube.get_value_coordinate(result, rowxcolumn)] = result

row_elements = []
row_elements.append(tuple([None]*len(cube.rows)))
col_elements = []
col_elements.append(tuple([None]*len(cube.columns)))

#TODO: we need to handle better the none keys, right now, we cant know if a
# None comes from the name we give to him or form the query of the database
for key in values.keys():
    if (key[0].count(None) == len(cube.rows)-1 and
            key[1].count(None) == len(cube.columns)):
        for sub_key in values.keys():
            if (sub_key[0][0] == key[0][0] and
                    sub_key[1].count(None) == len(cube.columns)):
                row_elements.append(sub_key[0])

    if (key[0].count(None) == len(cube.rows) and
            key[1].count(None) == len(cube.columns)-1):
        for sub_key in values.keys():
            if (sub_key[0].count(None) == len(cube.rows) and
                    sub_key[1][0] == key[1][0]):
                col_elements.append(sub_key[1])

row_header = cube.get_row_header(row_elements, cube.rows)
table = cube.get_column_header(col_elements, cube.columns)
for row in range(len(row_elements)):
    table_row = []
    table_row += row_header[row]
    for col in range(len(col_elements)):
        value = values.get((row_elements[row], col_elements[col]))
        if value:
            for cell in value:
                table_row.append(cell)
        else:
            for measure in range(len(cube.measures)):
                table_row.append(Cell(None))
    table.append(table_row)
print(tabulate(table))
