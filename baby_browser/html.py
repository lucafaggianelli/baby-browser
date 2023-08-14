from html import unescape


def _convert_html_entity(value: str) -> str:
    return unescape(f"&{value};")


class Node:
    def __init__(self) -> None:
        pass


class Text(Node):
    def __init__(self, text: str) -> None:
        self.text = text

    def __str__(self) -> str:
        return f"<Text {self.text=}>"


class Tag(Node):
    def __init__(self, tag: str) -> None:
        self.tag = tag

    def __str__(self) -> str:
        return f"<Tag {self.tag=}>"


def lexer(html: str):
    output: list[Node] = []
    text = ""

    # After <
    in_tag = False
    # After < before " "
    in_tag_name = False
    # In the body tag
    in_body = False

    # HTML Entity i.e. &apos;
    in_entity = False

    tag_name = ""
    entity_content = ""

    for i, c in enumerate(html):
        if c == "<" and (
            tag_name != "script" or (i < len(html) and html[i + 1] == "/")
        ):
            in_tag = True
            in_tag_name = True
            tag_name = ""

            if text:
                output.append(Text(text))
            text = ""
        elif c == ">":
            in_tag = False
            in_tag_name = False

            if tag_name == "body":
                in_body = True

            output.append(Tag(tag_name))
            text = ""
        elif not in_tag and c == "&" and tag_name != "script":
            in_entity = True
            entity_content = ""
        elif in_entity and c == ";":
            in_entity = False
            text += _convert_html_entity(entity_content)
        elif in_tag and in_tag_name and c == " ":
            in_tag_name = False
        elif in_tag_name:
            tag_name += c.lower()
        elif in_entity:
            entity_content += c.lower()
        elif not in_tag and in_body:
            text += c

    if not in_tag and text:
        output.append(Text(text))

    return output
