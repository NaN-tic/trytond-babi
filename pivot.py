import ast
import re
import json
from itertools import product
from enum import Enum
from werkzeug.routing import Rule
from werkzeug.utils import redirect
from dominate.tags import (div, h1, p, a, form, button, span, table, thead,
    tbody, tr, td, head, html, meta, link, title, script, h3, comment, select,
    option, main, th)
from dominate.util import raw
from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction
from trytond.modules.voyager.voyager import Component
from trytond.modules.voyager.i18n import _
from werkzeug.wrappers import Response
from decimal import Decimal
from urllib.parse import urlencode, parse_qs

from trytond.protocols.jsonrpc import JSONEncoder, JSONDecoder
from collections import deque, OrderedDict

# Icons used in website
COLLAPSE = '➖'
EXPAND = '➕'
SWAP_AXIS = raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M7.5 21 3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5" /></svg>')
RELOAD = raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99" /></svg>')
DOWNLOAD = raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3" /></svg>')
ROWS_ICON = raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6" transform="rotate(90)"><path stroke-linecap="round" stroke-linejoin="round" d="M9 4.5v15m6-15v15m-10.875 0h15.75c.621 0 1.125-.504 1.125-1.125V5.625c0-.621-.504-1.125-1.125-1.125H4.125C3.504 4.5 3 5.004 3 5.625v12.75c0 .621.504 1.125 1.125 1.125Z" /></svg>')
COLUMNS_ICON = raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M9 4.5v15m6-15v15m-10.875 0h15.75c.621 0 1.125-.504 1.125-1.125V5.625c0-.621-.504-1.125-1.125-1.125H4.125C3.504 4.5 3 5.004 3 5.625v12.75c0 .621.504 1.125 1.125 1.125Z" /></svg>')
MEASURE_ICON = raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 0 1-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 0 1 4.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0 1 12 15a9.065 9.065 0 0 0-6.23-.693L5 14.5m14.8.8 1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0 1 12 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5" /></svg>')
ADD_ICON = raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15" /></svg>')
REMOVE_ICON = raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M5 12h14" /></svg>')
UP_ARROW = raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 10.5 12 3m0 0 7.5 7.5M12 3v18" /></svg>')
DOWN_ARROW = raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M19.5 13.5 12 21m0 0-7.5-7.5M12 21V3" /></svg>')
CLOSE_ICON = raw('<svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>')


class Site(metaclass=PoolMeta):
    __name__ = 'www.site'

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls.type.selection += [('babi_pivot', 'Pivot')]

    @classmethod
    def dispatch(cls, site_type, site_id, request, user):
        with Transaction().set_context(language=Transaction().language):
            return super().dispatch(site_type, site_id, request, user)


###############################################################################
#################################### CUBE #####################################
###############################################################################
class Cube:
    def __init__(self, rows=[], columns=[], measures=[], table=None,
            order=[], expansions=[]):
        self.table = table # We need the table name to make the query
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
                    #print(f'- CELL TYPE: {result[index].type}')
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

        cursor = Transaction().connection.cursor()
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

###############################################################################
#################################### SITE #####################################
###############################################################################


class Layout(Component):
    'Layout'
    __name__ = 'www.layout.pivot'
    _path = None
    __slots__ = ['main']

    title = fields.Char('Title')

    def __init__(self, *args, **kwargs):
        self.main = div()
        super().__init__(*args, **kwargs)

    def render(self):
        site = self.site

        html_layout = html()
        with html_layout:
            with head():
                meta(charset='utf-8')
                meta(name='viewport',
                    content='width=device-width, initial-scale=1')
                if site.metadescription:
                    meta(name='description', content=site.metadescription)
                if site.keywords:
                    meta(name='keywords', content=site.keywords)
                if hasattr(self, 'title'):
                    title(self.title)
                if site.canonical:
                    meta(name='canonical', href=f'{site.url} {site.canonical}')
                if site.author:
                    meta(name='author', content=site.author)
                comment('CSS')
                link(href="/static/output.css", rel="stylesheet")
                script(src='https://unpkg.com/htmx.org@2.0.0')
                script(src="https://cdn.tailwindcss.com")
            main_body = div(id='main', cls='bg-white')
            flash_div = div(id='flash_messages',
                cls="flex w-full flex-col items-center space-y-4 sm:items-end")
            flash_div['hx-swap-oob'] = "afterbegin"
            main_body += flash_div
            main_body += self.main
        return html_layout


