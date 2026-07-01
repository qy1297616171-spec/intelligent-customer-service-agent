import re


class RuleBasedSafetyPolicy:
    """Fast deterministic guard for data exfiltration and prompt injection requests."""

    _RULES = {
        "cross_customer_data": (
            r"其他(用户|客户).*(订单|信息|数据)",
            r"别人.*(订单|地址|手机号)",
        ),
        "secret_exfiltration": (
            r"(数据库|管理员|系统).*(密码|口令|密钥)",
            r"(告诉我|发给我|导出).*(密码|口令|密钥)",
        ),
        "instruction_override": (
            r"忽略.*(规则|指令|限制)",
            r"(编造|伪造).*(退款|订单|物流|赔偿).*(结果|状态)?",
            r"没有依据.*(承诺|回答|赔偿)",
        ),
    }

    def block_reason(self, question: str) -> str | None:
        normalized = question.strip().lower()
        for reason, patterns in self._RULES.items():
            if any(re.search(pattern, normalized) for pattern in patterns):
                return reason
        return None
