from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Any, Set

from n2t import xml_helpers
from n2t.shared import BaseParser, WhiteSpaceStrategy


class TokenType(Enum):
    KEYWORD = 0
    SYMBOL = 1
    IDENTIFIER = 2
    INT_CONST = 3
    STRING_CONST = 4


class JackKeyword(Enum):
    CLASS = 0
    METHOD = 1
    FUNCTION = 2
    CONSTRUCTOR = 3
    INT = 4
    BOOLEAN = 5
    CHAR = 6
    VOID = 7
    VAR = 8
    STATIC = 9
    FIELD = 10
    LET = 11
    DO = 12
    IF = 13
    ELSE = 14
    WHILE = 15
    RETURN = 16
    TRUE = 17
    FALSE = 18
    NULL = 19
    THIS = 20


class JackAnalyzer:
    def __init__(self):
        pass


@dataclass
class Token:
    content: str
    type: TokenType


token_xml_mapping = {
    TokenType.INT_CONST: "integerConstant",
    TokenType.SYMBOL: "symbol",
    TokenType.STRING_CONST: "stringConstant",
    TokenType.KEYWORD: "keyword",
    TokenType.IDENTIFIER: "identifier",
}


class JackTokenizer(BaseParser):

    @staticmethod
    def _jack_tokenizer(text: str) -> List[Token]:
        symbols = {"{", "}", "(", ")", "[", "]", ".", ",", ";", "+", "-", "*", "/", "&", "|", "<", ">", "=", "~"}
        keywords = {"class", "constructor", "function", "method", "field", "static", "var", "int", "char", "boolean",
                    "void", "true", "false", "null", "this", "let", "do", "if", "else", "while", "return"}
        empty_space = " "
        splitter = symbols.union({empty_space})
        override = {'"', "'"}
        overriding_with = None
        tokens: List[Token] = []
        collector = ""

        def collector_finish(given_type: Optional[TokenType] = None):
            nonlocal collector
            evaluated_type = None
            if not given_type:
                # try keyword
                if collector in keywords:
                    evaluated_type = TokenType.KEYWORD
                else:
                    # try int const
                    try:
                        integer = int(collector)
                        if integer < 0 or integer > 32767:
                            raise Exception("Encountered int that is outside 0-32767")
                        evaluated_type = TokenType.INT_CONST
                    except ValueError:
                        # then assume identifier
                        evaluated_type = TokenType.IDENTIFIER

            if collector:
                tokens.append(Token(collector, given_type if given_type else evaluated_type))
                collector = ""

        for char in text:

            # We want quotes to be handled differently
            if overriding_with:
                if char == overriding_with:  # got to end of quote section
                    collector_finish(TokenType.STRING_CONST)
                    overriding_with = None
                else:  # still going with the override
                    collector += char
                continue
            if char in override:
                overriding_with = char
                continue

            # If it's a non-quote, then we can handle those cases here
            if char == "\n":
                pass
            elif char in splitter:
                collector_finish()
                if char != empty_space:
                    tokens.append(Token(char, TokenType.SYMBOL))
            else:
                collector += char
        return tokens

    def __init__(self, raw_file_contents: str):
        super().__init__(raw_file_contents,
                         WhiteSpaceStrategy.MAX_ONE_IN_BETWEEN_WORDS,
                         tokenizer=JackTokenizer._jack_tokenizer)

    def get_xml(self) -> str:
        start = "<tokens>\n"
        end = "</tokens>\n"
        body = ""

        for token in self.get_all():
            xml_tag_text = token_xml_mapping[token.type]
            body += xml_helpers.formulate_line(xml_tag_text, token.content) + "\n"

        return start + body + end


def get_tokens_as_xml(code: str) -> str:
    tokenizer = JackTokenizer(code)
    return tokenizer.get_xml()


def compile_as_xml(code: str) -> str:
    tokenizer = JackTokenizer(code)
    engine = CompilationEngine(tokenizer)
    unit = engine.compile()
    return CompilationEngine.unit_as_xml(unit)


