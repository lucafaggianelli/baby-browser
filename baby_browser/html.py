from html.entities import html5 as html_entities


def _convert_html_entity(value: str):
    return html_entities[value + ";"]


def render_html(html: str):
    in_tag = False
    in_tag_name = False
    in_body = False
    in_entity = False

    tag_name = ""
    entity_content = ""

    for c in html:
        if c == "<" and tag_name != "script":
            in_tag = True
            in_tag_name = True
            tag_name = ""
        elif c == ">":
            in_tag = False
            in_tag_name = False

            if tag_name == "body":
                in_body = True
        elif not in_tag and c == "&" and tag_name != "script":
            in_entity = True
            entity_content = ""
        elif in_entity and c == ";":
            in_entity = False
            print(_convert_html_entity(entity_content), end="")
        elif in_tag and in_tag_name and c == " ":
            in_tag_name = False
        elif in_tag_name:
            tag_name += c.lower()
        elif in_entity:
            entity_content += c.lower()
        elif not in_tag and in_body:
            print(c, end="")
