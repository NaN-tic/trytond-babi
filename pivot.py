import logging
import secrets
import tempfile
from datetime import date, datetime
from dominate.tags import (div, h1, p, pre, a, form, button, span, table, thead,
    tbody, tr, td, head, html, meta, title, script, h3, comment, select,
    option, main, th, style, details, summary, input_)
from dominate.util import raw
from openpyxl import Workbook
from openpyxl.writer.excel import save_workbook
from psycopg2.errors import UndefinedTable
from werkzeug.utils import redirect
from werkzeug.wrappers import Response
from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction
from trytond.modules.voyager.voyager import Component, Endpoint
from trytond.modules.voyager.i18n import _
from .cube import Cube, CellType, capitalize
from .table import datetime_to_company_tz
from .tools import adjust_column_widths


logger = logging.getLogger(__name__)

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
EXPAND_ALL = raw('<svg xmlns="http://www.w3.org/2000/svg" height="24px" viewBox="0 -960 960 960" width="24px" fill="currentColor"><path d="M200-200v-240h80v160h160v80H200Zm480-320v-160H520v-80h240v240h-80Z"/></svg>')
COLLAPSE_ALL = raw('<svg xmlns="http://www.w3.org/2000/svg" height="24px" viewBox="0 -960 960 960" width="24px" fill="currentColor"><path d="M440-440v240h-80v-160H200v-80h240Zm160-320v160h160v80H520v-240h80Z"/></svg>')
DOWNLOAD = raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3" /></svg>')
ROWS_ICON = raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6" transform="rotate(90)"><path stroke-linecap="round" stroke-linejoin="round" d="M9 4.5v15m6-15v15m-10.875 0h15.75c.621 0 1.125-.504 1.125-1.125V5.625c0-.621-.504-1.125-1.125-1.125H4.125C3.504 4.5 3 5.004 3 5.625v12.75c0 .621.504 1.125 1.125 1.125Z" /></svg>')
COLUMNS_ICON = raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M9 4.5v15m6-15v15m-10.875 0h15.75c.621 0 1.125-.504 1.125-1.125V5.625c0-.621-.504-1.125-1.125-1.125H4.125C3.504 4.5 3 5.004 3 5.625v12.75c0 .621.504 1.125 1.125 1.125Z" /></svg>')
PROPERTY_ICON = raw('<svg xmlns="http://www.w3.org/2000/svg" height="24px" viewBox="0 -960 960 960" width="24px" fill="#000000"><path d="M160-760v560h240v-560H160ZM80-120v-720h720v160h-80v-80H480v560h240v-80h80v160H80Zm400-360Zm-80 0h80-80Zm0 0Zm320 120v-80h-80v-80h80v-80h80v80h80v80h-80v80h-80Z"/></svg>')
MEASURE_ICON = raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 0 1-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 0 1 4.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0 1 12 15a9.065 9.065 0 0 0-6.23-.693L5 14.5m14.8.8 1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0 1 12 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5" /></svg>')
ADD_ICON = raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15" /></svg>')
REMOVE_ICON = raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M5 12h14" /></svg>')
UP_ARROW = raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 10.5 12 3m0 0 7.5 7.5M12 3v18" /></svg>')
DOWN_ARROW = raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M19.5 13.5 12 21m0 0-7.5-7.5M12 21V3" /></svg>')
CLOSE_ICON = raw('<svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>')
ORDER_ICON = raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25H12" /></svg>')
ORDER_ASC_ICON = raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M3 4.5h14.25M3 9h9.75M3 13.5h9.75m4.5-4.5v12m0 0-3.75-3.75M17.25 21 21 17.25" /></svg>')
ORDER_DESC_ICON = raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M3 4.5h14.25M3 9h9.75M3 13.5h5.25m5.25-.75L17.25 9m0 0L21 12.75M17.25 9v12" /></svg>')
LOADING_SPINNER = raw('<svg aria-hidden="true" class="m-2 w-8 h-8 text-gray-200 animate-spin dark:text-gray-600 fill-blue-600" viewBox="0 0 100 101" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M100 50.5908C100 78.2051 77.6142 100.591 50 100.591C22.3858 100.591 0 78.2051 0 50.5908C0 22.9766 22.3858 0.59082 50 0.59082C77.6142 0.59082 100 22.9766 100 50.5908ZM9.08144 50.5908C9.08144 73.1895 27.4013 91.5094 50 91.5094C72.5987 91.5094 90.9186 73.1895 90.9186 50.5908C90.9186 27.9921 72.5987 9.67226 50 9.67226C27.4013 9.67226 9.08144 27.9921 9.08144 50.5908Z" fill="currentColor"/><path d="M93.9676 39.0409C96.393 38.4038 97.8624 35.9116 97.0079 33.5539C95.2932 28.8227 92.871 24.3692 89.8167 20.348C85.8452 15.1192 80.8826 10.7238 75.2124 7.41289C69.5422 4.10194 63.2754 1.94025 56.7698 1.05124C51.7666 0.367541 46.6976 0.446843 41.7345 1.27873C39.2613 1.69328 37.813 4.19778 38.4501 6.62326C39.0873 9.04874 41.5694 10.4717 44.0505 10.1071C47.8511 9.54855 51.7191 9.52689 55.5402 10.0491C60.8642 10.7766 65.9928 12.5457 70.6331 15.2552C75.2735 17.9648 79.3347 21.5619 82.5849 25.841C84.9175 28.9121 86.7997 32.2913 88.1811 35.8758C89.083 38.2158 91.5421 39.6781 93.9676 39.0409Z" fill="currentFill"/></svg>')


def _get_filter_parameters(table):
    pool = Pool()
    Parameter = pool.get('babi.filter.parameter')
    if not table or not getattr(table, 'filter', None):
        return []
    parameters = Parameter.search([('filter', '=', table.filter)])
    valid_parameters = []
    for parameter in parameters:
        try:
            if parameter.check_parameter_in_filter():
                valid_parameters.append(parameter)
        except Exception:
            logger.exception('Error checking parameter %s', parameter.id)
    return valid_parameters


def _format_parameter_value(parameter, value):
    if value is None:
        return ''
    ttype = parameter.ttype
    if ttype == 'boolean':
        return bool(value)
    if ttype == 'date' and isinstance(value, date):
        return value.isoformat()
    if ttype == 'datetime':
        if isinstance(value, datetime):
            return value.strftime('%Y-%m-%dT%H:%M')
        if isinstance(value, date):
            return value.strftime('%Y-%m-%dT00:00')
    if ttype == 'many2many':
        if isinstance(value, (list, tuple)):
            return ', '.join(str(x) for x in value)
    return str(value)


def _parse_parameter_value(parameter, raw_value):
    if raw_value is not None and not isinstance(raw_value, str):
        return raw_value
    ttype = parameter.ttype
    if ttype == 'boolean':
        return raw_value in ('true', 'True', '1', 'on', 'yes')
    if raw_value in (None, ''):
        return None
    if ttype in ('integer', 'many2one'):
        return int(raw_value)
    if ttype in ('float', 'numeric'):
        return float(raw_value)
    if ttype == 'date':
        return date.fromisoformat(raw_value)
    if ttype == 'datetime':
        return datetime.fromisoformat(raw_value)
    if ttype == 'many2many':
        values = [x.strip() for x in raw_value.split(',') if x.strip()]
        return [int(x) for x in values]
    return raw_value


