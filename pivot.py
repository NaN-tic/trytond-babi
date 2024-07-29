import datetime
from werkzeug.routing import Rule
from werkzeug.utils import redirect, send_from_directory
from dominate.tags import (div, h1, h2, p, a, form, button, span, table, thead,
    tbody, tr, td, input_, br, head, html, body, meta, link, title, script, h3,
    comment, section, header, nav, ul, li, img, footer, label, ol, dl, dt, dd,
    select, option, main, th, fieldset, legend, h4, time_, h5, aside)
from dominate.util import raw
from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction
from trytond.modules.voyager.voyager import Component, Trigger
from trytond.modules.voyager.i18n import _
from werkzeug.wrappers import Response
from trytond.config import config

from collections import deque


class Site(metaclass=PoolMeta):
    __name__ = 'www.site'

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls.type.selection += [('babi_pivot', 'Pivot')]

###############################################################################
################################ PIVOT CLASSES ################################
###############################################################################
class Operation:
    # Common fields
    name = ''
    table = ''
    # Grouping fields
    position = ''
    hierarchy = ''
    state = ''
    operation = ''
    parent = None
    # Result fields
    aggregation_operation = ''
    # Record fields
    record_state = ''
    open_records = []
    parent_record = []
    childs_record = []
    # List of grouping fields and reuslt fields, needed to create the urls
    grouping_fields = []
    result_fields = []
    database_name = ''

    def select_closed(self, table_structure):
        h = Header(self.name, None, self.hierarchy, self.position, [], self.record_state)
        if self.parent:
            h.parent = self.parent

        # The columns at level 0 are like the parents and must have the same
        # name as the column from postgress
        if self.hierarchy == 0:
            if self.position == 'row':
                table_structure.table_rows.append(h)
                #table_structure.rows.append(h)
            elif self.position == 'column':
                table_structure.table_columns.append(h)
                #table_structure.columns.append(h)

        if self.parent:
            self.parent.childs.append(h)
        #TODO: Diference between table row/column and records used as headers
        # Calculate only the total (like using a sum)
        if self.position == 'row':
            table_structure.rows.append(h)
        elif self.position == 'column':
            table_structure.columns.append(h)
        else:
            raise

        return []

    def select_open(self, table_structure):
        # We need to get the child level
        print('SELECT OPEN')
        cursor = Transaction().connection.cursor()
        cursor.execute(f'SELECT {self.name} FROM {self.table} GROUP BY {self.name} ORDER BY {self.name};')

        h = Header(self.name, None, self.hierarchy, self.position, [], self.record_state)
        if self.position == 'row':
            table_structure.table_rows.append(h)
            # Only add as row the first level of the table
            if self.hierarchy == 0:
                table_structure.rows.append(h)
        elif self.position == 'column':
            table_structure.table_columns.append(h)
            # Only add as row the first level of the table
            if self.hierarchy == 0:
                table_structure.columns.append(h)

        results = cursor.fetchall()
        new_operations = []
        for result in results:
            op = Operation()
            op.name = result[0]
            op.position = self.position
            op.hierarchy = self.hierarchy + 1
            op.state = 'closed'
            op.table = self.table
            op.operation = 'select_closed'
            op.parent = h
            op.open_records = self.open_records
            op.record_state = 'closed'
            if str(result[0]) in self.open_records:
                op.record_state = 'open'
            new_operations.append(op)
        return new_operations

    def calculate_total(self, table_structure):
        cursor = Transaction().connection.cursor()
        cursor.execute(f'SELECT {self.aggregation_oeration}({self.name}) FROM {self.table}')
        results = cursor.fetchall()
        if (None, None) not in table_structure.values.keys():
            table_structure.values[(None, None)] = {}
        if (self.aggregation_oeration, self.name) not in table_structure.values[(None, None)].keys():
            table_structure.values[(None, None)][(self.aggregation_oeration, self.name)] = {}
        table_structure.values[(None, None)][(self.aggregation_oeration, self.name)] = results[0][0]
        table_structure.aggregations.append((self.aggregation_oeration, self.name))
        return []

    def calculate_values(self, table_structure):
        values = {}
        cursor = Transaction().connection.cursor()
        aggregate_fields = ','.join([f'{aggregation[0]}({aggregation[1]})' for aggregation in table_structure.aggregations])
        #TODO: If we only have a one dimension in the rows or the columns we dont need to do the group by

        # Get the hierarchy levels of the columns and rows
        hierarchy_columns = [t.hierarchy for t in table_structure.columns]
        hierarchy_columns.sort()
        hierarchy_columns = list(set(hierarchy_columns))
        hierarchy_rows = [t.hierarchy for t in table_structure.rows]
        hierarchy_rows.sort()
        hierarchy_rows = list(set(hierarchy_rows))

        for hierarchy_column in hierarchy_columns:
            for table_structure_column in table_structure.table_columns:
                # If we only have one dimension, we dont need to calculate
                # anything the values are already calculated using
                # "calculate_totals"
                if len(table_structure.columns) < 1:
                    continue

                # Get the list of each parent
                table_strucutre_columns = []
                table_strucutre_columns.append(table_structure_column.name)
                # Loop trough all the hierarchy levels, we
                # remove one level (is the level where we are now)
                hierarchy_level = table_structure_column.hierarchy - 1
                while hierarchy_level >= 0:
                    for table_row in table_structure.table_columns:
                        if table_row.hierarchy == hierarchy_level:
                            table_strucutre_columns.append(table_row.name)
                    hierarchy_level -= 1
                table_strucutre_columns.reverse()

                for aggregation in table_structure.aggregations:
                    # If we are checking the first level, we need to do other things
                    if (table_structure_column.hierarchy == hierarchy_column and
                        hierarchy_column == hierarchy_columns[0]):
                        cursor.execute(f'SELECT {table_structure_column.name}, {aggregate_fields} FROM {self.table} GROUP BY {table_structure_column.name} ORDER BY {table_structure_column.name};')
                        results = cursor.fetchall()
                        if results:
                            for result in results:
                                if (result[0], None) not in values.keys():
                                    values[(result[0], None)] = {}
                                if aggregation not in values[(result[0], None)].keys():
                                    values[(result[0], None)][aggregation] = {}
                                values[(result[0], None)][aggregation] = result[-1]
                    # for each other level, we need to get all the parents and group by them
                    elif (table_structure_column.hierarchy == hierarchy_column):
                        # Get the list of each parent
                        cursor.execute(f'SELECT {",".join(table_strucutre_columns)}, {aggregate_fields} FROM {self.table} GROUP BY {",".join(table_strucutre_columns)} ORDER BY {",".join(table_strucutre_columns)};')
                        results = cursor.fetchall()
                        #if results:
                        #    for result in results:


                    else:
                        continue
                for hierarchy_row in hierarchy_rows:
                    for table_structure_row in table_structure.table_rows:
                        if len(table_structure.rows) < 1:
                            continue

                        # Get the list of each parent
                        table_strucutre_rows = []
                        table_strucutre_rows.append(table_structure_row.name)
                        # Loop trough all the hierarchy levels, we
                        # remove one level (is the level where we are now)
                        hierarchy_level = table_structure_row.hierarchy - 1
                        while hierarchy_level >= 0:
                            for table_row in table_structure.table_rows:
                                if table_row.hierarchy == hierarchy_level:
                                    table_strucutre_rows.append(table_row.name)
                            hierarchy_level -= 1
                        table_strucutre_rows.reverse()

                        for aggregation in table_structure.aggregations:
                            # If we are checking the first level, we need to do other things
                            if (table_structure_row.hierarchy == hierarchy_row and
                                    hierarchy_row == hierarchy_rows[0]):
                                cursor.execute(f'SELECT {table_structure_row.name}, {aggregate_fields} FROM {self.table} GROUP BY {table_structure_row.name} ORDER BY {table_structure_row.name}')
                                results = cursor.fetchall()
                                if results:
                                    for result in results:
                                        if (None, result[0]) not in values.keys():
                                            values[(None, result[0])] = {}
                                        if aggregation not in values[(None, result[0])].keys():
                                            values[(None, result[0])][aggregation] = {}
                                        values[(None, result[0])][aggregation] = result[-1]
                            elif (table_structure_row.hierarchy == hierarchy_row):
                                cursor.execute(f'SELECT {",".join(table_strucutre_rows)} , {aggregate_fields} FROM {self.table} GROUP BY {",".join(table_strucutre_rows)} ORDER BY {",".join(table_strucutre_rows)};')
                                results = cursor.fetchall()
                                if results:
                                    for result in results:
                                        test = (result[:len(table_strucutre_rows)])
                                        if (result[:len(table_strucutre_rows)]) not in values.keys():
                                            values[(result[:len(table_strucutre_rows)])] = {}
                                        if aggregation not in values[(result[:len(table_strucutre_rows)])].keys():
                                            values[(result[0], result[1])][aggregation] = {}
                                        values[(result[:len(table_strucutre_rows)])][aggregation] = result[-1]
                            else:
                                continue

                            cursor.execute(f'SELECT {",".join(table_strucutre_columns + table_strucutre_rows)}, {aggregate_fields} FROM {self.table} GROUP BY {",".join(table_strucutre_columns + table_strucutre_rows)} ORDER BY {",".join(table_strucutre_columns + table_strucutre_rows)};')
                            results = cursor.fetchall()
                            if results:
                                for result in results:
                                    if (result[:len(table_strucutre_columns + table_strucutre_rows)]) not in values.keys():
                                        values[(result[:len(table_strucutre_columns + table_strucutre_rows)])] = {}
                                    if aggregation not in values[(result[:len(table_strucutre_columns + table_strucutre_rows)])].keys():
                                        values[(result[:len(table_strucutre_columns + table_strucutre_rows)])][aggregation] = {}
                                    values[(result[:len(table_strucutre_columns + table_strucutre_rows)])][aggregation] = result[-1]
        #print(f'VALUES: {values}')
        table_structure.values = {**table_structure.values, **values}
        return []

    def create_table(self, table_structure):
        pool = Pool()
        Pivot = pool.get('www.pivot_table')
        # For now, to show the values we separtate the table in rows and
        # calculate all the values of each row
        # The column list (the first row of the table) contain all the columns + a space for each row
        # Get the hierarchy levels of the columns and rows
        hierarchy_columns = [t.hierarchy for t in table_structure.columns]
        hierarchy_columns.sort()
        hierarchy_columns = list(set(hierarchy_columns))
        hierarchy_rows = [t.hierarchy for t in table_structure.rows]
        hierarchy_rows.sort()
        hierarchy_rows = list(set(hierarchy_rows))
        # For each column hierarchy level we need to add a new row
        # For each row hierarchy level we need to add a new column

        def create_row_childs(table_value_row_cordinates_, hierarchy_row, index):
            create_childs_rows = True
            hierarchy_row_child = hierarchy_row + 1
            index_child = index + 1

            lines_to_add = []
            while create_childs_rows:
                create_childs_rows = False
                for table_structure_child_row in table_structure.rows:
                    row = tr()
                    table_value_row_cordinates = [] + table_value_row_cordinates_
                    if table_structure_child_row.hierarchy == hierarchy_row_child:
                        for i in range(index_child):
                            row.add(td('',cls="text-xs uppercase bg-gray-300 text-gray-900 px-6 py-3"))
                        row.add(td(str(table_structure_child_row.name), cls="text-xs uppercase bg-gray-300 text-gray-900 px-6 py-3"))

                        for i in range(len(hierarchy_rows)-(index_child+1)):
                            row.add(td('',cls="text-xs uppercase bg-gray-300 text-gray-900 px-6 py-3"))

                        table_value_row_cordinates.append(table_structure_child_row.name)

                        for table_structure_column in table_structure.columns:
                            for aggregation in table_structure.aggregations:
                                table_value_column_cordinates = []
                                value = '0'

                                table_value_column_cordinate = table_structure_column.name
                                if table_structure_column in table_structure.table_columns:
                                    table_value_column_cordinate = None
                                table_value_column_cordinates.append(table_value_column_cordinate)

                                coordinates = tuple(table_value_column_cordinates + table_value_row_cordinates)

                                if coordinates in table_structure.values.keys():
                                    if (aggregation[0], aggregation[1]) in table_structure.values[coordinates].keys():
                                        value = table_structure.values[coordinates][(aggregation[0], aggregation[1])]
                                        if value == {}:
                                            value = '0'

                                # If we have value = '0' we need to check if any of the coordinates is "None" and try to search again without this coordinate:
                                if value == '0':
                                    coordinates = tuple([c for c in list(coordinates) if c != None])
                                    if coordinates in table_structure.values.keys():
                                        if (aggregation[0], aggregation[1]) in table_structure.values[coordinates].keys():
                                            value = table_structure.values[coordinates][(aggregation[0], aggregation[1])]
                                            if value == {}:
                                                value = '0'
                                row.add(td(str(value),cls="border-b bg-gray-50 border-gray-000 px-6 py-4"))
                        if table_structure_child_row.state == 'open':
                            create_childs_rows = True
                        lines_to_add.append(row)
                index_child += 1
            return lines_to_add

        table_to_show = []
        # Header
        # If true, we dont show the next level or any other level by default, only if the header is "open"
        specific_record_column_open = None
        for hierarchy_column in hierarchy_columns:
            row = tr()
            #row.add(td('',cls="text-xs uppercase bg-gray-300 text-gray-900 px-6 py-3"))
            for i in range(len(hierarchy_rows)):
                row.add(td('',cls="text-xs uppercase bg-gray-300 text-gray-900 px-6 py-3"))
            first_column = True

            if specific_record_column_open and specific_record_column_open < hierarchy_column:
                row.add(td('',cls="text-xs uppercase bg-gray-300 text-gray-900 px-6 py-3"))
                for table_strucutre_column in table_structure.columns:
                    if table_strucutre_column.hierarchy == specific_record_column_open:
                        if table_strucutre_column.record_childs:
                            row.add(td('',cls="text-xs uppercase bg-gray-300 text-gray-900 px-6 py-3"))
                            for record_child in table_strucutre_column.record_childs:
                                row.add(td(record_child.name,cls="text-xs uppercase bg-gray-300 text-gray-900 px-6 py-3"))
                        else:
                            row.add(td('',cls="text-xs uppercase bg-gray-300 text-gray-900 px-6 py-3"))
                table_to_show.append(row)
                continue
            print(f'TABLE STRUCUTRE COLUMNS: {table_structure.columns}')
            for table_structure_column in table_structure.columns:
                print(f'TABLE STRUCUTRE COLUMN: {table_structure_column.name} | {table_structure_column.hierarchy} | {hierarchy_column}')
                if table_structure_column.hierarchy == hierarchy_column:
                    if hierarchy_column != hierarchy_columns[0] and first_column:
                        first_column = False
                        parent = table_structure_column.parent
                        while parent:
                            row.add(td('',cls="text-xs uppercase bg-gray-300 text-gray-900 px-6 py-3"))
                            parent = parent.parent

                        grouping_fields, result_fields = self.create_url(table_structure_column)
                        row.add(td(a(table_structure_column.name, href="#",
                                hx_target="#pivot_table",
                                hx_post=Pivot(database_name=self.database_name,
                                    table_name=self.table, grouping_fields=grouping_fields,
                                    result_fields=result_fields, render=False).url(),
                                hx_trigger="click", hx_swap="outerHTML"),
                            cls="text-xs uppercase bg-gray-300 text-gray-900 px-6 py-3"))
                    else:
                        grouping_fields, result_fields = self.create_url(table_structure_column)
                        row.add(td(a(table_structure_column.name, href="#",
                                    hx_target="#pivot_table",
                                    hx_post=Pivot(database_name=self.database_name,
                                        table_name=self.table, grouping_fields=grouping_fields,
                                        result_fields=result_fields, render=False).url(),
                                    hx_trigger="click", hx_swap="outerHTML"),
                            cls="text-xs uppercase bg-gray-300 text-gray-900 px-6 py-3"))
                        #row.add(td(table_structure_column.name,cls="text-xs uppercase bg-gray-300 text-gray-900 px-6 py-3"))
                        for child in table_structure_column.childs:
                            row.add(td('',cls="text-xs uppercase bg-gray-300 text-gray-900 px-6 py-3"))
                        #TODO: add news columns of childs
                    if table_structure_column.state == 'open':
                        specific_record_column_open = hierarchy_column
                        for table_structure_child_column in table_structure.columns:
                            if table_structure_child_column.hierarchy == hierarchy_column + 1:
                                table_structure_column.record_childs.append(table_structure_child_column)
                                table_structure_child_column.record_parents.append(table_structure_column)
                                row.add(td('',cls="text-xs uppercase bg-gray-300 text-gray-900 px-6 py-3"))
            table_to_show.append(row)

        index = 0
        # If true, we dont show the next level or any other level by default, only if the header is "open"
        specific_record_row_open = None
        for hierarchy_row in hierarchy_rows:
            # Fill row headers
            for table_structure_row in table_structure.rows:
                row = tr()

                if table_structure_row.hierarchy == hierarchy_row:
                    # This "if" dont let the script create more sublevels if we
                    # have any open, this way, we dont have at the end the
                    # sublevels rows with "0" as value (because they dont have a value)
                    if specific_record_row_open and specific_record_row_open < table_structure_row.hierarchy:
                        continue
                    #row.add(td('',cls="text-xs uppercase bg-gray-300 text-gray-900 px-6 py-3"))
                    for i in range(index):
                        row.add(td('',cls="text-xs uppercase bg-gray-300 text-gray-900 px-6 py-3"))
                    #TODO: URL
                    grouping_fields, result_fields = self.create_url(table_structure_row)

                    row.add(td(a(table_structure_row.name, href="#",
                            hx_target="#pivot_table",
                            hx_post=Pivot(database_name=self.database_name,
                                table_name=self.table, grouping_fields=grouping_fields,
                                result_fields=result_fields, render=False).url(),
                            hx_trigger="click", hx_swap="outerHTML"),
                        cls="text-xs uppercase bg-gray-300 text-gray-900 px-6 py-3"))

                    for i in range((len(hierarchy_rows))-(index+1)):
                        row.add(td('',cls="text-xs uppercase bg-gray-300 text-gray-900 px-6 py-3"))

                    table_value_row_cordinates = []
                    if table_structure_row in table_structure.table_rows:
                        table_value_row_cordinates.append(None)
                    else:
                        table_value_row_cordinates.append(table_structure_row.name)

                    for table_structure_column in table_structure.columns:
                        for aggregation in table_structure.aggregations:
                            value = '0'

                            table_value_column_cordinates = []
                            if table_structure_column in table_structure.table_columns:
                                table_value_column_cordinates.append(None)
                            else:
                                table_value_column_cordinates.append(table_structure_column.name)

                            coordinates = tuple(table_value_column_cordinates + table_value_row_cordinates)

                            if (coordinates) in table_structure.values.keys():
                                if (aggregation[0], aggregation[1]) in table_structure.values[(coordinates)].keys():
                                    value = table_structure.values[(coordinates)][(aggregation[0], aggregation[1])]
                                    if value == {}:
                                        value = '0'
                            row.add(td(str(value),cls="border-b bg-gray-50 border-gray-000 px-6 py-4"))

                            if table_structure_column.state == 'open' and specific_record_column_open:
                                #TODO: we need to remade this section
                                for record_child in table_structure_column.record_childs:
                                    table_value_column_cordinates = []
                                    table_value_column_cordinates.append(table_structure_column.name)
                                    table_value_column_cordinates.append(record_child.name)

                                    #TODO: loop to navigate multiple open levles
                                    coordinates = tuple(table_value_column_cordinates + table_value_row_cordinates)

                                    if (coordinates) in table_structure.values.keys():
                                        if (aggregation[0], aggregation[1]) in table_structure.values[(coordinates)].keys():
                                            value = table_structure.values[(coordinates)][(aggregation[0], aggregation[1])]
                                            if value == {}:
                                                value = '0'
                                    row.add(td(str(value),cls="border-b bg-gray-50 border-gray-000 px-6 py-4"))
                    table_to_show.append(row)
                    if table_structure_row.state == 'open':
                        specific_record_row_open = hierarchy_row
                        child_rows = create_row_childs(table_value_row_cordinates, hierarchy_row, index)
                        table_to_show += child_rows
            index += 1
        #print(tabulate(table_to_show, tablefmt='fancy_grid'))
        pivot_table = table(cls="w-full text-sm text-left rtl:text-right text-gray-600")
        for row in table_to_show:
            pivot_table.add(row)
        pivot_div = div(id='pivot_table', cls="inline-block min-w-full py-2 align-middle sm:px-6 lg:px-8")
        pivot_div.add(pivot_table)
        return pivot_div

    def create_url(self, cell):
        url = ''
        parent = None
        if cell.parent:
            parent = cell.parent
        # Prepare the modified grouping_field
        new_grouping_field = None
        if parent:
            for grouping_field in self.grouping_fields:
                if grouping_field.name == parent.name:
                    new_grouping_field = GroupingField()
                    new_grouping_field.name = grouping_field.name
                    new_grouping_field.position = grouping_field.position
                    new_grouping_field.hierarchy = grouping_field.hierarchy
                    new_grouping_field.state = grouping_field.state
                    new_grouping_field.open_records = grouping_field.open_records
                    #new_grouping_field = grouping_field
        else:
            for grouping_field in self.grouping_fields:
                if grouping_field.name == cell.name:
                    new_grouping_field = GroupingField()
                    new_grouping_field.name = grouping_field.name
                    new_grouping_field.position = grouping_field.position
                    new_grouping_field.hierarchy = grouping_field.hierarchy
                    new_grouping_field.state = grouping_field.state
                    new_grouping_field.open_records = grouping_field.open_records
                    #new_grouping_field = grouping_field

        print(f'{parent} CELL STATE: {cell.name} | {cell.state} | {cell.state  == "closed"} ')
        print(f'    GROUPING STATE: {new_grouping_field.name} | {new_grouping_field.state} | {new_grouping_field.state == "closed" } ')

        if not new_grouping_field:
            print('NOT NET GROUPING FIELD')
            #TODO: we need to serach what we do in this case
            raise
        if new_grouping_field.state == 'closed':
            if not new_grouping_field:
                new_grouping_field = GroupingField()
                new_grouping_field.name = cell.name
                new_grouping_field.position = cell.position
                new_grouping_field.hierarchy = cell.hierarchy
                new_grouping_field.state = 'open'
                new_grouping_field.open_records = []
            elif new_grouping_field and parent:
                if not new_grouping_field.open_records:
                    new_grouping_field.open_records = [cell.name]
                else:
                    new_grouping_field.open_records.append(cell.name)
            else:
                new_grouping_field.state = 'open'
        else:
            if new_grouping_field and parent:
                #print(f'REMOVE OPEN RECORS :{new_grouping_field.open_records} | NAME: {new_grouping_field.name}')
                if new_grouping_field.open_records:
                    new_grouping_field.open_records.remove(cell.name)
            else:
                new_grouping_field.state = 'closed'

        print(f'    GROUPING STATE2: {new_grouping_field.name} | {new_grouping_field.state} | {new_grouping_field.state == "closed" } ')
        # Adapt to the url format
        grouping_fields = ''
        new_record_added = False
        for grouping_field in self.grouping_fields:
            if ((parent and parent.name == grouping_field.name) or
                    (cell.name == grouping_field.name)):
                new_record_added = True
                grouping_fields += f'name={new_grouping_field.name}&position={new_grouping_field.position}&hierarchy={new_grouping_field.hierarchy}&state={new_grouping_field.state}&open_records={new_grouping_field.open_records}&__'
            else:
                grouping_fields += f'name={grouping_field.name}&position={grouping_field.position}&hierarchy={grouping_field.hierarchy}&state={grouping_field.state}&open_records={grouping_field.open_records}&__'
        if not new_record_added:
            grouping_fields += f'name={new_grouping_field.name}&position={new_grouping_field.position}&hierarchy={new_grouping_field.hierarchy}&state={new_grouping_field.state}&open_records={new_grouping_field.open_records}&__'

        result_fields = ''
        for result_field in self.result_fields:
            result_fields += f'name={result_field.name}&operation={result_field.operation}&__'
        return [grouping_fields, result_fields]


