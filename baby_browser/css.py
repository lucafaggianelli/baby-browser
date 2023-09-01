import logging
from baby_browser.html import Element, Node
from baby_browser.logger import get_logger

logger = get_logger(__name__)
logger.setLevel(logging.WARNING)


class CSSSelector:
    priority: int = 1

    def matches(self, node: Node) -> bool:
        return False


class TagSelector(CSSSelector):
    def __init__(self, tag):
        self.tag = tag

    def matches(self, node: Node) -> bool:
        return isinstance(node, Element) and self.tag == node.tag

    def __repr__(self) -> str:
        return self.tag


class ClassSelector(CSSSelector):
    def __init__(self, class_name: str) -> None:
        self.class_name = class_name.lstrip(".").strip()
        self.priority = 10

    def matches(self, node: Node) -> bool:
        return isinstance(node, Element) and self.class_name in node.classes

    def __repr__(self) -> str:
        return f".{self.class_name}"


class DescendantSelector(CSSSelector):
    def __init__(self, ancestor: CSSSelector, descendant: CSSSelector):
        self.ancestor = ancestor
        self.descendant = descendant
        self.priority = ancestor.priority + descendant.priority

    def matches(self, node: Node) -> bool:
        if not self.descendant.matches(node):
            return False

        while node.parent:
            if self.ancestor.matches(node.parent):
                return True
            node = node.parent

        return False

    def __repr__(self) -> str:
        return f"{self.ancestor} {self.descendant}"


class SequenceSelector(CSSSelector):
    def __init__(self, selectors: list[CSSSelector]) -> None:
        self.selectors = selectors
        self.priority = sum(selector.priority for selector in self.selectors)

    def matches(self, node: Node) -> bool:
        return all(selector.matches(node) for selector in self.selectors)

    def __repr__(self) -> str:
        return "".join([str(sel) for sel in self.selectors])


class ParsingError(Exception):
    expected_kw: str
    index: int
    context: str

    def __init__(self, expected_kw: str, index: int, context: str) -> None:
        self.expected_kw = expected_kw
        self.index = index
        self.context = context

        message = f"Expected {self.expected_kw} at index {self.index} but found: {self.context}"

        super().__init__(message)


class CSSParser:
    def __init__(self, source: str) -> None:
        self.source = source
        self._index = 0

    def _create_error(self, expected_kw: str):
        start = max(self._index - 10, 0)
        end = min(start + 10, len(self.source))

        return ParsingError(expected_kw, self._index, self.source[start:end])

    @property
    def _is_not_finished(self):
        return self._index < len(self.source)

    def _whitespace(self):
        while self._is_not_finished and self._char.isspace():
            self._index += 1

    @property
    def _char(self):
        return self.source[self._index]

    def _word(self) -> str:
        start = self._index

        while self._is_not_finished:
            if self._char.isalnum() or self._char in "#-.%":
                self._index += 1
            else:
                break

        if not self._index > start:
            raise self._create_error("word")

        return self.source[start : self._index]

    def _literal(self, literal: str):
        if not (self._is_not_finished and self._char == literal):
            raise self._create_error(literal)

        self._index += 1

    def _pair(self):
        prop = self._word()
        self._whitespace()
        self._literal(":")
        self._whitespace()
        val = self._word()
        return prop.lower(), val

    def _ignore_until(self, chars: str):
        while self._is_not_finished:
            if self._char in chars:
                return self._char
            else:
                self._index += 1

    def parse_rule_body(self):
        pairs = {}

        while self._is_not_finished and self._char != "}":
            try:
                prop, val = self._pair()
                pairs[prop] = val

                self._whitespace()
                self._literal(";")
                self._whitespace()
            except ParsingError as err:
                logger.debug(err)

                why = self._ignore_until(";}")

                if why == ";":
                    self._literal(";")
                    self._whitespace()
                else:
                    break

        return pairs

    def _selector(self) -> CSSSelector:
        word = self._word().lower()

        if word.startswith("."):
            out = ClassSelector(word)
        elif "." in word:
            parts = word.split(".")

            tag = TagSelector(parts[0])
            classes = [ClassSelector(class_name) for class_name in parts[1:]]

            out = SequenceSelector([tag, *classes])
        else:
            out = TagSelector(word)

        self._whitespace()

        while self._is_not_finished and self._char != "{":
            word = self._word().lower()

            if word.startswith("."):
                descendant = ClassSelector(word)
            elif "." in word:
                parts = word.split(".")

                tag = TagSelector(parts[0])
                classes = [ClassSelector(class_name) for class_name in parts[1:]]

                descendant = SequenceSelector([tag, *classes])
            else:
                descendant = TagSelector(word)

            out = DescendantSelector(out, descendant)

            self._whitespace()

        return out

    def parse_css(self):
        rules = []

        while self._is_not_finished:
            try:
                self._whitespace()
                selector = self._selector()
                self._literal("{")
                self._whitespace()
                body = self.parse_rule_body()
                self._literal("}")

                rules.append((selector, body))
                self._whitespace()
            except ParsingError as err:
                logger.debug(err)

                why = self._ignore_until("}")

                if why == "}":
                    self._literal("}")
                    self._whitespace()
                else:
                    break

        return rules


if __name__ == "__main__":
    print(CSSParser("background-image: #abcdef").parse_rule_body())
    print(CSSParser("div { background-image: #abcdef }").parse_css())