class WrapperType(Enum):
    SubroutineDeclaration = 0
    SubroutineBody = 1
    VariableDeclaration = 2
    Statements = 3
    LetStatement = 4
    DoStatement = 5
    ClassVariableDeclaration = 6
    ReturnStatement = 7
    ParameterList = 8
    IfStatement = 9
    Expression = 10
    Class = 11
    Term = 12
    ExpressionList = 13
    WhileStatement = 14


@dataclass
class Unit:
    type: WrapperType
    children: List[Any]  # NOTE: can't type because recursive nature...


unit_xml_mapping = {
    WrapperType.SubroutineDeclaration: "subroutineDec",
    WrapperType.SubroutineBody: "subroutineBody",
    WrapperType.VariableDeclaration: "varDec",
    WrapperType.Statements: "statements",
    WrapperType.LetStatement: "letStatement",
    WrapperType.DoStatement: "doStatement",
    WrapperType.ClassVariableDeclaration: "classVarDec",
    WrapperType.ReturnStatement: "returnStatement",
    WrapperType.ParameterList: "parameterList",
    WrapperType.IfStatement: "ifStatement",
    WrapperType.WhileStatement: "whileStatement",
    WrapperType.Expression: "expression",
    WrapperType.Class: "class",
    WrapperType.Term: "term",
    WrapperType.ExpressionList: "expressionList",
}


