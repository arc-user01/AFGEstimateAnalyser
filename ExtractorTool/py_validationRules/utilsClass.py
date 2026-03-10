class PyUtils:

    def __init__(self):
        pass

    def remove_trailing_empty_excel_rows(self, df, columns):
        """
        Remove only trailing rows where all Excel-style cells are empty
        after the '_' delimiter (e.g., A69_ B69_ C69_).

        Rows that contain any string followed by ':' (e.g., 'Total:', '(aed):')
        will be removed. Rows that have empty values but have data below them
        will be preserved.
        """

        if df.empty or not columns:
            return df

        # Remove rows containing any text followed by ':'
        mask = df.apply(
            lambda r: r.astype(str).str.contains(r"[A-Za-z].*:", regex=True, na=False).any(),
            axis=1
        )  
        df = df[~mask].reset_index(drop=True)

        temp = df.copy()

        # extract right side value after '_'
        for c in columns:
            temp[c] = (
                temp[c]
                .astype(str)
                .str.split("_", n=1)
                .str[1]
                .fillna("")
                .str.strip()
            )

        # True if row has any real data
        has_data = ~(temp[columns] == "").all(axis=1)

        # find last row that contains actual data
        last_data_index = has_data[::-1].idxmax() if has_data.any() else None

        if last_data_index is None:
            return df.iloc[0:0]

        return df.loc[:last_data_index]

