from decimal import Decimal
import json
from trytond.pool import Pool, PoolMeta
from trytond.backend import DatabaseOperationalError
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
    parent = fields.Many2One('babi.dashboard.item', 'Parent', domain=[
            ('dashboard', '=', Eval('dashboard')),
            ], depends=['dashboard'])
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
                'children': cls._get_view(widget.children),
                })
        return res


class Widget(ModelSQL, ModelView):
    'Widget'
    __name__ = 'babi.widget'
    name = fields.Char('Name', required=True)
    type = fields.Selection([
            (None, ''),
            ('area', 'Area'),
            ('bar', 'Bar'),
            ('bubble', 'Bubble'),
            ('doughnut', 'Doughnut'),
            ('funnel', 'Funnel'),
            ('gauge', 'Gauge'),
            ('line', 'Line'),
            ('country-map', 'Country Map'),
            ('pie', 'Pie'),
            ('scatter', 'Scatter'),
            ('scatter-map', 'Scatter Map'),
            ('table', 'Table'),
            ('value', 'Value'),
            ], 'Type')
    table = fields.Many2One('babi.table', 'Table', states={
            'invisible': ~Bool(Eval('type')),
            'required': Bool(Eval('type')),
            }, depends=['type'])
    where = fields.Char('Where', states={
            'invisible': ~Bool(Eval('type')),
            }, depends=['type'])
    parameters = fields.One2Many('babi.widget.parameter', 'widget',
        'Parameters')
    chart = fields.Function(fields.Text('Chart'), 'on_change_with_chart')
    timeout = fields.Integer('Timeout (s)', required=True)
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
            }, depends=['type'])

    @staticmethod
    def default_timeout():
        Config = Pool().get('babi.configuration')
        config = Config(1)
        return config.default_timeout or 30

    @staticmethod
    def default_show_title():
        return True

    @staticmethod
    def default_show_toolbox():
        return 'on-hover'

    @staticmethod
    def default_image_format():
        return 'svg'

    @fields.depends('type', 'where', 'parameters', 'timeout', 'show_title',
        'show_toolbox', 'show_legend', 'static', 'name', 'image_format',
        'zoom', methods=['get_values'])
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

        values = self.get_values()

        try:
            chart = {
                'type': self.type,
            }
            data.append(chart)
            if self.type == 'area':
                chart.update(values)
                chart['type'] = 'scatter'
                chart['fill'] = 'tonexty'
            elif self.type == 'bar':
                chart.update(values)
            elif self.type == 'bubble':
                chart['type'] = 'scatter'
                chart.update({
                        'x': values.get('x', []),
                        'y': values.get('y', []),
                        })
                chart['mode'] = 'markers'
                chart['marker'] = {
                        'size': values.get('sizes', []),
                        }
            elif self.type == 'country-map':
                chart['type'] = 'scattergeo'
                chart['mode'] = 'markers'
                chart['text'] = values.get('labels', [])
                chart['locations'] = values.get('locations', [])
                sizes = values.get('sizes', [])
                if sizes:
                    chart['marker'] = {
                        'size': values.get('sizes', []),
                        }
                colors = values.get('colors', [])
                if colors:
                    chart['marker'] = {
                        'color': values.get('colors', []),
                        }
            elif self.type == 'doughnut':
                chart.update(values)
                chart['type'] = 'pie'
                chart['hole'] = 0.4
            elif self.type == 'funnel':
                chart['type'] = 'funnelarea'
                chart['values'] = values.get('values', [])
                chart['text'] = values.get('labels', [])
                layout.update({
                        'funnelmode': 'stack',
                        })
            elif self.type == 'gauge':
                value = values.get('value', [])
                chart['value'] = value and value[0] or '-'
                chart['mode'] = 'gauge'
                if 'delta' in values:
                    chart['mode'] += '+delta'
                    delta = values['delta']
                    chart['delta'] = {
                        'reference': delta and delta[0] or '-',
                        }
                min = values.get('min', [])
                min = min and min[0] or 0
                max = values.get('max', [])
                max = max and max[0] or 100
                chart['type'] = 'indicator'
                chart['gauge'] = {
                    'axis': {
                        'visible': False,
                        'range': [min, max],
                        },
                    }
                print(chart)
            elif self.type == 'line':
                chart['type'] = 'scatter'
                chart.update(values)
            elif self.type == 'pie':
                chart.update(values)
            elif self.type == 'scatter':
                chart['type'] = 'scatter'
                chart.update(values)
                chart['mode'] = 'markers'
            elif self.type == 'scatter-map':
                chart['text'] = values.get('labels', [])
                chart['lat'] = values.get('latitude', [])
                chart['lon'] = values.get('longitude', [])
                chart['type'] = 'scattermapbox'
                if chart['lat']:
                    # Latitude median:
                    center_latitude = sum(chart['lat']) / len(chart['lat'])
                    # Longitude median:
                    center_longitude = sum(chart['lon']) / len(chart['lon'])
                else:
                    center_latitude = 0
                    center_longitude = 0
                sizes = values.get('sizes', [])
                if sizes:
                    chart['marker'] = {
                        'size': sizes,
                        }
                colors = values.get('colors', [])
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
            elif self.type == 'table':
                chart['type'] = 'table'
                header = []
                columns = []
                for key, vals in values.items():
                    header.append(key)
                    columns.append(vals)
                chart['header'] = {
                    'values': header,
                    }
                chart['cells'] = {
                    'values': columns,
                    }
            elif self.type == 'value':
                value = values.get('value', [])
                chart['value'] = value and value[0] or '-'
                chart['mode'] = 'number'
                if 'delta' in values:
                    chart['mode'] += '+delta'
                    delta = values['delta']
                    chart['delta'] = {
                        'reference': delta and delta[0] or '-',
                        }
                chart['type'] = 'indicator'
                chart['gauge'] = {
                    'axis': {
                        'visible': False,
                        },
                    }
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
        if not self.table:
            return {}
        fields = [x.select_expression for x in self.parameters]
        if None in fields:
            return {}
        groupby = [x.groupby_expression for x in self.parameters
            if x.groupby_expression]
        records = self.table.execute_query(fields, self.where, groupby,
            self.timeout)

        res = {}
        types = [x.type for x in self.parameters]
        # Transpose records and fields
        transposed = list(map(list, zip(*records)))
        for type, values in zip(types, transposed):
            res[type] = [float(x) if isinstance(x, Decimal) else x
                for x in values]
        return res

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
                'delta': {
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
                'delta': {
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


class WidgetParameter(ModelSQL, ModelView):
    'Widget Parameter'
    __name__ = 'babi.widget.parameter'
    widget = fields.Many2One('babi.widget', 'Widget', required=True,
        ondelete='CASCADE')
    type = fields.Selection([
            ('colors', 'Colors'),
            ('delta', 'Delta'),
            ('labels', 'Labels'),
            ('latitude', 'Latitude'),
            ('locations', 'Locations'),
            ('longitude', 'Longitude'),
            ('minimum', 'Minimum'),
            ('maximum', 'Maximum'),
            ('sizes', 'Sizes'),
            ('value', 'Value'),
            ('values', 'Values'),
            ('x', 'X'),
            ('y', 'Y'),
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
            ], 'Aggregate', states={
            'required': Bool(Eval('aggregate_required')),
            'invisible': Bool(Eval('aggregate_invisible')),
            }, depends=['type', 'aggregate_required', 'aggregate_invisible'])
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
        if not self.widget:
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

        if self.aggregate in ('sum', 'avg'):
            if self.field.type not in ('integer', 'float', 'numeric'):
                raise UserError(gettext('babi.msg_invalid_aggregate',
                    parameter=self.rec_name, widget=self.widget.rec_name))
        settings = self.widget.parameter_settings()

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
            return '%s(%s)' % (self.aggregate.upper(), self.field.internal_name)
        else:
            settings = self.widget.parameter_settings()
            if settings.get(self.type, {}).get('aggregate') == 'required':
                return
        return self.field.internal_name