class Index(Component):
    'Index'
    __name__ = 'www.index.pivot'
    _path = None

    database_name = fields.Char('Database Name')
    table_name = fields.Char('Table Name')
    table_properties = fields.Char('Table Properties')

    @classmethod
    def get_url_map(cls):
        #TODO: we need to hande multiple URLs with the same endpoint
        return [
            #Rule('/<string:database_name>/babi/pivot/<string:table_name>/'),
            #Rule('/<string:database_name>/babi/pivot/<string:table_name>'),
            Rule('/<string:database_name>/babi/pivot/<string:table_name>/<string:table_properties>'),
        ]

    def render(self):
        pool = Pool()
        BabiTable = pool.get('babi.table')
        # Components
        PivotHeaderAxis = pool.get('www.pivot_header.axis')
        PivotHeaderMeasure = pool.get('www.pivot_header.measure')
        PivotTable = pool.get('www.pivot_table')

        '''
            We need to:
            - Show the header:
                - Show the button to invert axis
                - Show the button to relad the page with a new configuration
            - Show the table headers:
                - Show the row table header
                - Show the column table header
                - Show the measure table header (aggregation)
                - Show the order table header
            - Once a value is selected in a table, we cant show this value in
                the other tables
            - In the order table, we need to show the aggregation of the
                columns we have in the row, column and measure headers
            - If we delete a cell from any of the table that is begin used in
                the order table, we need to delete the field from the order table
            - If we delte a cell from the order table, we dont need to do
                anything apart of realoading the table
        '''

        table_name = self.table_name
        print(f'Table Name: {table_name}')
        if table_name.startswith('__'):
            table_name = table_name.split('__')[-1]

        babi_table = BabiTable.search([
            ('internal_name', '=', table_name)], limit=1)

        # Check if the user can see the table, if not, return an error page
        access = False
        if babi_table:
            babi_table, = babi_table
            table_name = babi_table.name
            access = babi_table.check_access()

        if not access or not babi_table:
            # TODO: move the error page to a component, this way we call the same error in multiple places
            with main(cls="grid min-h-full place-items-center bg-white px-6 py-24 sm:py-32 lg:px-8") as error_section:
                with div(cls="text-center"):
                    p(_('404'), cls="text-base font-semibold text-indigo-600")
                    h1(_('Page not found'), cls="mt-4 text-3xl font-bold tracking-tight text-gray-900 sm:text-5xl")
                    p(_('Sorry, we couldn’t find the page you’re looking for.'), cls="mt-6 text-base leading-7 text-gray-600")
            layout = Layout(title=_('Page not found | Tryton'))
            layout.main.add(error_section)
            return layout.tag()

        # Check if we have the cube properties to see the table, if not, show a messagge
        show_error = True
        if not hasattr(self, 'table_properties'):
            table_properties = 'null'
        else:
            if self.table_properties == 'null':
                cube = Cube(table=babi_table.name)
            else:
                print(f'TABLE PROPERTIES: {self.table_properties}')
                cube = Cube.parse_cube_properties(self.table_properties, table_name)

            print('==== AAA ====')
            #import pdb; pdb.set_trace()
            print(f'ROWS: {cube.rows}\nCOLUMNS: {cube.columns}\nMEASURES: {cube.measures}')
            if cube.rows and cube.columns and cube.measures:
                show_error = False

        # Prepare the cube properties to the invert cube function
        axuiliar_row = cube.rows
        cube.rows = cube.columns
        cube.columns = axuiliar_row
        inverted_table_properties = cube.encode_cube_properties()

        with main() as index_section:
            with div(cls="border-b border-gray-200 bg-white px-4 py-5 sm:px-6 grid grid-cols-4"):
                div(cls="col-span-1").add(h3(table_name, cls="text-base font-semibold leading-6 text-gray-900"))
                # Invert axis button
                with div(cls="col-span-1"):
                    a(href=Index(database_name=self.database_name, table_name=self.table_name, table_properties=inverted_table_properties, render=False).url(),
                        cls="absolute right-12").add(SWAP_AXIS)
                # Empty cube properties
                with div(cls="col-span-1"):
                    a(href=Index(database_name=self.database_name, table_name=self.table_name, table_properties='null', render=False).url(),
                        cls="absolute right-3").add(RELOAD)
            with div(cls="grid grid-cols-12"):
                PivotHeaderAxis(database_name=self.database_name,
                    table_name=self.table_name, axis='x',
                    table_properties=self.table_properties)
                PivotHeaderAxis(database_name=self.database_name,
                    table_name=self.table_name, axis='y',
                    table_properties=self.table_properties)
                PivotHeaderMeasure(database_name=self.database_name,
                    table_name=self.table_name,
                    table_properties=self.table_properties)

            print(f'SHOW ERROR: {show_error}')
            #TODO: add table
            with div(cls="mt-8 flow-root"):
                with div(cls="-mx-4 -my-2 overflow-x-auto sm:-mx-6 lg:-mx-8"):
                    if show_error == True:
                        div(cls="text-center").add(p(_('You need to select at least one field in each column to show a table'), cls="mt-1 text-sm text-gray-500"))
                    else:
                        PivotTable(database_name=self.database_name, table_name=self.table_name,
                            table_properties=self.table_properties)
        layout = Layout(title=f'{table_name} | Tryton')
        layout.main.add(index_section)
        return layout.tag()


