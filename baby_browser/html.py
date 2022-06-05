def render_html(html: str):
    in_tag = False

    for c in html:
        if c == "<":
            in_tag = True
        elif c == ">":
            in_tag = False
        elif not in_tag:
            print(c, end="")
