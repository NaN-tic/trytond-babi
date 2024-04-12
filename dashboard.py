from datetime import date, datetime, timedelta
from collections import OrderedDict
from decimal import Decimal
import json
from trytond.pool import Pool
from trytond.model import ModelSQL, ModelView, sequence_ordered, fields
from trytond.pyson import Eval, Bool
from trytond.transaction import Transaction
from trytond.exceptions import UserError
from trytond.i18n import gettext
from .table import convert_to_symbol


class Dashboard(ModelSQL, ModelView):
    'Dashboard'
    __name__ = 'babi.dashboard'
    name = fields.Char('Name', required=True)
    widgets = fields.One2Many('babi.dashboard.item', 'dashboard', 'Widgets')
    view = fields.Function(fields.Text('View'), 'get_view')

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls._order.insert(0, ('name', 'ASC'))
        cls._buttons.update({
                'show': {
                    'icon': 'tryton-board',
                    },
                })

    def get_view(self, name):
        pool = Pool()
        Widget = pool.get('babi.dashboard.item')
        return json.dumps(Widget._get_view(self.widgets))

    @classmethod
    @ModelView.button
    def show(cls, actions):
        if not actions:
            return
        action = actions[0]
        return {
            'name': action.name,
            'type': 'babi.action.dashboard',
            'dashboard': action.id,
            }

class DashboardItem(sequence_ordered(), ModelSQL, ModelView):
    'Dashboard Item'
    __name__ = 'babi.dashboard.item'
    dashboard = fields.Many2One('babi.dashboard', 'Dashboard', required=True)
    widget = fields.Many2One('babi.widget', 'Widget', required=True)
    colspan = fields.Integer('Columns')
    height = fields.Integer('Height', help='The default is 450px')
    parent = fields.Many2One('babi.dashboard.item', 'Parent', domain=[
            ('dashboard', '=', Eval('dashboard')),
            ])
    children = fields.One2Many('babi.dashboard.item', 'parent', 'Children')

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls.__access__.add('dashboard')

    @classmethod
    def _get_view(cls, widgets):
        res = []
        for widget in widgets:
            res.append({
                'widget': widget.widget.id,
                'colspan': widget.colspan or 1,
                'height': widget.height or 450,
                'children': cls._get_view(widget.children),
                })
        return res


class Result:
    def __init__(self, type=None, name=None, values=None):
        if values is None:
            values = []
        self.type = type
        self.name = name
        self.values = values

    def single(self, default=None):
        return self.values and self.values[0] or default

    def __bool__(self):
        return bool(self.values)


class ResultSet:
    def __init__(self, parameters=None, records=None):
        # parameters must be a list of tuples in the form:
        # [(type, name), ...]
        if parameters is None:
            parameters = []
        if records is None:
            records = []
        self.records = []
        for record in records:
            # Copy so that we do not modify the original records
            record = list(record)
            self.records.append(record)
            for i, value in enumerate(record):
                if isinstance(value, Decimal):
                    # Ensure we do not try to send Decimal to the client
                    record[i] = float(value)
                elif isinstance(value, date):
                    record[i] = value.strftime('%Y-%m-%d')
                elif isinstance(value, datetime):
                    record[i] = value.strftime('%Y-%m-%d %H:%M:%S')
                elif isinstance(value, timedelta):
                    record[i] = round(value.total_seconds() / 3600, 2)

        #self.parameters = parameters
        self.transposed = list(map(list, zip(*self.records)))
        self.results = []
        for parameter, values in zip(parameters, self.transposed):
            self.results.append(Result(parameter[0], parameter[1], values))

    def count(self, type):
        return len([x for x in self.results if x.type == type])

    def values_by_type(self, type):
        for result in self.results:
            if result.type == type:
                return result
        return Result()

    def value_list_by_type(self, type):
        res = []
        for result in self.results:
            if result.type == type:
                res.append(result)
        return res

    def z_values_on_y(self):
        ys = self.values_by_type('y')
        zs = self.values_by_type('z')

        indexed = OrderedDict()
        for pos in range(len(ys.values)):
            y = ys.values[pos]
            z = zs.values[pos]
            indexed.setdefault(z, []).append(y)

        records = []
        for x, data in indexed.items():
            record = []
            for y in data:
                record.append(y)
            records.append(record)

        parameters = []
        for z in indexed.keys():
            parameters.append((ys.type, z))
        return ResultSet(parameters, records)

    def z_values_on_x_y(self):
        xs = self.values_by_type('x')
        ys = self.values_by_type('y')
        zs = self.values_by_type('z')
        zz = OrderedDict()
        for z in zs.values:
            zz.setdefault(z)

        indexed = OrderedDict()
        for pos in range(len(xs.values)):
            x = xs.values[pos]
            y = ys.values[pos]
            z = zs.values[pos]
            if x not in indexed:
                indexed[x] = zz.copy()
            indexed[x][z] = y

        records = []
        for x, data in indexed.items():
            record = []
            record.append(x)
            for y in data.values():
                record.append(y)
            records.append(record)

        parameters = []
        parameters.append((xs.type, xs.name))
        for z in zz.keys():
            parameters.append((ys.type, z))
        return ResultSet(parameters, records)


