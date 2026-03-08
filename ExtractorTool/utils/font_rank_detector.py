import re


def get_font_ranks(soup):
    """
    Extract font classes and rank them by font-size.
    Returns sorted list: [largest_font, second_largest_font,...]
    """

    style_tag = soup.find("style")

    if not style_tag:
        return []

    css = style_tag.text

    fonts = {}

    matches = re.findall(r'\.(font\d+)\s*\{([^}]*)\}', css)

    for cls, body in matches:

        size_match = re.search(r'font-size:\s*(\d+)pt', body)

        if size_match:

            size = int(size_match.group(1))

            fonts[cls] = size


    # Sort largest → smallest

    ranked = sorted(
        fonts.items(),
        key=lambda x: x[1],
        reverse=True
    )

    return ranked