def _normalize_table_name(name):
    if name.startswith('__'):
        return name.split('__')[-1]
    return name


class Site(metaclass=PoolMeta):
    __name__ = 'www.site'

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls.type.selection += [('babi_pivot', 'Pivot')]

    def get_cache(self, session, request):
        if self.type == 'babi_pivot':
            # Disable cache
            return
        return super().get_cache(session, request)

    @classmethod
    def dispatch(cls, site_type, site_id, request, user, web_prefix=None):
        with Transaction().set_context(language=Transaction().language):
            return super().dispatch(site_type, site_id, request, user,
                web_prefix)

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
                style('.loading-indicator{visibility: hidden;}'
                    '.htmx-request .loading-indicator{visibility: visible; transition: opacity 200ms ease-in;}'
                    '.htmx-request.loading-indicator{visibility: visible; transition: opacity 200ms ease-in;}')
                script(src='https://unpkg.com/htmx.org@2.0.0')
                script(src="https://cdn.tailwindcss.com")
            main_body = div(id='main', cls='bg-white')
            flash_div = div(id='flash_messages',
                cls="flex w-full flex-col items-center space-y-4 sm:items-end")
            flash_div['hx-swap-oob'] = "afterbegin"
            main_body += flash_div
            main_body += self.main
        return html_layout


class IndexMixin(object):
    __slots__ = ()

    table_name = fields.Char('Table Name')
    table_properties = fields.Char('Table Properties')