class TableStrucutre:
    def __init__(self, columns, rows, values):
        # Columns/rows we use in the pibot table to show
        self.columns = columns
        self.rows = rows
        # List of aggregations we need to show (aggregation, field)
        self.aggregations = []
        # List of values for each coordinate (column, row) for each aggregation
        self.values = values
        # Original table columns/rows we use to get the values
        self.table_columns = []
        self.table_rows = []

class Header:
    def __init__(self, name, parent, hierarchy, position, childs, state):
        self.name = name
        self.position = position
        self.hierarchy = hierarchy
        self.parent = parent
        self.childs = childs
        self.table_name = []
        # Indicate if this record is open or closed
        self.state = state
        self.record_childs = []
        self.record_parents = []

class GroupingField:
    # Name of the column
    name = ''
    # Position of the field (column or row)
    position = ''
    # Position of the field (column or row)
    hierarchy = ''
    # State of the field (open or closed)
    state = ''
    # Specific records open in this level
    # Open records structure waited: [(level0, level1, level2, ...)]
    open_records = []

    """     def __init__(self, name, position, hierarchy, state, open_records):
        # Name of the column
        self.name = name
        # Position of the field (column or row)
        self.position = position
        # Position of the field (column or row)
        self.hierarchy = hierarchy
        # State of the field (open or closed)
        self.state = state
        # Specific records open in this level
        # Open records structure waited: [(level0, level1, level2, ...)]
        self.open_records = open_records """

    def create_operation(self, table=None):
        op = Operation()
        op.name = self.name
        op.position = self.position
        op.hierarchy = self.hierarchy
        op.state = self.state
        op.table = table
        op.open_records = self.open_records
        op.record_state = 'closed'

        if self.state == 'closed':
            op.operation = 'select_closed'
        elif self.state == 'open':
            op.operation = 'select_open'
        else:
            raise
        return op

