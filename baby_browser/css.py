from baby_browser.html import Element, Node
from baby_browser.logger import get_logger

logger = get_logger(__name__)


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
                logger.warning(err)

                why = self._ignore_until(";}")

                if why == ";":
                    self._literal(";")
                    self._whitespace()
                else:
                    break

        return pairs

    def _selector(self) -> CSSSelector:
        out = TagSelector(self._word().lower())

        self._whitespace()

        while self._is_not_finished and self._char != "{":
            descendant = TagSelector(self._word().lower())
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
                logger.warning(err)

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