# This class handle the row/columns table headers
class PivotHeaderAxis(Component):
    'Pivot Header Axis'
    __name__ = 'www.pivot_header.axis'
    _path = None

    header = fields.Char('Header')
    database_name = fields.Char('Database Name')
    table_name = fields.Char('Table Name')
    table_properties = fields.Char('Table Properties')
    axis = fields.Char('Axis')

    @classmethod
    def get_url_map(cls):
        return [
            Rule('/<string:database_name>/babi/pivot/<string:table_name>/header/<string:axis>/<string:table_properties>'),
        ]

    def render(self):
        pool = Pool()
        PivotHeader = pool.get('www.pivot_header')
        PivotHeaderSelection = pool.get('www.pivot_header.selection')

        if not self.axis or self.axis not in ['x', 'y']:
            #TODO: add error "Page not found"
            raise

        fields = []
        cube = None
        if self.table_properties != 'null':
            cube = Cube.parse_cube_properties(self.table_properties, self.table_name)

        if self.axis == 'x':
            icon = ROWS_ICON
            name = _('Rows')
            if cube:
                fields = cube.rows
        else:
            icon = COLUMNS_ICON
            name = _('Columns')
            if cube:
                fields = cube.columns

        self.header = name
        with div(cls="px-4 sm:px-6 lg:px-8 mt-8 flow-root col-span-3", id=f'header_{self.axis}') as header_axis:
            div(id=f'field_selection_{self.axis}')
            with div(cls="-mx-4 -my-2 overflow-x-auto sm:-mx-6 lg:-mx-8"):
                with div(cls="inline-block min-w-full py-2 align-middle sm:px-6 lg:px-8"):
                    with table(cls="min-w-full divide-y divide-gray-300"):
                        with thead():
                            with tr():
                                th(scope="col", cls="relative py-3.5 pl-3 pr-4 sm:pr-0").add(icon)
                                th(name, scope="col", cls="py-3.5 pl-4 pr-3 text-left text-sm font-semibold text-gray-900 sm:pl-0")
                                th(scope="col", cls="relative py-3.5 pl-3 pr-4 sm:pr-0").add(span(_('Up'), cls="sr-only"))
                                th(scope="col", cls="relative py-3.5 pl-3 pr-4 sm:pr-0").add(span(_('Down'), cls="sr-only"))
                                with th(scope="col", cls="relative py-3.5 pl-3 pr-4 sm:pr-0"):
                                    a(href="#", cls="text-indigo-600 hover:text-indigo-900",
                                        hx_target=f"#field_selection_{self.axis}",
                                        hx_post=PivotHeaderSelection(header=self.axis, database_name=self.database_name, table_name=self.table_name, table_properties=self.table_properties, render=False).url(),
                                        hx_trigger="click", hx_swap="outerHTML").add(ADD_ICON)
                                    span(_('Add'), cls="sr-only")
                        with tbody(cls="divide-y divide-gray-200"):
                            for field in fields:
                                with tr():
                                    td(field.capitalize(), colspan="2", cls="whitespace-nowrap px-3py-4 pl-4 pr-3 text-sm font-medium text-gray-900 sm:pl-0")
                                    with td(cls="relative whitespace-nowrap py-4 pl-3 pr-4 text-right text-sm font-medium sm:pr-0"):
                                        if field != fields[0]:
                                            a(href=PivotHeader(database_name=self.database_name, table_name=self.table_name, header=self.header, field=field, table_properties=self.table_properties, level_action='up', render=False).url('level_field'),
                                                cls="text-indigo-600 hover:text-indigo-900").add(UP_ARROW)
                                    with td(cls="relative whitespace-nowrap py-4 pl-3 pr-4 text-right text-sm font-medium sm:pr-0"):
                                        if field != fields[-1]:
                                            a(href=PivotHeader(database_name=self.database_name, table_name=self.table_name, header=self.header, field=field, table_properties=self.table_properties, level_action='down', render=False).url('level_field'),
                                                cls="text-indigo-600 hover:text-indigo-900").add(DOWN_ARROW)
                                    with td(cls="relative whitespace-nowrap py-4 pl-3 pr-4 text-right text-sm font-medium sm:pr-0"):
                                        a(href=PivotHeader(database_name=self.database_name, table_name=self.table_name, header=self.header, field=field, table_properties=self.table_properties, render=False).url('remove_field'),
                                            cls="text-indigo-600 hover:text-indigo-900").add(REMOVE_ICON)
        return header_axis