class ResultField():
    name = ''
    operation = ''

    def create_operation(self, table=None):
        op = Operation()
        op.name = self.name
        op.table = table
        op.aggregation_oeration = self.operation
        op.operation = 'calculate_total'
        return op

###############################################################################
#################################### BASE #####################################
###############################################################################
class Layout(Component):
    'Layout'
    __name__ = 'www.layout'
    _path = None
    __slots__ = ['main']

    title = fields.Char('Title')

    def __init__(self, *args, **kwargs):
        self.main = div()
        super().__init__(*args, **kwargs)

    def render(self):
        pool = Pool()
        #Header = pool.get('www.header')
        #Footer = pool.get('www.footer')

        # Prepare the head with all the scripts
        site = self.context['site']

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
                #script(src="{{ url_for('static',
                #   filename='bower_components/jquery/dist/jquery.min.js') }}")
                #script(src="{{ url_for('static', filename='js/nantic.js') }}")
                comment('CSS')
                link(href="/static/output.css", rel="stylesheet")
                script(src='https://unpkg.com/htmx.org@2.0.0')
                script(src="https://cdn.tailwindcss.com")
            main_body = div(id='main', cls='bg-white')
            #main_body += Header().tag()
            flash_div = div(id='flash_messages',
                cls="flex w-full flex-col items-center space-y-4 sm:items-end")
            flash_div['hx-swap-oob'] = "afterbegin"
            main_body += flash_div
            main_body += self.main
            #main_body += Footer().tag()
        return html_layout