class Index(IndexMixin, Endpoint):
    'Index'
    __name__ = 'www.index.pivot'
    _url = '/<string:table_name>/<string:table_properties>'
    _type = 'babi_pivot'

    def render(self):
        pool = Pool()
        BabiTable = pool.get('babi.table')
        Layout = pool.get('www.layout.pivot')
        PivotHeaderAxis = pool.get('www.pivot_header.axis')
        PivotHeaderMeasure = pool.get('www.pivot_header.measure')
        PivotHeaderOrder = pool.get('www.pivot_header.order')
        PivotTable = pool.get('www.pivot_table')
        PivotCompute = pool.get('www.pivot_compute')
        PivotApply = pool.get('www.pivot_apply')
        PivotSave = pool.get('www.pivot_save')

        '''
        We need to:
        - If we delete a cell from any of the table that is begin used in
            the order table, we need to delete the field from the order table
        - If we delte a cell from the order table, we dont need to do
            anything apart of realoading the table
        '''

        table_name = _normalize_table_name(self.table_name)

        tables = BabiTable.search([
                ('internal_name', '=', table_name),
                ], limit=1)

        # Check if the user can see the table, if not, return an error page
        access = False
        if tables:
            table, = tables
            access = table.check_access()

        if not access or not tables:
            # TODO: move the error page to a component, this way we call the same error in multiple places
            with main(cls="grid min-h-full place-items-center bg-white px-6 py-24 sm:py-32 lg:px-8") as error_section:
                with div(cls="text-center"):
                    p(_('404'), cls="text-base font-semibold text-indigo-600")
                    h1(_("Page not found or you don't have access to it"), cls="mt-4 text-3xl font-bold tracking-tight text-gray-900 sm:text-5xl")
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
            cube = Cube(table=table.name)
        else:
            cube = Cube.parse_properties(self.table_properties, table.name)
        current_parameters = (
            cube.parameters
            if getattr(cube, 'parameters', None)
            else (table.parameters or {})
        )

        if cube.measures and (cube.rows or cube.columns):
            show_error = False

        # Prepare the cube properties for the invert cube function
        cube.table = table.name
        cube.rows, cube.columns = cube.columns, cube.rows
        inverted_table_properties = cube.encode_properties()

        with main() as index_section:
            with div(cls="border-b border-gray-200 bg-white px-4 py-3 sm:px-6 grid grid-cols-4"):
                with div(cls="col-span-2"):
                    span(f'{table.name}', cls="text-base font-semibold leading-6 text-gray-900")
                    # TODO: Those timestamps are not exactly right because a
                    # table may depend on other tables so even if this table
                    # has been recently computed it may depend on old data.
                    # Even if that seems correct (the table does not currently
                    # depend on other tables) it may happen that the table did
                    # depend on other tables when it was computed for the last
                    # time and at that moment those other tables where not up
                    # to date.
                    # All of this is solvable but requires more infrastructure,
                    # that should probably be implemented in the babi.table
                    # model.
                    if table.type in ('model', 'table'):
                        if table.calculation_date:
                            timestamp = _('data from %s') % datetime_to_company_tz(table.calculation_date)
                        else:
                            timestamp = _('not calculated yet')
                    else:
                        timestamp = _('current data')
                    timestamp = f'({timestamp})'
                    # Use a smaller text
                    span(timestamp, cls="text-sm text-gray-500 ml-2")
                with div(cls="col-span-2 flex items-center justify-end gap-2 pr-1"):
                    with form(id="compute_form",
                            action=PivotCompute.url(table_name=self.table_name,
                                table_properties=self.table_properties),
                            method="POST",
                            hx_post=PivotCompute.url(table_name=self.table_name,
                                table_properties=self.table_properties),
                            cls="inline-flex items-center"):
                        with button(type="submit",
                                cls="inline-flex items-center rounded-md bg-blue-600 px-2.5 h-7 text-xs font-semibold text-white hover:bg-blue-500 active:bg-blue-700 active:scale-95 transition"):
                            span(_('Compute'))
                            span(cls="loading-indicator").add(LOADING_SPINNER)
                    a(href=Index.url(table_name=self.table_name, table_properties=inverted_table_properties),
                        cls="inline-flex items-center justify-center h-7 w-7 rounded-md text-gray-700 ring-1 ring-inset ring-gray-300 hover:bg-indigo-50 hover:text-indigo-700 active:bg-indigo-100 active:text-indigo-800 active:scale-95 transition").add(SWAP_AXIS)
                    a(href=Index.url(table_name=self.table_name, table_properties='null'),
                        cls="inline-flex items-center justify-center h-7 w-7 rounded-md text-gray-700 ring-1 ring-inset ring-gray-300 hover:bg-indigo-50 hover:text-indigo-700 active:bg-indigo-100 active:text-indigo-800 active:scale-95 transition").add(RELOAD)

            parameters = _get_filter_parameters(table)
            with details(cls="m-2 border border-gray-200 rounded-lg", open=True):
                summary(cls="px-2 py-1 text-sm font-semibold text-gray-900 hover:text-indigo-700 transition").add(_('Parameters'))
                if not parameters:
                    div(_('No parameters defined for this table.'),
                        cls="px-2 pt-2 text-xs text-gray-500")
                else:
                    with div(cls="grid grid-cols-1 gap-3 px-3 pb-2 pt-2 sm:grid-cols-2"):
                        for parameter in parameters:
                            field_name = f'{parameter.name}_{parameter.id}'
                            value = _format_parameter_value(
                                parameter,
                                current_parameters.get(parameter.name))
                            ttype = parameter.ttype
                            with div(cls="flex flex-col gap-1"):
                                if ttype == 'boolean':
                                    with div(cls="flex items-center gap-2"):
                                        input_(type="checkbox",
                                            name=field_name,
                                            form="compute_form",
                                            checked=bool(value),
                                            cls="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500")
                                        span(parameter.name,
                                            cls="text-xs font-medium text-gray-700")
                                else:
                                    span(parameter.name,
                                        cls="text-xs font-medium text-gray-700")
                                    input_type = 'text'
                                    input_step = None
                                    if ttype in ('integer', 'many2one'):
                                        input_type = 'number'
                                        input_step = '1'
                                    elif ttype in ('float', 'numeric'):
                                        input_type = 'number'
                                        input_step = 'any'
                                    elif ttype == 'date':
                                        input_type = 'date'
                                    elif ttype == 'datetime':
                                        input_type = 'datetime-local'
                                    input_kwargs = {
                                        'type': input_type,
                                        'name': field_name,
                                        'form': 'compute_form',
                                        'value': value,
                                        'required': True,
                                        'cls': ("w-full rounded-md border border-gray-300 px-2 py-1 "
                                            "text-xs text-gray-900 focus:border-blue-500 "
                                            "focus:ring-blue-500"),
                                        }
                                    if input_step:
                                        input_kwargs['step'] = input_step
                                    if ttype == 'many2many':
                                        input_kwargs['placeholder'] = _('Comma-separated IDs')
                                    if ttype == 'many2one':
                                        input_kwargs['placeholder'] = _('Record ID')
                                    input_(**input_kwargs)

            # Details always opened by default
            with details(cls="m-2 border border-gray-200 rounded-lg", open=True):
                summary(cls="px-2 py-1 text-sm font-semibold text-gray-900 hover:text-indigo-700 transition").add(_('Configuration'))
                pivots = [p for p in table.pivots if p.active]
                selected_pivot_id = None
                if pivots and self.table_properties and self.table_properties != 'null':
                    for pivot in pivots:
                        cube = pivot.get_cube()
                        if not cube:
                            continue
                        if cube.encode_properties() == self.table_properties:
                            selected_pivot_id = pivot.id
                            break
                if pivots:
                    with div(cls="px-2 pt-2"):
                        with div(cls="flex items-center gap-2 align-middle"):
                            with form(action=PivotApply.url(
                                    table_name=self.table_name,
                                    table_properties=self.table_properties),
                                    method="POST",
                                    cls="flex items-center gap-2 h-7"):
                                span(_('Pivot Table'), cls="text-xs text-gray-700 align-middle")
                                with select(name="pivot", cls="text-xs rounded-md border border-gray-300 px-2 py-0 h-7 align-middle",
                                        onchange="this.form.submit()"):
                                    if selected_pivot_id is None:
                                        option('-', value="")
                                    for pivot in pivots:
                                        if selected_pivot_id == pivot.id:
                                            option(pivot.rec_name, value=str(pivot.id), selected=True)
                                        else:
                                            option(pivot.rec_name, value=str(pivot.id))
                            if selected_pivot_id is None:
                                button(_('Save Configuration'),
                                    type="button",
                                    cls="inline-flex items-center rounded-md bg-gray-900 px-3 h-7 text-xs font-semibold text-white hover:bg-gray-800 active:bg-gray-950 active:scale-95 transition align-middle",
                                    onclick="document.getElementById('save_pivot_modal').style.display='block'")
                    if selected_pivot_id is None:
                        with div(id="save_pivot_modal", cls="relative z-10", style="display: none;", aria_labelledby="modal-title", role="dialog", aria_modal="true"):
                            div(cls="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity", aria_hidden="true")
                            with div(cls="fixed inset-0 z-10 w-screen overflow-y-auto"):
                                with div(cls="flex min-h-full items-end justify-center p-4 text-center sm:items-center sm:p-0"):
                                    with form(action=PivotSave.url(
                                            table_name=self.table_name,
                                            table_properties=self.table_properties),
                                            method="POST",
                                            cls="relative transform overflow-hidden rounded-lg bg-white px-4 pb-4 pt-5 text-left shadow-xl transition-all sm:my-8 sm:w-full sm:max-w-lg sm:p-6"):
                                        with div(cls="absolute right-0 top-0 hidden pr-4 pt-4 sm:block"):
                                            button(type="button",
                                                cls="rounded-md bg-white text-gray-400 hover:text-gray-500",
                                                onclick="document.getElementById('save_pivot_modal').style.display='none'").add(CLOSE_ICON)
                                        h3(_('Save Configuration'), cls="text-sm font-semibold text-gray-900")
                                        p(_('Name'), cls="mt-3 text-xs text-gray-700")
                                        input_(type="text", name="name", required=True,
                                            value=f'{table.name} pivot',
                                            cls="mt-1 w-full text-xs rounded-md border border-gray-300 px-2 py-1")
                                        with div(cls="mt-4 flex justify-end gap-2"):
                                            button(_('Cancel'),
                                                type="button",
                                                cls="inline-flex items-center rounded-md bg-white px-3 py-1.5 text-xs font-semibold text-gray-900 ring-1 ring-inset ring-gray-300 hover:bg-gray-50 active:bg-gray-100 active:scale-95 transition",
                                                onclick="document.getElementById('save_pivot_modal').style.display='none'")
                                            button(_('Save Configuration'),
                                                type="submit",
                                                cls="inline-flex items-center rounded-md bg-gray-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-gray-800 active:bg-gray-950 active:scale-95 transition")
                with div(cls="grid grid-cols-12 px-3 pb-2"):
                    PivotHeaderAxis(table_name=self.table_name, axis='x',
                        table_properties=self.table_properties)
                    PivotHeaderAxis(table_name=self.table_name, axis='y',
                        table_properties=self.table_properties)
                    PivotHeaderMeasure(table_name=self.table_name,
                        table_properties=self.table_properties)
                    PivotHeaderAxis(table_name=self.table_name, axis='property',
                        table_properties=self.table_properties)
                    PivotHeaderOrder(table_name=self.table_name,
                        table_properties=self.table_properties)
            with div(cls="mt-8 flow-root"):
                with div(cls="-mx-4 -my-2 overflow-x-auto sm:-mx-6 lg:-mx-8"):
                    if show_error == True:
                        div(cls="text-center").add(p(_('You need to select at least one measure and one row or one column to show the table.'), cls="mt-1 text-sm text-gray-500"))
                    else:
                        try:
                            PivotTable(table_name=self.table_name,
                                table_properties=self.table_properties)
                        except UndefinedTable:
                            div(cls="text-center").add(_("Table has not been computed. Click on the 'Compute' button or wait until the process has finished. Also ensure there is no 'Errors' tab in the table."))
                        except Exception as e:
                            div(cls="text-center").add(p(_('Error building the cube:'), cls="mt-1 text-sm text-gray-500"))
                            print_trace = True
                            if 'function avg(' in str(e):
                                div(cls="text-center").add(_("HINT: You are trying to make average of a text type field, please try with a numeric type field or change the operation."))
                                print_trace = False
                            if 'function sum(' in str(e):
                                div(cls="text-center").add(_("HINT: You are trying to sum a text type field, please try with a numeric type field or change the operation."))
                                print_trace = False
                            with details() as traceback_details:
                                summary(_('Show more details'),
                                    cls="text-sm font-semibold text-gray-900 hover:text-indigo-700 transition")
                                p(pre(str(e)))
                            div(cls="text-center").add(traceback_details)
                            if print_trace:
                                logger.exception(e)

        layout = Layout(title=f'{table.name} | Tryton')
        layout.main.add(index_section)
        return layout.tag()