# This class handle the measure table header
class PivotHeaderMeasure(Component):
    'Pivot Header Measure'
    __name__ = 'www.pivot_header.measure'
    _path = None

    header = fields.Char('Header')
    database_name = fields.Char('Database Name')
    table_name = fields.Char('Table Name')
    table_properties = fields.Char('Table Properties')

    @classmethod
    def get_url_map(cls):
        return [
            Rule('/<string:database_name>/babi/pivot/<string:table_name>/header_measure/<string:table_properties>'),
        ]

    def render(self):
        pool = Pool()
        PivotHeader = pool.get('www.pivot_header')
        PivotHeaderSelection = pool.get('www.pivot_header.selection')

        fields = []
        if self.table_properties != 'null':
            cube = Cube.parse_cube_properties(self.table_properties,
                self.table_name)
            fields = cube.measures

        self.header = _('Measures')
        with div(cls="px-4 sm:px-6 lg:px-8 mt-8 flow-root col-span-3", id='header_aggregation') as header_aggregation:
            div(id='field_selection_aggregation')
            with div(cls="-mx-4 -my-2 overflow-x-auto sm:-mx-6 lg:-mx-8"):
                with div(cls="inline-block min-w-full py-2 align-middle sm:px-6 lg:px-8"):
                    with table(cls="min-w-full divide-y divide-gray-300"):
                        with thead():
                            with tr():
                                th(scope="col", cls="relative py-3.5 pl-3 pr-4 sm:pr-0").add(MEASURE_ICON)
                                th(_('Aggregation fields'), scope="col", cls="py-3.5 pl-4 pr-3 text-left text-sm font-semibold text-gray-900 sm:pl-0")
                                th(scope="col", cls="relative py-3.5 pl-3 pr-4 sm:pr-0").add(span(_('Aggregation type'), cls="sr-only"))
                                with th(scope="col", cls="relative py-3.5 pl-3 pr-4 sm:pr-0"):
                                    a(href="#", cls="text-indigo-600 hover:text-indigo-900",
                                        hx_target="#field_selection_aggregation",
                                        hx_post=PivotHeaderSelection(header='aggregation', database_name=self.database_name, table_name=self.table_name, table_properties=self.table_properties, render=False).url(),
                                        hx_trigger="click", hx_swap="outerHTML").add(ADD_ICON)
                                    span(_('Remove'), cls="sr-only")
                        with tbody(cls="divide-y divide-gray-200"):
                            for field in fields:
                                with tr():
                                    td(field[0].capitalize(), colspan="2", cls="whitespace-nowrap px-3py-4 pl-4 pr-3 text-sm font-medium text-gray-900 sm:pl-0")
                                    with td(cls="relative whitespace-nowrap py-4 pl-3 pr-4 text-right text-sm font-medium sm:pr-0"):
                                        with div():
                                            with select(id="aggregation", name="aggregation", cls="mt-2 block w-full rounded-md border-0 py-1.5 pl-3 pr-10 text-gray-900 ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-indigo-600 sm:text-sm sm:leading-6", disabled=True):
                                                option(field[1].capitalize(), value=field)
                                    with td(cls="relative whitespace-nowrap py-4 pl-3 pr-4 text-right text-sm font-medium sm:pr-0"):
                                        a(href=PivotHeader(database_name=self.database_name, table_name=self.table_name, header=self.header, field=field[0], table_properties=self.table_properties, render=False).url('remove_field'),
                                            cls="text-indigo-600 hover:text-indigo-900").add(REMOVE_ICON)
        return header_aggregation


