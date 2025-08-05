from openpyxl.utils import get_column_letter

def adjust_column_widths(ws, padding=2, max_width=None):
    """
    Adjusts the width of each column in the worksheet `ws`
    to fit all text, with additional padding.
    """
    for col_cells in ws.columns:
        col_letter = get_column_letter(col_cells[0].column)
        max_length = 0
        for cell in col_cells:
            if cell.value is not None:
                cell_length = len(str(cell.value))
                if cell_length > max_length:
                    max_length = cell_length
                if max_width is not None and max_length > max_width:
                    max_length = max_width
                    break
        ws.column_dimensions[col_letter].width = max_length + padding