class IndexNull(IndexMixin, Endpoint):
    'Index Null'
    __name__ = 'www.index.pivot.null'
    _url = '/<string:table_name>'
    _type = 'babi_pivot'

    def render(self):
        pool = Pool()
        Index = pool.get('www.index.pivot')
        return Index(self.table_name)


class PivotCompute(Endpoint):
    'Pivot Compute'
    __name__ = 'www.pivot_compute'
    _url = '/compute/<string:table_name>/<string:table_properties>'
    _type = 'babi_pivot'
    _method = 'POST'
    __slots__ = ('__dict__',)

    table_name = fields.Char('Table Name')
    table_properties = fields.Char('Table Properties')

    def render(self):
        pool = Pool()
        Index = pool.get('www.index.pivot')
        Table = pool.get('babi.table')
        table_name = _normalize_table_name(self.table_name)

        tables = Table.search([
                ('internal_name', '=', table_name),
                ], limit=1)
        access = False
        if tables:
            table, = tables
            access = table.check_access()

        target_table_name = self.table_name
        cube = None
        redirect_properties = self.table_properties
        if access:
            request = Transaction().context.get('voyager_context').request
            if self.table_properties == 'null':
                cube = Cube(table=table.name)
            else:
                cube = Cube.parse_properties(self.table_properties, table.name)
            existing_parameters = (
                cube.parameters if getattr(cube, 'parameters', None) else {})
            parameters = _get_filter_parameters(table)
            params_by_name = {}
            for parameter in parameters:
                field_name = f'{parameter.name}_{parameter.id}'
                raw_value = request.form.get(field_name) if request else None
                if raw_value in (None, '') and parameter.name in existing_parameters:
                    raw_value = existing_parameters.get(parameter.name)
                if parameter.ttype == 'boolean' and raw_value is None:
                    parsed_value = False
                else:
                    parsed_value = _parse_parameter_value(
                        parameter, raw_value)
                params_by_name[parameter.name] = parsed_value

            if cube:
                cube.parameters = params_by_name
            if parameters:
                internal_name = 'parametrized_' + secrets.token_hex(8)
                new_tables = Table.copy([table], default={
                    'internal_name': internal_name,
                    'parameters': params_by_name,
                    'crons': [],
                })
                if not new_tables:
                    logger.error('Parametrized table copy returned empty list')
                else:
                    table = new_tables[0]
                    table._compute()
                    target_table_name = table.table_name
                    if self.table_properties == 'null':
                        pivots = [p for p in table.pivots if p.active]
                        if pivots:
                            pivot_cube = pivots[0].get_cube()
                            if pivot_cube:
                                pivot_cube.parameters = params_by_name
                                redirect_properties = pivot_cube.encode_properties()
                        elif cube:
                            redirect_properties = cube.encode_properties()
                    elif cube:
                        redirect_properties = cube.encode_properties()
            else:
                Table.compute([table])
                if cube:
                    redirect_properties = cube.encode_properties()

        if redirect_properties == 'null':
            redirect_url = Index.url(table_name=target_table_name,
                table_properties='null')
        else:
            placeholder = '__TABLE_PROPERTIES__'
            redirect_url = Index.url(table_name=target_table_name,
                table_properties=placeholder)
            redirect_url = redirect_url.replace(placeholder, redirect_properties)
        request = Transaction().context.get('voyager_context').request
        if request and request.headers.get('HX-Request') == 'true':
            response = Response('')
            response.headers['HX-Redirect'] = redirect_url
            return response
        return redirect(redirect_url)


class PivotApply(Endpoint):
    'Pivot Apply'
    __name__ = 'www.pivot_apply'
    _url = '/apply/<string:table_name>/<string:table_properties>'
    _type = 'babi_pivot'
    _method = 'POST'

    table_name = fields.Char('Table Name')
    table_properties = fields.Char('Table Properties')
    pivot = fields.Many2One('babi.pivot', 'Pivot')

    def render(self):
        pool = Pool()
        Index = pool.get('www.index.pivot')
        Table = pool.get('babi.table')

        table_name = _normalize_table_name(self.table_name)

        tables = Table.search([
                ('internal_name', '=', table_name),
                ], limit=1)
        access = False
        if tables:
            table, = tables
            access = table.check_access()

        if access and self.pivot and self.pivot.table == table:
            cube = self.pivot.get_cube()
            if cube:
                properties = cube.encode_properties()
                return redirect(Index.url(table_name=self.table_name,
                    table_properties=properties))

        return redirect(Index.url(table_name=self.table_name,
            table_properties=self.table_properties))


class PivotSave(Endpoint):
    'Pivot Save'
    __name__ = 'www.pivot_save'
    _url = '/save/<string:table_name>/<string:table_properties>'
    _type = 'babi_pivot'
    _method = 'POST'

    table_name = fields.Char('Table Name')
    table_properties = fields.Char('Table Properties')
    name = fields.Char('Name')

    def render(self):
        pool = Pool()
        Index = pool.get('www.index.pivot')
        Table = pool.get('babi.table')
        RowDimension = pool.get('babi.pivot.row_dimension')
        ColumnDimension = pool.get('babi.pivot.column_dimension')
        Measure = pool.get('babi.pivot.measure')
        Property = pool.get('babi.pivot.property')
        Order = pool.get('babi.pivot.order')
        Pivot = pool.get('babi.pivot')

        table_name = _normalize_table_name(self.table_name)

        tables = Table.search([
                ('internal_name', '=', table_name),
                ], limit=1)
        access = False
        if tables:
            table, = tables
            access = table.check_access()

        if (not access or not self.table_properties
                or self.table_properties == 'null'):
            return redirect(Index.url(table_name=self.table_name,
                table_properties=self.table_properties))

        if not self.name:
            return redirect(Index.url(table_name=self.table_name,
                table_properties=self.table_properties))
        pivot, = Pivot.create([{
                    'table': table.id,
                    'name': self.name,
                    }])

        cube = Cube.parse_properties(self.table_properties, table.name)
        fields_by_internal = {f.internal_name: f for f in table.fields_}

        to_create_rows = []
        to_create_cols = []
        to_create_measures = []
        to_create_properties = []

        for field_name in cube.rows:
            field = fields_by_internal.get(field_name)
            if field:
                to_create_rows.append(RowDimension(pivot=pivot, field=field))

        for field_name in cube.columns:
            field = fields_by_internal.get(field_name)
            if field:
                to_create_cols.append(ColumnDimension(pivot=pivot, field=field))

        for field_name, aggregate in cube.measures:
            field = fields_by_internal.get(field_name)
            if field and aggregate:
                to_create_measures.append(Measure(pivot=pivot,
                    field=field, aggregate=aggregate))

        for field_name in cube.properties:
            field = fields_by_internal.get(field_name)
            if field:
                to_create_properties.append(Property(pivot=pivot, field=field))

        # Replace all pivot elements
        RowDimension.delete(list(pivot.row_dimensions))
        ColumnDimension.delete(list(pivot.column_dimensions))
        Measure.delete(list(pivot.measures))
        Property.delete(list(pivot.properties))
        Order.delete(list(pivot.order))

        RowDimension.save(to_create_rows)
        ColumnDimension.save(to_create_cols)
        Measure.save(to_create_measures)
        Property.save(to_create_properties)

        # Recreate order entries and apply cube order
        pivot = Pivot(pivot.id)
        Pivot.update_order([pivot])
        pivot = Pivot(pivot.id)

        element_map = {}
        for item in pivot.row_dimensions:
            element_map[item.field.internal_name] = item
        for item in pivot.column_dimensions:
            element_map[item.field.internal_name] = item
        for item in pivot.properties:
            element_map[item.field.internal_name] = item
        for item in pivot.measures:
            element_map[(item.field.internal_name, item.aggregate)] = item

        sequence = 0
        to_save_orders = []
        for element_key, order in cube.order:
            element = element_map.get(element_key)
            if not element:
                continue
            sequence += 1
            for order_line in pivot.order:
                if order_line.element == element:
                    order_line.sequence = sequence
                    order_line.order = order
                    to_save_orders.append(order_line)
                    break
        Order.save(to_save_orders)

        return redirect(Index.url(table_name=self.table_name,
            table_properties=self.table_properties))