class Widget(ModelSQL, ModelView):
    'Widget'
    __name__ = 'babi.widget'
    name = fields.Char('Name', required=True)
    type = fields.Selection([
            ('area', 'Area'),
            ('bar', 'Bar'),
            ('box', 'Box'),
            ('bubble', 'Bubble'),
            ('doughnut', 'Doughnut'),
            ('funnel', 'Funnel'),
            ('gauge', 'Gauge'),
            ('line', 'Line'),
            ('country-map', 'Country Map'),
            ('pie', 'Pie'),
            ('scatter', 'Scatter'),
            ('scatter-map', 'Scatter Map'),
            ('sunburst', 'Sunburst'),
            ('table', 'Table'),
            ('value', 'Value'),
            ], 'Type', required=True)
    table = fields.Many2One('babi.table', 'Table', states={
            'invisible': ~Bool(Eval('type')),
            'required': Bool(Eval('type')),
            })
    where = fields.Char('Where', states={
            'invisible': ~Bool(Eval('type')),
            })
    parameters = fields.One2Many('babi.widget.parameter', 'widget',
        'Parameters')
    chart = fields.Function(fields.Text('Chart'), 'on_change_with_chart')
    timeout = fields.Integer('Timeout (s)', required=True)
    limit = fields.Integer('Limit', required=True,
        help='Limit the number of rows')
    show_title = fields.Boolean('Show Title')
    show_legend = fields.Boolean('Show Legend')
    static = fields.Boolean('Static')
    show_toolbox = fields.Selection([
            ('on-hover', 'On Hover'),
            ('always', 'Always'),
            ('never', 'Never'),
            ], 'Show Toolbox', required=True, states={
            'invisible': Bool(Eval('static')),
            })
    image_format = fields.Selection([
            ('svg', 'SVG'),
            ('png', 'PNG'),
            ('jpeg', 'JPEG'),
            ('webp', 'WebP'),
            ], 'Image Format', required=True, states={
            'invisible': Bool(Eval('static')),
            })
    zoom = fields.Integer('Zoom', states={
            'invisible': Eval('type') != 'scatter-map',
            })
    box_points = fields.Selection([
            (None, 'None'),
            ('all', 'All'),
            ('outliers', 'Outliers'),
            ('suspectedoutliers', 'Suspected Outliers'),
            ], 'Box Points', states={
            'invisible': Eval('type') != 'box',
            })
    total_branch_values = fields.Boolean('Total Branch Values')
    help = fields.Function(fields.Text('Help'), 'on_change_with_help')

    @staticmethod
    def default_timeout():
        Config = Pool().get('babi.configuration')
        config = Config(1)
        return config.default_timeout or 30

    @staticmethod
    def default_limit():
        return 1000

    @staticmethod
    def default_show_title():
        return True

    @staticmethod
    def default_show_toolbox():
        return 'on-hover'

    @staticmethod
    def default_image_format():
        return 'svg'

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls._order.insert(0, ('name', 'ASC'))

    @classmethod
    def validate(cls, widgets):
        super().validate(widgets)
        for widget in widgets:
            widget.check_parameters()

    def check_parameters(self):
        settings = self.parameter_settings()
        counter = {}
        for parameter in self.parameters:
            counter.setdefault(parameter.type, 0)
            counter[parameter.type] += 1
        for key, count in counter.items():
            setting = settings.get(key)
            if setting:
                if count > setting['max']:
                    raise UserError(gettext('babi.msg_too_many_parameters',
                            widget=self.rec_name, type=key, max=setting['max']))
                if count < setting['min']:
                    raise UserError(gettext('babi.msg_not_enough_parameters',
                            widget=self.rec_name, type=key, min=setting['min']))

    @fields.depends('type')
    def on_change_with_help(self, name=None):
        settings = self.parameter_settings()
        if not settings:
            return
        help_list = []
        for key, value in settings.items():
            help_list.append('- %s (%s - %s)' % (key, value['min'],
                value['max']))
        return gettext('babi.msg_widget_help', list='\n'.join(help_list))

    @fields.depends('type', 'where', 'parameters', 'timeout', 'limit',
        'show_title', 'show_toolbox', 'show_legend', 'static', 'name',
        'image_format', 'zoom', 'box_points', methods=['get_values'])
    def on_change_with_chart(self, name=None):
        data = []
        layout = {
            'title': self.show_title and self.name or '',
            # None should become false, not null in JS
            'showlegend': bool(self.show_legend),
            }
        config = {
            'staticPlot': bool(self.static),
            'locale': Transaction().language,
            'displaylogo': False,
            'toImageButtonOptions': {
                'format': self.image_format,
                'filename': convert_to_symbol(self.name or 'tryton'),
                }
            }

        # By default modebar is shown on-hover
        if self.show_toolbox != 'on-hover':
            config['displayModeBar'] = self.show_toolbox == 'always'

        try:
            values = self.get_values()
        except Exception as e:
            data = [{
               'type': 'error',
               'message': str(e),
            }]
            return json.dumps({
                    'data': data,
                    'layout': layout,
                    'config': config,
                    })

        chart = {
            'type': self.type,
        }
        data.append(chart)
        if self.type == 'area':
            if values.count('z'):
                values = values.z_values_on_x_y()

            data = []
            x = values.values_by_type('x')
            for y in values.value_list_by_type('y'):
                chart = {}
                chart['x'] = x.values
                chart['y'] = y.values
                chart['type'] = 'scatter'
                chart['fill'] = 'tonexty'
                chart['name'] = y.name
                data.append(chart)
        elif self.type == 'bar':
            if values.count('z'):
                values = values.z_values_on_x_y()

            data = []
            x = values.values_by_type('x')
            for y in values.value_list_by_type('y'):
                chart = {}
                chart['x'] = x.values
                chart['y'] = y.values
                chart['type'] = 'bar'
                chart['name'] = y.name
                data.append(chart)
        elif self.type == 'box':
            if values.count('z'):
                values = values.z_values_on_y()

            data = []
            for y in values.value_list_by_type('y'):
                chart = {}
                chart['y'] = y.values
                chart['type'] = 'box'
                chart['name'] = y.name
                chart['boxpoints'] = self.box_points or False
                data.append(chart)
        elif self.type == 'bubble':
            chart['type'] = 'scatter'
            x = values.values_by_type('x')
            chart['x'] = x.values
            y = values.values_by_type('y')
            chart['y'] = y.values
            chart['mode'] = 'markers'
            chart['marker'] = {
                    'size': values.values_by_type('sizes').values,
                    }
        elif self.type == 'country-map':
            chart['type'] = 'scattergeo'
            chart['mode'] = 'markers'
            chart['text'] = values.values_by_type('values').values
            chart['locations'] = values.values_by_type('locations').values
            sizes = values.values_by_type('sizes')
            if sizes:
                chart['marker'] = {
                    'size': sizes.values,
                    }
            colors = values.values_by_type('colors')
            if colors:
                chart['marker'] = {
                    'color': colors.values,
                    }
        elif self.type == 'doughnut':
            labels = values.values_by_type('labels')
            if labels:
                chart['labels'] = labels.values
            vals = values.values_by_type('values')
            if vals:
                chart['values'] = vals.values
            chart['type'] = 'pie'
            chart['hole'] = 0.4
        elif self.type == 'funnel':
            chart['type'] = 'funnelarea'
            vals = values.values_by_type('values')
            if vals:
                chart['values'] = vals.values
            labels = values.values_by_type('labels')
            if labels:
                chart['text'] = labels.values
            layout.update({
                    'funnelmode': 'stack',
                    })
        elif self.type == 'gauge':
            chart['value'] = values.values_by_type('value').single('-')
            chart['mode'] = 'gauge'
            reference = values.values_by_type('reference')
            if reference:
                chart['mode'] += '+delta'
                chart['delta'] = {
                    'reference': reference.single('-'),
                    }
            min = values.values_by_type('min')
            if min:
                min = min.single(default=0)
            else:
                min = 0
            max = values.values_by_type('max')
            if max:
                max = max.single(default=100)
            else:
                max = 100
            chart['type'] = 'indicator'
            chart['gauge'] = {
                'axis': {
                    'visible': False,
                    'range': [min, max],
                    },
                }
        elif self.type == 'line':
            if values.count('z'):
                values = values.z_values_on_x_y()

            data = []
            x = values.values_by_type('x')
            for y in values.value_list_by_type('y'):
                chart = {}
                chart['x'] = x.values
                chart['y'] = y.values
                chart['type'] = 'scatter'
                chart['name'] = y.name
                data.append(chart)
        elif self.type == 'pie':
            chart['labels'] = values.values_by_type('labels').values
            chart['values'] = values.values_by_type('values').values
        elif self.type == 'scatter':
            chart['type'] = 'scatter'
            chart['x'] = values.values_by_type('x').values
            chart['y'] = values.values_by_type('y').values
            chart['mode'] = 'markers'
        elif self.type == 'scatter-map':
            chart['text'] = values.values_by_type('values').values
            chart['lat'] = values.values_by_type('latitude').values
            chart['lon'] = values.values_by_type('longitude').values
            chart['type'] = 'scattermapbox'
            if chart['lat']:
                # Latitude median:
                center_latitude = sum(chart['lat']) / len(chart['lat'])
                # Longitude median:
                center_longitude = sum(chart['lon']) / len(chart['lon'])
            else:
                center_latitude = 0
                center_longitude = 0
            sizes = values.values_by_type('sizes').values
            if sizes:
                chart['marker'] = {
                    'size': sizes,
                    }
            colors = values.values_by_type('colors').values
            if colors:
                chart['marker'] = {
                    'color': colors,
                    }
            layout['dragmode'] = 'zoom'
            layout['mapbox'] = {
                'style': 'open-street-map',
                'center': {
                    'lat': center_latitude,
                    'lon': center_longitude,
                    },
                'zoom': self.zoom or 1,
                }
        elif self.type == 'sunburst':
            chart['type'] = 'sunburst'
            chart['labels'] = values.values_by_type('labels').values
            chart['parents'] = values.values_by_type('parents').values
            chart['values'] = values.values_by_type('values').values
            chart['branchvalues'] = ('total' if self.total_branch_values
                else 'relative')
        elif self.type == 'table':
            chart['type'] = 'table'
            header = []
            columns = []
            for result in values.results:
                header.append(result.name)
                columns.append(result.values)
            chart['header'] = {
                'values': header,
                }
            chart['cells'] = {
                'values': columns,
                }
        elif self.type == 'value':
            chart['value'] = values.values_by_type('value').single('-')
            chart['mode'] = 'number'
            reference = values.values_by_type('reference')
            if reference:
                chart['mode'] += '+delta'
                chart['delta'] = {
                    'reference': reference.single('-'),
                    }
            chart['type'] = 'indicator'
            chart['gauge'] = {
                'axis': {
                    'visible': False,
                    },
                }
        return json.dumps({
                'data': data,
                'layout': layout,
                'config': config,
                })

    @fields.depends('type', 'table', 'parameters')
    def on_change_type(self):
        pool = Pool()
        Parameter = pool.get('babi.widget.parameter')

        if not self.type:
            return
        settings = self.parameter_settings()
        parameters = []
        for type in settings.keys():
            for parameter in self.parameters:
                if parameter.type == type:
                    parameters.append(parameter)
                    break
            else:
                parameter = Parameter()
                parameter.type = type
                parameters.append(parameter)

        self.parameters = tuple(parameters)

    def get_parameter(self, type):
        for parameter in self.parameters:
            if parameter.type == type:
                return parameter

    @fields.depends('table', 'parameters', 'where', 'timeout')
    def get_values(self):
        if not self.table or not self.parameters:
            return ResultSet()
        fields = [x.select_expression for x in self.parameters]
        if None in fields:
            return ResultSet()
        groupby = [x.groupby_expression for x in self.parameters
            if x.groupby_expression]
        records = self.table.execute_query(fields, self.where, groupby,
            self.timeout)

        if len(records) > self.limit:
            raise UserError(gettext('babi.msg_chart_limit',
                    widget=self.rec_name, count=len(records), limit=self.limit))
        return ResultSet([(x.type, x.field.name) for x in self.parameters], records)

    @fields.depends('type')
    def parameter_settings(self):
        if self.type == 'area':
            return {
                'x': {
                    'min': 1,
                    'max': 1,
                    'aggregate': 'forbidden',
                    },
                'y': {
                    'min': 1,
                    'max': 10,
                    'aggregate': 'required',
                     },
                'z': {
                    'min': 0,
                    'max': 1,
                    'aggregate': 'forbidden',
                     },
                }
        elif self.type == 'bar':
            return {
                'x': {
                    'min': 1,
                    'max': 1,
                    'aggregate': 'forbidden',
                    },
                'y': {
                    'min': 1,
                    'max': 10,
                    'aggregate': 'required',
                     },
                'z': {
                    'min': 0,
                    'max': 1,
                    'aggregate': 'forbidden',
                     },
                }
        elif self.type == 'box':
            return {
                'y': {
                    'min': 1,
                    'max': 10,
                    'aggregate': 'forbidden',
                    },
                'z': {
                    'min': 0,
                    'max': 1,
                    'aggregate': 'forbidden',
                    },
                }
        elif self.type == 'pie':
            return {
                'labels': {
                    'min': 1,
                    'max': 1,
                    'aggregate': 'forbidden',
                    },
                'values': {
                    'min': 1,
                    'max': 1,
                    'aggregate': 'required',
                    },
                }
        elif self.type == 'bubble':
            return {
                'x': {
                    'min': 1,
                    'max': 1,
                    'aggregate': 'forbidden',
                    },
                'y': {
                    'min': 1,
                    'max': 1,
                    'aggregate': 'forbidden',
                    },
                'sizes': {
                    'min': 1,
                    'max': 1,
                    'aggregate': 'required',
                    },
                }
        elif self.type == 'country-map':
            return {
                'labels': {
                    'min': 1,
                    'max': 1,
                    'aggregate': 'forbidden',
                    },
                'locations': {
                    'min': 1,
                    'max': 1,
                    'aggregate': 'forbidden',
                    },
                'colors': {
                    'min': 0,
                    'max': 1,
                    'aggregate': 'required',
                    },
                'sizes': {
                    'min': 0,
                    'max': 1,
                    'aggregate': 'required',
                    },
                }
        elif self.type == 'doughnut':
            return {
                'labels': {
                    'min': 1,
                    'max': 1,
                    'aggregate': 'forbidden',
                    },
                'values': {
                    'min': 1,
                    'max': 1,
                    'aggregate': 'required',
                    },
                }
        elif self.type == 'funnel':
            return {
                'labels': {
                    'min': 1,
                    'max': 1,
                    'aggregate': 'forbidden',
                    },
                'values': {
                    'min': 1,
                    'max': 1,
                    'aggregate': 'required',
                    },
                }
        elif self.type == 'gauge':
            return {
                'reference': {
                    'min': 0,
                    'max': 1,
                    'aggregate': 'required',
                },
                'minimum': {
                    'min': 1,
                    'max': 1,
                    'aggregate': 'required',
                },
                'maximum': {
                    'min': 1,
                    'max': 1,
                    'aggregate': 'required',
                },
                'value': {
                   'min': 1,
                   'max': 1,
                   'aggregate': 'required',
                    },
                }
        elif self.type == 'line':
            return {
                'x': {
                    'min': 1,
                    'max': 1,
                    'aggregate': 'forbidden',
                    },
                'y': {
                    'min': 1,
                    'max': 10,
                    'aggregate': 'required',
                    },
                'z': {
                    'min': 0,
                    'max': 1,
                    'aggregate': 'forbidden',
                     },
                }
        elif self.type == 'scatter':
            return {
                'x': {
                    'min': 1,
                    'max': 1,
                    'aggregate': 'forbidden',
                    },
                'y': {
                    'min': 1,
                    'max': 1,
                    'aggregate': 'forbidden',
                    },
                }
        elif self.type == 'scatter-map':
            return {
                'labels': {
                    'min': 1,
                    'max': 1,
                    'aggregate': 'forbidden',
                    },
                'latitude': {
                    'min': 1,
                    'max': 1,
                    'aggregate': 'forbidden',
                    },
                'longitude': {
                    'min': 1,
                    'max': 1,
                    'aggregate': 'forbidden',
                    },
                'colors': {
                    'min': 0,
                    'max': 1,
                    'aggregate': 'required',
                    },
                'sizes': {
                    'min': 0,
                    'max': 1,
                    'aggregate': 'required',
                    },
                }
        elif self.type == 'sunburst':
            return {
                'labels': {
                    'min': 1,
                    'max': 1,
                    'aggregate': 'forbidden',
                    },
                'parents': {
                    'min': 1,
                    'max': 1,
                    'aggregate': 'forbidden',
                    },
                'values': {
                    'min': 1,
                    'max': 1,
                    'aggregate': 'required',
                    },
                }
        elif self.type == 'table':
            return {
                'labels': {
                    'min': 1,
                    'max': 1,
                    'aggregate': 'forbidden',
                    },
                'values': {
                    'min': 1,
                    'max': 10,
                    'aggregate': 'required',
                    },
                }
        elif self.type == 'value':
            return {
                'reference': {
                    'min': 0,
                    'max': 1,
                    'aggregate': 'required',
                },
                'value': {
                   'min': 1,
                   'max': 1,
                   'aggregate': 'required',
                    },
                }