# TODO: type
class CompilationEngine:
    _tokens: List[Token]

    def __init__(self, tokenizer: JackTokenizer):
        # TODO: it feels weird passing the parser then resetting it
        # TODO: it may make more sense for the token advance/retreat functionality to be split off
        tokenizer.reset()

        tokens = tokenizer.get_all()
        if not len(tokens):
            raise Exception("No tokens to compile...")
        if len(tokens) < 5 or (not tokens[0].type == TokenType.KEYWORD and tokens[0].content == "class"):
            raise Exception("Everything must be wrapped in a valid class...")

        self._tokenizer = tokenizer

    def compile(self) -> Unit:
        # excepts beginning `class Name {` and end `}`
        first = self._tokenizer.advance()
        second = self._tokenizer.advance()
        third = self._tokenizer.advance()
        if not first.content == "class" or not second.type == TokenType.IDENTIFIER or not third.content == "{":
            raise Exception("Class not correctly formed.")

        children = [first, second, third]

        # a class can have class var declarations or subroutine declarations
        while self._tokenizer.has_more():
            next_token = self._tokenizer.advance()
            if next_token.content in {"static", "field"}:
                children.append(self._compile_class_var_declaration(next_token))
            elif next_token.content in {"function", "method", "constructor"}:
                children.append(self._compile_subroutine_declaration(next_token))
            elif next_token.content == "}":
                if self._tokenizer.has_more():
                    next_token = self._tokenizer.advance()
                    raise Exception("Compiler didn't stick the landing... Found another token:", next_token)
                children.append(next_token)

        return Unit(WrapperType.Class, children)

    def _compile_class_var_declaration(self, first_token: Token) -> Unit:
        # first_token is expected to be the static/field keyword
        # ends in ; symbol
        children = [first_token]

        while True:
            next_token = self._tokenizer.advance()
            if next_token.content == ";":
                children.append(next_token)
                break
            else:
                children.append(next_token)

        return Unit(WrapperType.ClassVariableDeclaration, children)

    def _compile_subroutine_declaration(self, first_token: Token) -> Unit:
        # first_token is expected to be the function keyword
        # expects a return type, identifier, parameter list, body
        children = [first_token]
        return_type = self._tokenizer.advance()
        identifier = self._tokenizer.advance()
        parameter_list_start = self._tokenizer.advance()
        children.extend([return_type, identifier, parameter_list_start])
        parameter_list_children = []
        while True:
            next_token = self._tokenizer.advance()
            if next_token.content == ")":
                children.append(self._compile_parameter_list(parameter_list_children))
                children.append(next_token)
                break
            else:
                parameter_list_children.append(next_token)

        # TODO: why pass in first one out of tradition
        children.append(self._compile_subroutine_body(self._tokenizer.advance()))
        return Unit(WrapperType.SubroutineDeclaration, children)

    def _compile_subroutine_body(self, first_token: Token) -> Unit:
        # first_token is expected to be the { symbol
        # body can be virtually anything for now (if not weakly typed, it'd probably be picky here?)
        children = [first_token]

        while True:
            next_token = self._tokenizer.advance()
            if next_token.content == "var":
                children.append(self._compile_variable_declaration(next_token))
            else:
                self._tokenizer.retreat()
                children.extend(self._get_children_in_body_with_closing_brace())
                break

        return Unit(WrapperType.SubroutineBody, children)

    def _get_children_in_body_with_closing_brace(self, first_token: Optional[Token] = None) -> List:
        # TODO: type return
        children: List[Any] = [first_token] if first_token else []
        thing = False
        while True:
            next_token = self._tokenizer.advance()
            if next_token.content == "}" and thing:
                children.append(next_token)
                break
            else:
                self._tokenizer.retreat()
                children.append(self._compile_statements())
            thing = True
        return children

    def _compile_statements(self) -> Unit:
        children = []
        while True:
            next_token = self._tokenizer.advance()
            if next_token.content == "return":
                children.append(self._compile_return_statement(next_token))
            elif next_token.content == "let":
                children.append(self._compile_let_statement(next_token))
            elif next_token.content == "do":
                children.append(self._compile_do_statement(next_token))
            elif next_token.content == "if":
                children.append(self._compile_if_statement(next_token))
            elif next_token.content == "while":
                children.append(self._compile_while_statement(next_token))
            elif next_token.content == "}":
                self._tokenizer.retreat()
                break
            else:
                raise NotImplementedError(f"Wasn't ready to handle {next_token} when compiling statements")

        return Unit(WrapperType.Statements, children=children)

    def _compile_while_statement(self, first_token: Token) -> Unit:
        # first_token is expected to be `while`, second is `(`
        # TODO: similar to IF, combine? only thing different is `else` in the `while True:`
        # TODO: some of this logic should definitely be abstracted though
        children = [first_token, self._tokenizer.advance()]  # `while (`

        while True:
            next_token = self._tokenizer.advance()
            if next_token.content == ")":
                children.append(next_token)
                break
            else:
                children.append(self._compile_expression(next_token, {")"}))

        while True:
            next_token = self._tokenizer.advance()
            if next_token.content == "{":
                children.append(next_token)
                children.extend(self._get_children_in_body_with_closing_brace())
            else:
                self._tokenizer.retreat()
                break
        return Unit(WrapperType.WhileStatement, children)

    def _compile_if_statement(self, first_token: Token) -> Unit:
        # first_token is expected to be `if`, second is `(`
        children = [first_token, self._tokenizer.advance()]  # `if (`

        while True:
            next_token = self._tokenizer.advance()
            if next_token.content == ")":
                children.append(next_token)
                break
            else:
                children.append(self._compile_expression(next_token, {")"}))

        while True:
            next_token = self._tokenizer.advance()
            if next_token.content == "{":
                children.append(next_token)
                children.extend(self._get_children_in_body_with_closing_brace())
            elif next_token.content == "else":
                children.append(next_token)
            else:
                self._tokenizer.retreat()
                break
        return Unit(WrapperType.IfStatement, children)

    def _compile_let_statement(self, first_token: Token) -> Unit:
        # first_token is expected to be `let`
        # next tokens are identifier, `=` symbol, then an expression, ending in `;`
        children = [first_token]
        identifier = self._tokenizer.advance()
        assignment_symbol = self._tokenizer.advance()
        children.extend([identifier, assignment_symbol])
        while True:
            next_token = self._tokenizer.advance()
            if next_token.content == ";":
                children.append(next_token)
                break
            else:
                children.append(self._compile_expression(next_token, {";"}))

        return Unit(WrapperType.LetStatement, children)

    def _compile_expression(self, first_token: Token, end_symbols: Set[str]) -> Unit:
        children = [first_token if first_token.type == TokenType.SYMBOL else self._compile_term(first_token)]
        while True:
            next_token = self._tokenizer.advance()
            if next_token.content in end_symbols:
                self._tokenizer.retreat()
                break
            else:
                children.append(next_token if next_token.type == TokenType.SYMBOL else self._compile_term(next_token))
        return Unit(WrapperType.Expression, children)

    def _compile_term(self, first_token: Token) -> Unit:
        return Unit(WrapperType.Term, [first_token])

    def _compile_do_statement(self, first_token: Token) -> Unit:
        # first_token is expected to be a `do` keyword while the second is an identifier
        children = [first_token, self._tokenizer.advance()]
        third = self._tokenizer.advance()  # `(` or `.`
        children.append(third)
        if third.content == ".":
            fourth = self._tokenizer.advance()  # identifier
            fifth = self._tokenizer.advance()  # ( list
            children.extend([fourth, fifth])

        # TODO: this doesn't seem right, should be parameter, not expression?
        children.append(self._compile_expression_list())
        children.append(self._tokenizer.advance())  # )

        last_token = self._tokenizer.advance()
        assert last_token.content == ";", f"Expected last token of do statement to be a `;` but was {last_token.content}"
        children.append(last_token)
        return Unit(WrapperType.DoStatement, children)

    def _compile_return_statement(self, first_token: Token) -> Unit:
        # first_token is expected to be the return keyword
        # for now, assume no return, but TODO: fix it later
        children = [first_token]
        while True:
            next_token = self._tokenizer.advance()
            if next_token.content == ";":
                children.append(next_token)
                break
            else:
                children.append(self._compile_expression(next_token, {";"}))
        # TODO: this is like the variable declaration...
        return Unit(WrapperType.ReturnStatement, children)

    def _compile_variable_declaration(self, first_token: Token) -> Unit:
        # first_token is expected to be the var keyword
        # for now, body is expected to be terminal atoms, TODO: not realistic
        children = [first_token]
        while True:
            next_token = self._tokenizer.advance()
            children.append(next_token)
            if next_token.content == ";":
                break
        return Unit(WrapperType.VariableDeclaration, children)

    @staticmethod
    def _compile_parameter_list(tokens: List[Token]) -> Unit:
        # For now, just return tokens
        return Unit(WrapperType.ParameterList, children=tokens)

    def _compile_expression_list(self) -> Unit:

        # if first_token.content == ")":
        #     self._tokenizer.retreat()
        #     return Unit(WrapperType.ExpressionList, [])

        # an expression list is used as args when calling a function
        # each arg is separated by a `,` symbol and each arg will be a separate expression
        children = []
        # acc = [first_token]

        while True:
            next_token = self._tokenizer.advance()
            if next_token.content == ")":
                self._tokenizer.retreat()
                break
            elif next_token.content == ",":
                children.append(next_token)
                # children.extend([self._compile_expression(acc, {")", ","}), next_token])
                # acc = []
            else:
                children.append(self._compile_expression(next_token, {")", ","}))

        # if len(acc):
        #     children.append(self._compile_expression(acc))
        return Unit(WrapperType.ExpressionList, children)

    @staticmethod
    def unit_as_xml(unit: Unit, level=0) -> str:
        # f"<{xml_tag_text}> {formatted_content} </{xml_tag_text}>"
        xml_tag_text = unit_xml_mapping[unit.type]
        content = ""
        content += f"{' ' * level}<{xml_tag_text}>\n"
        for child in unit.children:
            if isinstance(child, Unit):
                content += CompilationEngine.unit_as_xml(child, level + 2)
            elif isinstance(child, Token):
                line = xml_helpers.formulate_line(token_xml_mapping[child.type], child.content)
                content += f"{' ' * (level + 2)}{line}\n"
            else:
                raise NotImplementedError
        content += f"{' ' * level}</{xml_tag_text}>\n"
        return content

#
# def get_xml(self) -> str:
#     start = "<tokens>\n"
#     end = "</tokens>\n"
#     body = ""
#
#     mapping = {
#         TokenType.INT_CONST: "integerConstant",
#         TokenType.SYMBOL: "symbol",
#         TokenType.STRING_CONST: "stringConstant",
#         TokenType.KEYWORD: "keyword",
#         TokenType.IDENTIFIER: "identifier",
#     }
#
#     for token in self.get_all():
#         xml_tag_text = mapping[token.type]
#         body += xml_helpers.formulate_line(xml_tag_text, token.content) + "\n"
#
#     return start + body + end
