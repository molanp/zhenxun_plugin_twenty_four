from collections import Counter
import contextlib
import itertools
import random
from typing import Any

from nonebot import on_message
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule
from nonebot_plugin_alconna import Alconna, UniMessage, UniMsg, on_alconna
from nonebot_plugin_uninfo import Uninfo
from simpleeval import simple_eval

from zhenxun.configs.utils.models import PluginExtraData
from zhenxun.models.user_console import UserConsole
from zhenxun.utils.enum import GoldHandle
from zhenxun.utils.exception import InsufficientGold

__plugin_meta__ = PluginMetadata(
    name="24点",
    description="24 点小游戏",
    usage="""
    开启游戏命令: 开始24点
    结束游戏命令: 结束24点

    你的回答直接发就行
    """.strip(),
    extra=PluginExtraData(
        author="molanp",
        version="0.2",
        introduction="24点小游戏，可以赚取金币",
    ).to_dict(),
)


no_solution_lst = {"无解", "none", "n/a", "na", "n.a.", "無解"}
twenty_four: dict[str, tuple[str | None, list[int]]] = {}
"""对局信息"""


def is_started() -> Rule:
    async def _rule(session: Uninfo) -> bool:
        return session.user.id in twenty_four

    return Rule(_rule)


async def add_gold(user_id: str, gold: int):
    await UserConsole.add_gold(user_id, gold, GoldHandle.PLUGIN, "twenty_four")


async def reduce_gold(user_id: str, gold: int):
    try:
        await UserConsole.reduce_gold(user_id, gold, GoldHandle.PLUGIN, "twenty_four")
        return True
    except InsufficientGold:
        return False


start = on_alconna(Alconna("开始24点"), priority=5, block=True)

stop = on_alconna(Alconna("结束24点"), priority=5, block=True)

answer = on_message(priority=6, block=True, rule=is_started())


def isint(num_str: Any) -> bool:
    """
    检查字符串是否符合int。
    """
    try:
        int(num_str)
        return True
    except ValueError:
        return False


def calc(expr) -> float:
    expr = expr.replace("\\", "")
    try:
        return simple_eval(expr)
    except Exception:
        return 0


def check_valid(expr):
    expr = expr.replace(" ", "")

    operators = {"+", "-", "*", "/"}
    num_numbers = 0
    open_parens = 0
    prev_char = ""

    i = 0
    while i < len(expr):
        char = expr[i]
        if isint(char):
            while i < len(expr) and isint(expr[i]):
                i += 1
            num_numbers += 1
            prev_char = "num"
            continue
        elif char in operators:
            if prev_char in operators or prev_char in ("", "("):
                return False
            prev_char = char
            i += 1
        elif char == "(":
            if prev_char in ["num", ")"]:
                return False
            open_parens += 1
            prev_char = char
            i += 1

        elif char == ")":
            if open_parens <= 0 or prev_char in operators or prev_char in ("", "("):
                return False
            open_parens -= 1
            prev_char = char
            i += 1
        elif char == "\\":
            i += 1
            continue
        else:
            return False

    return open_parens == 0 and num_numbers <= 9 and prev_char not in operators


async def find_solution(numbers):
    operators = ["+", "-", "*", "/"]
    perms = itertools.permutations(numbers)
    exprs = itertools.product(operators, repeat=4)
    for perm in perms:
        for expr in exprs:
            for exp in (
                f"(({perm[0]}{expr[0]}{perm[1]}){expr[1]}{perm[2]}){expr[2]}{perm[3]}",
                f"({perm[0]}{expr[0]}{perm[1]}){expr[1]}({perm[2]}{expr[2]}{perm[3]})",
                f"{perm[0]}{expr[0]}({perm[1]}{expr[1]}({perm[2]}{expr[2]}{perm[3]}))",
                f"{perm[0]}{expr[0]}({perm[1]}{expr[1]}{perm[2]}){expr[2]}{perm[3]}",
            ):
                with contextlib.suppress(Exception):
                    result = calc(exp)
                    if result == 24 or 0 < 24 - result < 1e-13:
                        return exp
    return None


def contains_all_numbers(expr, numbers):
    expr_numbers = []
    i = 0
    while i < len(expr):
        if isint(expr[i]):
            num = expr[i]
            while i + 1 < len(expr) and isint(expr[i + 1]):
                num += expr[i + 1]
                i += 1
            expr_numbers.append(int(num))
        i += 1
    return Counter(expr_numbers) == Counter(numbers)


@start.handle()
async def _(session: Uninfo):
    user_id = session.user.id
    if user_id in twenty_four:
        await UniMessage("24点游戏已开始，请勿重复开启").finish(reply_to=True)
    numbers = [random.randint(1, 13) for _ in range(4)]
    solution = await find_solution(numbers)
    twenty_four[user_id] = (solution, numbers)
    await UniMessage(
        f"给出的数字组合：{numbers}\n请输入表达式(由加减乘除和括号组成)使其结果为 24。(若无解，请输入“无解”)"
    ).finish(reply_to=True)


@answer.handle()
async def _(session: Uninfo, msg: UniMsg):
    user_id = session.user.id
    solution, numbers = twenty_four[user_id]
    expr = msg.extract_plain_text().strip().replace("（", "(").replace("）", ")")

    async def fail(msg_text):
        if not await reduce_gold(user_id, 10):
            await UniMessage("你没有足够的金币继续此游戏！已自动结算").send(
                reply_to=True
            )
            twenty_four.pop(user_id, None)
        await UniMessage(msg_text).finish(reply_to=True)

    if expr.lower() in no_solution_lst:
        if solution:
            await fail(
                f"回答错误：该组合存在解。\n其中一组解为：{solution}.已扣除你10金币"
            )
        else:
            await add_gold(user_id, 5)
            twenty_four.pop(user_id, None)
            await UniMessage("回答正确, 奖励你5金币").finish(reply_to=True)
    elif check_valid(expr):
        result = calc(expr)
        if not result:
            await fail("回答错误：表达式无效.已扣除你10金币")
        elif (result == 24 or 0 < 24 - result < 1e-13) and contains_all_numbers(
            expr, numbers
        ):
            await add_gold(user_id, 5)
            twenty_four.pop(user_id, None)
            await UniMessage("回答正确, 奖励你5金币").finish(reply_to=True)
        else:
            await fail("回答错误.已扣除你10金币")
    else:
        await fail("回答错误：表达式无效.已扣除你10金币")


@stop.handle()
async def _(session: Uninfo):
    if twenty_four.pop(session.user.id, None):
        await UniMessage("已结束24点游戏").finish(reply_to=True)
    else:
        await UniMessage("未开始24点游戏").finish(reply_to=True)
