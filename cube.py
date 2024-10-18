import ast
import binascii
from datetime import datetime, date, timedelta
from decimal import Decimal
from itertools import product
from collections import OrderedDict
from enum import Enum
from urllib.parse import urlencode, parse_qs
from trytond.config import config
from trytond.i18n import gettext
from trytond.transaction import Transaction

DEFAULT_MIME_TYPE = config.get('babi', 'mime_type', default='image/png')

# From html_report
def strfdelta(tdelta, fmt):
    d = {"days": tdelta.days}
    d["hours"], rem = divmod(tdelta.seconds, 3600)
    d["minutes"], d["seconds"] = divmod(rem, 60)
    d['minutes'] = '%02d' % d['minutes']
    d['seconds'] = '%02d' % d['seconds']
    if not 'days' in fmt and d.get('days') > 0:
        d["hours"] += d.get('days') * 24 # 24h/day
    return fmt.format(**d)


class Cube:
    def __init__(self, table=None, rows=None, columns=None, measures=None,
            order=None, expansions=None):
        '''
        order must have the following format:
        [('column_name', 'asc'), ('column_name', 'desc'), ('measure', 'sum', 'asc')]
        '''
        if rows is None:
            rows = []
        if columns is None:
            columns = []
        if measures is None:
            measures = []
        if order is None:
            order = []
        if expansions is None:
            expansions = []
        assert all(len(x) in (2, 3) for x in order), ('Each order item have 2 '
            'or 3 elements')
        self.table = table
        self.rows = rows
        self.columns = columns
        self.measures = measures
        self.order = order
        self.expansions = expansions

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
                # Prepare the first level of the table, this name always will
                # be the name we get form the database
                header_cell = Cell(cube_rows[0], type=CellType.ROW_HEADER)
                header_cell.expansion = cube_rows[0]
                if cube_rows[0] in self.expansions:
                    header_cell.expansion = None
                row.append(header_cell)
                row += [Cell('', type=CellType.ROW_HEADER)]*len(cube_rows)
            else:
                # Each list "r" must have only one element with a value, this
                # element will be always the last element of the list with
                # text. An example of what we do here is:
                # r = ['Element1', 'Subelement1'] -> row = [None, 'Subelement1']
                last_item = [lt for lt in [
                    next(item for item in reversed(r) if item is not None)]][0]

                # The empty row at the start represnet the column where we have
                # total
                row.append(Cell('', type=CellType.ROW_HEADER))
                for element in r:
                    if element and element == last_item:
                        # In the case of being in the last element of the list,
                        # we can know that there are no more expansions
                        if element == r[-1]:
                            row.append(Cell(element.value, type=CellType.ROW_HEADER))
                        else:
                            # Here we are calculating the expansion of this
                            # cell. Here is an example:
                            # r = ['Element1', None] -> ['Element1']
                            element_expansion = [e.value for e in r[:r.index(element)+1]]
                            if element_expansion in self.expansions:
                                element_expansion = None

                            print('ELEMENT EXPANSION: ', element_expansion)
                            row.append(Cell(element.value, type=CellType.ROW_HEADER,
                                expansion=element_expansion))
                    else:
                        row.append(Cell('', type=CellType.ROW_HEADER))
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
        row_extra_space = [Cell('', type=CellType.COLUMN_HEADER)]*(len(self.rows)+1)

        column_header = []
        # We need to add one extra number to the range to represent the total
        # cell (coordinate None)
        for i in range(len(cube_columns)+1):
            column = []
            for row in columns_in_rows:
                column.append(Cell(row[i].value, type=CellType.COLUMN_HEADER,
                    expansion=row[i].expansion))
                # We need to substrac 1 to the measure length because the firt
                # space is were the name of the column go
                for y in range(len(self.measures)-1):
                    column.append(Cell('', type=CellType.COLUMN_HEADER))
            column_header.append(row_extra_space + column)

        # Add the measure information row
        measure_names = [Cell(m[0], type=CellType.COLUMN_HEADER) for m in self.measures]
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
        self.expansions = sorted(self.expansions, key=len)

        # Format the measures to use them in the query
        measures = ','.join(
            [f'{measure[1]}({measure[0]})' for measure in self.measures])
        cursor = Transaction().connection.cursor()
        values = OrderedDict()
        for rowxcolumn in rxc:
            print(f'  RC: {rowxcolumn}')
            # Transform the list of coordinates into a string to use it in the
            # query
            groupby_columns = ','.join([rc for rowcolumn in rowxcolumn
                for rc in rowcolumn if rc != None])

            # TODO: There's a huge SQL injection issue in this code

            # In the case of having all the columns as "None", it means we are
            # in the first level and we dont need to do a group by
            if groupby_columns:
                query = (f'SELECT {groupby_columns}, {measures} FROM '
                    f'{self.table} GROUP BY {groupby_columns}')
            else:
                query = f'SELECT {measures} FROM {self.table}'

            # Prepare the order we need to use in the query
            order = []
            for item in self.order:
                if len(item) == 2:
                    for column in groupby_columns.split(","):
                        if column == item[0]:
                            order.append(f'{item[0]} {item[-1]}')
                elif len(item) == 3:
                    for measure in self.measures:
                        if measure == item[:-1]:
                            order.append(f'{item[1]}({item[0]}) {item[-1]}')

            if order:
                query += f' ORDER BY {",".join(order)}'

            print(f'  QUERY: {query}')
            cursor.execute(query)
            results = cursor.fetchall()
            # If we dont have any expansion -> we are in the level 0
            # TODO: We need a "special" case to show all levels
            for result in results:
                result = [Cell(x) for x in result]
                coordinates = self.get_value_coordinate(result, rowxcolumn)
                # To know which part of the result is the key and which is the
                # value of the measures we use the lenght of the
                # "groupby_columns", this variable is a string with the list of
                # columns we use for the group by in postgresql

                # We need to show always the level 0, so this level skip the
                # expansions checks
                if (coordinates != tuple([ tuple([None]*len(self.rows)), tuple(
                    [None]*len(self.columns))])):

                    if self.expansions:
                        for expansion in self.expansions:
                            print(f'Expansion: {expansion}')
                            # First we check if the type of the expansion if is
                            # a str it means is one of the default headers from
                            # level 0
                            if isinstance(expansion, str):
                                # In this case, first we need to check what
                                # measure comes the expansion
                                pass
                            else:
                                # If its a list it means is one of the headers from
                                # level 1 or above
                                pass
                    else:
                        # If we dont have any expansion it mean we dont need
                        # to check anythyng and dont show any level (except the
                        # level 0 that skip the checks)
                        continue

                if groupby_columns:
                    # If we have the groupby_columns attribute, we get all the
                    # values since the last column that is not a group by
                    # column
                    values[coordinates] = result[
                        len(groupby_columns.split(",")):]
                else:
                    # In the case we have all the columns as none, the result
                    # will equal the number of measures we have
                    values[coordinates] = result
        print(f'VALUES: {len(values)}')
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

        # TODO: for each cell header, know the expansion we need to do
        row_header = self.get_row_header(row_elements, self.rows)
        table = self.get_column_header(col_elements, self.columns)
        for row in table:
            yield row
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
            yield table_row

    def encode_properties(self):
        '''
        Given a cube instance, return a string with the properties of the cube.
        Make the trasformation using the urllib.parse.urlencode function
        '''
        cube_properties = self.__dict__
        # We need to delte the table property because it is already in the url
        del cube_properties['table']
        return urlencode(self.__dict__, doseq=True)

    @classmethod
    def parse_properties(cls, url, table_name=None):
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

    def __init__(self, value, type=CellType.VALUE, expansion=None):
        self.value = value
        # Use as a type an enum, it is much faster than a dictionary
        self.type = type
        self.expansion = expansion

    def text(self, lang=None):
        if not lang:
            return str(self)

        value = self.value
        if value is None:
            return '-'
        if isinstance(value, (float, Decimal)):
            # TODO: Make it configurable
            digits = 2
            return lang.format('%.*f', (digits, value),
                grouping=True)
        if isinstance(value, bool):
            return (gettext('babi.msg_yes') if value else
                gettext('babi.msg_no'))
        if isinstance(value, int):
            return lang.format('%d', value, grouping=True)
        if isinstance(value, datetime):
            return lang.strftime(value)
        if isinstance(value, date):
            return lang.strftime(value)
        if isinstance(value, timedelta):
            return strfdelta(value, '{hours}:{minutes}')
        if isinstance(value, str):
            return value.replace('\n', '<br/>')
        if isinstance(value, bytes):
            value = binascii.b2a_base64(value)
            value = value.decode('ascii')
            return ('data:%s;base64,%s' % (DEFAULT_MIME_TYPE, value)).strip()
        return str(value)

    def __str__(self):
        if self.value is None:
            return '-'
        if isinstance(self.value, (float, Decimal)):
            return f'{self.value:.2f}'
        return str(self.value)

    def __eq__(self, value):
        if isinstance(value, Cell):
            return self.value == value.value and self.type == value.type
        return False

    def __hash__(self):
        return hash((self.value, self.type))
