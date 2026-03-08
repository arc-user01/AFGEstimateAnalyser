def check_duplicates_multi(
    table_column_map: dict,
    conn,
    utils,
    sheet_name: str | None = None,
    header: str | None = None
) -> pd.DataFrame:

    results = []

    for table_name, column_names in table_column_map.items():

        cols = ", ".join(column_names)
        query = f"SELECT id, {cols} FROM {table_name}"

        filters = []
        params = []

        if sheet_name:
            filters.append("sheet_name = ?")
            params.append(sheet_name)

        if header:
            filters.append("header = ?")
            params.append(header)

        if filters:
            query += " WHERE " + " AND ".join(filters)

        df = pd.read_sql(query, conn, params=params)

        if df.empty:
            continue

        df = utils.remove_trailing_empty_excel_rows(df, column_names)

        for c in column_names:

            split_vals = df[c].astype(str).str.split("_", n=1, expand=True)

            df[f"{c}_cell"] = split_vals[0]

            df[c] = (
                split_vals[1]
                .fillna("")
                .str.lower()
                .str.strip()
                .replace("", "__blank__")
            )

            grp = (
                df.groupby(c)
                .agg(
                    occurrence_count=("id", "count"),
                    excel_cells=(f"{c}_cell", lambda x: ",".join(x))
                )
                .reset_index()
            )

            blank_mask = grp[c] == "__blank__"

            blank_rows = grp[blank_mask]
            non_blank_rows = grp[~blank_mask]

            # duplicates
            dup_rows = non_blank_rows[non_blank_rows["occurrence_count"] > 1].copy()
            dup_rows["issue_type"] = "duplicate"

            # missing values
            blank_rows = blank_rows.copy()
            blank_rows["issue_type"] = "missing"

            result = pd.concat([dup_rows, blank_rows], ignore_index=True)

            result[c] = result[c].replace("__blank__", "blank")

            result.rename(columns={c: "value"}, inplace=True)

            result["table_name"] = table_name
            result["column_name"] = c

            results.append(
                result[
                    [
                        "table_name",
                        "column_name",
                        "issue_type",
                        "value",
                        "occurrence_count",
                        "excel_cells",
                    ]
                ]
            )

    if not results:
        return pd.DataFrame(
            columns=[
                "table_name",
                "column_name",
                "issue_type",
                "value",
                "occurrence_count",
                "excel_cells",
            ]
        )

    return pd.concat(results, ignore_index=True)

df_missing = check_duplicates_multi(
    {"waterfall_capex_3rd_party_implementation": ["title","cost_aed"]},
    conn,
    uc
)



print(tabulate(df_missing, headers="keys", tablefmt="sql", showindex=False))