'''
# This class handle the order table header
class PivotHeaderOrder(Component):
    'Pivot Header Component'
    __name__ = 'www.pivot_header.order'
    _path = None

    @classmethod
    def get_url_map(cls):
        return [
        ]

    def render(self):
        pass
'''


class PivotHeaderSelection(Component):
    'Pivot Header Selection'
    __name__ = 'www.pivot_header.selection'
    _path = None

    header = fields.Char('Header')
    database_name = fields.Char('Database Name')
    table_name = fields.Char('Table Name')
    table_properties = fields.Char('Table Properties')
    field = fields.Char('Field')
    aggregation = fields.Char('Aggregation')

    @classmethod
    def get_url_map(cls):
        return [
            Rule('/<string:database_name>/babi/pivot/<string:table_name>/open_field_selection/<string:header>/<string:table_properties>'),
            Rule('/<string:database_name>/babi/pivot/<string:table_name>/close_field_selection/<string:header>/<string:table_properties>', endpoint='close_field_selection'),
            Rule('/<string:database_name>/babi/pivot/<string:table_name>/add_field_selection/<string:header>/<string:table_properties>', endpoint='add_field_selection'),
        ]

    def render(self):
        pool = Pool()

        name = None
        #TODO: we need to handle the order case
        match self.header:
            case 'x':
                name = 'field_selection_x'
            case 'y':
                name = 'field_selection_y'
            case 'aggregation':
                name = 'field_selection_aggregation'
            case 'order':
                name = 'field_selection_order'

        fields_used = []
        if self.table_properties != 'null':
            cube = Cube.parse_cube_properties(self.table_properties,
                self.table_name)
            fields_used = cube.rows + cube.columns + [m[0] for m in cube.measures]

        cursor = Transaction().connection.cursor()
        cursor.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{self.table_name}';")
        fields = cursor.fetchall()

        with div(id=name, cls="relative z-10", aria_labelledby="modal-title", role="dialog", aria_modal="true") as field_slection:
            div(cls="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity", aria_hidden="true")
            with div(cls="fixed inset-0 z-10 w-screen overflow-y-auto"):
                with div(cls="flex min-h-full items-end justify-center p-4 text-center sm:items-center sm:p-0"):
                    with form(action=self.url('add_field_selection') ,method="POST", cls="relative transform overflow-hidden rounded-lg bg-white px-4 pb-4 pt-5 text-left shadow-xl transition-all sm:my-8 sm:w-full sm:max-w-lg sm:p-6"):
                        with div(cls="absolute right-0 top-0 hidden pr-4 pt-4 sm:block"):
                            with a(href="#",
                                    hx_target=f"#{name}",
                                    hx_post=self.url('close_field_selection'),
                                    hx_trigger="click", hx_swap="outerHTML",
                                    cls="rounded-md bg-white text-gray-400 hover:text-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2").add(CLOSE_ICON):
                                span(_('Close'), cls="sr-only")
                                CLOSE_ICON
                        with div(cls="sm:flex sm:items-start"):
                            with div(cls="mt-3 text-center sm:ml-4 sm:mt-0 sm:text-left"):
                                h3(_('Select a field to add:'), cls="text-base font-semibold leading-6 text-gray-900", id="modal-title")
                                with div(cls="mt-2"):
                                    with select(id="field", name="field", cls="mt-2 block w-full rounded-md border-0 py-1.5 pl-3 pr-10 text-gray-900 ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-indigo-600 sm:text-sm sm:leading-6"):
                                        for field in fields:
                                            if field[0] not in fields_used:
                                                option(field[0].capitalize(), value=field[0])
                                    if self.header == 'aggregation':
                                        with select(id="aggregation", name="aggregation", cls="mt-2 block w-full rounded-md border-0 py-1.5 pl-3 pr-10 text-gray-900 ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-indigo-600 sm:text-sm sm:leading-6"):
                                            option(_('Sum'), value='sum')
                                            option(_('Average'), value='average')
                                            option(_('Max'), value='max')
                                            option(_('Min'), value='min')
                                            option(_('Count'), value='count')
                                    if self.header == 'option':
                                        #TODO: we need to handle the order case
                                        pass
                        with div(cls="mt-5 sm:mt-4 sm:flex sm:flex-row-reverse"):
                            button(_('Add'), type="submit", cls="inline-flex w-full justify-center rounded-md bg-blue-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-blue-500 sm:ml-3 sm:w-auto")
                            a(_('Cancel'), href="#",
                                hx_target=f"#{name}",
                                hx_post=self.url('close_field_selection'),
                                hx_trigger="click", hx_swap="outerHTML",
                                hx_vals="{'test': 'THIS IS TEST DATA'}",
                                cls="mt-3 inline-flex w-full justify-center rounded-md bg-white px-3 py-2 text-sm font-semibold text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 hover:bg-gray-50 sm:mt-0 sm:w-auto")
        return field_slection

    def close_field_selection(self):
        name = None
        match self.header:
            case 'x':
                name = 'field_selection_x'
            case 'y':
                name = 'field_selection_y'
            case 'aggregation':
                name = 'field_selection_aggregation'
            case 'order':
                name = 'field_selection_order'

        field_selection = div(id=name)
        return field_selection

    def add_field_selection(self):
        pool = Pool()
        Index = pool.get('www.index.pivot')

        table_properties = 'null'
        if self.table_properties == 'null':
            cube = Cube(table=self.table_name)
        else:
            cube = Cube.parse_cube_properties(self.table_properties,
                self.table_name)

        print(f'\n\nCUBE: {cube}')
        match self.header:
            case 'x':
                cube.rows.append(self.field)
            case 'y':
                cube.columns.append(self.field)
            case 'aggregation':
                cube.measures.append((self.field, self.aggregation))
            case 'order':
                #TODO: we need to handle the order case
                pass

        return redirect(Index(database_name=self.database_name, table_name=self.table_name, table_properties=cube.encode_cube_properties(), render=False).url())


