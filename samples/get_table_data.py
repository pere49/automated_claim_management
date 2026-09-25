import pandas as pd
import numpy as np
import pdfplumber

pdf_path = "./EA_Card Expenses_August.pdf"
with pdfplumber.open(pdf_path) as pdf:
    first_page = pdf.pages[0]
    # text = first_page.extract_text()
    header, *data = first_page.extract_table()
    df = pd.DataFrame(data, columns=header)
    print(data)

def extract_description(data):
    descr_filt = list(filter(lambda x: x not in [None, ''], data))
    descr_struct = dict(zip(descr_filt[::2], descr_filt[1::2]))
    return descr_struct

def extract_data_rows(data):
    data_rows = []
    cols = data[0]
    for row in range(1, len(data)):
        data_row=dict(zip(cols, data[row]))

        first_col = data_row['Date'].strip()

        if first_col == "":continue
        if first_col.lower() == "total": 
            get_total = data[row][-1]
            data_rows.append(get_total)
            break
        data_rows.append(data_row)

    return cols, data_rows

columns, data_info = extract_data_rows(data[2:])

structure = {
    "header": list(filter(lambda x: x is not None, data[0])),
    "Document Details": extract_description(data[1]),
    "data_columns": columns,
    "data_rows": data_info[:-1],
    "Total": data_info[-1]
}
print(structure)