# This class handle the row/columns table headers
class PivotHeaderAxis(Endpoint):
    'Pivot Header Axis'
    __name__ = 'www.pivot_header.axis'
    _url = '/<string:table_name>/header/<string:axis>/<string:table_properties>'
    _type = 'babi_pivot'

    header = fields.Char('Header')
    table_name = fields.Char('Table Name')
    table_properties = fields.Char('Table Properties')
    axis = fields.Char('Axis')

    def render(self):
        pool = Pool()
        PivotHeaderSelection = pool.get('www.pivot_header.selection')
        PivotHeaderLevelField = pool.get('www.pivot_header.level_field')
        PivotHeaderRemoveField = pool.get('www.pivot_header.remove_field')
        Table = pool.get('babi.table')

        if not self.axis or self.axis not in ['x', 'y', 'property']:
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
        elif self.axis == 'y':
            icon = COLUMNS_ICON
            name = _('Columns')
            if cube:
                fields = cube.columns
        else:
            icon = PROPERTY_ICON
            name = _('Properties')
            if cube:
                fields = cube.properties

        internal_name = _normalize_table_name(self.table_name)
        tables = Table.search([('internal_name', '=', internal_name)], limit=1)
        if not tables:
            return div()
        btable = tables[0]
        field_names = dict((x.internal_name, x.name) for x in btable.fields_)

        self.header = self.axis
        with div(cls="px-1 mt-2 flow-root col-span-2", id=f'header_{self.axis}') as header_axis:
            div(id=f'field_selection_{self.axis}')
            with div(cls="-mx-4 -my-2 overflow-x-auto sm:-mx-6 lg:-mx-8"):
                with div(cls="inline-block min-w-full py-2 align-middle sm:px-6 lg:px-8"):
                    with table(cls="min-w-full divide-y divide-gray-300"):
                        with thead():
                            with tr():
                                th(scope="col", cls="relative py-2 pl-3 pr-4 sm:pr-0").add(icon)
                                th(name, scope="col", cls="py-2 pl-4 pr-3 text-left text-sm font-semibold text-gray-900 sm:pl-0")
                                th(scope="col", cls="relative py-2 pl-3 pr-4 sm:pr-0").add(span(_('Up'), cls="sr-only"))
                                th(scope="col", cls="relative py-2 pl-3 pr-4 sm:pr-0").add(span(_('Down'), cls="sr-only"))
                                with th(scope="col", cls="relative py-2 pl-3 pr-4 sm:pr-0"):
                                    a(href="#", cls="text-indigo-600 hover:text-indigo-700 active:text-indigo-800 active:scale-95 transition",
                                        hx_target=f"#field_selection_{self.axis}",
                                        hx_post=PivotHeaderSelection.url(header=self.axis, table_name=self.table_name, table_properties=self.table_properties),
                                        hx_trigger="click", hx_swap="outerHTML").add(ADD_ICON)
                                    span(_('Add'), cls="sr-only")
                        with tbody(cls="divide-y divide-gray-200"):
                            for field in fields:
                                with tr():
                                    td(capitalize(field_names[field]), colspan="2", cls="whitespace-nowrap px-3 py-2 pl-4 pr-3 text-sm font-medium text-gray-900 sm:pl-0")
                                    with td(cls="relative whitespace-nowrap py-2 pl-3 pr-4 text-right text-sm font-medium sm:pr-0"):
                                        if field != fields[0]:
                                            a(href=PivotHeaderLevelField.url(table_name=self.table_name, header=self.axis, field=field, table_properties=self.table_properties, level_action='up'),
                                                cls="text-indigo-600 hover:text-indigo-700 active:text-indigo-800 active:scale-95 transition").add(UP_ARROW)
                                    with td(cls="relative whitespace-nowrap py-2 pl-3 pr-4 text-right text-sm font-medium sm:pr-0"):
                                        if field != fields[-1]:
                                            a(href=PivotHeaderLevelField.url(table_name=self.table_name, header=self.axis, field=field, table_properties=self.table_properties, level_action='down'),
                                                cls="text-indigo-600 hover:text-indigo-700 active:text-indigo-800 active:scale-95 transition").add(DOWN_ARROW)
                                    with td(cls="relative whitespace-nowrap py-2 pl-3 pr-4 text-right text-sm font-medium sm:pr-0"):
                                        a(href=PivotHeaderRemoveField.url(table_name=self.table_name, header=self.axis, field=field, table_properties=self.table_properties),
                                            cls="text-indigo-600 hover:text-indigo-700 active:text-indigo-800 active:scale-95 transition").add(REMOVE_ICON)
        return header_axis


