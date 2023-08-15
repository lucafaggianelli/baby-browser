from dataclasses import field, dataclass
from html import unescape
from typing import Optional
from baby_browser.logger import get_logger

from baby_browser.utils import timed


logger = get_logger(__name__)


SELF_CLOSING_TAGS = [
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
]


def _convert_html_entity(value: str) -> str:
    return unescape(f"&{value};")


def _unquote_string(value: str) -> str:
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]

    return value


@dataclass
class Node:
    children: list["Node"] = field(default_factory=list, init=False)
    parent: Optional["Node"] = None


@dataclass
class Text(Node):
    text: str = field(kw_only=True)

    def __repr__(self) -> str:
        return repr(self.text)


@dataclass
class Element(Node):
    tag: str = field(kw_only=True)
    attributes: dict[str, str | None] = field(default_factory=dict)

    def __repr__(self) -> str:
        return f"<{self.tag} {self.attributes}>"


class HTMLParser:
    root: Optional[Node] = None

    def __init__(self, html: str) -> None:
        self.html = html
        self._unfinished_nodes: list[Node] = []

    @timed(logger)
    def parse(self):
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
        tag_attributes = ""
        entity_content = ""

        for i, c in enumerate(self.html):
            if c == "<" and (
                tag_name != "script" or (i < len(self.html) and self.html[i + 1] == "/")
            ):
                in_tag = True
                in_tag_name = True
                tag_name = ""
                tag_attributes = ""

                if text:
                    self._add_text(text)

                text = ""
            elif c == ">":
                in_tag = False
                in_tag_name = False

                if tag_name == "body":
                    in_body = True

                self._add_tag(tag_name, tag_attributes)
                text = ""
            elif not in_tag and c == "&" and tag_name != "script":
                in_entity = True
                entity_content = ""
            elif in_entity:
                if c == ";":
                    in_entity = False
                    text += _convert_html_entity(entity_content)
                else:
                    entity_content += c.lower()
            elif in_tag:
                if in_tag_name:
                    if c == " ":
                        in_tag_name = False
                    else:
                        tag_name += c.lower()
                else:
                    tag_attributes += c
            elif not in_tag and in_body:
                text += c

        if not in_tag and text:
            self._add_text(text)

        return self._finish()

    def _parse_tag_attributes(self, raw_attributes: str) -> dict[str, str | None]:
        attributes = {}

        for pair in raw_attributes.strip().split():
            if "=" in pair:
                key, value = pair.split("=", 1)
                attributes[key.lower()] = _unquote_string(value)
            else:
                attributes[pair.lower()] = None

        return attributes

    def _get_last_seen_node(self) -> Optional[Node]:
        return (
            self._unfinished_nodes[-1] if len(self._unfinished_nodes) > 0 else self.root
        )

    def _add_text(self, text: str):
        if text.isspace():
            return

        # Last node seen by the parser
        parent = self._get_last_seen_node()

        node = Text(text=text, parent=parent)

        if parent:
            parent.children.append(node)
        else:
            logger.error("A text node became the root", node)
            self.root = node

    def _add_tag(self, tag_name: str, attributes: Optional[str] = None):
        if tag_name.startswith("!"):
            return

        if tag_name.startswith("/"):
            # It's a close tag: `/div`
            try:
                node = self._unfinished_nodes.pop()
            except IndexError:
                logger.error("Found a closing tag without an opening: %s", tag_name)
                return

            parent = self._get_last_seen_node()

            if parent:
                parent.children.append(node)
            else:
                self.root = node
        elif tag_name in SELF_CLOSING_TAGS:
            parent = self._get_last_seen_node()
            node = Element(
                tag=tag_name,
                parent=parent,
                attributes=self._parse_tag_attributes(attributes) if attributes else {},
            )

            if parent:
                parent.children.append(node)
            else:
                logger.error("A self closing tag can't be the HTML root: %s", tag_name)
        else:
            # It's an open tag: `div`
            parent = self._get_last_seen_node()
            node = Element(
                tag=tag_name,
                parent=parent,
                attributes=self._parse_tag_attributes(attributes) if attributes else {},
            )

            self._unfinished_nodes.append(node)

    def print_tree(self, node: Optional[Node] = None, indent=0):
        node = node or self.root

        if not node:
            raise ValueError("The parser has not been initialized or there's no root")

        print(" " * indent, node)

        for child in node.children:
            self.print_tree(child, indent + 2)

    def _finish(self) -> Optional[Node]:
        node = self.root

        while len(self._unfinished_nodes) > 0:
            node = self._unfinished_nodes.pop()
            parent = self._get_last_seen_node()

            if parent:
                parent.children.append(node)
            else:
                self.root = node

        return node