class WidgetParameter(sequence_ordered(), ModelSQL, ModelView):
    'Widget Parameter'
    __name__ = 'babi.widget.parameter'
    widget = fields.Many2One('babi.widget', 'Widget', required=True,
        ondelete='CASCADE')
    type = fields.Selection([
            ('colors', 'Colors'),
            ('reference', 'Reference'),
            ('labels', 'Labels'),
            ('latitude', 'Latitude'),
            ('locations', 'Locations'),
            ('longitude', 'Longitude'),
            ('minimum', 'Minimum'),
            ('maximum', 'Maximum'),
            ('parents', 'Parents'),
            ('sizes', 'Sizes'),
            ('value', 'Value'),
            ('values', 'Values'),
            ('x', 'X'),
            ('y', 'Y'),
            ('z', 'Z'),
            ], 'Type', required=True)
    field = fields.Many2One('babi.field', 'Field', domain=[
            ('table', '=', Eval('_parent_widget', {}).get('table', -1)),
            ])
    aggregate = fields.Selection([
            (None, ''),
            ('sum', 'Sum'),
            ('count', 'Count'),
            ('avg', 'Average'),
            ('min', 'Minimum'),
            ('max', 'Maximum'),
            ('median', 'Median'),
            ], 'Aggregate', states={
            'required': Bool(Eval('aggregate_required')),
            'invisible': Bool(Eval('aggregate_invisible')),
            })
    aggregate_required = fields.Function(fields.Boolean('Aggregate Required'),
        'on_change_with_aggregate_required')
    aggregate_invisible = fields.Function(fields.Boolean('Aggregate Invisible'),
        'on_change_with_aggregate_invisible')

    @fields.depends('type', 'widget', '_parent_widget.type')
    def on_change_with_aggregate_required(self, name=None):
        if not self.widget:
            return
        settings = self.widget.parameter_settings()
        return settings.get(self.type, {}).get('aggregate') == 'required'

    @fields.depends('type', 'widget', '_parent_widget.type')
    def on_change_with_aggregate_invisible(self, name=None):
        if not self.widget or not self.type:
            return
        settings = self.widget.parameter_settings()
        return settings.get(self.type, {}).get('aggregate') == 'forbidden'

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls.__access__.add('widget')

    @classmethod
    def validate(cls, parameters):
        super().validate(parameters)
        for parameter in parameters:
            parameter.check_aggregate()
            parameter.check_type()

    def get_rec_name(self, name):
        res = self.type
        if self.field:
            res += ' - ' + self.field.name
        return res

    def check_aggregate(self):
        if not self.aggregate or not self.field:
            return
        if self.aggregate in ('sum', 'avg', 'median'):
            if (self.field and self.field.type
                    and self.field.type not in ('integer', 'float', 'numeric')):
                raise UserError(gettext('babi.msg_invalid_aggregate',
                    parameter=self.rec_name, widget=self.widget.rec_name))

    def check_type(self):
        settings = self.widget.parameter_settings()
        if self.type not in settings:
            raise UserError(gettext('babi.msg_invalid_parameter_type',
                parameter=self.rec_name, widget=self.widget.rec_name,
                types=', '.join(settings.keys())))

    @property
    def groupby_expression(self):
        if not self.field:
            return
        if self.aggregate:
            return
        return self.field.internal_name

    @property
    def select_expression(self):
        if not self.field:
            return
        if self.aggregate:
            if self.aggregate == 'median':
                return ('percentile_cont(0.5) WITHIN GROUP (ORDER BY "%s")' %
                    self.field.internal_name)
            else:
                return '%s("%s")' % (self.aggregate.upper(),
                    self.field.internal_name)
        else:
            settings = self.widget.parameter_settings()
            if settings.get(self.type, {}).get('aggregate') == 'required':
                return
        return self.field.internal_name
