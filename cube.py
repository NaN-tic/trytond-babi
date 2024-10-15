#cat modules/babi/cube.py | ./trytond/bin/trytond-console -d database -c trytond.conf
import ast
from tabulate import tabulate
from itertools import product
from collections import OrderedDict
from enum import Enum
from urllib.parse import urlencode, parse_qs


class Cube:
    def __init__(self, rows=None, columns=None, measures=None, table=None,
            order=None, expansions=None):
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
        for rowxcolumn in rxc:
            rowxcolumn_coordinate = []
            for rowxcolumn_element in rowxcolumn:
                if not rowxcolumn_element:
                    rowxcolumn_coordinate.append(None)
                else:
                    #rowxcolumn_coordinate.append(Cell(result[index]))
                    result[index].type = CellType.ROW_HEADER
                    rowxcolumn_coordinate.append(result[index])
                    index += 1
            key.append(tuple(rowxcolumn_coordinate))
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
        row_extra_space = ['']*(len(self.rows)+1)

        column_header = []
        # We need to add one extra number to the range to represent the total
        # cell (coordinate None)
        for i in range(len(cube_columns)+1):
            column = []
            for row in columns_in_rows:
                column.append(row[i])
                # We need to substrac 1 to the measure length because the firt
                # space is were the name of the column go
                for y in range(len(self.measures)-1):
                    column.append('')
            column_header.append(row_extra_space + column)

        # Add the measure information row
        measure_names = [m[0] for m in self.measures]
        column_length = len(column_header[0])-(len(self.rows)+1)
        new_list = ((measure_names * (column_length // len(measure_names))) +
            measure_names[:column_length % len(measure_names)])
        column_header.append(row_extra_space + new_list)

        return column_header

    def get_values(self):
        '''
        Calculate the values of the cube. Return a dictionary with the format:
        values = {[((Cell('Party Name 1'), Cell(None)),
            (Cell('Type'), Cell(None)))]: (Cell(value1), Cell(value2))}
        '''
        rows = self.get_query_list(self.rows)
        columns = self.get_query_list(self.columns)

        # Get the cartesian product between the rows and columns
        rxc = list(product(rows, columns))
        print(f'ROWS COORDINATES: {rows}\nCOLUMNS COORDINATES: {columns}\nRxC: {rxc}')

        # Format the measures to use them in the query
        measures = ','.join([f'{measure[1]}({measure[0]})' for measure in self.measures])

        cursor = transaction.connection.cursor()
        values = OrderedDict()
        for rowxcolumn in rxc:
            print(f'  RC: {rowxcolumn}')
            # Transform the list of coordinates into a string to use it in the
            # query
            groupby_columns = ','.join([rc for rowcolumn in rowxcolumn
                for rc in rowcolumn if rc != None])

            # In the case of having all the columns as "None", it means we are
            # in the first level and we dont need to do a group by
            if groupby_columns:
                query = (f'SELECT {groupby_columns}, {measures} FROM '
                    f'{self.table} GROUP BY {groupby_columns}')
            else:
                query = f'SELECT {measures} FROM {self.table}'

            # Perpare the order we need to use in the query
            if self.order:
                order_fields = []
                for order in self.order:
                    for groupby_column in groupby_columns.split(","):
                        if groupby_column == order[0]:
                            order_fields.append(f'{order[0]} {order[1]}')
                    if len(order) > 1:
                        for measure in self.measures:
                            if measure == order[0]:
                                order_fields.append(
                                    f'{order[0][1]}({order[0][0]}) {order[1]}')

                if order_fields:
                    query += f' ORDER BY {",".join(order_fields)}'

            print(f'  QUERY: {query}')
            cursor.execute(query)
            results = cursor.fetchall()

            for result in results:
                result = [Cell(x) for x in result]
                # To know whick part of the result is the key and which is the
                # value of the measures we use the lenght of the
                # "groupby_columns", this variable is a string with the list of
                # columns we use for the group by in postgresql
                if groupby_columns:
                    # If we have the groupby_columns attribute, we get all the
                    # values since the last column that is not a group by
                    # column
                    values[self.get_value_coordinate(result, rowxcolumn)] = (
                        result[len(groupby_columns.split(",")):])
                else:
                    # In the case we have all the columns as none, the result
                    # will equal the number of measures we have
                    values[self.get_value_coordinate(result, rowxcolumn)] = (
                        result)

        return values

    def build(self):
        '''
        Create the table with values from a cube object. Return a list of lists
        with the format:
            table = [[Cell, Cell, Cell, Cell], [Cell, Cell, Cell, Cell]]
        '''
        values = self.get_values()

        row_elements = []
        row_elements.append(tuple([None]*len(self.rows)))
        col_elements = []
        col_elements.append(tuple([None]*len(self.columns)))

        #TODO: re-implement this loop
        for key in values.keys():
            if (key[0].count(None) == len(self.rows)-1 and
                    key[1].count(None) == len(self.columns)):
                for sub_key in values.keys():
                    if (sub_key[0][0] == key[0][0] and
                            sub_key[1].count(None) == len(self.columns)):
                        row_elements.append(sub_key[0])

            if (key[0].count(None) == len(self.rows) and
                    key[1].count(None) == len(self.columns)-1):
                for sub_key in values.keys():
                    if (sub_key[0].count(None) == len(self.rows) and
                            sub_key[1][0] == key[1][0]):
                        col_elements.append(sub_key[1])

        #TODO: instead of return the list "table", return for each row a yeld,
        # this way we dont need to save in memory the whole table
        row_header = self.get_row_header(row_elements, self.rows)
        table = self.get_column_header(col_elements, self.columns)
        for row in range(len(row_elements)):
            table_row = []
            table_row += row_header[row]
            for col in range(len(col_elements)):
                value = values.get((row_elements[row], col_elements[col]))
                if value:
                    for cell in value:
                        table_row.append(cell)
                else:
                    for measure in range(len(self.measures)):
                        table_row.append(Cell(None))
            table.append(table_row)
        return table

    def encode_cube_properties(self):
        '''
        Given a cube instance, return a string with the properties of the cube.
        Make the trasformation using the urllib.parse.urlencode function
        '''
        cube_properties = self.__dict__
        # We need to delte the table property because it is already in the url
        del cube_properties['table']
        return urlencode(self.__dict__, doseq=True)

    @classmethod
    def parse_cube_properties(cls, url, table_name=None):
        '''
        Given a string with the properties of a cube, return a cube instance.
        Make the trasformation using the urllib.parse.parse_qs function
        '''
        cube_properties = parse_qs(url)
        # We need to handle the format of measures and order, the rows and
        # columns its ok because they are a list of strings, we use
        # ast.literal_eval because is more secure than eval

        if cube_properties.get('measures'):
            cube_properties['measures'] = [
                ast.literal_eval(m) for m in cube_properties['measures']]

        if cube_properties.get('order'):
            cube_properties['order'] = [
                ast.literal_eval(m) for m in cube_properties['order']]

        if table_name:
            cube_properties['table'] = table_name
        return cls(**cube_properties)


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


# Prepare the cube object. We need the table name, the list of rows and
# columns, the list of measures and the order we want to follow
if __name__ == '__main__':
    cube = Cube(
        table='__productes_franquicies_per_tipus_de_vendes',
        rows=['franquicia', 'coordinador'],
        columns=['tipo_venda'],
        measures=[('sum', 'SUM'), ('total_line', 'SUM')],
        order=[('franquicia', 'ASC'), (('sum', 'SUM'), 'DESC')])

    print(f'Cube table: {cube.table}\nCube rows: {cube.rows}\n'
        f'Cube columns: {cube.columns}\nCube measures: {cube.measures}\n'
        f'Cube order: {cube.order}\n')

    dict = cube.encode_cube_properties()
    x = Cube.parse_cube_properties(dict, '__productes_franquicies_per_tipus_de_vendes')
    table = cube.build()
    print(tabulate(table))