class Index(Component):
    'Index'
    __name__ = 'www.index'
    _path = None

    database_name = fields.Char('Database Name')
    table_name = fields.Char('Table Name')

    @classmethod
    def get_url_map(cls):
        return [
            Rule('/<string:database_name>/babi/pivot/<string:table_name>')
        ]

    def render(self):
        pool = Pool()
        Layout = pool.get('www.layout')
        Pivot = pool.get('www.pivot_table')

        # TODO: search a way to get all the column names form the table
        fields = ['employee', 'year', 'month', 'duration']

        with main() as index_section:
            # Show all the fields avaialble in the table
            with div():
                with ul(role="list", cls="mt-3 grid grid-cols-1 gap-5 sm:grid-cols-2 sm:gap-6 lg:grid-cols-4"):
                    for field in fields:
                        with li(cls="col-span-1 flex rounded-md shadow-sm"):
                            with div(cls="flex flex-1 items-center justify-between truncate rounded-r-md rounded-l-md border-b border-r border-t border-l border-gray-200 bg-white"):
                                with div(cls="flex-1 truncate px-4 py-2 text-sm"):
                                    a(field, href="#", cls="font-medium text-gray-900 hover:text-gray-600")

            with div(cls="grid grid-cols-12"):
                with div(cls="px-4 sm:px-6 lg:px-8 mt-8 flow-root col-span-4"):
                    with div(cls="-mx-4 -my-2 overflow-x-auto sm:-mx-6 lg:-mx-8"):
                        with div(cls="inline-block min-w-full py-2 align-middle sm:px-6 lg:px-8"):
                            with table(cls="min-w-full divide-y divide-gray-300"):
                                with thead():
                                    with tr():
                                        th('X axis', scope="col", cls="py-3.5 pl-4 pr-3 text-left text-sm font-semibold text-gray-900 sm:pl-0")
                                        th(scope="col", cls="relative py-3.5 pl-3 pr-4 sm:pr-0").add(span('Remove', cls="sr-only"))
                                        th(scope="col", cls="relative py-3.5 pl-3 pr-4 sm:pr-0").add(span('Up', cls="sr-only"))
                                        with th(scope="col", cls="relative py-3.5 pl-3 pr-4 sm:pr-0"):
                                            a(href="#", cls="text-indigo-600 hover:text-indigo-900").add(raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15" /></svg>'))
                                            span('Down', cls="sr-only")
                                with tbody(cls="divide-y divide-gray-200") :
                                    #TODO: Loop trough the fields
                                    with tr():
                                        td('Year', cls="whitespace-nowrap px-3py-4 pl-4 pr-3 text-sm font-medium text-gray-900 sm:pl-0")
                                        with td(cls="relative whitespace-nowrap py-4 pl-3 pr-4 text-right text-sm font-medium sm:pr-0"):
                                            a(href="#", cls="text-indigo-600 hover:text-indigo-900").add(raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M5 12h14" /></svg>'))
                                        with td(cls="relative whitespace-nowrap py-4 pl-3 pr-4 text-right text-sm font-medium sm:pr-0"):
                                            a(href="#", cls="text-indigo-600 hover:text-indigo-900").add(raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 10.5 12 3m0 0 7.5 7.5M12 3v18" /></svg>'))
                                        with td(cls="relative whitespace-nowrap py-4 pl-3 pr-4 text-right text-sm font-medium sm:pr-0"):
                                            a(href="#", cls="text-indigo-600 hover:text-indigo-900").add(raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M19.5 13.5 12 21m0 0-7.5-7.5M12 21V3" /></svg>'))
                with div(cls="px-4 sm:px-6 lg:px-8 mt-8 flow-root col-span-4"):
                    with div(cls="-mx-4 -my-2 overflow-x-auto sm:-mx-6 lg:-mx-8"):
                        with div(cls="inline-block min-w-full py-2 align-middle sm:px-6 lg:px-8"):
                            with table(cls="min-w-full divide-y divide-gray-300"):
                                with thead():
                                    with tr():
                                        th('Y axis', scope="col", cls="py-3.5 pl-4 pr-3 text-left text-sm font-semibold text-gray-900 sm:pl-0")
                                        th(scope="col", cls="relative py-3.5 pl-3 pr-4 sm:pr-0").add(span('Remove', cls="sr-only"))
                                        th(scope="col", cls="relative py-3.5 pl-3 pr-4 sm:pr-0").add(span('Up', cls="sr-only"))
                                        with th(scope="col", cls="relative py-3.5 pl-3 pr-4 sm:pr-0"):
                                            a(href="#", cls="text-indigo-600 hover:text-indigo-900").add(raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15" /></svg>'))
                                            span('Down', cls="sr-only")
                                with tbody(cls="divide-y divide-gray-200") :
                                    #TODO: Loop trough the fields
                                    with tr():
                                        td('Employee', cls="whitespace-nowrap px-3py-4 pl-4 pr-3 text-sm font-medium text-gray-900 sm:pl-0")
                                        with td(cls="relative whitespace-nowrap py-4 pl-3 pr-4 text-right text-sm font-medium sm:pr-0"):
                                            a(href="#", cls="text-indigo-600 hover:text-indigo-900").add(raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M5 12h14" /></svg>'))
                                        with td(cls="relative whitespace-nowrap py-4 pl-3 pr-4 text-right text-sm font-medium sm:pr-0"):
                                            a(href="#", cls="text-indigo-600 hover:text-indigo-900").add(raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 10.5 12 3m0 0 7.5 7.5M12 3v18" /></svg>'))
                                        with td(cls="relative whitespace-nowrap py-4 pl-3 pr-4 text-right text-sm font-medium sm:pr-0"):
                                            a(href="#", cls="text-indigo-600 hover:text-indigo-900").add(raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M19.5 13.5 12 21m0 0-7.5-7.5M12 21V3" /></svg>'))
                with div(cls="px-4 sm:px-6 lg:px-8 mt-8 flow-root col-span-4"):
                    with div(cls="-mx-4 -my-2 overflow-x-auto sm:-mx-6 lg:-mx-8"):
                        with div(cls="inline-block min-w-full py-2 align-middle sm:px-6 lg:px-8"):
                            with table(cls="min-w-full divide-y divide-gray-300"):
                                with thead():
                                    with tr():
                                        th('Aggregation fields', scope="col", cls="py-3.5 pl-4 pr-3 text-left text-sm font-semibold text-gray-900 sm:pl-0")
                                        th(scope="col", cls="relative py-3.5 pl-3 pr-4 sm:pr-0").add(span('Remove', cls="sr-only"))
                                        with th(scope="col", cls="relative py-3.5 pl-3 pr-4 sm:pr-0"):
                                            a(href="#", cls="text-indigo-600 hover:text-indigo-900").add(raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15" /></svg>'))
                                            span('Aggregation type', cls="sr-only")
                                with tbody(cls="divide-y divide-gray-200") :
                                    #TODO: Loop trough the fields
                                    with tr():
                                        td('Duration', cls="whitespace-nowrap px-3py-4 pl-4 pr-3 text-sm font-medium text-gray-900 sm:pl-0")
                                        with td(cls="relative whitespace-nowrap py-4 pl-3 pr-4 text-right text-sm font-medium sm:pr-0"):
                                            a(href="#", cls="text-indigo-600 hover:text-indigo-900").add(raw('<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-6"><path stroke-linecap="round" stroke-linejoin="round" d="M5 12h14" /></svg>'))
                                        with td(cls="relative whitespace-nowrap py-4 pl-3 pr-4 text-right text-sm font-medium sm:pr-0"):
                                            with div():
                                                with select(id="aggregation", name="aggregation", cls="mt-2 block w-full rounded-md border-0 py-1.5 pl-3 pr-10 text-gray-900 ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-indigo-600 sm:text-sm sm:leading-6"):
                                                    option('Sum')
                                                    option('Average')
                                                    option('Max')
                                                    option('Min')
                                                    option('Count')

            '''
            grouping_fields = []
            gf1 = GroupingField(fields[0], 'column', 0, 'open', [])
            grouping_fields.append(gf1)
            gf2 = GroupingField(fields[1], 'row', 0, 'open', ['2019.0', '2022.0'])
            grouping_fields.append(gf2)
            gf3 = GroupingField(fields[3], 'row', 1, 'open',  [])
            grouping_fields.append(gf3)
            '''

            # Format the values in a string (this way we dont need to difference
            # between a normal call and the first call)
            #TODO: set the default values based om the fields pickied by the user
            grouping_fields = f'name={fields[0]}&position=column&hierarchy=0&state=closed&open_records=&__name={fields[1]}&position=row&hierarchy=0&state=closed&open_records=&'
            #__name={fields[2]}&position=row&hierarchy=1&state=closed&open_records=&

            result_fields = f'name={fields[3]}&operation=sum'
            #Pivot(database_name=self.database_name, table_name=self.table_name,
            #    grouping_fields=grouping_fields, result_fields=result_fields).render()

            #pivot_table = self.pivot_table(self.table_name, grouping_fields, result_fields)
            with div(cls="mt-8 flow-root"):
                with div(cls="-mx-4 -my-2 overflow-x-auto sm:-mx-6 lg:-mx-8"):
                    #with div(id='pivot_table', cls="inline-block min-w-full py-2 align-middle sm:px-6 lg:px-8"):
                    Pivot(database_name=self.database_name, table_name=self.table_name,
                        grouping_fields=grouping_fields, result_fields=result_fields)
                    #self.pivot_table(self.table_name, grouping_fields, result_fields)
        layout = Layout(title='PIVOT TEST')
        layout.main.add(index_section)
        return layout.tag()


class PivotTable(Component):
    'Pivot Table'
    __name__ = 'www.pivot_table'
    _path = None

    database_name = fields.Char('Database Name')
    table_name = fields.Char('Table Name')
    grouping_fields = fields.Char('Grouping Fields')
    result_fields = fields.Char('Result Fields')

    @classmethod
    def get_url_map(cls):
        return [
            Rule('/<string:database_name>/babi/pivot/<string:table_name>/<string:grouping_fields>/<string:result_fields>')
        ]

    def render(self):
        #parse values
        print(f'\nGROUPING FIELDS: {self.grouping_fields}')

        grouping_fields = []
        for grouping_field in self.grouping_fields.split('__'):
            if grouping_field:
                groupingfield = GroupingField()
                for field in grouping_field.split('&'):
                    if field:
                        if field.split('=')[0] == 'hierarchy' and field.split('=')[1]:
                            setattr(groupingfield, field.split('=')[0], int(field.split('=')[1]))
                        else:
                            setattr(groupingfield, field.split('=')[0], field.split('=')[1])
                grouping_fields.append(groupingfield)

        result_fields = []
        for result_field in self.result_fields.split('__'):
            if result_field:
                resultfield = ResultField()
                for field in result_field.split('&'):
                    if field:
                        setattr(resultfield, field.split('=')[0], field.split('=')[1])
                result_fields.append(resultfield)

        table_structure = TableStrucutre([], [], {})
        operations = deque()

        for grouping_field in grouping_fields:
            print(f'GROUPING FIELD: {grouping_field.name} | {grouping_field.position} | {grouping_field.hierarchy} | {grouping_field.state} | {grouping_field.open_records}')

        for grouping_field in grouping_fields:
            operations.append(
                GroupingField.create_operation(grouping_field, self.table_name))

        for result_field in result_fields:
            operations.append(ResultField.create_operation(result_field,
                self.table_name))

        last_steps = False
        while operations:
            print(f'\nOperation name: {operations[0].operation}')
            operation = operations.popleft()

            new_operations = getattr(operation, operation.operation)(table_structure)
            if isinstance(new_operations, list):
                if new_operations:
                    for new_operation in new_operations:
                        operations.append(new_operation)
            else:
                # For now, if we return anything, that is not a list, we suppose is the html table
                return new_operations
            if len(operations) == 0 and not last_steps:
                # Create the last operations (get values) and create table
                last_steps = True
                op = Operation()
                op.operation = 'calculate_values'
                op.table = self.table_name
                operations.append(op)
                op = Operation()
                op.operation = 'create_table'
                op.table = self.table_name
                op.grouping_fields = grouping_fields
                op.result_fields = result_fields
                op.database_name = self.database_name
                operations.append(op)

