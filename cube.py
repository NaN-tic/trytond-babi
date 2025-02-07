import ast
import binascii
import hashlib
import sql
from datetime import datetime, date, timedelta
from decimal import Decimal
from itertools import product
from collections import OrderedDict
from enum import Enum
from urllib.parse import urlencode, parse_qs
from trytond.config import config
from trytond.i18n import gettext
from trytond.transaction import Transaction
from trytond import backend

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

def capitalize(string):
    return ' '.join([word.capitalize() for word in string.split('_')])


class Cube:
    def __init__(self, table=None, rows=None, columns=None, measures=None,
            properties=None, order=None, expansions_rows=None,
            expansions_columns=None):
        '''
        order must have the following format:
        [('column_name', 'asc'), ('column_name', 'desc'), (('measure', 'sum'), 'asc')]
        '''
        if rows is None:
            rows = []
        if columns is None:
            columns = []
        if measures is None:
            measures = []
        if properties is None:
            properties = []
        if order is None:
            order = []
        if expansions_rows is None:
            expansions_rows = []
        if expansions_columns is None:
            expansions_columns = []

        assert all(len(x) == 2 for x in order), ('Each order item must '
            'have 2 elements')
        self.table = table
        self.rows = rows
        self.columns = columns
        self.measures = measures
        self.properties = properties
        self.order = order
        self.expansions_rows = expansions_rows
        self.expansions_columns = expansions_columns

    def clear_cache(self):
        cursor = Transaction().connection.cursor()
        if backend.name == 'postgresql':
            table = sql.Table('tables', schema='information_schema')
            query = table.select(table.table_name, where=(
                    table.table_schema == 'public') &
                (table.table_name.like(self.cache_prefix() + '%')))
        else:
            table = sql.Table('sqlite_master')
            query = table.select(table.name, where=(table.type == 'table') &
                (table.name.like(self.cache_prefix() + '%')))
        cursor.execute(*query)
        for cache in [x[0] for x in cursor.fetchall()]:
            cursor.execute('DROP TABLE IF EXISTS "%s"' % cache)

    @staticmethod
    def clear_orphan_caches(tables):
        # Remove all cache tables that are not in use by any of the tables
        prefixes = []
        for table in tables:
            cube = Cube(table)
            prefixes.append(cube.cache_prefix())
        cursor = Transaction().connection.cursor()
        if backend.name == 'postgresql':
            table = sql.Table('tables', schema='information_schema')
            query = table.select(table.table_name,
                where=(table.table_schema == 'public') &
                (table.table_name.like('_babi_cache_%')))
        else:
            table = sql.Table('sqlite_master')
            query = table.select(table.name,
                where=(table.type == 'table') &
                (table.name.like('_babi_cache_%')))
        cursor.execute(*query)
        for cache in [x[0] for x in cursor.fetchall()]:
            for prefix in prefixes:
                if cache.startswith(prefix):
                    break
            else:
                cursor.execute('DROP TABLE IF EXISTS "%s"' % cache)

    def cache_prefix(self):
        h = hashlib.md5(self.table.encode()).hexdigest()[:20]
        return f'_babi_cache_{h}_'

    def get_data(self, query, orderby):
        cursor = Transaction().connection.cursor()

        cursor.execute('SAVEPOINT babi_cube')
        try:
            mogrified = cursor.mogrify(*query)
            cache = self.cache_prefix() + hashlib.md5(mogrified).hexdigest()[:20]
            mogrified = mogrified.decode('utf-8')
            unlogged = ''
            if backend.name == 'postgresql':
                unlogged = 'UNLOGGED'

                # Even if we use CREATE TABLE IF NOT EXISTS, we need to do an
                # explicit lock in order to prevent an error when two transactions
                # try to create the same table. See:
                # https://stackoverflow.com/questions/29900845/create-schema-if-not-exists-raises-duplicate-key-error
                lock_id = int(hashlib.sha1(cache.encode("utf-8")).hexdigest(), 16) % (2 ** 63)
                cursor.execute(f'SELECT pg_advisory_xact_lock({lock_id})')

            # TODO: We could have some performance improvements if we did not
            # depend on the order of the fields in the query. That would probably mean
            # that get_values() should sort groupby fields alphabetically and then
            # be able to pick the right values from the result tuple
            # (probably using DictCursor)
            cursor.execute(f"CREATE {unlogged} TABLE IF NOT EXISTS {cache} AS {mogrified}")

            table = sql.Table(cache)
            query_order = []
            for field, order in orderby:
                query_order.append(
                    self.apply_order(getattr(table, field), order))

            cursor.execute(*table.select(order_by=query_order))
            records = cursor.fetchall()
            cursor.execute('RELEASE SAVEPOINT babi_cube')
        except:
            cursor.execute('ROLLBACK TO SAVEPOINT babi_cube')
            raise
        return records

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
        the key of the dictionary of values we need to use. The strucutre we
        follow is:
            result: ('Party Name 1', Decimal('10.01'))
            rxc: ([None, None], ['party_name'])
        The key we end calculating will be:
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
                    result[index].type = CellType.ROW_HEADER
                    rowxcolumn_coordinate.append(result[index])
                    index += 1
            key.append(tuple(rowxcolumn_coordinate))
        return tuple(key)

    def get_row_header(self, rows, cube_rows):
        '''
        Given a list of all the row headers ordered, return a list with the
        header cells. The structre we follow is:
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
                if cube_rows:
                    value = cube_rows[0]
                else:
                    value = ''
                header_cell = Cell(value, type=CellType.ROW_HEADER)
                header_cell.expansion_row = tuple([None]*(len(cube_rows)))
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
                            row.append(element.copy(type=CellType.ROW_HEADER))
                        else:
                            # Here we are calculating the expansion of this
                            # cell. Here is an example:
                            # r = ['Element1', None] -> ['Element1']
                            element_expansion = tuple([e.value for e in r[:r.index(element)+1]])
                            row.append(element.copy(type=CellType.ROW_HEADER,
                                expansion_row=element_expansion))
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
                element_expansion = row[i].expansion_row
                if element_expansion == tuple([None]*len(self.rows)):
                    element_expansion = tuple([None]*len(self.columns))
                column.append(Cell(row[i].value, type=CellType.COLUMN_HEADER,
                    expansion_column=element_expansion))
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

    @classmethod
    def measure_method(cls, table, measure):
        field = measure[0]
        aggregate = measure[1]
        if aggregate == 'average':
            aggregate = 'avg'
        Operator = getattr(sql.aggregate, aggregate.capitalize())
        return Operator(getattr(table, field)).as_(cls.measure_name(measure))

    @classmethod
    def measure_name(cls, measure):
        field = measure[0]
        aggregate = measure[1]
        return f'{aggregate}_{field}__'

    @classmethod
    def property_name(cls, property):
        return f'prop_{property}__'

    @staticmethod
    def apply_order(field, order):
        if order == 'asc':
            return field.asc
        else:
            return field.desc

    def get_values(self):
        '''
        Calculate the values of the cube. Returns a tuple of OrderedDicts:
        (values, property_values). Both dictionaries follow the same structure
        where the key is a tuple of (row, column) coordinates and the value is
        a tuple of cells. The values dictionary contains the values of the
        measures and the property_values dictionary contains the values of the
        properties. Ie.:

        {
            ((Cell('Party Name 1'), Cell(None)), (Cell('Type'), Cell(None))):
                (Cell(value1), Cell(value2)),
        }
        '''
        rows = self.get_query_list(self.rows)
        columns = self.get_query_list(self.columns)

        # Get the cartesian product between the rows and columns
        rxc = list(product(rows, columns))

        table = sql.Table(self.table)
        # Format the measures and properties to use them in the query
        measures = [self.measure_method(table, x) for x in self.measures]
        # We could use DISTINCT ON but unfortunately it is not standard and
        # not supported by SQLite
        # See: https://www.postgresql.org/docs/17/sql-select.html#SQL-DISTINCT
        properties = [sql.aggregate.Min(
                getattr(table, x)).as_(self.property_name(x))
            for x in self.properties]
        values = OrderedDict()
        property_values = OrderedDict()
        for rowxcolumn in rxc:
            groupby = [rc for rowcolumn in rowxcolumn
                for rc in rowcolumn if rc != None]

            # Prepare the order we need to use in the query
            orderby = []
            for item in self.order:
                if isinstance(item[0], tuple):
                    orderby.append((self.measure_name(item[0]), item[1]))
                else:
                    if item[0] in groupby:
                        orderby.append(item)

            groupby = [getattr(table, x) for x in groupby]
            fields = groupby + measures + properties
            query = table.select(*fields, group_by=groupby)
            results = self.get_data(query, orderby)

            # If we dont have any expansion -> we are in the level 0
            # TODO: We need a "special" case to show all levels list
            #  |-> use expansions / None -> open everything
            default_row_coordinates = tuple([None] * len(self.rows))
            default_column_coordinates = tuple([None] * len(self.columns))
            for raw_result in results:
                if properties:
                    result = [Cell(x) for x in raw_result[:-len(properties)]]
                else:
                    result = [Cell(x) for x in raw_result]
                coordinates = self.get_value_coordinate(result, rowxcolumn)

                if properties and coordinates[0] and coordinates[0][-1] is not None:
                    coordinates[0][-1].properties = raw_result[-len(properties):]

                # Get the row values from the coordinates
                row_coordinate_values = tuple(
                    [c.value if c else None for c in coordinates[0]])
                row_ok = False
                if self.expansions_rows:
                    for expansion_row in self.expansions_rows:
                        # If the expression is equal to the default coords, it
                        # means we try to open the first level, we check if all
                        # elements except the first are None
                        if expansion_row == default_row_coordinates:
                            if (row_coordinate_values[1:len(expansion_row)] ==
                                    tuple([None]*(len(self.rows)-1))):
                                row_ok = True
                                break
                        # In any other case, we check if the expansion is
                        # inside the coordinate
                        elif ((row_coordinate_values[:len(expansion_row)]
                                == expansion_row)
                                and (len(row_coordinate_values)
                                     - row_coordinate_values.count(None)
                                     == len(expansion_row) + 1)):
                            row_ok = True
                            break
                else:
                    # If we don't have any expansions, we only allow the rows
                    # with the default value
                    if row_coordinate_values == default_row_coordinates:
                        row_ok = True

                # Get the column values from the coordinates
                column_coordinate_values = tuple(
                    [c.value if c else None for c in coordinates[1]])
                column_ok = False
                if self.expansions_columns:
                    for expansion_column in self.expansions_columns:
                        # If the expression is equal to the default coords, it
                        # means we try to open the first level, we check if all
                        # elements except the first are None
                        if expansion_column == default_column_coordinates:
                            if (column_coordinate_values[1:len(expansion_column)] ==
                                    tuple([None]*(len(self.columns)-1))):
                                column_ok = True
                                break
                        # In any other case, we check if the expansion is
                        # inside the coordinate
                        elif ((column_coordinate_values[:len(expansion_column)]
                                == expansion_column)
                                and (len(column_coordinate_values)
                                     - column_coordinate_values.count(None)
                                     == len(expansion_column) + 1)):
                            column_ok = True
                            break
                else:
                    # If we don't have any expansions, we only allow the columns
                    # with the default value
                    if column_coordinate_values == default_column_coordinates:
                        column_ok = True

                if row_ok and column_ok:
                    if groupby:
                        # If we have the groupby_columns attribute, we get all the
                        # values since the last column that is not a group by
                        # column
                        values[coordinates] = result[len(groupby):]
                    else:
                        # In the case we have all the columns as none, the result
                        # will equal the number of measures we have
                        values[coordinates] = result
        return values, property_values

    def build(self):
        '''
        Create the table with values from a cube object. Return a list of lists
        with the format:
            table = [[Cell, Cell, Cell, Cell], [Cell, Cell, Cell, Cell]]
        '''
        values, property_values = self.get_values()

        def get_rows(values, key, nones, depth, added):
            res = []
            for row, col in values.keys():
                if row.count(None) != nones:
                    continue
                rk = row[:len(key)]
                if rk != key:
                    continue
                if row in added:
                    continue
                added.add(row)
                res.append(row)
                res += get_rows(values, row[:depth], nones-1, depth+1, added)
            return res

        def get_cols(values, key, nones, depth, added):
            res = []
            for row, col in values.keys():
                if col.count(None) != nones:
                    continue
                ck = col[:len(key)]
                if ck != key:
                    continue
                if col in added:
                    continue
                added.add(col)
                res.append(col)
                res += get_cols(values, col[:depth], nones-1, depth+1, added)
            return res

        added = set()
        row_elements = [tuple([None]*len(self.rows))]
        row_elements += get_rows(values, (), len(self.rows)-1, 1, added)
        added = set()
        col_elements = [tuple([None]*len(self.columns))]
        col_elements += get_cols(values, (), len(self.columns)-1, 1, added)

        # TODO: for each cell header, know the expansion we need to do
        row_header = self.get_row_header(row_elements, self.rows)
        table = self.get_column_header(col_elements, self.columns)
        count = 0
        for row in table:
            count += 1
            if self.properties:
                if row_header:
                    length = len(row_header[0])
                else:
                    length = 0
                nrow = row[:length]
                if count == len(table):
                    nrow += [Cell(x, type=CellType.ROW_HEADER) for x in self.properties]
                else:
                    nrow += [Cell('', type=CellType.ROW_HEADER)] * len(self.properties)
                nrow += row[length:]
                row = nrow
            yield row
        for row in range(len(row_elements)):
            table_row = row_header[row]
            if self.properties:
                if row_header:
                    length = len(row_header[0])
                else:
                    length = 0
            if self.properties:
                props = table_row[-1].properties or [''] * len(self.properties)
                table_row += [Cell(x, type=CellType.ROW_HEADER) for x in props]
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
        # We need to delete the table property because it is already in the url
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

        if cube_properties.get('expansions_rows'):
            cube_properties['expansions_rows'] = [
                ast.literal_eval(m) for m in cube_properties['expansions_rows']]

        if cube_properties.get('expansions_columns'):
            cube_properties['expansions_columns'] = [
                ast.literal_eval(m) for m in cube_properties['expansions_columns']]

        if table_name:
            cube_properties['table'] = table_name
        return cls(**cube_properties)


class CellType(Enum):
    VALUE = 0
    ROW_HEADER = 1
    COLUMN_HEADER = 2


class Cell:
    __slots__ = ('value', 'type', 'expansion_row', 'expansion_column', 'properties')

    def __init__(self, value=None, type=CellType.VALUE, expansion_row=None,
            expansion_column=None, properties=None):
        self.value = value
        # Use as a type an enum, it is much faster than a dictionary
        self.type = type
        self.expansion_row = expansion_row
        self.expansion_column = expansion_column
        self.properties = properties

    def formatted(self, lang=None, excel=False):
        if not lang:
            return str(self)

        value = self.value
        if value is None:
            return '-'
        if isinstance(value, (float, Decimal)):
            # TODO: Make digits configurable
            digits = 2
            if excel:
                return round(value, digits)
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

    def __repr__(self):
        return f'<Cell {self.value} {self.type}>'

    def __eq__(self, value):
        if isinstance(value, Cell):
            return self.value == value.value and self.type == value.type
        return False

    def __hash__(self):
        return hash((self.value, self.type))

    def copy(self, **kwargs):
        new = Cell(self.value, self.type, self.expansion_row,
            self.expansion_column, self.properties)
        for arg in kwargs:
            setattr(new, arg, kwargs[arg])
        return new