# This class handle the measure table header
class PivotHeaderMeasure(Endpoint):
    'Pivot Header Measure'
    __name__ = 'www.pivot_header.measure'
    _url = '/<string:table_name>/header_measure/<string:table_properties>'
    _type = 'babi_pivot'

    header = fields.Char('Header')
    table_name = fields.Char('Table Name')
    table_properties = fields.Char('Table Properties')

    def render(self):
        pool = Pool()
        PivotHeaderSelection = pool.get('www.pivot_header.selection')
        Table = pool.get('babi.table')
        PivotHeaderRemoveField = pool.get('www.pivot_header.remove_field')
        internal_name = _normalize_table_name(self.table_name)
        tables = Table.search([('internal_name', '=', internal_name)], limit=1)
        if not tables:
            return div()
        btable = tables[0]
        field_names = dict((x.internal_name, x.name) for x in btable.fields_)

        fields = []
        if self.table_properties != 'null':
            cube = Cube.parse_properties(self.table_properties,
                self.table_name)
            fields = cube.measures
        self.header = 'measures'
        with div(cls="px-1 mt-2 flow-root col-span-3", id='header_measure') as header_measure:
            div(id='field_selection_measure')
            with div(cls="-mx-4 -my-2 overflow-x-auto sm:-mx-6 lg:-mx-8"):
                with div(cls="inline-block min-w-full py-2 align-middle sm:px-6 lg:px-8"):
                    with table(cls="min-w-full divide-y divide-gray-300"):
                        with thead():
                            with tr():
                                th(scope="col", cls="relative py-2 pl-3 pr-4 sm:pr-0").add(MEASURE_ICON)
                                th(_('Measure fields'), scope="col", cls="py-2 pl-4 pr-3 text-left text-sm font-semibold text-gray-900 sm:pl-0")
                                th(scope="col", cls="relative py-2 pl-3 pr-4 sm:pr-0").add(span(_('Measure type'), cls="sr-only"))
                                with th(scope="col", cls="relative py-2 pl-3 pr-4 sm:pr-0"):
                                    a(href="#", cls="text-indigo-600 hover:text-indigo-700 active:text-indigo-800 active:scale-95 transition",
                                        hx_target="#field_selection_measure",
                                        hx_post=PivotHeaderSelection.url(header='measure', table_name=self.table_name, table_properties=self.table_properties, render=False),
                                        hx_trigger="click", hx_swap="outerHTML").add(ADD_ICON)
                                    span(_('Add'), cls="sr-only")
                        with tbody(cls="divide-y divide-gray-200"):
                            for field in fields:
                                with tr():
                                    td(capitalize(field_names[field[0]]), colspan="2", cls="whitespace-nowrap px-3 py-2 pl-4 pr-3 text-sm font-medium text-gray-900 sm:pl-0")
                                    with td(cls="relative whitespace-nowrap py-2 pl-3 pr-4 text-right text-sm font-medium sm:pr-0"):
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
                                    with td(cls="relative whitespace-nowrap py-2 pl-3 pr-4 text-right text-sm font-medium sm:pr-0"):
                                        a(href=PivotHeaderRemoveField.url(table_name=self.table_name, header=self.header, field=field[0], table_properties=self.table_properties),
                                            cls="text-indigo-600 hover:text-indigo-700 active:text-indigo-800 active:scale-95 transition").add(REMOVE_ICON)
        return header_measure


# This class handle the order table header
class PivotHeaderOrder(Endpoint):
    'Pivot Header Component'
    __name__ = 'www.pivot_header.order'
    _url = '/<string:table_name>/header_order/<string:table_properties>'
    _type = 'babi_pivot'

    header = fields.Char('Header')
    table_name = fields.Char('Table Name')
    table_properties = fields.Char('Table Properties')

    def render(self):
        pool = Pool()
        # Components
        Index = pool.get('www.index.pivot')
        Table = pool.get('babi.table')
        PivotHeaderLevelField = pool.get('www.pivot_header.level_field')
        internal_name = _normalize_table_name(self.table_name)
        tables = Table.search([('internal_name', '=', internal_name)], limit=1)
        if not tables:
            return div()
        btable = tables[0]
        field_names = dict((x.internal_name, x.name) for x in btable.fields_)
        items = []
        if self.table_properties != 'null':
            cube = Cube.parse_properties(self.table_properties,
                self.table_name)
            items = cube.order
        self.header = 'order'
        with div(cls="px-1 mt-2 flow-root col-span-3", id='header_order') as header_order:
            div(id='field_selection_order')
            with div(cls="-mx-4 -my-2 overflow-x-auto sm:-mx-6 lg:-mx-8"):
                with div(cls="inline-block min-w-full py-2 align-middle sm:px-6 lg:px-8"):
                    with table(cls="min-w-full divide-y divide-gray-300"):
                        with thead():
                            with tr():
                                th(scope="col", cls="relative py-2 pl-3 pr-4 sm:pr-0").add(ORDER_ICON)
                                th(_('Order fields'), scope="col", cls="py-2 pl-4 pr-3 text-left text-sm font-semibold text-gray-900 sm:pl-0")
                                th(scope="col", cls="relative py-2 pl-3 pr-4 sm:pr-0").add(span(_('Measure type'), cls="sr-only"))
                                th(scope="col", cls="relative py-2 pl-3 pr-4 sm:pr-0")
                        with tbody(cls="divide-y divide-gray-200"):
                            for item in items:
                                with tr():
                                    if isinstance(item[0], tuple):
                                        value = f'{field_names.get(item[0][1], item[0][1])}({field_names.get(item[0][0], item[0][0])})'
                                        field = '__'.join(item[0])
                                    else:
                                        value = capitalize(field_names[item[0]])
                                        field = item[0]
                                    td(value, colspan="2", cls="whitespace-nowrap px-3 py-2 pl-4 pr-3 text-sm font-medium text-gray-900 sm:pl-0")
                                    with td(cls="relative whitespace-nowrap py-2 pl-3 pr-4 text-right text-sm font-medium sm:pr-0"):
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
                                            a(href=Index.url(table_name=self.table_name, table_properties=invert_table_properties),
                                                cls="text-indigo-600 hover:text-indigo-700 active:text-indigo-800 active:scale-95 transition").add(ORDER_DESC_ICON)
                                        else:
                                            a(href=Index.url(table_name=self.table_name, table_properties=invert_table_properties),
                                                cls="text-indigo-600 hover:text-indigo-700 active:text-indigo-800 active:scale-95 transition").add(ORDER_ASC_ICON)
                                    with td(cls="relative whitespace-nowrap py-2 pl-3 pr-4 text-right text-sm font-medium sm:pr-0"):
                                        if item != items[0]:
                                            a(href=PivotHeaderLevelField.url(table_name=self.table_name, header=self.header, field=field, table_properties=self.table_properties, level_action='up'),
                                                cls="text-indigo-600 hover:text-indigo-700 active:text-indigo-800 active:scale-95 transition").add(UP_ARROW)
                                    with td(cls="relative whitespace-nowrap py-2 pl-3 pr-4 text-right text-sm font-medium sm:pr-0"):
                                        if item != items[-1]:
                                            a(href=PivotHeaderLevelField.url(table_name=self.table_name, header=self.header, field=field, table_properties=self.table_properties, level_action='down'),
                                                cls="text-indigo-600 hover:text-indigo-700 active:text-indigo-800 active:scale-95 transition").add(DOWN_ARROW)
        return header_order


# This function handles the pup up that is show in every header table and add
# the item to the table properties
class PivotHeaderSelectionMixin(object):
    __slots__ = ()

    header = fields.Char('Header')
    table_name = fields.Char('Table Name')
    table_properties = fields.Char('Table Properties')
    measure = fields.Char('Measure')


