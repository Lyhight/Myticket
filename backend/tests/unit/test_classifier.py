import pytest

from app.agent.classifier import (
    RuleBasedTicketClassifier,
)


@pytest.mark.parametrize(
    (
        "title",
        "content",
        "expected_category",
        "expected_priority",
        "expected_intent",
        "expected_route",
    ),
    [
        (
            "物流一直没更新",
            "我的包裹三天没有动了",
            "LOGISTICS",
            "NORMAL",
            "shipping_issue",
            "logistics_support",
        ),
        (
            "我要退款",
            "商品质量不好，申请退货",
            "REFUND",
            "HIGH",
            "refund_or_return",
            "after_sales",
        ),
        (
            "优惠券不能使用",
            "结算时提示优惠券不可用",
            "COUPON",
            "NORMAL",
            "coupon_issue",
            "marketing_support",
        ),
        (
            "无法登录",
            "忘记账号密码了",
            "ACCOUNT",
            "NORMAL",
            "account_issue",
            "account_support",
        ),
        (
            "订单支付失败",
            "付款后订单没有更新",
            "ORDER",
            "NORMAL",
            "order_issue",
            "order_support",
        ),
        (
            "商品怎么使用",
            "请提供产品使用说明",
            "PRODUCT",
            "NORMAL",
            "product_issue",
            "product_support",
        ),
        (
            "其他问题",
            "我想咨询一下",
            "OTHER",
            "LOW",
            "general_question",
            "general_support",
        ),
        (
            "签收后退款",
            "快递已经签收，但是我要退款",
            "REFUND",
            "HIGH",
            "refund_or_return",
            "after_sales",
        ),
        (
            "账号被盗",
            "请立即冻结账户",
            "ACCOUNT",
            "URGENT",
            "account_issue",
            "account_support",
        ),
    ],
)
async def test_rule_based_classifier(
    title: str,
    content: str,
    expected_category: str,
    expected_priority: str,
    expected_intent: str,
    expected_route: str,
) -> None:
    classifier = RuleBasedTicketClassifier()

    result = await classifier.classify(
        title=title,
        content=content,
    )

    assert result.category == expected_category
    assert result.priority == expected_priority
    assert result.intent == expected_intent
    assert result.route_to == expected_route
