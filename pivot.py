from dominate.tags import (div, h1, p, a, form, button, span, table, thead,
    tbody, tr, td, head, html, meta, link, title, script, h3, comment, select,
    option, main, th, label, input_)
from dominate.util import raw
from openpyxl import Workbook
from openpyxl.writer.excel import save_workbook
import tempfile
from werkzeug.routing import Rule
from werkzeug.utils import redirect
from werkzeug.wrappers import Response
from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction
from trytond.modules.voyager.voyager import Component
from trytond.modules.voyager.i18n import _
from .cube import Cube, CellType


# TODO: Use table.py implementation in 7.2 version and above
def save_virtual_workbook(workbook):
    with tempfile.NamedTemporaryFile() as tmp:
        save_workbook(workbook, tmp.name)
        with open(tmp.name, 'rb') as f:
            return f.read()

# Icons used in website
COLLAPSE = '➖'
EXPAND = '➕'
SWAP_AXIS = raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M7.5 21 3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5" /></svg>')
RELOAD = raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99" /></svg>')
EXPAND_ALL = raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M3.75 3.75v4.5m0-4.5h4.5m-4.5 0L9 9M3.75 20.25v-4.5m0 4.5h4.5m-4.5 0L9 15M20.25 3.75h-4.5m4.5 0v4.5m0-4.5L15 9m5.25 11.25h-4.5m4.5 0v-4.5m0 4.5L15 15" /></svg>')
DOWNLOAD = raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3" /></svg>')
ROWS_ICON = raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6" transform="rotate(90)"><path stroke-linecap="round" stroke-linejoin="round" d="M9 4.5v15m6-15v15m-10.875 0h15.75c.621 0 1.125-.504 1.125-1.125V5.625c0-.621-.504-1.125-1.125-1.125H4.125C3.504 4.5 3 5.004 3 5.625v12.75c0 .621.504 1.125 1.125 1.125Z" /></svg>')
COLUMNS_ICON = raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M9 4.5v15m6-15v15m-10.875 0h15.75c.621 0 1.125-.504 1.125-1.125V5.625c0-.621-.504-1.125-1.125-1.125H4.125C3.504 4.5 3 5.004 3 5.625v12.75c0 .621.504 1.125 1.125 1.125Z" /></svg>')
MEASURE_ICON = raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 0 1-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 0 1 4.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0 1 12 15a9.065 9.065 0 0 0-6.23-.693L5 14.5m14.8.8 1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0 1 12 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5" /></svg>')
ADD_ICON = raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15" /></svg>')
REMOVE_ICON = raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M5 12h14" /></svg>')
UP_ARROW = raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 10.5 12 3m0 0 7.5 7.5M12 3v18" /></svg>')
DOWN_ARROW = raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M19.5 13.5 12 21m0 0-7.5-7.5M12 21V3" /></svg>')
CLOSE_ICON = raw('<svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>')
ORDER_ICON = raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25H12" /></svg>')
ORDER_ASC_ICON = raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M3 4.5h14.25M3 9h9.75M3 13.5h9.75m4.5-4.5v12m0 0-3.75-3.75M17.25 21 21 17.25" /></svg>')
ORDER_DESC_ICON = raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M3 4.5h14.25M3 9h9.75M3 13.5h5.25m5.25-.75L17.25 9m0 0L21 12.75M17.25 9v12" /></svg>')

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
            Rule('/<string:database_name>/babi/pivot/<string:table_name>', endpoint='render_null'),
            Rule('/<string:database_name>/babi/pivot/<string:table_name>/<string:table_properties>'),
        ]

    # Temporal solution to have differents urls with the same endpoint
    def render_null(self):
        return self.render()

    def render(self):
        pool = Pool()
        BabiTable = pool.get('babi.table')
        # Components
        Layout = pool.get('www.layout.pivot')
        PivotHeaderAxis = pool.get('www.pivot_header.axis')
        PivotHeaderMeasure = pool.get('www.pivot_header.measure')
        PivotHeaderOrder = pool.get('www.pivot_header.order')
        PivotTable = pool.get('www.pivot_table')

        '''
        We need to:
        - If we delete a cell from any of the table that is begin used in
            the order table, we need to delete the field from the order table
        - If we delte a cell from the order table, we dont need to do
            anything apart of realoading the table
        '''

        table_name = self.table_name
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

        # Ensure we have a value in table_properties
        if not hasattr(self, 'table_properties'):
            self.table_properties = 'null'

        # Check if we have the cube properties to see the table, if not, show a messagge
        show_error = True
        if self.table_properties == 'null':
            cube = Cube(table=babi_table.name)
        else:
            cube = Cube.parse_properties(self.table_properties, table_name)

        if cube.rows and cube.columns and cube.measures:
            show_error = False

        # Prepare the cube properties to the expand all cube function
        auxiliar_expansion_rows = cube.expansions_rows
        auxiliar_expansions_columns = cube.expansions_columns
        cube.expansions_rows = 'all'
        cube.expansions_columns = 'all'
        expansion_cube_properties = cube.encode_properties()
        cube.expansions_rows = auxiliar_expansion_rows
        cube.expansions_columns = auxiliar_expansions_columns

        # Prepare the cube properties to the invert cube function
        cube.table = table_name
        axuiliar_row = cube.rows
        cube.rows = cube.columns
        cube.columns = axuiliar_row
        inverted_table_properties = cube.encode_properties()

        with main() as index_section:
            with div(cls="border-b border-gray-200 bg-white px-4 py-5 sm:px-6 grid grid-cols-4"):
                div(cls="col-span-1").add(h3(table_name, cls="text-base font-semibold leading-6 text-gray-900"))
                # Each button is a 36px width
                #TODO: Expand all button
                #with div(cls="col-span-1"):
                #    a(href=Index(database_name=self.database_name, table_name=self.table_name, table_properties=expansion_cube_properties, render=False).url(),
                #        cls="absolute right-[84px]").add(EXPAND_ALL)
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
                PivotHeaderOrder(database_name=self.database_name,
                    table_name=self.table_name,
                    table_properties=self.table_properties)

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
            cube = Cube.parse_properties(self.table_properties, self.table_name)

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

        self.header = self.axis
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
                                            a(href=PivotHeader(database_name=self.database_name, table_name=self.table_name, header=self.axis, field=field, table_properties=self.table_properties, level_action='up', render=False).url('level_field'),
                                                cls="text-indigo-600 hover:text-indigo-900").add(UP_ARROW)
                                    with td(cls="relative whitespace-nowrap py-4 pl-3 pr-4 text-right text-sm font-medium sm:pr-0"):
                                        if field != fields[-1]:
                                            a(href=PivotHeader(database_name=self.database_name, table_name=self.table_name, header=self.axis, field=field, table_properties=self.table_properties, level_action='down', render=False).url('level_field'),
                                                cls="text-indigo-600 hover:text-indigo-900").add(DOWN_ARROW)
                                    with td(cls="relative whitespace-nowrap py-4 pl-3 pr-4 text-right text-sm font-medium sm:pr-0"):
                                        a(href=PivotHeader(database_name=self.database_name, table_name=self.table_name, header=self.axis, field=field, table_properties=self.table_properties, render=False).url('remove_field'),
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
            cube = Cube.parse_properties(self.table_properties,
                self.table_name)
            fields = cube.measures
        self.header = 'measures'
        with div(cls="px-4 sm:px-6 lg:px-8 mt-8 flow-root col-span-3", id='header_measure') as header_measure:
            div(id='field_selection_measure')
            with div(cls="-mx-4 -my-2 overflow-x-auto sm:-mx-6 lg:-mx-8"):
                with div(cls="inline-block min-w-full py-2 align-middle sm:px-6 lg:px-8"):
                    with table(cls="min-w-full divide-y divide-gray-300"):
                        with thead():
                            with tr():
                                th(scope="col", cls="relative py-3.5 pl-3 pr-4 sm:pr-0").add(MEASURE_ICON)
                                th(_('Measure fields'), scope="col", cls="py-3.5 pl-4 pr-3 text-left text-sm font-semibold text-gray-900 sm:pl-0")
                                th(scope="col", cls="relative py-3.5 pl-3 pr-4 sm:pr-0").add(span(_('Measure type'), cls="sr-only"))
                                with th(scope="col", cls="relative py-3.5 pl-3 pr-4 sm:pr-0"):
                                    a(href="#", cls="text-indigo-600 hover:text-indigo-900",
                                        hx_target="#field_selection_measure",
                                        hx_post=PivotHeaderSelection(header='measure', database_name=self.database_name, table_name=self.table_name, table_properties=self.table_properties, render=False).url(),
                                        hx_trigger="click", hx_swap="outerHTML").add(ADD_ICON)
                                    span(_('Add'), cls="sr-only")
                        with tbody(cls="divide-y divide-gray-200"):
                            for field in fields:
                                with tr():
                                    td(field[0].capitalize(), colspan="2", cls="whitespace-nowrap px-3py-4 pl-4 pr-3 text-sm font-medium text-gray-900 sm:pl-0")
                                    with td(cls="relative whitespace-nowrap py-4 pl-3 pr-4 text-right text-sm font-medium sm:pr-0"):
                                        match field[1]:
                                            case 'sum':
                                                p(_('Sum'))
                                            case 'avg':
                                                p(_('Average'))
                                            case 'count':
                                                p(_('Count'))
                                            case 'min':
                                                p(_('Minimum'))
                                            case 'max':
                                                p(_('Maximum'))
                                    with td(cls="relative whitespace-nowrap py-4 pl-3 pr-4 text-right text-sm font-medium sm:pr-0"):
                                        a(href=PivotHeader(database_name=self.database_name, table_name=self.table_name, header=self.header, field=field[0], table_properties=self.table_properties, render=False).url('remove_field'),
                                            cls="text-indigo-600 hover:text-indigo-900").add(REMOVE_ICON)
        return header_measure


# This class handle the order table header
class PivotHeaderOrder(Component):
    'Pivot Header Component'
    __name__ = 'www.pivot_header.order'
    _path = None

    header = fields.Char('Header')
    database_name = fields.Char('Database Name')
    table_name = fields.Char('Table Name')
    table_properties = fields.Char('Table Properties')

    @classmethod
    def get_url_map(cls):
        return [
            Rule('/<string:database_name>/babi/pivot/<string:table_name>/header_order/<string:table_properties>'),
        ]

    def render(self):
        pool = Pool()
        # Components
        Index = pool.get('www.index.pivot')
        PivotHeader = pool.get('www.pivot_header')

        items = []
        if self.table_properties != 'null':
            cube = Cube.parse_properties(self.table_properties,
                self.table_name)
            items = cube.order
        self.header = 'order'
        with div(cls="px-4 sm:px-6 lg:px-8 mt-8 flow-root col-span-3", id='header_order') as header_order:
            div(id='field_selection_order')
            with div(cls="-mx-4 -my-2 overflow-x-auto sm:-mx-6 lg:-mx-8"):
                with div(cls="inline-block min-w-full py-2 align-middle sm:px-6 lg:px-8"):
                    with table(cls="min-w-full divide-y divide-gray-300"):
                        with thead():
                            with tr():
                                th(scope="col", cls="relative py-3.5 pl-3 pr-4 sm:pr-0").add(ORDER_ICON)
                                th(_('Order fields'), scope="col", cls="py-3.5 pl-4 pr-3 text-left text-sm font-semibold text-gray-900 sm:pl-0")
                                th(scope="col", cls="relative py-3.5 pl-3 pr-4 sm:pr-0").add(span(_('Measure type'), cls="sr-only"))
                                th(scope="col", cls="relative py-3.5 pl-3 pr-4 sm:pr-0")
                        with tbody(cls="divide-y divide-gray-200"):
                            for item in items:
                                with tr():
                                    if isinstance(item[0], tuple):
                                        value = f'{item[0][1].capitalize()}({item[0][0].capitalize()})'
                                        field = '__'.join(item[0])
                                    else:
                                        value = item[0].capitalize()
                                        field = item[0]
                                    td(value, colspan="2", cls="whitespace-nowrap px-3py-4 pl-4 pr-3 text-sm font-medium text-gray-900 sm:pl-0")
                                    with td(cls="relative whitespace-nowrap py-4 pl-3 pr-4 text-right text-sm font-medium sm:pr-0"):
                                        cube = Cube.parse_properties(self.table_properties,
                                            self.table_name)
                                        auxiliar_position = cube.order.index(item)
                                        auxiliar_element = item
                                        cube.order.remove(auxiliar_element)
                                        auxiliar_element = list(item)
                                        if auxiliar_element[1] == 'asc':
                                                auxiliar_element[1] = 'desc'
                                        else:
                                            auxiliar_element[1] = 'asc'
                                        cube.order.insert(auxiliar_position, tuple(auxiliar_element))
                                        invert_table_properties = cube.encode_properties()

                                        if item[1] == 'desc':
                                            a(href=Index(database_name=self.database_name, table_name=self.table_name, table_properties=invert_table_properties, render=False).url(),
                                                cls="text-indigo-600 hover:text-indigo-900").add(ORDER_DESC_ICON)
                                        else:
                                            a(href=Index(database_name=self.database_name, table_name=self.table_name, table_properties=invert_table_properties, render=False).url(),
                                                cls="text-indigo-600 hover:text-indigo-900").add(ORDER_ASC_ICON)
                                    with td(cls="relative whitespace-nowrap py-4 pl-3 pr-4 text-right text-sm font-medium sm:pr-0"):
                                        if item != items[0]:
                                            a(href=PivotHeader(database_name=self.database_name, table_name=self.table_name, header=self.header, field=field, table_properties=self.table_properties, level_action='up', render=False).url('level_field'),
                                                cls="text-indigo-600 hover:text-indigo-900").add(UP_ARROW)
                                    with td(cls="relative whitespace-nowrap py-4 pl-3 pr-4 text-right text-sm font-medium sm:pr-0"):
                                        if item != items[-1]:
                                            a(href=PivotHeader(database_name=self.database_name, table_name=self.table_name, header=self.header, field=field, table_properties=self.table_properties, level_action='down', render=False).url('level_field'),
                                                cls="text-indigo-600 hover:text-indigo-900").add(DOWN_ARROW)
        return header_order


# This function handles the pup up that is show in every header table and add
# the item to the table properties
class PivotHeaderSelection(Component):
    'Pivot Header Selection'
    __name__ = 'www.pivot_header.selection'
    _path = None

    header = fields.Char('Header')
    database_name = fields.Char('Database Name')
    table_name = fields.Char('Table Name')
    table_properties = fields.Char('Table Properties')
    field = fields.Char('Field')
    measure = fields.Char('Measure')

    @classmethod
    def get_url_map(cls):
        return [
            Rule('/<string:database_name>/babi/pivot/<string:table_name>/open_field_selection/<string:header>/<string:table_properties>'),
            Rule('/<string:database_name>/babi/pivot/<string:table_name>/close_field_selection/<string:header>/<string:table_properties>', endpoint='close_field_selection'),
            Rule('/<string:database_name>/babi/pivot/<string:table_name>/add_field_selection/<string:header>/<string:table_properties>', endpoint='add_field_selection'),
        ]

    def render(self):
        pool = Pool()
        Table = pool.get('babi.table')

        name = None
        match self.header:
            case 'x':
                name = 'field_selection_x'
            case 'y':
                name = 'field_selection_y'
            case 'measure':
                name = 'field_selection_measure'
            case 'order':
                name = 'field_selection_order'

        fields_used = []
        if self.table_properties != 'null':
            cube = Cube.parse_properties(self.table_properties,
                self.table_name)
            if self.header != 'order':
                fields_used = cube.rows + cube.columns + [m[0] for m in cube.measures]
            else:
                order_fields = [o[0] for o in cube.order]
                fields_used = cube.rows + cube.columns + cube.measures

        table, = Table.search([('internal_name', '=', self.table_name[2:])], limit=1)
        fields = [x.internal_name for x in table.fields_]

        with div(id=name, cls="relative z-10", aria_labelledby="modal-title", role="dialog", aria_modal="true") as field_selection:
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
                                with div(cls="mt-2 space-y-4"):
                                    with select(id="field", name="field", cls="mt-2 block w-full rounded-md border-0 py-1.5 pl-3 pr-10 text-gray-900 ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-indigo-600 sm:text-sm sm:leading-6"):
                                        if self.header != 'order':
                                            for field in fields:
                                                if field not in fields_used:
                                                    option(field.capitalize(), value=field)
                                        else:
                                            for field in fields_used:
                                                if field not in order_fields:
                                                    if isinstance(field, tuple):
                                                        name_ = f'{field[1].capitalize()}({field[0].capitalize()})'
                                                    else:
                                                        name_=field.capitalize()
                                                    option(name_, value=field)

                                    if self.header == 'measure':
                                        with select(id="measure", name="measure", required=True, cls="mt-2 block w-full rounded-md border-0 py-1.5 pl-3 pr-10 text-gray-900 ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-indigo-600 sm:text-sm sm:leading-6"):
                                            option(_('Sum'), value='sum')
                                            option(_('Average'), value='average')
                                            option(_('Max'), value='max')
                                            option(_('Min'), value='min')
                                            option(_('Count'), value='count')
                        with div(cls="mt-5 sm:mt-4 sm:flex sm:flex-row-reverse"):
                            button(_('Add'), type="submit", cls="inline-flex w-full justify-center rounded-md bg-blue-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-blue-500 sm:ml-3 sm:w-auto")
                            a(_('Cancel'), href="#",
                                hx_target=f"#{name}",
                                hx_post=self.url('close_field_selection'),
                                hx_trigger="click", hx_swap="outerHTML",
                                cls="mt-3 inline-flex w-full justify-center rounded-md bg-white px-3 py-2 text-sm font-semibold text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 hover:bg-gray-50 sm:mt-0 sm:w-auto")
        return field_selection

    def close_field_selection(self):
        name = None
        match self.header:
            case 'x':
                name = 'field_selection_x'
            case 'y':
                name = 'field_selection_y'
            case 'measure':
                name = 'field_selection_measure'
            case 'order':
                name = 'field_selection_order'

        field_selection = div(id=name)
        return field_selection

    def add_field_selection(self):
        pool = Pool()
        Index = pool.get('www.index.pivot')

        if self.table_properties == 'null':
            cube = Cube(table=self.table_name)
        else:
            cube = Cube.parse_properties(self.table_properties,
                self.table_name)

        # We need to check if a specific field is already in the cube, if is
        # the case, dont add again. If we clic fast enougth while adding fields
        # we can send multiple times a request to the server, tryton to add
        # multiple times a field. For each header, we add the field in his
        # header and in the order header
        match self.header:
            case 'x':
                if self.field not in cube.rows:
                    cube.rows.append(self.field)
                    cube.order.append((self.field, 'asc'))
            case 'y':
                if self.field not in cube.columns:
                    cube.columns.append(self.field)
                    cube.order.append((self.field, 'asc'))
            case 'measure':
                if (self.field, self.measure) not in cube.measures:
                    cube.measures.append((self.field, self.measure))
                    cube.order.append(((self.field, self.measure), 'asc'))
                pass

        return redirect(Index(database_name=self.database_name, table_name=self.table_name, table_properties=cube.encode_properties(), render=False).url())


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
        pool = Pool()
        # Component
        Index = pool.get('www.index.pivot')
        cube = Cube.parse_properties(self.table_properties, self.table_name)
        match self.header:
            case 'x':
                cube.rows.remove(self.field)
            case 'y':
                cube.columns.remove(self.field)
            case 'measures':
                #TODO: we need to handle the case when we have multiple
                # measures for the same field.
                # For example, we can have: SUM('x') and MAX('x')
                index = 0
                for measure in cube.measures:
                    if measure[0] == self.field:
                        cube.measures.pop(index)
                        break
                    index += 1

        # Remove the field from the order property
        index = 0
        for order in cube.order:
            if self.header in ['x', 'y'] and order[0] == self.field:
                cube.order.pop(index)
                break
            if self.header == 'measures':
                if isinstance(order[0], tuple) and order[0][0] == self.field:
                    cube.order.pop(index)
                    break
            index +=1

        table_properties = cube.encode_properties()
        #TODO: remove this section when we found the correct way to handle
        # multiple URLs with the same endpoint
        if not cube.rows and not cube.columns and not cube.measures and not cube.order:
            table_properties = 'null'
        return redirect(Index(database_name=self.database_name, table_name=self.table_name, table_properties=table_properties, render=False).url())

    def level_field(self):
        pool = Pool()
        Index = pool.get('www.index.pivot')

        cube = Cube.parse_properties(self.table_properties, self.table_name)
        auxiliar_position = None
        headers = {
            'x': 'rows',
            'y': 'columns',
            'measures': 'measures',
            'order': 'order',
        }

        if self.header in headers:
            cube_attribute = getattr(cube, headers[self.header])
            if self.header == 'order':
                field = self.field.split('__')
                if len(field) > 1:
                    field = tuple(field)
                else:
                    field = self.field

                index = 0
                for ca in cube_attribute:
                    if ca[0] == field:
                        field = ca
                        break
                    index +1
                auxiliar_position = cube_attribute.index(field)
            else:
                auxiliar_position = cube_attribute.index(self.field)
            # Get element and save it in a auxiliar val
            auxiliar_value = cube_attribute[auxiliar_position]
            # remove element from list
            cube_attribute.remove(auxiliar_value)
            # Add element in the new position
            if self.level_action == 'up':
                cube_attribute.insert(auxiliar_position-1, auxiliar_value)
            else:
                cube_attribute.insert(auxiliar_position+1, auxiliar_value)

        table_properties = cube.encode_properties()
        return redirect(Index(database_name=self.database_name, table_name=self.table_name, table_properties=table_properties, render=False).url())


#This function handles the render of the cube into a table and the download button
class PivotTable(Component):
    'Pivot Table'
    __name__ = 'www.pivot_table'
    _path = None

    database_name = fields.Char('Database Name')
    table_name = fields.Char('Table Name')
    table_properties = fields.Char('Table Properties')

    @classmethod
    def get_url_map(cls):
        return [
            Rule('/<string:database_name>/babi/pivot/table/<string:table_name>/<string:table_properties>'),
        ]

    def render(self):
        pool = Pool()
        # Component
        DownloadReport = pool.get('www.download_report')
        Language = pool.get('ir.lang')

        cube = Cube.parse_properties(self.table_properties, self.table_name)
        language = Transaction().context.get('language', 'en')
        language, = Language.search([('code', '=', language)], limit=1)

        download = a(DOWNLOAD, href=DownloadReport(
                database_name=self.database_name, table_name=self.table_name,
                table_properties=self.table_properties, render=False).url('download'))

        pivot_table = table(cls="table-auto text-sm text-left rtl:text-right text-gray-600")
        for row in cube.build():
            pivot_row = tr()
            for cell in row:
                if download:
                    # Paint the download button in the first cell
                    pivot_row.add(td(download, cls="text-xs uppercase bg-gray-300 text-gray-900 px-6 py-3"))
                    download = None
                    continue
                # Handle the headers links
                if (cell.type == CellType.ROW_HEADER or
                        cell.type == CellType.COLUMN_HEADER):
                    cell_value = cell.text(language)
                    table_properties = None
                    if (cell.expansion_row and cell.expansion_row in
                            cube.expansions_rows) or (cell.expansion_column and
                            cell.expansion_column in cube.expansions_columns):
                        # This case handles the collapse action of the headers cells
                        icon = COLLAPSE

                        cell_cube = Cube.parse_properties(
                            self.table_properties, self.table_name)
                        if cell.type == CellType.ROW_HEADER:
                            cell_cube.expansions_rows.remove(
                                cell.expansion_row)
                        elif cell.type == CellType.COLUMN_HEADER:
                            cell_cube.expansions_columns.remove(
                                cell.expansion_column)
                        table_properties = cell_cube.encode_properties()
                    elif cell.expansion_row or cell.expansion_column:
                        # This case handles all the expansions
                        icon = EXPAND

                        cell_cube = Cube.parse_properties(
                            self.table_properties, self.table_name)
                        if cell.type == CellType.ROW_HEADER:
                            cell_cube.expansions_rows.append(cell.expansion_row)
                        elif cell.type == CellType.COLUMN_HEADER:
                            cell_cube.expansions_columns.append(
                                cell.expansion_column)
                        table_properties = cell_cube.encode_properties()

                    if table_properties:
                        cell_value = a(
                            str(icon) + ' ' + str(cell.text(language)),
                            href="#", hx_target="#pivot_table",
                            hx_post=PivotTable(
                                    database_name=self.database_name,
                                    table_name=self.table_name,
                                    table_properties=table_properties,
                                    render=False).url(),
                            hx_trigger="click", hx_swap="outerHTML")

                    pivot_row.add(td(cell_value, cls="text-xs uppercase bg-gray-300 text-gray-900 px-6 py-3"))

                else:
                    pivot_row.add(td(cell.text(language), cls="border-b bg-gray-50 border-gray-000 px-6 py-4 text-right"))
            pivot_table.add(pivot_row)

        pivot_div = div(id='pivot_table', cls="inline-block min-w-full py-2 align-middle sm:px-6 lg:px-8")
        pivot_div.add(pivot_table)
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
        pool = Pool()
        Language = pool.get('ir.lang')

        language = Transaction().context.get('language', 'en')
        language, = Language.search([('code', '=', language)], limit=1)

        cube = Cube.parse_properties(self.table_properties, self.table_name)
        wb = Workbook()
        ws = wb.active
        for row in cube.build():
            ws.append([x.text(language) for x in row])
        response = Response(save_virtual_workbook(wb))
        response.headers['Content-Disposition'] = f'attachment; filename={self.table_name}.xlsx'
        response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        return response
