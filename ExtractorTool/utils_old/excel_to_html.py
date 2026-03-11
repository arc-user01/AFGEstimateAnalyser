import os
import aspose.cells as ac


def convert_excel_to_html(excel_path, output_folder):

    os.makedirs(output_folder, exist_ok=True)

    print(f"Loading workbook: {excel_path}")

    workbook = ac.Workbook(excel_path)

    workbook.calculate_formula()


    # SAFE: Extract names first (prevents enumeration error)
    sheet_names = [ws.name for ws in workbook.worksheets]


    for sheet_name in sheet_names:

        worksheet = workbook.worksheets.get(sheet_name)


        # ---------------------------------------
        # Skip Hidden Sheets
        # ---------------------------------------

        if worksheet.is_visible == False:

            print(f"Skipping hidden sheet: {sheet_name}")

            continue


        print(f"Processing sheet: {sheet_name}")


        cells = worksheet.cells


        # ---------------------------------------
        # Unhide rows
        # ---------------------------------------

        for r in range(cells.max_row + 1):

            cells.unhide_row(r, 15.0)


        # ---------------------------------------
        # Unhide columns
        # ---------------------------------------

        for c in range(cells.max_column + 1):

            cells.unhide_column(c, 8.43)


        options = ac.HtmlSaveOptions()

        options.export_cell_coordinate = True
        options.export_grid_lines = True
        options.export_active_worksheet_only = True
        options.export_images_as_base64 = True


        workbook.worksheets.active_sheet_index = worksheet.index


        safe_name = sheet_name.replace(" ", "_").replace("/", "_")


        output_html_path = os.path.join(
            output_folder,
            f"{safe_name}.html"
        )


        print(f"Saving: {output_html_path}")


        workbook.save(output_html_path, options)


    print("\nAll visible sheets converted.")