# In this function we have some default options available in all the PivotHeader components (handle levels, remove items from header)
class PivotHeader(Component):
    'Pivot Header'
    __name__ = 'www.pivot_header'
    _path = None

    header = fields.Char('Header')
    database_name = fields.Char('Database Name')
    table_name = fields.Char('Table Name')
    table_properties = fields.Char('Table Properties')
    level_action = fields.Char('Level Action')

    field = fields.Char('Field')

    @classmethod
    def get_url_map(cls):
        return [
            Rule('/<string:database_name>/babi/pivot/<string:table_name>/remove_field/<string:header>/<string:field>/<string:table_properties>', endpoint='remove_field'),
            Rule('/<string:database_name>/babi/pivot/<string:table_name>/level/<string:level_action>/<string:header>/<string:field>/<string:table_properties>', endpoint='level_field'),
        ]

    def render(self):
        pass

    def remove_field(self):
        #TODO: here we only need to delete the field form the correct property
        pass

    def level_field(self):
        #TODO: here we need to level up by 1 element or down by element the field properties
        pass

class PivotTable(Component):
    'Pivot Table'
    __name__ = 'www.pivot_table'
    _path = None

    database_name = fields.Char('Database Name')
    table_name = fields.Char('Table Name')
    table_properties = fields.Char('Table Properties')
    #grouping_fields = fields.Char('Grouping Fields')
    #result_fields = fields.Char('Result Fields')

    @classmethod
    def get_url_map(cls):
        return [
            Rule('/<string:database_name>/babi/pivot/table/<string:table_name>/<string:table_properties>'),
            #Rule('/<string:database_name>/babi/pivot/<string:table_name>/<string:grouping_fields>/<string:result_fields>')
        ]

    def render(self):
        pool = Pool()
        # Component
        DownloadReport = pool.get('www.download_report')

        cube = Cube.parse_cube_properties(self.table_properties, self.table_name)
        cube_table = cube.build()

        '''
        # TODO: we need to handle the expansions
        row.add(td(a(str(icon) +  ' ' + str(table_structure_child_row.name or '(Empty)'), href="#",
                hx_target="#pivot_table",
                hx_post=Pivot(database_name=self.database_name,
                    table_name=self.table, grouping_fields=grouping_fields,
                    result_fields=result_fields, render=False).url(),
                hx_trigger="click", hx_swap="outerHTML"),
            cls="text-xs uppercase bg-gray-300 text-gray-900 px-6 py-3 hover:underline"))
        '''

        '''
        pivot_table_ = table(cls="table-auto text-sm text-left rtl:text-right text-gray-600")
        for row in cube_table:
            pivot_row = tr()
            for cell in row:
                #TODO: som cell are string, not a cell object, fix this
                if isinstance(cell, str):
                    pivot_row.add(td(cell, cls="border-b bg-gray-50 border-gray-000 px-6 py-4 text-right"))
                else:
                    pivot_row.add(td(str(cell.value), cls="border-b bg-gray-50 border-gray-000 px-6 py-4 text-right"))
                #if cell.type == CellType.ROW_HEADER:
                #    pivot_row.add(td(cell, cls="text-xs uppercase bg-gray-300 text-gray-900 px-6 py-3"))
                #else:
                #    pivot_row.add(td(cell, cls="border-b bg-gray-50 border-gray-000 px-6 py-4 text-right"))
            pivot_table_.add(pivot_row)
        '''

        with div(id='pivot_table', cls="inline-block min-w-full py-2 align-middle sm:px-6 lg:px-8") as pivot_div:
            with div(cls="w-10"):
                a(href=DownloadReport(database_name=self.database_name, table_name=self.table_name,
                    table_properties=self.table_properties, render=False).url('download'))
        #pivot_div.add(pivot_table_)
        return pivot_div


class DownloadReport(Component):
    'Download Report'
    __name__ = 'www.download_report'
    _path = None

    database_name = fields.Char('Database Name')
    table_name = fields.Char('Table Name')
    table_properties = fields.Char('Table Properties')

    @classmethod
    def get_url_map(cls):
        return [
            Rule('/<string:database_name>/babi/pivot/download/<string:table_name>/<string:table_properties>/', endpoint="download")
        ]

    def render(self):
        pass

    def download(self):
        cube = Cube.parse_cube_properties(self.table_properties, self.table_name)
        table = cube.build()
        #TODO: transform the list of lists (table) in a xlsx file
        #response = Response(table)
        response = Response(None)
        response.headers['Content-Disposition'] = f'attachment; filename={self.table_name}.xlsx'
        response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        #return response
        pass