class PivotHeaderSelection(PivotHeaderSelectionMixin, Endpoint):
    'Pivot Header Selection'
    __name__ = 'www.pivot_header.selection'
    _url = '/<string:table_name>/open_field_selection/<string:header>/<string:table_properties>'
    _type = 'babi_pivot'
    _method = 'POST'


    def render(self):
        pool = Pool()
        Table = pool.get('babi.table')
        PivotHeaderSelectionAddField = pool.get('www.pivot_header.selection.add_field')
        PivotHeaderSelectionCloseField = pool.get('www.pivot_header.selection.close_field')

        name = None
        match self.header:
            case 'x':
                name = 'field_selection_x'
            case 'y':
                name = 'field_selection_y'
            case 'measure':
                name = 'field_selection_measure'
            case 'property':
                name = 'field_selection_property'
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

        internal_name = _normalize_table_name(self.table_name)
        tables = Table.search([('internal_name', '=', internal_name)], limit=1)
        if not tables:
            return div()
        table = tables[0]
        fields = [x.internal_name for x in table.fields_]
        field_names = dict((x.internal_name, x.name) for x in table.fields_)

        with div(id=name, cls="relative z-10", aria_labelledby="modal-title", role="dialog", aria_modal="true") as field_selection:
            div(cls="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity", aria_hidden="true")
            with div(cls="fixed inset-0 z-10 w-screen overflow-y-auto"):
                with div(cls="flex min-h-full items-end justify-center p-4 text-center sm:items-center sm:p-0"):
                    with form(action=PivotHeaderSelectionAddField.url(header=self.header,
                            table_name=self.table_name, table_properties=self.table_properties),
                            method="POST", cls="relative transform overflow-hidden rounded-lg bg-white px-4 pb-4 pt-5 text-left shadow-xl transition-all sm:my-8 sm:w-full sm:max-w-lg sm:p-6"):
                        with div(cls="absolute right-0 top-0 hidden pr-4 pt-4 sm:block"):
                            with a(href="#",
                                    hx_target=f"#{name}",
                                    hx_post=PivotHeaderSelectionCloseField.url(header=self.header,
                                        table_name=self.table_name, table_properties=self.table_properties),
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
                                            for field in sorted(fields):
                                                if field not in fields_used:
                                                    option(capitalize(field_names[field]), value=field)
                                        else:
                                            for field in fields_used:
                                                if field not in order_fields:
                                                    if isinstance(field, tuple):
                                                        field_1 = field_names[field[0]]
                                                        field_0 = field_names[field[1]]
                                                        name_ = f'{field_1}({field_0})'
                                                    else:
                                                        name_ = field_names[field]
                                                    option(name_, value=field)

                                    if self.header == 'measure':
                                        with select(id="measure", name="measure", required=True, cls="mt-2 block w-full rounded-md border-0 py-1.5 pl-3 pr-10 text-gray-900 ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-indigo-600 sm:text-sm sm:leading-6"):
                                            option(_('Average'), value='average')
                                            option(_('Count'), value='count')
                                            option(_('Max'), value='max')
                                            option(_('Min'), value='min')
                                            option(_('Sum'), value='sum', selected=True)
                        with div(cls="mt-5 sm:mt-4 sm:flex sm:flex-row-reverse"):
                            button(_('Add'), type="submit", cls="inline-flex w-full justify-center rounded-md bg-blue-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-blue-500 sm:ml-3 sm:w-auto")
                            a(_('Cancel'), href="#",
                                hx_target=f"#{name}",
                                hx_post=PivotHeaderSelectionCloseField.url(header=self.header,
                                    table_name=self.table_name, table_properties=self.table_properties),
                                hx_trigger="click", hx_swap="outerHTML",
                                cls="mt-3 inline-flex w-full justify-center rounded-md bg-white px-3 py-2 text-sm font-semibold text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 hover:bg-gray-50 sm:mt-0 sm:w-auto")
        return field_selection


class PivotHeaderSelectionCloseField(PivotHeaderSelectionMixin, Endpoint):
    'Pivot Header Selection Close Field'
    __name__ = 'www.pivot_header.selection.close_field'
    _url = '/<string:table_name>/close_field_selection/<string:header>/<string:table_properties>'
    _type = 'babi_pivot'
    _method = ('GET', 'POST')

    field = fields.Char('Field')

    def render(self):
        name = None
        match self.header:
            case 'x':
                name = 'field_selection_x'
            case 'y':
                name = 'field_selection_y'
            case 'measure':
                name = 'field_selection_measure'
            case 'property':
                name = 'field_selection_property'
            case 'order':
                name = 'field_selection_order'

        field_selection = div(id=name)
        return field_selection


class PivotHeaderSelectionAddField(PivotHeaderSelectionMixin, Endpoint):
    'Pivot Header Selection Add Field'
    __name__ = 'www.pivot_header.selection.add_field'
    _url = '/<string:table_name>/add_field_selection/<string:header>/<string:table_properties>'
    _type = 'babi_pivot'
    _method = 'POST'

    field = fields.Char('Field')

    def render(self):
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
            case 'property':
                if self.field not in cube.properties:
                    cube.properties.append(self.field)

        return redirect(Index.url(table_name=self.table_name,
            table_properties=cube.encode_properties()))


# In this function we have some default options available in all the PivotHeader components (handle levels, remove items from header)
class PivotHeaderMixin(object):
    __slots__ = ()

    header = fields.Char('Header')
    table_name = fields.Char('Table Name')
    table_properties = fields.Char('Table Properties')
    level_action = fields.Char('Level Action')
    field = fields.Char('Field')


class PivotHeaderRemoveField(PivotHeaderMixin, Endpoint):
    'Pivot Header'
    __name__ = 'www.pivot_header.remove_field'
    _url = '/<string:table_name>/remove_field/<string:header>/<string:field>/<string:table_properties>'
    _type = 'babi_pivot'

    def render(self):
        pool = Pool()
        # Component
        Index = pool.get('www.index.pivot')
        cube = Cube.parse_properties(self.table_properties, self.table_name)

        match self.header:
            case 'x':
                cube.rows.remove(self.field)
            case 'y':
                cube.columns.remove(self.field)
            case 'property':
                cube.properties.remove(self.field)
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
        return redirect(Index.url(table_name=self.table_name,
            table_properties=table_properties))


class PivotHeaderLevelField(PivotHeaderMixin, Endpoint):
    'Pivot Header'
    __name__ = 'www.pivot_header.level_field'
    _url = '/<string:table_name>/level/<string:level_action>/<string:header>/<string:field>/<string:table_properties>'
    _type = 'babi_pivot'

    def render(self):
        pool = Pool()
        Index = pool.get('www.index.pivot')

        cube = Cube.parse_properties(self.table_properties, self.table_name)
        auxiliar_position = None
        headers = {
            'x': 'rows',
            'y': 'columns',
            'property': 'properties',
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
        return redirect(Index.url(table_name=self.table_name,
            table_properties=table_properties))


#This function handles the render of the cube into a table and the download button
class PivotTable(Endpoint):
    'Pivot Table'
    __name__ = 'www.pivot_table'
    _url = '/table/<string:table_name>/<string:table_properties>'
    _type = 'babi_pivot'
    _method = 'POST'

    table_name = fields.Char('Table Name')
    table_properties = fields.Char('Table Properties')

    def render(self):
        pool = Pool()
        # Component
        DownloadReport = pool.get('www.download_report')
        Language = pool.get('ir.lang')
        Table = pool.get('babi.table')

        internal_name = _normalize_table_name(self.table_name)
        tables = Table.search([('internal_name', '=', internal_name)], limit=1)
        if not tables:
            return div()
        btable = tables[0]
        field_names = dict((x.internal_name, x.name) for x in btable.fields_)

        language = Transaction().context.get('language', 'en')
        language, = Language.search([('code', '=', language)], limit=1)

        download = a(DOWNLOAD, cls="inline-flex items-center justify-center h-7 w-7 rounded-md text-gray-700 ring-1 ring-inset ring-gray-300 hover:bg-indigo-50 hover:text-indigo-700 active:bg-indigo-100 active:text-indigo-800 active:scale-95 transition", href=DownloadReport.url(
                table_name=self.table_name, table_properties=self.table_properties))

        cube = Cube.parse_properties(self.table_properties, self.table_name)

        # Prepare the cube properties for the expand all cube function
        cube.table = self.table_name
        cube.row_expansions = Cube.EXPAND_ALL
        cube.column_expansions = Cube.EXPAND_ALL
        expanded_table_properties = cube.encode_properties()

        # Prepare the cube properties for the collapse all cube function
        cube.table = self.table_name
        cube.row_expansions = []
        cube.column_expansions = []
        collapsed_table_properties = cube.encode_properties()

        cube = Cube.parse_properties(self.table_properties, self.table_name)

        css = 'text-gray-300'
        if cube.row_expansions != Cube.EXPAND_ALL or cube.column_expansions != Cube.EXPAND_ALL:
            css = 'text-black'
        expand_all = a(cls="inline-flex items-center justify-center h-7 w-7 rounded-md ring-1 ring-inset ring-gray-300 hover:bg-indigo-50 hover:text-indigo-700 active:bg-indigo-100 active:text-indigo-800 active:scale-95 transition " + css,
            href=Index.url(table_name=self.table_name,
                table_properties=expanded_table_properties))
        expand_all.add(EXPAND_ALL)
        css = 'text-gray-300'
        if cube.row_expansions != [] or cube.column_expansions != []:
            css = 'text-black'
        collapse_all = a(cls="inline-flex items-center justify-center h-7 w-7 rounded-md ring-1 ring-inset ring-gray-300 hover:bg-indigo-50 hover:text-indigo-700 active:bg-indigo-100 active:text-indigo-800 active:scale-95 transition " + css,
            href=Index.url(table_name=self.table_name,
                table_properties=collapsed_table_properties))
        collapse_all.add(COLLAPSE_ALL)

        controls = div(cls="flex items-center gap-2 pb-2")
        controls.add(expand_all)
        controls.add(collapse_all)
        controls.add(download)

        pivot_table = table(cls="table-auto text-sm text-left rtl:text-right text-black overflow-x-auto shadow-md rounded-lg")
        for row in cube.build():
            pivot_row = tr(cls="hover:bg-gray-50 transition-colors")
            for cell in row:
                if download:
                    # Keep the top-left header cell empty now that controls are outside the table.
                    pivot_row.add(td('', cls="text-xs bg-blue-300 text-black px-6 py-1.5 border-b-0.5 border-black"))
                    download = None
                    continue

                # Handle the headers links
                if (cell.type == CellType.ROW_HEADER or
                        cell.type == CellType.COLUMN_HEADER):
                    cell_cube = Cube.parse_properties(
                        self.table_properties, self.table_name)
                    cell_value = cell.formatted(language)

                    icon = None
                    if (cell_value and (cube.row_expansions == Cube.EXPAND_ALL or
                                         cube.column_expansions == Cube.EXPAND_ALL)):
                        if cell.row_expansion or cell.column_expansion:
                            icon = COLLAPSE
                        cell_cube.row_expansions = []
                        cell_cube.column_expansions = []

                    elif (cell.row_expansion and cell.row_expansion in
                            cube.row_expansions) or (cell.column_expansion and
                            cell.column_expansion in cube.column_expansions):
                        # This case handles the collapse action of the headers cells
                        icon = COLLAPSE

                        if cell.type == CellType.ROW_HEADER:
                            try:
                                cell_cube.row_expansions.remove(
                                    cell.row_expansion)
                            except ValueError:
                                # row_expansions may be equal to Cube.EXPAND_ALL
                                pass
                        elif cell.type == CellType.COLUMN_HEADER:
                            try:
                                cell_cube.column_expansions.remove(
                                    cell.column_expansion)
                            except ValueError:
                                # row_expansions may be equal to Cube.EXPAND_ALL
                                pass
                    elif cell.row_expansion or cell.column_expansion:
                        # This case handles all the expansions
                        icon = EXPAND

                        if cell.type == CellType.ROW_HEADER:
                            cell_cube.row_expansions.append(cell.row_expansion)
                        elif cell.type == CellType.COLUMN_HEADER:
                            cell_cube.column_expansions.append(
                                cell.column_expansion)

                    table_properties = cell_cube.encode_properties()

                    if table_properties:
                        field = str(cell.formatted(language))
                        field = field_names.get(field, field)
                        cell_value = a(
                            str(icon or '') + ' ' + field,
                            href="#", hx_target="#pivot_table",
                            hx_post=PivotTable.url(
                                    table_name=self.table_name,
                                    table_properties=table_properties),
                            hx_trigger="click", hx_swap="outerHTML",
                            hx_indicator="#loading-state")

                    pivot_row.add(td(cell_value, cls="text-xs bg-blue-300 text-black px-2 py-1 border-b-0.5 border-black", style="white-space: nowrap"))

                else:
                    pivot_row.add(td(cell.formatted(language), cls="border-b text-black bg-blue-50 border-gray-200 px-2 py-1 text-right", style="white-space: nowrap"))
            pivot_table.add(pivot_row)

        loading_div = div(id="loading-state", cls="loading-indicator absolute -translate-x-1/2 -translate-y-1/2 top-2/4 left-1/2 w-full bg-gray-800 bg-opacity-50 h-full")
        loading_spinner_ = div(role="status", cls="absolute -translate-x-1/2 -translate-y-1/2 top-20 left-48")
        loading_spinner_.add(LOADING_SPINNER)
        loading_spinner_.add(p(_('Loading ...'), cls="text-white"))
        loading_div.add(loading_spinner_)

        pivot_div = div(id='pivot_table', cls="inline-block min-w-full py-2 align-middle sm:px-6 lg:px-8 relative max-w-sm")
        pivot_div.add(loading_div)
        pivot_div.add(controls)
        pivot_div.add(pivot_table)
        return pivot_div


class DownloadReport(Endpoint):
    'Download Report'
    __name__ = 'www.download_report'
    _url = '/download/<string:table_name>/<string:table_properties>/'
    _type = 'babi_pivot'

    table_name = fields.Char('Table Name')
    table_properties = fields.Char('Table Properties')

    def render(self):
        pool = Pool()
        Language = pool.get('ir.lang')

        language = Transaction().context.get('language', 'en')
        language, = Language.search([('code', '=', language)], limit=1)

        cube = Cube.parse_properties(self.table_properties, self.table_name)
        wb = Workbook()
        ws = wb.active
        for row in cube.build():
            ws.append([x.formatted(language, worksheet=ws) for x in row])
        adjust_column_widths(ws, max_width=30)
        response = Response(save_virtual_workbook(wb))
        response.headers['Content-Disposition'] = f'attachment; filename={self.table_name}.xlsx'
        response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        return response
